"""Create one shared baseline, then initialize independent local arm state."""
from pathlib import Path
import platform
import subprocess
from r3e.protocol.hashing import hash_file, hash_payload
from r3e.policy.registry_v2 import initialize_registry, get_active_policy
from competition.services.repair_service import RepairService
from competition.services.common import executable_versions
from competition.services.policy_runtime_service import PolicyRuntimeService
from competition.arena.evidence import read, signed, verify_signed, freeze
from competition.arena.isolation import verify_evaluation_manifest


def portable_toolchain():
    return {k:{"available":v["available"],"version":v["version"]} for k,v in executable_versions().items()}

def source_identity(root):
    root = Path(root).resolve()
    paths = sorted(p for top in ("competition", "r3e", "configs") for p in (root/top).rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and "results" not in p.parts and p.suffix in {".py", ".json", ".yaml", ".js", ".css", ".html", ".txt"})
    source_hash = hash_payload({str(p.relative_to(root)): hash_file(p) for p in paths})
    def git(*args):
        run = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return run.stdout.strip() if run.returncode == 0 else ""
    # An exported candidate underneath another checkout is NOT that checkout's commit.
    own_checkout = git("rev-parse", "--show-toplevel") == str(root)
    return {"git_commit": git("rev-parse", "HEAD") if own_checkout else "",
            "dirty": bool(git("status", "--porcelain")) if own_checkout else True,
            "source_hash": source_hash}


def build_baseline(root, *, provider_identity, evaluation_manifests, seeds, image_hash="unrecorded"):
    root = Path(root).resolve()
    if len(seeds) < 3 or len(set(seeds)) != len(seeds) or any(type(s) is not int for s in seeds):
        raise ValueError("three or more paired seeds required")
    for field in ("provider_id", "model_id", "model_version"):
        if not isinstance(provider_identity.get(field), str) or not provider_identity[field]:
            raise ValueError(f"missing provider identity: {field}")
    if provider_identity.get("temperature") != 0.0:
        raise ValueError("M3 fixes temperature to zero")
    if set(evaluation_manifests) != {"strider14", "red-heldout"}:
        raise ValueError("both strider14 and red-heldout must be sealed before initialization")
    for name, manifest in evaluation_manifests.items():
        verify_evaluation_manifest(manifest, root)
        if manifest["metadata"]["dataset"] != name:
            raise ValueError("evaluation dataset name mismatch")
    repair = RepairService(root, root / "runtime" / "baseline-check")
    initial = repair._policy()
    body = initial.to_dict()
    base_hash = hash_payload({k:body[k] for k in ("schema_version","configuration","budgets","frozen_assets","candidate_portfolio_binding")})
    policy = initial.with_updates(policy_id="B0", parent_policy_id="", parent_policy_hash="", created_round=0, base_policy_hash=base_hash)
    return signed({"schema_version": "r3e-aic-dual-baseline-v1", **source_identity(root),
        "container_image_hash": image_hash, "python": platform.python_version(),
        "toolchain": portable_toolchain(), "provider": provider_identity,
        "candidate_budget": 3, "required_adversarial_rounds": 5,
        "seeds": list(seeds), "policy": policy.to_dict(),
        "initial_policy_hash": policy.policy_hash, "memory_hash": hash_payload({"enabled": False, "entries": []}),
        "blue_binding": policy.candidate_portfolio_binding,
        "evaluation_manifests": {k:v["manifest_hash"] for k,v in evaluation_manifests.items()}}, "baseline_hash")


def initialize_arm(root, state_root, config, baseline):
    verify_signed(baseline, "baseline_hash")
    if config.arm == "observer":
        raise ValueError("observer cannot initialize mutable state")
    root, state = Path(root).resolve(), Path(state_root).resolve()
    if state == root or state in root.parents:
        raise ValueError("private runtime directory required")
    if state.exists() and any(state.iterdir()):
        raise ValueError("state root must be empty; never reuse another arm's state")
    if source_identity(root)["source_hash"] != baseline["source_hash"]:
        raise ValueError("baseline code differs from checkout")
    if portable_toolchain() != baseline["toolchain"] or platform.python_version() != baseline["python"]:
        raise ValueError("baseline toolchain mismatch")
    if list(config.raw["evaluation"]["seeds"]) != baseline["seeds"]:
        raise ValueError("baseline seed mismatch")
    state.mkdir(parents=True, exist_ok=True)
    freeze(state/"baseline.json", baseline)
    freeze(state/"base_policy.json", baseline["policy"])
    freeze(state/"memory.json", {"enabled": False, "entries": []})
    registry = initialize_registry(state/"base_policy.json", state/"registry.json")
    machine = signed({"schema_version": "r3e-aic-machine-v1", "experiment_id": config.experiment_id,
        "arm": config.arm, "baseline_hash": baseline["baseline_hash"], "config_hash": config.config_hash,
        "initial_policy_hash": get_active_policy(registry).policy_hash,
        "initial_registry_hash": registry["registry_hash"], "memory_hash": baseline["memory_hash"],
        "cross_arm_state_import": False}, "machine_hash")
    freeze(state/"machine_manifest.json", machine)
    return machine


def load_runtime(state_root):
    state = Path(state_root).resolve()
    machine = verify_signed(read(state/"machine_manifest.json"), "machine_hash")
    baseline = verify_signed(read(state/"baseline.json"), "baseline_hash")
    if machine["baseline_hash"] != baseline["baseline_hash"] or hash_payload(read(state/"memory.json")) != baseline["memory_hash"]:
        raise ValueError("baseline or fixed memory changed")
    runtime = PolicyRuntimeService(state/"registry.json", arm=machine["arm"], initial_policy_hash=machine["initial_policy_hash"])
    runtime.active_policy()
    if machine["arm"] == "static":
        from r3e.policy.registry_v2 import load_registry
        if load_registry(runtime.registry_path)["registry_hash"] != machine["initial_registry_hash"]:
            raise ValueError("static registry changed")
        if (state/"red_residual_archive.jsonl").exists() or (state/"rounds").exists():
            raise ValueError("static arm contains evolution state")
    return runtime, machine, baseline
