"""Test observable requirements, not just successful execution of the pipeline."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_m3_arena import ROOT, client, setup_arm
from competition.arena.evidence import read, signed
from competition.arena.isolation import promotion_design_roles
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.adapters.competition_evolution_adapter import CompetitionEvolutionAdapter
from competition.services.arena_evaluation_service import ArenaEvaluationService
from r3e.arena.manifests import make_manifest, split_for_promotion
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier, public_case_from_manifest
from r3e.blue.portfolio.runtime_evidence import build_runtime_evidence, verify_runtime_evidence
from r3e.memory.schema import FailureDescriptor
from r3e.protocol.hashing import hash_payload


def provider(calls):
    return PolicyCandidateProvider(client(calls), verifier_id=PublicManifestOracleVerifier.verifier_id,
                                   verifier_version=PublicManifestOracleVerifier.verifier_version)


def test_selected_supplied_versions_have_an_actual_role():
    bank = read(ROOT / "competition/manifests/demo18_repair_bank.json")
    assert bank["row_count"] == 10
    qualifications = read(ROOT / "competition/manifests/demo18_qualification.json")
    assert len(qualifications["rows"]) == 10 and all(r["qualified"] for r in qualifications["rows"])
    roles = promotion_design_roles(read(ROOT / "competition/manifests/demo18_red_sources.json"))
    practice, exam = split_for_promotion(make_manifest([], split="residual"), min_target_designs=2,
                                        design_roles=roles, supplied_manifest=bank)
    assert practice["row_count"] + exam["row_count"] == 10
    assert {r["case_id"] for r in practice["rows"] + exam["rows"]} == {r["case_id"] for r in bank["rows"]}
    assert {r["design"] for r in practice["rows"]}.isdisjoint(r["design"] for r in exam["rows"])
    assert exam["metadata"]["provided_cases_are_not_claimed_as_red_discoveries"]
    assert exam["metadata"]["generated_residual_case_count"] == 0
    assert not exam["metadata"]["promotion_eligible"]
    assert exam["metadata"]["defer_reason"] == "no_admitted_red_failure"


def test_real_model_requests_contain_values_and_k_changes_observations(tmp_path):
    calls = []
    service = ArenaEvaluationService(ROOT, tmp_path, provider=provider(calls))
    policy = service.repair._policy()
    row = next(r for r in read(ROOT / "competition/manifests/demo18_red_sources.json")["rows"]
               if r["case_id"] == "assignment4v:mux21_1")
    evidence = {}
    for mode, k in (("raw", 1), ("raw", 6), ("hybrid", 6)):
        current = policy.with_updates(configuration={**policy.configuration, "evidence_mode": mode, "evidence_k": k})
        before = len(calls)
        receipt = service.evaluate_case_with_policy(current, row, 1)
        assert len(calls) - before == 3
        for request in calls[before:]:
            prompt = json.loads(request["messages"][1]["content"])
            assert not {"golden_rtl", "reference_rtl", "tb_sources", "fixed_rtl"} & prompt.keys()
            observed = prompt["current_failure_evidence"]["runtime_observations"]
            assert "@cycle" in observed["raw_mismatches"]
            evidence[(mode, k)] = observed
        raw = read(tmp_path / receipt["artifact_id"] / "evaluation.json")
        assert raw["runtime_evidence"]["descriptor"]["cycle_offset_bucket"] == 0
    assert len(evidence[("raw", 6)]["raw_mismatches"]) > len(evidence[("raw", 1)]["raw_mismatches"])
    assert "structured_diagnosis" not in evidence[("raw", 6)]
    assert "实得" in evidence[("hybrid", 6)]["structured_diagnosis"]
    assert "应为" in evidence[("hybrid", 6)]["structured_diagnosis"]


def test_challenge_and_replay_use_same_observations_despite_old_labels(tmp_path):
    row = next(r for r in read(ROOT / "competition/manifests/demo18_supplied_assets.json")["rows"]
               if r["case_id"] == "assignment4v:JG3_1")
    case = public_case_from_manifest(row, project_root=ROOT)
    old = FailureDescriptor.create({"sequential_context": True,
        "observable_artifact_hashes": {"old": hash_payload("old")}}).to_dict()
    other = FailureDescriptor.create({"sequential_context": False,
        "observable_artifact_hashes": {"old": hash_payload("other")}}).to_dict()
    a = build_runtime_evidence(case, project_root=ROOT, source_descriptor=old)
    b = build_runtime_evidence(case, project_root=ROOT, source_descriptor=other)
    assert a["descriptor"] == b["descriptor"]
    assert a["observations"] == b["observations"]
    assert a["descriptor"]["sequential_context"] is False
    assert a["descriptor"]["cycle_offset_bucket"] == 0
    forged = deepcopy(a)
    forged["observations"]["raw_by_k"]["1"] = "invented output"
    forged["context_hash"] = hash_payload({k: v for k, v in forged.items() if k != "context_hash"})
    with pytest.raises(ValueError, match="reconstructed|binding"):
        verify_runtime_evidence(forged, source_descriptor=old)


def test_teacher_really_covers_raw_alternative_too(tmp_path):
    service = ArenaEvaluationService(ROOT, tmp_path, provider=provider([]))
    adapter = object.__new__(CompetitionEvolutionAdapter)
    adapter.seeds = (1, 2, 3)
    adapter.toolchain_fingerprint = service.provider.toolchain_fingerprint
    attempted = []
    def replay(policy, row, seed):
        combination = (policy.configuration["evidence_mode"], policy.configuration["evidence_k"])
        attempted.append(combination)
        return {"oracle_ok": combination == ("raw", 6), "resource_usage": {"provider_calls": 3}}
    adapter.replay = replay
    result = adapter.probe_learnability(service.repair._policy(), {})
    assert set(attempted) == {(mode, k) for mode in ("raw", "hybrid") for k in (1, 3, 6)}
    assert result["label"] == "reachable" and result["attempts"] == 6


def test_T0_stays_outside_evolution_and_does_not_seal_final(tmp_path, monkeypatch):
    from competition.arena import cli
    _, baseline, state = setup_arm(tmp_path)
    c = client([])
    monkeypatch.setattr(c, "readiness", lambda: {"ready": True})
    monkeypatch.setattr(cli, "_client", lambda path: c)
    observed = []
    def evaluate(service, policy, manifest, seeds, *, runtime):
        observed.append(service.output)
        assert policy.policy_hash == baseline["initial_policy_hash"]
        return signed({"repaired": 0, "denominator": len(manifest["rows"]) * len(seeds), "repair_rate": 0})
    monkeypatch.setattr(ArenaEvaluationService, "evaluate_policy", evaluate)
    result = cli.main(["arena-eval", "--state-root", str(state), "--client-config", "unused",
        "--dataset", "strider-subset4", "--phase", "T0", "--max-calls", "1", "--max-tokens", "100"], ROOT)
    assert Path(result["output"]).parent == state.parent / "baseline-evaluations/adversarial"
    assert state not in observed[0].parents
    assert not (state / "final_evaluation_started.json").exists()


def test_full_supplied_bank_round_and_resume(tmp_path):
    from competition.arena.runtime import build_arena_service
    from r3e.arena.audit import verify_frozen_round
    config, baseline, state = setup_arm(tmp_path)
    calls = []
    c = client(calls)
    evolve = read(ROOT / "competition/manifests/demo18_red_sources.json")
    regression = read(ROOT / "competition/manifests/guard_regression.json")
    service, cfg = build_arena_service(ROOT, state, config, "R000", c, evolve, regression)
    summary = service.run_round("R000", cfg, evolution_manifest=evolve, regression_manifest=regression)
    assert verify_frozen_round(state / "rounds/R000")["audit_record_hash"] == summary["audit_record_hash"]
    count = len(calls)
    assert count > 0
    resumed, cfg = build_arena_service(ROOT, state, config, "R000", c, evolve, regression)
    assert resumed.resume_round("R000", cfg, evolution_manifest=evolve, regression_manifest=regression) == summary
    assert len(calls) == count
    assert service.active_policy().policy_hash == summary["active_policy_hash"]


def test_freeze_requires_T0_for_both_datasets_and_initial_policy():
    from test_m3_evidence import arms, resign
    from competition.services.arena_comparison_service import verify_arm
    arm, _ = arms()
    arm["live_plan"] = signed({"arm": "static", "round_ids": [], "evaluation_phases": ["T0", "T1"],
        "baseline_hash": arm["baseline"]["baseline_hash"], "max_calls": 10, "max_tokens": 1000})
    arm["provider_budget"] = {"max_calls": 10, "max_tokens": 1000, "calls": 0, "reserved_tokens": 0}
    with pytest.raises(ValueError, match="T0 baseline"):
        verify_arm(resign(arm))
    arm["baseline_evaluations"] = deepcopy(arm["evaluations"])
    verify_arm(resign(arm))
    evaluation = arm["baseline_evaluations"]["red-heldout"]
    evaluation["policy_hash"] = "different_initial_policy"
    for row in evaluation["cases"]:
        row["policy_hash"] = evaluation["policy_hash"]
    evaluation["cases"] = [resign(row, "receipt_hash") for row in evaluation["cases"]]
    arm["baseline_evaluations"]["red-heldout"] = resign(evaluation)
    with pytest.raises(ValueError, match="T0 differs"):
        verify_arm(resign(arm))


def test_selected_final_cases_have_usable_candidate_sources():
    from r3e.red.grounded.verilog_ast import tokenize_verilog
    from competition.arena.isolation import verify_evaluation_manifest
    manifests = [read(ROOT / f"competition/manifests/{name}.json")
                 for name in ("demo18_heldout", "demo18_strider")]
    assert sum(m["row_count"] for m in manifests) == 6
    for manifest in manifests:
        verify_evaluation_manifest(manifest, ROOT)
        for row in manifest["rows"]:
            tokenize_verilog((ROOT / row["buggy_rtl"]).read_text())
            tokenize_verilog((ROOT / row["golden_rtl"]).read_text())
