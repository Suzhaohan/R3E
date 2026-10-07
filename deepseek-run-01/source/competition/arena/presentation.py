"""Allowlisted result views. Never export prompts, answer RTL or credentials."""
import json
import difflib
from pathlib import Path
from competition.arena.evidence import read, signed
from r3e.arena.audit import verify_frozen_round
from r3e.protocol.hashing import hash_file


def round_view(directory, *, include_local_diffs=False):
    directory = Path(directory)
    audit = verify_frozen_round(directory)
    summary = read(directory / "round_summary.json")
    if any(summary[k] != audit[k] for k in ("round_id", "parent_policy_hash", "active_policy_hash", "promoted", "audit_record_hash")):
        raise ValueError("round summary differs from audited result")
    def records(name):
        return [json.loads(s) for s in (directory / name).read_text().splitlines() if s.strip()]
    proposed = records("red_candidates.jsonl")
    valid = {r["poison_id"]: r for r in records("valid_poisons.jsonl")}
    challenges = {r["poison_id"]: r for r in records("blue_challenge_results.jsonl")}
    cases = []
    for row in proposed:
        blue = challenges.get(row["poison_id"], {}).get("blue_results", [])
        receipt = row.get("grounded_materialization_receipt", {})
        edit = receipt.get("edit", {})
        authority = valid.get(row["poison_id"], {}).get("grounded_authority_bundle", {})
        runs = authority.get("execution_bundle", {}).get("evidence", {}).get("poison_runs", [])
        mismatch = runs[0].get("observed", {}).get("oracle_provider_receipt", {}).get("result", {}) if runs else {}
        diffs = {}
        if include_local_diffs and blue:
            buggy = Path(row["buggy_rtl"]).resolve()
            if directory.resolve() not in buggy.parents or hash_file(buggy) != receipt["poison_rtl_hash"]:
                raise ValueError("candidate diff source path/hash mismatch")
            source = buggy.read_text().splitlines(keepends=True)
            for b in blue:
                for generated in b["candidate_provider_receipts"]:
                    patch = generated["patch_payload"]
                    diffs[(b["seed"], generated["candidate_id"])] = "".join(difflib.unified_diff(
                        source, patch["replacement_rtl"].splitlines(keepends=True), fromfile="buggy.v", tofile="candidate.v"))
        cases.append({"case_id": row["case_id"], "poison_id": row["poison_id"],
            "design": row["design"], "family": row["family"],
            "operator": row.get("grounded_mutation_plan", {}).get("operator_id", ""),
            "poison_hash": receipt.get("poison_rtl_hash", ""),
            "valid": row["poison_id"] in valid,
            "first_mismatch": {k: mismatch[k] for k in ("first_divergence_cycle", "first_divergence_signal", "mismatch_pattern") if k in mismatch},
            "mutation": {k: edit[k] for k in ("old_text", "new_text", "clean_start") if k in edit},
            "challenged_policy_id": row["challenged_policy_id"],
            "seeds": [{"seed": b["seed"], "oracle_ok": b["oracle_ok"],
                "candidates": [{**{k: c[k] for k in ("candidate_id", "parse_ok", "compile_ok", "scope_ok", "oracle_ok", "verification_hash") if k in c},
                                **({"diff": diffs[(b["seed"], c["candidate_id"])]} if include_local_diffs else {})}
                               for c in b["candidate_verification_receipts"]]} for b in blue]})
    return signed({**summary, "audit_record_hash": audit["audit_record_hash"],
        "stages": [c["stage"] for c in read(directory / "round_state.json")["checkpoints"]],
        "designs": sorted({r["design"] for r in proposed}),
        "families": sorted({r["family"] for r in proposed}),
        "proposed_count": len(proposed), "valid_count": len(valid),
        "repaired_count": sum(bool(c["seeds"]) and all(s["oracle_ok"] for s in c["seeds"]) for c in cases),
        "child_count": len(records("child_policies.jsonl")),
        "promotion_gates": [{k: d[k] for k in ("candidate_policy_id", "decision", "checks", "prior_failure_recovery", "target", "non_target", "cost_ratio") if k in d}
                            for d in records("promotion_decisions.jsonl")],
        "cases": cases}, "view_hash")


def paired_case_views(left, right):
    """Inputs must already have passed paired evaluation verification."""
    right_rows = {(r["case_id"], r["seed"]): r for r in right["cases"]}
    return [{"case_id": a["case_id"], "seed": a["seed"],
             **{arm: {k: r[k] for k in ("oracle_ok", "status", "policy_hash", "source_kind", "resource_usage", "receipt_hash")}
                for arm, r in (("static", a), ("adversarial", right_rows[(a["case_id"], a["seed"])]))}}
            for a in left["cases"]]
