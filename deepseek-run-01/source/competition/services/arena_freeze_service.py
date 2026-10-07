"""Reconstruct local raw receipts before exporting read-only arm telemetry."""
from pathlib import Path
from r3e.arena.audit import verify_frozen_round
from r3e.blue.portfolio.audit import verify_blue_evaluation
from r3e.protocol.hashing import hash_payload
from competition.arena.baseline import load_runtime, source_identity
from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.arena_comparison_service import verify_arm, verify_evaluation


def freeze_arm(root, state_root, evaluation_paths, target, *, evolution_claim=False):
    state=Path(state_root)
    runtime,machine,baseline=load_runtime(state)
    identity=source_identity(root)
    if identity["dirty"] or not identity["git_commit"] or identity["git_commit"] != baseline["git_commit"] or identity["source_hash"] != baseline["source_hash"]:
        raise ValueError("freeze requires unchanged, clean, committed source")
    policy=runtime.active_policy()
    rounds=[verify_frozen_round(p) for p in sorted((state/"rounds").glob("R*")) if p.is_dir()]
    plan = verify_signed(read(state/"live_plan.json")) if (state/"live_plan.json").exists() else None
    if plan is not None:
        expected = [f"R{i:03d}" for i in range(5)] if machine["arm"] == "adversarial" else []
        if plan["baseline_hash"] != baseline["baseline_hash"] or plan["arm"] != machine["arm"] or plan["round_ids"] != expected or [r["round_id"] for r in rounds] != expected:
            raise ValueError("five-round live plan is incomplete or changed")
    budget_path = state/"budgets/total.json"
    budget = read(budget_path) if budget_path.exists() else {"calls": 0, "reserved_tokens": 0,
        "max_calls": plan["max_calls"] if plan else 0, "max_tokens": plan["max_tokens"] if plan else 0}
    service=ArenaEvaluationService(root,state/"eval")
    evaluations={}
    for path in evaluation_paths:
        envelope=verify_signed(read(path))
        if envelope["experiment_id"] != machine["experiment_id"] or envelope["arm"] != machine["arm"] or envelope["baseline_hash"] != baseline["baseline_hash"]:
            raise ValueError("evaluation belongs to another arm/baseline")
        evaluation=verify_evaluation(envelope["evaluation"],live_only=True)
        if evaluation["dataset"] in evaluations:
            raise ValueError("duplicate evaluation dataset")
        artifact_root=state/"eval"/evaluation["dataset"]
        for receipt in evaluation["cases"]:
            work=(artifact_root/receipt["artifact_id"]).resolve()
            if work.parent != artifact_root.resolve():
                raise ValueError("unsafe evaluation artifact identity")
            if read(work/"receipt.json") != receipt:
                raise ValueError("raw receipt differs from summary")
            if receipt["status"] != "evaluated":
                # Keep unavailable cases in the denominator; zero model calls and zero success.
                if receipt["oracle_ok"] or receipt["resource_usage"]["provider_calls"] != 0:
                    raise ValueError("invalid unevaluated case")
                continue
            evaluation_raw=read(work/"evaluation.json")
            verify_blue_evaluation(evaluation_raw,policy=policy,registry=service.repair.registry,
                portfolio=service.repair.portfolio,provider_fingerprints=[receipt["provider_fingerprint"]],
                expected_verifier_hash=receipt["verifier_hash"],router=service.repair.router,
                descriptor=read(work/"descriptor.json"))
            if evaluation_raw["portfolio_execution_hash"] != receipt["portfolio_execution_hash"] or evaluation_raw["oracle_ok"] != receipt["oracle_ok"]:
                raise ValueError("raw execution differs from accepted result")
        evaluations[evaluation["dataset"]]=evaluation
    archive=state/"red_residual_archive.jsonl"
    from competition.arena.presentation import round_view
    result=signed({"schema_version":"r3e-aic-frozen-arm-v1", "source_kind":"live_model",
        "experiment_id":machine["experiment_id"],"arm":machine["arm"],"baseline":baseline,
        "final_policy_hash":policy.policy_hash,"memory_hash":baseline["memory_hash"],
        "rounds":rounds,"promotion_count":sum(r["promoted"] for r in rounds),
        "red_archive_count":len([x for x in archive.read_text().splitlines() if x.strip()]) if archive.exists() else 0,
        "evolution_claim":evolution_claim,"evaluations":evaluations,
        "round_views": [round_view(state/"rounds"/r["round_id"]) for r in rounds],
        **({"live_plan": plan, "provider_budget": budget} if plan else {})})
    verify_arm(result)
    return freeze(target,result)
