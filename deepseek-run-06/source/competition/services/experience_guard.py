"""Qualify v2 case memory through the existing same-policy paired replays.

Keep the run's cases, seeds, candidate budget and executor. Apply the v2
coverage, net-gain and sign-test gate to memory delivered after a failure.
"""
from math import comb
from pathlib import Path

from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.experience_memory import ExperienceMemory
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.blue.portfolio.runtime_evidence import build_runtime_evidence, visible_observations
from r3e.protocol.hashing import hash_payload


# Defaults from v2 r3e/loop/qualification.py. No extra repetitions/model calls
# are introduced: insufficient evidence leaves the proposed memory inactive.
QUALIFICATION = {"min_coverage": 1, "min_net_gain": 2, "max_p_value": 0.2, "max_harmed": 0}


def qualification(pairs):
    covered = [p for p in pairs if p.get("memory_delivered")]
    helped = sum(not p["before"]["oracle_ok"] and p["after"]["oracle_ok"] for p in covered)
    harmed = sum(p["before"]["oracle_ok"] and not p["after"]["oracle_ok"] for p in pairs)
    n = helped + harmed
    p_value = sum(comb(n, k) for k in range(helped, n + 1)) / 2 ** n if n else 1.0
    return {"coverage": len(covered), "helped": helped, "harmed": harmed, "p_value": p_value}


def verify_guard(report):
    verify_signed(report)
    binding = report["binding"]
    if report.get("qualification") != QUALIFICATION:
        raise ValueError("memory qualification settings differ")
    expected = {(case, seed) for case in binding["case_ids"] for seed in binding["seeds"]}
    seen = set()
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
    stats = qualification(report["pairs"])
    accepted = bool(expected) and report["complete"] and seen == expected and all(
        p[k]["status"] == "evaluated" for p in report["pairs"] for k in ("before", "after"))
    accepted = accepted and stats["coverage"] >= QUALIFICATION["min_coverage"] and (
        stats["helped"] - stats["harmed"] >= QUALIFICATION["min_net_gain"]
        and stats["harmed"] <= QUALIFICATION["max_harmed"]
        and stats["p_value"] <= QUALIFICATION["max_p_value"])
    if report["accepted"] != accepted or (report["complete"] and seen != expected) or report.get("statistics") != stats:
        raise ValueError("memory activation not supported by complete paired evidence")
    return report


def guard(root, state, operation, client, policy, rows, seeds, previous, proposed):
    state = Path(state)
    old_memory, new_memory = ExperienceMemory(previous), ExperienceMemory(proposed)
    directory = state / "experience/guards" / operation
    services = []
    for memory in (old_memory, new_memory):
        provider = PolicyCandidateProvider(client, memory=memory,
            verifier_id=PublicManifestOracleVerifier.verifier_id,
            verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
        services.append(ArenaEvaluationService(root, state / "replays", provider=provider))
    affected = []
    for row in rows:
        if not old_memory.value["items"] and not new_memory.value["items"]:
            break
        case = services[0]._case(row)
        context = build_runtime_evidence(case, project_root=root,
            source_descriptor={"descriptor_hash": hash_payload({"case_id": row["case_id"]})})
        artifact = {"case_id": case["case_id"], "top_module": case["top_module"],
                    "buggy_rtl_source": case["buggy_rtl_source"]}
        evidence = {"runtime_observations": visible_observations(context, policy)}
        if old_memory.retrieve(artifact, evidence=evidence) != new_memory.retrieve(artifact, evidence=evidence):
            affected.append(row)
    rows = affected
    binding = {"parent_memory_hash": previous["result_hash"], "proposed_memory_hash": proposed["result_hash"],
               "policy_hash": policy.policy_hash, "case_ids": [r["case_id"] for r in rows], "seeds": list(seeds)}
    report_path = directory / "report.json"
    if report_path.exists():
        report = verify_guard(read(report_path))
        if report["binding"] != binding:
            raise ValueError("experience guard binding changed")
        return report["accepted"]
    for earlier in sorted((state / "experience/guards").glob("*/report.json")):
        report = verify_guard(read(earlier))
        if report["binding"] == binding:
            freeze(report_path, report)
            return report["accepted"]

    pairs = []

    def finish(complete, reason):
        stats = qualification(pairs)
        accepted = bool(rows) and complete and all(
            p[k]["status"] == "evaluated" for p in pairs for k in ("before", "after")) and (
            stats["coverage"] >= QUALIFICATION["min_coverage"]
            and stats["helped"] - stats["harmed"] >= QUALIFICATION["min_net_gain"]
            and stats["harmed"] <= QUALIFICATION["max_harmed"]
            and stats["p_value"] <= QUALIFICATION["max_p_value"])
        report = signed({"binding": binding, "qualification": QUALIFICATION,
            "statistics": stats, "accepted": accepted, "reason": reason,
            "pairs": pairs, "complete": complete})
        freeze(report_path, verify_guard(report))
        return accepted

    if not rows:
        return finish(True, "no_coverage")
    for row in rows:
        for seed in seeds:
            before, after = [service.evaluate_case_cached(policy, row, seed, cache_root=directory / "cache")
                             for service in services]
            # A successful first attempt never receives memory. Do not count
            # first-attempt sampling differences as gains from memory.
            delivered = False
            if all(r["status"] == "evaluated" for r in (before, after)):
                executions = [read(state / "replays" / r["artifact_id"] / "evaluation.json")
                              for r in (before, after)]
                delivered = all(len(e["candidate_verification_receipts"]) > 1
                    and not e["candidate_verification_receipts"][0]["oracle_ok"] for e in executions)
            pairs.append({"before": before, "after": after, "memory_delivered": delivered})
            if ((before["oracle_ok"] and not after["oracle_ok"])
                    or before["status"] != "evaluated" or after["status"] != "evaluated"):
                return finish(False, "regression_or_unavailable")
    return finish(True, "paired_case_memory_qualification")
