from copy import deepcopy
from pathlib import Path
import json

import pytest

from competition.services.experience_memory import ExperienceMemory, bank, collect, snapshot
from competition.arena.evidence import freeze, read
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from r3e.arena.manifests import make_manifest, split_for_promotion
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.blue.portfolio.rtl_ast_materializer import materialize_rtl_ast_semantic_patch, RtlAstMaterializationViolation

ROOT = Path(__file__).resolve().parents[2]


def test_supplied_bank_search_runs_without_new_red_but_keeps_roles():
    from competition.arena.isolation import promotion_design_roles
    directory = ROOT / "competition/manifests"
    roles = promotion_design_roles(read(directory / "demo32_red_sources.json"))
    supplied = read(directory / "demo32_repair_bank.json")
    residual = make_manifest([], split="residual")
    _, legacy = split_for_promotion(residual, min_target_designs=2, design_roles=roles, supplied_manifest=supplied)
    assert not legacy["metadata"]["promotion_eligible"]
    practice, exam = split_for_promotion(residual, min_target_designs=2, design_roles=roles,
        supplied_manifest=supplied, allow_supplied_only=True)
    assert exam["metadata"]["promotion_eligible"]
    assert exam["metadata"]["search_trigger"] == "supplied_bank"
    assert exam["metadata"]["generated_residual_case_count"] == 0
    assert {r["design"] for r in practice["rows"]}.isdisjoint(r["design"] for r in exam["rows"])


def test_historical_memory_excludes_final_families_and_reference_rtl():
    value = read(ROOT / "competition/manifests/history_memory.json")
    assert len(value["entries"]) > 0
    assert not ({e["family"] for e in value["entries"]} & {"counter6bit", "flip_flop", "lshift_reg"})
    assert "replacement_rtl" not in json.dumps(value)
    memory = ExperienceMemory(value)
    notes = memory.retrieve({"case_id": "assignment4v:decl7s_1"})
    assert notes and all(n["family"] == "decl7s" for n in notes)
    assert len(notes) <= 6
    assert memory.retrieve({"top_module": "decl7s_test"}) == notes


def test_snapshot_does_not_read_final_results_and_resume_is_immutable(tmp_path):
    first = snapshot(ROOT, tmp_path, "R000", evolving=True, approve=lambda before, after: False)
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval/receipt.json").write_text("not valid JSON")
    assert snapshot(ROOT, tmp_path, "R000", evolving=True) == first
    assert snapshot(ROOT, tmp_path, "T1", evolving=True) == first
    assert snapshot(ROOT, tmp_path, "T0") == first


def test_context_reaches_real_request_and_cache_rejects_changed_memory(tmp_path):
    from tests.competition.test_m3_arena import client
    calls = []
    memory = ExperienceMemory(read(ROOT / "competition/manifests/history_memory.json"))
    provider = PolicyCandidateProvider(client(calls), memory=memory,
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version)
    service = ArenaEvaluationService(ROOT, tmp_path, provider=provider)
    row = read(ROOT / "competition/manifests/demo32_supplied_assets.json")["rows"][0]
    policy = service.repair._policy()
    receipt = service.evaluate_case_cached(policy, row, 1, cache_root=tmp_path / "cache")
    assert receipt["experience_memory_hash"] == memory.memory_hash
    assert any("Historical repair observations" in str(c) for c in calls)
    index = next((tmp_path / "cache").glob("*.json"))
    provider.memory_hash = "changed"
    with pytest.raises(ValueError, match="experience memory"):
        service._validated_cached_receipt(index, policy, row, 1, provider)


def test_macro_edits_cannot_change_global_definitions():
    old = "`define MASK 1\nmodule t(input a, output y); assign y = a & `MASK; endmodule\n"
    with pytest.raises(RtlAstMaterializationViolation, match="directives"):
        materialize_rtl_ast_semantic_patch(buggy_source=old,
            candidate_source=old.replace("MASK 1", "MASK 0"), top_module="t", expected_patch_scope="local_block")


def test_memory_guard_requires_complete_gain_and_zero_losses():
    from competition.arena.evidence import signed
    from competition.services.experience_guard import verify_guard
    def receipt(case, memory, ok):
        return signed({"case_id": case, "seed": 1, "oracle_ok": ok, "policy_hash": "p",
            "case_asset_hash": case, "provider_fingerprint": {}, "budget_hash": "budget",
            "verifier_hash": "verifier", "experience_memory_hash": memory}, "receipt_hash")
    binding = {"case_ids": ["a", "b"], "seeds": [1], "policy_hash": "p",
               "parent_memory_hash": "old", "proposed_memory_hash": "new"}
    pairs = [{"before": receipt("a", "old", False), "after": receipt("a", "new", True)},
             {"before": receipt("b", "old", True), "after": receipt("b", "new", True)}]
    assert verify_guard(signed({"binding": binding, "pairs": pairs, "complete": True, "accepted": True}))
    with pytest.raises(ValueError, match="complete paired"):
        verify_guard(signed({"binding": binding, "pairs": pairs[:1], "complete": True, "accepted": True}))
    pairs[1]["after"] = receipt("b", "new", False)
    with pytest.raises(ValueError, match="complete paired"):
        verify_guard(signed({"binding": binding, "pairs": pairs, "complete": True, "accepted": True}))
