"""Malformed live-model JSON must be diagnosable and retries stay bounded."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from competition.arena.budget import BudgetedClient
from r3e.protocol.hashing import hash_payload
from r3e.providers.openai_compatible import OpenAICompatibleClientConfig, OpenAICompatibleJSONClient
from r3e.red.grounded.openai_provider import OpenAICompatibleGroundedChoiceProvider, RealGroundedPlannerViolation

ROOT = Path(__file__).resolve().parents[2]
VALID = {"target_module": "design", "node_ordinal": 7, "rationale": "select comparator"}


def setup_choice(tmp_path, results, *, max_calls=10):
    calls = []
    def transport(**request):
        calls.append(request)
        return {"content": json.dumps(results[len(calls) - 1]),
                "input_tokens": 100, "output_tokens": 20,
                "provider_request_id": f"fixture-{len(calls)}"}
    cfg = OpenAICompatibleClientConfig.from_dict(json.loads(
        (ROOT / "competition/configs/deepseek_flash.example.json").read_text()))
    client = BudgetedClient(OpenAICompatibleJSONClient(cfg, transport=transport, environ={}),
                            tmp_path / "budget.json", max_calls=max_calls, max_tokens=100000)
    provider = OpenAICompatibleGroundedChoiceProvider(client)
    policy = SimpleNamespace(policy_hash="policy", effective_policy_hash="effective")
    intent = {"intent_id": "intent", "intent_hash": "intent-hash",
              "challenged_policy_hash": "policy", "challenged_effective_policy_hash": "effective",
              "family_id": "family", "operator_id": "operator", "expected_runtime_effect_id": "effect",
              "difficulty_target": {}, "target_role": "comparator"}
    assignment = {"assignment_id": "assignment", "assignment_hash": "assignment-hash",
                  "intent_id": "intent", "intent_hash": "intent-hash", "challenged_policy_hash": "policy",
                  "model_id": cfg.model_id, "toolchain_fingerprint_hash": provider.toolchain_fingerprint_hash,
                  "input_token_budget": 2048, "output_token_budget": 4096,
                  "wall_time_budget_ms": 10000, "budget_hash": "budget"}
    node = SimpleNamespace(ordinal=7, node_hash="node", node_kind="comparison", old_text="<", metadata={})
    kwargs = dict(policy=policy, intent=intent, assignment=assignment, clean_source="private golden RTL",
                  target_module="design", nodes=[node], seed=17, response_dir=tmp_path / "responses")
    return provider, kwargs, calls


@pytest.mark.parametrize("bad", [
    {**VALID, "node_hash": "node"},
    {"target_module": "design", "node_ordinal": 7},
    {"result": VALID},
])
def test_format_correction_is_logged_and_all_calls_are_charged(tmp_path, bad):
    provider, kwargs, calls = setup_choice(tmp_path, [bad, VALID])
    receipt = provider.choose_target(**kwargs)
    assert len(calls) == 2
    assert receipt["selected_node_ordinal"] == 7
    assert receipt["input_tokens"] == 200 and receipt["output_tokens"] == 40
    assert len(receipt["provider_attempts"]) == 2
    assert json.loads((tmp_path / "budget.json").read_text())["calls"] == 2
    records = [json.loads(p.read_text()) for p in (tmp_path / "responses").glob("*.json")]
    assert len(records) == 2
    assert {r["record_hash"] for r in records} == {r["record_hash"] for r in receipt["provider_attempts"]}
    assert next(r for r in records if r["attempt"] == 1)["response"]["result"] == bad
    for record in records:
        assert record["record_hash"] == hash_payload({k: v for k, v in record.items() if k != "record_hash"})
    assert "private golden RTL" not in json.dumps(calls)
    assert "thinking" in calls[0] and "seed" not in calls[0]


def test_valid_output_needs_one_call(tmp_path):
    provider, kwargs, calls = setup_choice(tmp_path, [VALID])
    assert provider.choose_target(**kwargs)["selected_node_hash"] == "node"
    assert len(calls) == 1


def test_repeated_bad_fields_stop_with_actionable_diagnostics(tmp_path):
    provider, kwargs, calls = setup_choice(tmp_path, [{"unexpected": True}] * 2)
    with pytest.raises(RealGroundedPlannerViolation, match="fields mismatch after 2") as error:
        provider.choose_target(**kwargs)
    assert '"missing"' in str(error.value) and '"extra":["unexpected"]' in str(error.value)
    assert str(tmp_path / "responses") in str(error.value)
    assert len(calls) == 2 and len(list((tmp_path / "responses").glob("*.json"))) == 2


@pytest.mark.parametrize("field,value,message", [
    ("node_ordinal", 99, "outside parser authority"),
    ("node_ordinal", True, "is invalid"),
    ("node_ordinal", "7", "is invalid"),
    ("target_module", "other", "is invalid"),
    ("rationale", "", "is invalid"),
])
def test_format_retry_does_not_relax_target_authority(tmp_path, field, value, message):
    provider, kwargs, calls = setup_choice(tmp_path, [{**VALID, field: value}])
    with pytest.raises(RealGroundedPlannerViolation, match=message):
        provider.choose_target(**kwargs)
    assert len(calls) == 1
    assert len(list((tmp_path / "responses").glob("*.json"))) == 1


def test_cumulative_assignment_budget_includes_rejected_response(tmp_path):
    provider, kwargs, calls = setup_choice(tmp_path, [{}, VALID])
    kwargs["assignment"]["input_token_budget"] = 150
    with pytest.raises(RealGroundedPlannerViolation, match="scheduled budget: input_tokens"):
        provider.choose_target(**kwargs)
    assert len(calls) == 2


def test_no_retry_when_assignment_budget_is_used_up(tmp_path):
    provider, kwargs, calls = setup_choice(tmp_path, [{}])
    kwargs["assignment"]["input_token_budget"] = 100
    with pytest.raises(RealGroundedPlannerViolation, match="after 1 attempt"):
        provider.choose_target(**kwargs)
    assert len(calls) == 1


def test_global_budget_can_prevent_retry(tmp_path):
    provider, kwargs, calls = setup_choice(tmp_path, [{}], max_calls=1)
    with pytest.raises(RuntimeError, match="explicit provider budget exhausted"):
        provider.choose_target(**kwargs)
    assert len(calls) == 1
