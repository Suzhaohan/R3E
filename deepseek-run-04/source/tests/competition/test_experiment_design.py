"""Regression tests for the current experiment's design, without network calls."""
from itertools import product
import json

import pytest

from test_m3_arena import ROOT, client
from competition.arena.evidence import read
from competition.arena.isolation import promotion_design_roles
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from r3e.arena.manifests import make_manifest, split_for_promotion, ManifestViolation
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.policy.search import propose_children


def test_generated_variants_are_separate_questions_but_one_design(tmp_path):
    from r3e.arena.paired_replay import paired_replay
    from r3e.policy.promotion import _paired, _verify_rows_against_manifests, decide_policy_promotion, PromotionViolation
    parent = ArenaEvaluationService(ROOT, tmp_path).repair._policy()
    practice = make_manifest([{"case_id": "practice", "design": "practice"}], split="adaptation")
    child = propose_children(parent, practice, read(ROOT / "competition/configs/arena/policy_search_space_v1.json"), round_id="R000")[0]
    target = make_manifest([{"case_id": "original", "poison_id": p, "design": "one-design"}
                            for p in ("bug-a", "bug-b")], split="target")
    regression = make_manifest([{"case_id": "regression", "design": "regression"}], split="non_target")
    def evaluate(policy, case, seed):
        return {"policy_hash": policy.policy_hash, "oracle_ok": policy == child or case["case_id"] == "regression",
                "model_id": "fixture", "budget_hash": "same", "verifier_hash": "same", "cost": 1}
    rows = paired_replay(parent, child, target_manifest=target, non_target_manifest=regression, seeds=[1], evaluator=evaluate)
    assert len(_paired(rows)["target"]) == 2
    _verify_rows_against_manifests(rows, target, regression)
    decision = decide_policy_promotion(parent, child, rows, validation_manifest_hash="fixture")
    assert decision["target"]["total"] == 2
    assert decision["prior_failure_recovery"] == 2
    assert decision["covered_designs"] == ["one-design"]
    assert not decision["checks"]["covered_designs"]
    with pytest.raises(PromotionViolation, match="cover the frozen target"):
        _verify_rows_against_manifests([r for r in rows if r.get("poison_id") != "bug-b"], target, regression)
    with pytest.raises(PromotionViolation, match="duplicate paired"):
        _paired(rows + [rows[0]])


def test_current_entry_status_and_help_do_not_start_a_run(tmp_path, capsys):
    from competition.scripts.run_current import main
    root = tmp_path / "source"
    root.mkdir()
    assert main(["status"], root=root) == 0
    assert json.loads(capsys.readouterr().out) == {"a": {"initialized": False}, "b": {"initialized": False}}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source"]
    with pytest.raises(SystemExit) as exc:
        main(["b"], root=root)
    assert exc.value.code == 2


def test_current_entry_uses_only_current_run_paths(tmp_path, monkeypatch, capsys):
    from competition.scripts import run_current
    root = tmp_path / "source"
    root.mkdir()
    called = []
    def fake_run(actual_root, args):
        called.append(args)
        assert actual_root == root
        assert args.client_config == str(tmp_path / "client.json")
        assert args.baseline == str(tmp_path / "baseline.json")
        assert args.state_root == str(tmp_path / "arm-b")
        assert args.arm == "adversarial"
        assert (args.max_calls, args.max_tokens) == (123, 456)
        return {"ok": True}
    monkeypatch.setattr(run_current, "run", fake_run)
    assert run_current.main(["b", "--max-calls", "123", "--max-tokens", "456"], root=root) == 0
    assert len(called) == 1


def test_preflight_rejects_bad_data_before_any_paid_call(tmp_path, monkeypatch):
    from competition.scripts import run_arena_live
    monkeypatch.setattr(run_arena_live, "portable_toolchain", lambda: {"fake": {"available": True}})
    monkeypatch.setattr(run_arena_live, "source_identity", lambda root: {"git_commit": "frozen", "dirty": False})
    report = run_arena_live.preflight(tmp_path, tmp_path / "missing-client.json")
    assert report["network_calls"] == 0
    assert not report["checks"]["dataset_separation"]
    assert not report["ready"]


def test_all_five_alternatives_including_teacher_combinations_are_testable(tmp_path):
    service = ArenaEvaluationService(ROOT, tmp_path)
    base = service.repair._policy()
    space = read(ROOT / "competition/configs/arena/policy_search_space_v1.json")
    adaptation = make_manifest([{"case_id": "practice", "design": "practice"}], split="adaptation")
    combinations = set(product(("raw", "hybrid"), (1, 3, 6)))
    for mode, depth in combinations:
        parent = base.with_updates(configuration={**base.configuration, "evidence_mode": mode, "evidence_k": depth})
        children = propose_children(parent, adaptation, space, round_id="R000", seed=5)
        assert len(children) == 5
        assert {(c.configuration["evidence_mode"], c.configuration["evidence_k"]) for c in children} == combinations - {(mode, depth)}
        assert all(c.budgets == parent.budgets and c.configuration["n_candidates"] == 3 for c in children)


def test_practice_designs_never_become_exam_when_residual_pool_grows():
    evolve = read(ROOT / "competition/manifests/demo32_red_sources.json")
    roles = promotion_design_roles(evolve)
    assert list(roles.values()).count("adaptation") == 2
    assert list(roles.values()).count("target") == 3
    for count in range(1, len(evolve["rows"]) + 1):
        source = make_manifest(evolve["rows"][:count], split="residual")
        practice, exam = split_for_promotion(source, min_target_designs=2, design_roles=roles)
        assert all(roles[row["design"]] == "adaptation" for row in practice["rows"])
        assert all(roles[row["design"]] == "target" for row in exam["rows"])
        assert practice["row_count"] + exam["row_count"] == source["row_count"]
        if exam["metadata"]["promotion_eligible"]:
            assert len({r["design"] for r in practice["rows"]}) >= 1
            assert len({r["design"] for r in exam["rows"]}) >= 2


def test_three_designs_on_wrong_side_do_not_start_an_impossible_exam():
    roles = {"a": "adaptation", "b": "adaptation", "c": "adaptation", "d": "target", "e": "target"}
    source = make_manifest([{"case_id": d, "design": d} for d in "abc"], split="residual")
    _, exam = split_for_promotion(source, min_target_designs=2, design_roles=roles)
    assert not exam["metadata"]["promotion_eligible"]
    assert exam["metadata"]["design_allocation"]["missing_target_designs"] == 2
    source = make_manifest([{"case_id": "unknown", "design": "unknown"}], split="residual")
    with pytest.raises(ManifestViolation, match="frozen design roles"):
        split_for_promotion(source, min_target_designs=2, design_roles=roles)


def test_round_replay_reuses_verified_receipts_but_new_round_remeasures(tmp_path):
    calls = []
    provider = PolicyCandidateProvider(client(calls), verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    service = ArenaEvaluationService(ROOT, tmp_path / "replays", provider=provider)
    row = read(ROOT / "competition/manifests/demo32_red_sources.json")["rows"][-1]
    parent = service.repair._policy()
    cache = tmp_path / "R000/cache"
    first = service.evaluate_case_cached(parent, row, 1, cache_root=cache)
    assert len(calls) == 3
    restarted = ArenaEvaluationService(ROOT, tmp_path / "replays", provider=provider)
    assert restarted.evaluate_case_cached(parent, row, 1, cache_root=cache) == first
    assert len(calls) == 3
    restarted.evaluate_case_cached(parent, row, 2, cache_root=cache)
    assert len(calls) == 6
    restarted.evaluate_case_cached(parent, row, 1, cache_root=tmp_path / "R001/cache")
    assert len(calls) == 9
    receipt_path = service.output / first["artifact_id"] / "receipt.json"
    altered = read(receipt_path)
    altered["oracle_ok"] = not altered["oracle_ok"]
    receipt_path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="cached receipt"):
        restarted.evaluate_case_cached(parent, row, 1, cache_root=cache)
    assert len(calls) == 9
