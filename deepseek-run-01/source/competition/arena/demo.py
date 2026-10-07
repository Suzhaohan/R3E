"""Offline protocol demonstration. Never eligible for live comparison evidence.

The scripted provider intentionally knows the frozen training/regression
solutions. It illustrates policy plumbing, not learning or heldout performance.
All challenge, replay, promotion and EDA decisions still come from the Core.
"""
from __future__ import annotations

import difflib
import json
import tempfile
from pathlib import Path

from competition.arena.baseline import build_baseline, initialize_arm, load_runtime
from competition.arena.cli import _split_certificate
from competition.arena.evidence import freeze, read, signed, verify_signed
from competition.arena.runtime import build_arena_service
from competition.arena_config import load_arena_config
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.arena_comparison_service import verify_evaluation
from r3e.arena.audit import verify_frozen_round
from r3e.arena.round_state import RoundState, STAGES
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.providers.openai_compatible import OpenAICompatibleClientConfig, OpenAICompatibleJSONClient

SCHEMA = "r3e-aic-offline-arena-demo-v1"
MODE = "offline_protocol_demo"
NOTICE = ("离线工程演示 · 脚本模型替身 + 真实 Icarus/Yosys · 同机独立目录。"
          "替身预置演化/回归案例答案；变化仅验证策略执行链，不能作为模型能力提升或双机正式评测。")


def demo_client(root):
    # Explicit allowlist: no final-evaluation answers are loaded by this fixture.
    rows = [row for name in ("red_evolve_v2", "red_regression_v2")
            for row in read(Path(root)/f"competition/manifests/{name}.json")["rows"]]
    solutions = [(Path(root)/row["golden_rtl"]).read_text() for row in rows]
    calls = []

    def transport(**request):
        calls.append(1)
        prompt = json.loads(request["messages"][1]["content"])
        if "allowed_nodes" in prompt:
            result = {"target_module": prompt["target_module"],
                      "node_ordinal": prompt["allowed_nodes"][0]["node_ordinal"],
                      "rationale": "offline protocol demonstration"}
        else:
            source = prompt["current_buggy_rtl"]
            hybrid = "Combine the observed" in prompt["lens_instruction"]
            replacement = max(solutions, key=lambda s: difflib.SequenceMatcher(None, source, s).ratio()) if hybrid else source
            result = {"replacement_rtl": replacement, "edit": "scripted demonstration, not model inference"}
        return {"content": json.dumps(result), "input_tokens": 100, "output_tokens": 20,
                "provider_request_id": f"offline-demo-{len(calls)}"}

    config = OpenAICompatibleClientConfig(
        provider_id="offline-demo", provider_version="1", endpoint_id="local-fixture",
        model_id="scripted-protocol-demo", model_version="1", api_key_env="UNUSED_DEMO_KEY",
        base_url_env="UNUSED_DEMO_URL", timeout_seconds=30, maximum_output_tokens=4096,
        temperature=0, require_seed=True)
    return OpenAICompatibleJSONClient(config, transport=transport, environ={})


def run_demo(root, output=None, *, rounds=5, progress=print):
    root = Path(root).resolve()
    if type(rounds) is not int or not 1 <= rounds <= 6:
        raise ValueError("demo rounds must be between 1 and 6")
    # Validate tools before allocating any persistent state.
    from competition.arena.baseline import portable_toolchain
    missing = [name for name, info in portable_toolchain().items() if not info["available"]]
    if missing:
        raise RuntimeError("missing EDA tools: " + ", ".join(missing))
    out = Path(output).resolve() if output else Path(tempfile.mkdtemp(prefix="r3e-arena-demo-"))
    if out.exists() and any(out.iterdir()):
        raise ValueError("demo output must be empty; existing runs are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    client = demo_client(root)
    manifests = {"strider14": read(root/"competition/manifests/strider14_sealed.json"),
                 "red-heldout": read(root/"competition/manifests/red_heldout_v2.json")}
    baseline = build_baseline(root, provider_identity={"provider_id": client.config.provider_id,
        "model_id": client.config.model_id, "model_version": "1", "temperature": 0},
        evaluation_manifests=manifests, seeds=[1, 2, 3])
    certificate = _split_certificate(root, baseline)
    for arm in ("static", "adversarial"):
        initialize_arm(root, out/arm, load_arena_config(root/f"competition/configs/arena/{arm}.yaml"), baseline)
        freeze(out/arm/"separation.json", certificate)
    evolve = read(root/"competition/manifests/red_evolve_v2.json")
    regression = read(root/"competition/manifests/red_regression_v2.json")
    config = load_arena_config(root/"competition/configs/arena/adversarial.yaml")
    summaries = []
    for index in range(rounds):
        round_id = f"R{index:03d}"
        progress(f"{round_id}: Red → validity → Blue → replay → promotion gate", flush=True)
        service, cfg = build_arena_service(root, out/"adversarial", config, round_id, client, evolve, regression)
        summary = service.run_round(round_id, cfg, evolution_manifest=evolve, regression_manifest=regression)
        verify_frozen_round(out/"adversarial/rounds"/round_id)
        summaries.append(summary)
        progress(f"{round_id}: {'PROMOTED' if summary['promoted'] else 'RETAINED'} · {summary['active_policy_id']}", flush=True)
    evaluations = {}
    for arm in ("static", "adversarial"):
        runtime, _, _ = load_runtime(out/arm)
        policy = runtime.active_policy()
        freeze(out/arm/"final_evaluation_started.json", {"policy_hash": policy.policy_hash,
            "baseline_hash": baseline["baseline_hash"], "mode": MODE})
        provider = PolicyCandidateProvider(client, verifier_id=PublicManifestOracleVerifier.verifier_id,
            verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
        evaluator = ArenaEvaluationService(root, out/arm/"demo-check", provider=provider)
        cases = [evaluator.evaluate_case_with_policy(policy, row, seed)
                 for row in regression["rows"] for seed in baseline["seeds"]]
        repaired = sum(row["oracle_ok"] for row in cases)
        evaluations[arm] = signed({"schema_version": "r3e-aic-arena-evaluation-v1",
            "dataset": "demo-regression-only", "manifest_hash": regression["manifest_hash"],
            "policy_hash": policy.policy_hash, "case_ids": [r["case_id"] for r in regression["rows"]],
            "seeds": baseline["seeds"], "cases": cases, "denominator": len(cases),
            "repaired": repaired, "repair_rate": repaired/len(cases)})
        progress(f"{arm}: engineering checks {repaired}/{len(cases)}", flush=True)
    result = signed({"schema_version": SCHEMA, "mode": MODE, "source_kind": "injected_test",
        "baseline": baseline, "rounds": summaries, "evaluations": evaluations})
    freeze(out/"demo.json", result)
    verify_demo(out/"demo.json")
    return {"mode": MODE, "notice": NOTICE, "artifact": str(out/"demo.json"),
            "promotions": sum(r["promoted"] for r in summaries)}


def verify_demo(path):
    """Reconstruct round authority and receipt membership before exposing a demo."""
    path = Path(path).resolve()
    data = verify_signed(read(path))
    if data.get("schema_version") != SCHEMA or data.get("mode") != MODE or data.get("source_kind") != "injected_test":
        raise ValueError("not an offline protocol demo")
    baseline = verify_signed(data["baseline"], "baseline_hash")
    if baseline["provider"]["provider_id"] != "offline-demo":
        raise ValueError("unexpected demonstration provider")
    current = baseline["initial_policy_hash"]
    if not data["rounds"]:
        raise ValueError("demo has no audited rounds")
    for index, summary in enumerate(data["rounds"]):
        if summary["round_id"] != f"R{index:03d}" or summary["parent_policy_hash"] != current:
            raise ValueError("demo policy chain mismatch")
        directory = path.parent/"adversarial/rounds"/summary["round_id"]
        audit = verify_frozen_round(directory)
        if read(directory/"round_summary.json") != summary or audit["audit_record_hash"] != summary["audit_record_hash"]:
            raise ValueError("demo round evidence mismatch")
        for key in ("parent_policy_hash", "active_policy_hash", "promoted"):
            if summary[key] != audit[key]:
                raise ValueError("demo summary differs from reconstructed audit")
        current = summary["active_policy_hash"]
    if set(data["evaluations"]) != {"static", "adversarial"}:
        raise ValueError("both demo arms required")
    for arm, evaluation in data["evaluations"].items():
        runtime, _, local_baseline = load_runtime(path.parent/arm)
        expected_policy = baseline["initial_policy_hash"] if arm == "static" else current
        if local_baseline != baseline or runtime.active_policy().policy_hash != expected_policy:
            raise ValueError("demo runtime/baseline mismatch")
        verify_evaluation(evaluation)
        if evaluation["policy_hash"] != expected_policy or evaluation["dataset"] != "demo-regression-only" or evaluation["seeds"] != baseline["seeds"]:
            raise ValueError("demo evaluation binding mismatch")
        for row in evaluation["cases"]:
            artifact_id = row["artifact_id"]
            if not isinstance(artifact_id, str) or Path(artifact_id).name != artifact_id:
                raise ValueError("unsafe demo receipt path")
            receipt = read(path.parent/arm/"demo-check"/artifact_id/"receipt.json")
            if receipt != row or row["source_kind"] != "injected_test":
                raise ValueError("demo receipt mismatch")
    left, right = (data["evaluations"][a] for a in ("static", "adversarial"))
    if any(left[k] != right[k] for k in ("case_ids", "seeds", "manifest_hash")):
        raise ValueError("demo A/B membership mismatch")
    return data


def demo_snapshot(path):
    data = verify_demo(path)
    baseline = data["baseline"]
    from competition.arena.presentation import round_view, paired_case_views
    rows = [round_view(Path(path).resolve().parent/"adversarial/rounds"/r["round_id"]) for r in data["rounds"]]
    if any(r["stages"] != STAGES for r in rows):
        raise ValueError("incomplete demo round")
    evaluations = data["evaluations"]
    metric = {"denominator": evaluations["static"]["denominator"]}
    for arm, evaluation in evaluations.items():
        metric[arm+"_repaired"] = evaluation["repaired"]
        metric[arm+"_rate"] = evaluation["repair_rate"]
    metric["delta"] = metric["adversarial_rate"]-metric["static_rate"]
    return {"available": True, "mode": MODE, "message": NOTICE,
        "baseline_hash": baseline["baseline_hash"], "model": baseline["provider"]["model_id"],
        "candidate_budget": baseline["candidate_budget"], "memory_fixed": True,
        "design_count": len({d for r in rows for d in r["designs"]}),
        "machines": {arm: {"policy_hash": e["policy_hash"], "red_enabled": arm == "adversarial",
            "promotion_count": sum(r["promoted"] for r in rows) if arm == "adversarial" else 0}
            for arm, e in evaluations.items()}, "rounds": rows,
        "metrics": {"工程回归检查（预置答案，非最终测试）": metric},
        "case_results": {"工程回归检查（预置答案，非最终测试）": paired_case_views(evaluations["static"], evaluations["adversarial"])}}
