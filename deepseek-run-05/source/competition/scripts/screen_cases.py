"""Explicit, budgeted development-only paired screening; never select on finals."""
from pathlib import Path

from competition.arena.cli import _client
from competition.arena.budget import BudgetedClient
from competition.arena.evidence import read, freeze, signed
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.experience_memory import ExperienceMemory, initial_bank, bank
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.protocol.hashing import hash_payload


def run(root, *, max_calls, max_tokens):
    root = Path(root)
    out = root.parent / "development-screen"
    client = BudgetedClient(_client(root.parent / "client.json"), out / "budget.json",
                            max_calls=max_calls, max_tokens=max_tokens)
    memory = ExperienceMemory(initial_bank(root))
    provider = PolicyCandidateProvider(client, memory=memory,
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    service = ArenaEvaluationService(root, out / "replays", provider=provider)
    static_provider = PolicyCandidateProvider(client, memory=ExperienceMemory(bank([])),
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    static = ArenaEvaluationService(root, out / "replays", provider=static_provider)
    parent = service.repair._policy()
    pool = read(root / "competition/manifests/demo32_supplied_assets.json")
    strategies = [(m, k) for m in ("raw", "hybrid") for k in (1, 3, 6)]
    freeze(out / "plan.json", signed({"manifest_hash": pool["manifest_hash"],
        "memory_hash": memory.memory_hash, "strategies": strategies, "seeds": [1, 2, 3],
        "max_calls": max_calls, "max_tokens": max_tokens,
        "provider": provider.toolchain_fingerprint, "policy": parent.to_dict()}))
    results = []
    for row in pool["rows"]:
        scores = {}
        static_receipts = [static.evaluate_case_cached(parent, row, seed, cache_root=out / "cache") for seed in (1, 2, 3)]
        for mode, depth in strategies:
            policy = parent if (mode, depth) == ("raw", 1) else parent.with_updates(
                policy_id=f"screen_{mode}_{depth}",
                configuration={**parent.configuration, "evidence_mode": mode, "evidence_k": depth})
            receipts = [service.evaluate_case_cached(policy, row, seed, cache_root=out / "cache") for seed in (1, 2, 3)]
            scores[f"{mode}/{depth}"] = {"successes": sum(r["oracle_ok"] for r in receipts),
                                         "receipt_hashes": [r["receipt_hash"] for r in receipts]}
        baseline = sum(r["oracle_ok"] for r in static_receipts)
        best = max(scores, key=lambda k: scores[k]["successes"])
        results.append({"case_id": row["case_id"], "design": row["design"], "strategies": scores,
                        "static_successes": baseline, "best_strategy": best,
                        "static_receipt_hashes": [r["receipt_hash"] for r in static_receipts],
                        "best_successes": scores[best]["successes"],
                        "strong_demo_candidate": baseline == 0 and scores[best]["successes"] == 3})
    report = signed({"schema_version": "r3e-paired-development-screen-v1", "rows": results,
        "selection_bias_note": "Development selection over six strategies; not independent final performance.",
        "all_cases_reported": True, "reference_answers_in_prompt": False})
    freeze(out / "report.json", report)
    return {"output": str(out / "report.json"), "strong_demo_candidates": [
        r["case_id"] for r in results if r["strong_demo_candidate"]], "report_hash": hash_payload(report)}
