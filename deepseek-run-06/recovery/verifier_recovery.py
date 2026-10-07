"""Resume direct Blue verification without overwriting earlier EDA artifacts."""
from copy import copy, deepcopy
from pathlib import Path
import tempfile

from competition.arena.evidence import freeze, read, signed, verify_signed
from r3e.protocol.hashing import hash_file, hash_payload


def verify_candidate(recovery, original, verifier, **kwargs):
    workspace = verifier.workspace.resolve()
    # EvaluationService already isolates its own per-case workspaces. The
    # direct challenge authority instead reuses this fixed round workspace.
    if not workspace.is_relative_to(recovery.state / "blue_verifier"):
        return original(verifier, **kwargs)
    candidate_id = kwargs["candidate_id"]
    if not candidate_id or Path(candidate_id).name != candidate_id or candidate_id in {".", ".."}:
        raise ValueError("unsafe recovery candidate identity")
    verifier._verify_manifest(kwargs["case"])
    buggy = verifier._case_artifact(kwargs["case"]["buggy_rtl_path"], field="buggy RTL")
    runner = verifier.command_runner
    binding = hash_payload({
        "workspace": str(workspace),
        "request": {**kwargs, "policy": kwargs["policy"].to_dict()},
        "buggy_file_hash": hash_file(buggy),
        "verifier_hash": verifier.verifier_hash,
        "maximum_ast_edits": verifier.maximum_ast_edits,
        "run_context_hash": runner.run_context_hash,
        "toolchain_fingerprint_hash": runner.toolchain_fingerprint_hash,
        "executables": {name: hash_file(path) for name, path in runner.allowed_executables.items()},
        "limits": [runner.timeout_seconds, runner.max_output_bytes, runner.max_memory_bytes],
    })
    target = recovery.root / "verifications" / (binding.split(":")[-1] + ".json")
    attempts = workspace / "recovery_attempts"
    if target.exists():
        saved = verify_signed(read(target))
        work = Path(saved["workspace"]).resolve()
        if saved["binding"] != binding or work.parent != attempts.resolve():
            raise ValueError("recovery verification binding changed")
        for name, digest in saved["files"].items():
            path = (work / name).resolve()
            if not path.is_relative_to(work) or not path.is_file() or hash_file(path) != digest:
                raise ValueError("recovery verification artifact changed")
        record = verify_signed(read(work / candidate_id / "verification.json"), "record_hash")
        if record != saved["record"]:
            raise ValueError("recovery verification record changed")
        verifier.verification_records.append(record)
        recovery.stats["reused_verifications"] += 1
        recovery.event("verification_reused", candidate_id=candidate_id, binding=binding)
        return deepcopy(saved["result"])

    # Old directories lack a complete input/output binding, so do not infer a
    # result from them. Recheck the cached candidate locally in a fresh attempt.
    # Partial attempts are also retained; neither success nor failure is erased.
    attempts.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=candidate_id + "-", dir=attempts))
    isolated = copy(verifier)
    isolated.workspace = work
    isolated.verification_records = []
    isolated.command_runner = copy(runner)
    isolated.command_runner.allowed_root = work
    isolated.command_runner.artifact_root = work / "command_artifacts"
    isolated.command_runner.temporary_root = work / ".grounded-tmp"
    isolated.command_runner.artifact_root.mkdir()
    isolated.command_runner.temporary_root.mkdir()
    result = original(isolated, **kwargs)
    record = verify_signed(read(work / candidate_id / "verification.json"), "record_hash")
    freeze(target, signed({
        "binding": binding, "workspace": str(work), "result": result, "record": record,
        "files": {str(path.relative_to(work)): hash_file(path)
                  for path in sorted(work.rglob("*")) if path.is_file()},
    }))
    verifier.verification_records.append(record)
    recovery.stats["new_verifications"] += 1
    recovery.event("verification_saved", candidate_id=candidate_id, binding=binding)
    return result
