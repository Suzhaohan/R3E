"""Activate accumulated context only after actual same-policy paired replays."""
from pathlib import Path

from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.experience_memory import ExperienceMemory
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier


def verify_guard(report):
    verify_signed(report)
    binding = report["binding"]
    expected = {(case, seed) for case in binding["case_ids"] for seed in binding["seeds"]}
    seen, gained, lost = set(), 0, 0
    for pair in report["pairs"]:
        before, after = (verify_signed(pair[k], "receipt_hash") for k in ("before", "after"))
        key = (before["case_id"], before["seed"])
        if key in seen or key not in expected or key != (after["case_id"], after["seed"]):
            raise ValueError("memory guard pair membership mismatch")
        seen.add(key)
        for field in ("policy_hash", "case_asset_hash", "provider_fingerprint", "budget_hash", "verifier_hash"):
            if before[field] != after[field]:
                raise ValueError("memory guard paired conditions differ")
        if (before["policy_hash"] != binding["policy_hash"]
                or before["experience_memory_hash"] != binding["parent_memory_hash"]
                or after["experience_memory_hash"] != binding["proposed_memory_hash"]):
            raise ValueError("memory guard context mismatch")
        gained += not before["oracle_ok"] and after["oracle_ok"]
        lost += before["oracle_ok"] and not after["oracle_ok"]
    accepted = seen == expected and gained > 0 and lost == 0
    if report["accepted"] != accepted or (report["complete"] and seen != expected):
        raise ValueError("memory activation not supported by complete paired evidence")
    return report


def guard(root, state, operation, client, policy, rows, seeds, previous, proposed):
    state = Path(state)
    directory = state / "experience/guards" / operation
    binding = {"parent_memory_hash": previous["result_hash"], "proposed_memory_hash": proposed["result_hash"],
               "policy_hash": policy.policy_hash, "case_ids": [r["case_id"] for r in rows], "seeds": list(seeds)}
    report_path = directory / "report.json"
    if report_path.exists():
        report = verify_guard(read(report_path))
        if report["binding"] != binding:
            raise ValueError("experience guard binding changed")
        return report["accepted"]
    # Reuse a completed decision only for exactly the same policy, memory,
    # cases and repetitions. No-cost rounds must not resample until something
    # actually changes.
    for earlier in sorted((state / "experience/guards").glob("*/report.json")):
        report = verify_guard(read(earlier))
        if report["binding"] == binding:
            freeze(report_path, report)
            return report["accepted"]
    old_memory, new_memory = ExperienceMemory(previous), ExperienceMemory(proposed)
    if all(old_memory.retrieve(row) == new_memory.retrieve(row) for row in rows):
        freeze(report_path, signed({"binding": binding, "accepted": False,
            "reason": "unchanged_retrieval", "pairs": [], "complete": False}))
        return False
    services = []
    for memory in (previous, proposed):
        provider = PolicyCandidateProvider(client, memory=ExperienceMemory(memory),
            verifier_id=PublicManifestOracleVerifier.verifier_id,
            verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
        services.append(ArenaEvaluationService(root, state / "replays", provider=provider))
    pairs = []
    for row in rows:
        for seed in seeds:
            before, after = [service.evaluate_case_cached(policy, row, seed, cache_root=directory / "cache")
                             for service in services]
            pairs.append({"before": before, "after": after})
            if before["oracle_ok"] and not after["oracle_ok"]:
                freeze(report_path, signed({"binding": binding, "accepted": False,
                    "reason": "regression", "pairs": pairs, "complete": False}))
                return False
    gained = sum(not p["before"]["oracle_ok"] and p["after"]["oracle_ok"] for p in pairs)
    accepted = gained > 0
    freeze(report_path, signed({"binding": binding, "accepted": accepted,
        "reason": "improved_without_regression" if accepted else "no_gain", "pairs": pairs, "complete": True}))
    return accepted
