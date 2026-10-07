"""Compare complete paired denominators; validate before rendering any gain."""
import math
from statistics import mean, stdev
from competition.arena.evidence import signed, verify_signed


def verify_evaluation(value, *, live_only=False):
    verify_signed(value)
    if value.get("schema_version") != "r3e-aic-arena-evaluation-v1":
        raise ValueError("evaluation schema mismatch")
    seeds, ids, rows = value["seeds"], value["case_ids"], value["cases"]
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int for s in seeds) or not ids or len(set(ids)) != len(ids):
        raise ValueError("invalid paired membership")
    expected = {(case, seed) for case in ids for seed in seeds}
    actual = [(r["case_id"],r["seed"]) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected or value["denominator"] != len(expected):
        raise ValueError("missing or duplicate case/seed; fixed denominator violated")
    for row in rows:
        verify_signed(row, "receipt_hash")
        if row["policy_hash"] != value["policy_hash"] or type(row["oracle_ok"]) is not bool:
            raise ValueError("evaluation policy/result mismatch")
        if live_only and row.get("source_kind") != "live_model":
            raise ValueError("guided/injected evidence cannot be frozen as live")
    successes = sum(r["oracle_ok"] for r in rows)
    if value["repaired"] != successes or value["repair_rate"] != successes/len(expected):
        raise ValueError("evaluation rate not derived from receipts")
    return value


def verify_arm(value, *, live_only=True):
    verify_signed(value)
    if value.get("schema_version") != "r3e-aic-frozen-arm-v1":
        raise ValueError("arm schema mismatch")
    baseline = verify_signed(value["baseline"], "baseline_hash")
    if live_only and (baseline["dirty"] is not False or not baseline["git_commit"] or value.get("source_kind") != "live_model"):
        raise ValueError("formal freeze requires clean committed source and live evidence")
    if value["memory_hash"] != baseline["memory_hash"]:
        raise ValueError("M3-A memory changed")
    if baseline.get("experience_memory_enabled"):
        snapshots = value.get("experience_snapshots", {})
        for snapshot in snapshots.values():
            verify_signed(snapshot)
        from competition.services.experience_guard import verify_guard
        previous = snapshots.get("T0")
        for record in value["rounds"]:
            context = snapshots[record["round_id"]]
            if previous is not None and context != previous:
                guard = verify_guard(value["experience_guards"][record["round_id"]])
                if (not guard["accepted"] or guard["binding"]["parent_memory_hash"] != previous["result_hash"]
                        or guard["binding"]["proposed_memory_hash"] != context["result_hash"]
                        or guard["binding"]["policy_hash"] != record["parent_policy_hash"]):
                    raise ValueError("experience activation chain mismatch")
            previous = context
        if value["rounds"] and snapshots.get("T1") != previous:
            raise ValueError("final experience differs from last guarded round")
        for phase, group in (("T1", value["evaluations"]), ("T0", value.get("baseline_evaluations", {}))):
            if not group:
                continue
            context = snapshots.get(phase)
            if context is None:
                raise ValueError("missing frozen experience context")
            if phase == "T0" or value["arm"] == "static":
                from r3e.protocol.hashing import hash_payload
                if hash_payload(context) != baseline["memory_hash"]:
                    raise ValueError("initial/static experience changed")
            for evaluation in group.values():
                if any(r.get("experience_memory_hash") != context["result_hash"] for r in evaluation["cases"]):
                    raise ValueError("evaluation experience context mismatch")
    rounds = value["rounds"]
    if value["arm"] == "adversarial" and "required_adversarial_rounds" in baseline:
        if [r["round_id"] for r in rounds] != [f"R{i:03d}" for i in range(baseline["required_adversarial_rounds"])]:
            raise ValueError("baseline requires all five adversarial rounds")
    if "live_plan" in value:
        plan = verify_signed(value["live_plan"])
        expected = [f"R{i:03d}" for i in range(5)] if value["arm"] == "adversarial" else []
        if plan["baseline_hash"] != baseline["baseline_hash"] or plan["arm"] != value["arm"] or plan["round_ids"] != expected or [r["round_id"] for r in rounds] != expected:
            raise ValueError("live five-round plan mismatch")
        usage = value["provider_budget"]
        if usage["max_calls"] != plan["max_calls"] or usage["max_tokens"] != plan["max_tokens"] or not 0 <= usage["calls"] <= usage["max_calls"] or not 0 <= usage["reserved_tokens"] <= usage["max_tokens"]:
            raise ValueError("live provider budget mismatch")
    current = baseline["initial_policy_hash"]
    promotions = 0
    for row in rounds:
        verify_signed(row, "audit_record_hash")
        if row["parent_policy_hash"] != current or row["validity_authority"] != "grounded_runtime_authority_v1" or row["blue_evaluation_authority"] != "candidate_portfolio_v1":
            raise ValueError("round policy/authority chain mismatch")
        if row["code_version"] != baseline["git_commit"] and live_only:
            raise ValueError("round commit differs from baseline")
        promotions += bool(row["promoted"])
        current = row["active_policy_hash"]
    if current != value["final_policy_hash"] or value["promotion_count"] != promotions:
        raise ValueError("final policy is not the audited registry chain")
    if "round_views" in value:
        if len(value["round_views"]) != len(rounds):
            raise ValueError("round presentation membership mismatch")
        for view, audit in zip(value["round_views"], rounds):
            verify_signed(view, "view_hash")
            if any(view[k] != audit[k] for k in ("round_id", "audit_record_hash", "parent_policy_hash", "active_policy_hash", "promoted")):
                raise ValueError("round presentation audit mismatch")
            if view.get("design_allocation") != audit.get("design_allocation"):
                raise ValueError("round presentation design allocation mismatch")
    if value["arm"] == "static":
        if rounds or promotions or value["red_archive_count"] or current != baseline["initial_policy_hash"]:
            raise ValueError("static arm changed")
    elif value["arm"] != "adversarial":
        raise ValueError("invalid experiment arm")
    if value.get("evolution_claim") and (not promotions or current == baseline["initial_policy_hash"]):
        raise ValueError("evolution claim requires an audited promotion")
    if set(value["evaluations"]) != set(baseline["evaluation_manifests"]):
        raise ValueError("both final datasets are required")
    for name, evaluation in value["evaluations"].items():
        verify_evaluation(evaluation, live_only=live_only)
        if evaluation["manifest_hash"] != baseline["evaluation_manifests"][name] or evaluation["seeds"] != baseline["seeds"] or evaluation["policy_hash"] != current:
            raise ValueError("evaluation differs from shared baseline/final policy")
    if value.get("live_plan", {}).get("evaluation_phases") == ["T0", "T1"]:
        before = value.get("baseline_evaluations", {})
        if set(before) != set(baseline["evaluation_manifests"]):
            raise ValueError("T0 baseline evaluations are required")
        for name, evaluation in before.items():
            verify_evaluation(evaluation, live_only=live_only)
            if (evaluation["manifest_hash"] != baseline["evaluation_manifests"][name]
                    or evaluation["policy_hash"] != baseline["initial_policy_hash"]
                    or evaluation["seeds"] != baseline["seeds"]
                    or evaluation["case_ids"] != value["evaluations"][name]["case_ids"]):
                raise ValueError("T0 differs from frozen initial policy/dataset")
    return value


def _wilson(k, n):
    z=1.959963984540054; p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,c-h),min(1,c+h)]


def compare_arms(left, right, *, live_only=True):
    verify_arm(left, live_only=live_only); verify_arm(right, live_only=live_only)
    if left["arm"] != "static" or right["arm"] != "adversarial":
        raise ValueError("comparison requires static left and adversarial right")
    if left["experiment_id"] != right["experiment_id"] or left["baseline"]["baseline_hash"] != right["baseline"]["baseline_hash"]:
        raise ValueError("A/B baseline, model, budget, toolchain or seeds mismatch")
    metrics = {}
    for name, a in left["evaluations"].items():
        b=right["evaluations"][name]
        if a["case_ids"] != b["case_ids"] or a["seeds"] != b["seeds"]:
            raise ValueError("A/B paired cases differ")
        ar={(r["case_id"],r["seed"]):r for r in a["cases"]}
        br={(r["case_id"],r["seed"]):r for r in b["cases"]}
        for key in ar:
            for field in ("model_id", "budget_hash", "verifier_hash", "provider_fingerprint", "case_asset_hash"):
                if ar[key][field] != br[key][field]:
                    raise ValueError(f"A/B paired {field} mismatch")
        gained=sum(not ar[k]["oracle_ok"] and br[k]["oracle_ok"] for k in ar)
        lost=sum(ar[k]["oracle_ok"] and not br[k]["oracle_ok"] for k in ar)
        per_seed={str(seed): {"static":sum(r["oracle_ok"] for r in a["cases"] if r["seed"]==seed)/len(a["case_ids"]),
            "adversarial":sum(r["oracle_ok"] for r in b["cases"] if r["seed"]==seed)/len(b["case_ids"])} for seed in a["seeds"]}
        metrics[name]={"denominator":a["denominator"], "static_repaired":a["repaired"], "adversarial_repaired":b["repaired"],
            "static_rate":a["repair_rate"], "adversarial_rate":b["repair_rate"], "delta":b["repair_rate"]-a["repair_rate"],
            "gained_pairs":gained,"lost_pairs":lost,"per_seed":per_seed,
            "seed_sd":{arm:stdev(row[arm] for row in per_seed.values()) if len(per_seed)>1 else 0.0 for arm in ("static","adversarial")},
            "wilson_descriptive": {"static":_wilson(a["repaired"],a["denominator"]),"adversarial":_wilson(b["repaired"],b["denominator"])},
            "statistical_note":"Repeated seeds on the same case are correlated; pooled intervals are descriptive, not independent-trial significance."}
        from r3e.policy.promotion import _exact_mcnemar
        if all("design" in row for row in [*ar.values(), *br.values()]):
            metrics[name]["mcnemar_repetition_pairs_descriptive"] = _exact_mcnemar(gained, lost)
            designs = sorted({r["design"] for r in ar.values()})
            by_design = {}
            for design in designs:
                keys = [key for key in ar if ar[key]["design"] == design]
                if any(br[key]["design"] != design for key in keys):
                    raise ValueError("A/B design grouping mismatch")
                old, new = (sum(rows[k]["oracle_ok"] for k in keys) / len(keys) for rows in (ar, br))
                by_design[design] = {"pairs": len(keys), "static_rate": old, "adversarial_rate": new, "delta": new-old}
            metrics[name]["per_design"] = by_design
            metrics[name]["design_equal_weighted_delta"] = mean(v["delta"] for v in by_design.values())
        if "baseline_evaluations" in left and "baseline_evaluations" in right:
            a0, b0 = left["baseline_evaluations"][name], right["baseline_evaluations"][name]
            metrics[name]["T0"] = {"static_rate": a0["repair_rate"], "adversarial_rate": b0["repair_rate"],
                "initial_gap": b0["repair_rate"] - a0["repair_rate"]}
            metrics[name]["change_from_T0"] = {"static": a["repair_rate"] - a0["repair_rate"],
                "adversarial": b["repair_rate"] - b0["repair_rate"]}
    acceptance = {}
    if "live_plan" in left and "live_plan" in right:
        acceptance = {"five_rounds_completed": len(right["rounds"]) == 5,
            "audited_promotion_observed": right["promotion_count"] > 0,
            "heldout_positive_gain": metrics["red-heldout"]["delta"] > 0,
            "strider_positive_gain": metrics["strider-subset4"]["delta"] > 0,
            "distinct_reported_hosts": left["live_plan"]["host_identity_hash"] != right["live_plan"]["host_identity_hash"],
            "deployment_note": "Host hashes are self-reported deployment metadata, not independent proof of two physical machines."}
    return signed({"schema_version":"r3e-aic-arena-comparison-v1", "available":True,
        "mode":"verified_evolution_replay" if live_only else "offline_contract_test",
        "experiment_id":left["experiment_id"], "baseline_hash":left["baseline"]["baseline_hash"],
        "static":left, "adversarial":right, "metrics":metrics,
        **({"acceptance": acceptance} if acceptance else {})}, "comparison_hash")


def verify_comparison(value):
    verify_signed(value,"comparison_hash")
    rebuilt=compare_arms(value["static"], value["adversarial"], live_only=True)
    if value != rebuilt:
        raise ValueError("comparison does not reconstruct")
    return value
