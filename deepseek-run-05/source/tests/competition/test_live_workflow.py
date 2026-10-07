"""Offline contract tests for real-run plumbing; no claim of model performance."""
from dataclasses import replace
from types import SimpleNamespace
import json
import pytest

from test_m3_arena import ROOT, client
from competition.arena.budget import BudgetedClient
from competition.arena.cli import _identity
from competition.arena.runtime import validate_client
from competition.arena.evidence import read
from competition.scripts.run_arena_live import preflight, run
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from r3e.arena.manifests import make_manifest
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier


def test_missing_configuration_never_starts_experiment(tmp_path):
    args = SimpleNamespace(client_config=str(tmp_path / "missing.json"), check=False)
    report = preflight(ROOT, args.client_config)
    assert not report["ready"] and report["network_calls"] == 0
    with pytest.raises(ValueError, match="尚未就绪"):
        run(ROOT, args)
    assert not list(tmp_path.iterdir())


def test_placeholder_template_rejected_without_printing_credentials(monkeypatch):
    monkeypatch.setenv("R3E_PILOT_API_KEY", "secret-marker-do-not-print")
    monkeypatch.setenv("R3E_PILOT_BASE_URL", "https://example.invalid/v1")
    report = preflight(ROOT, ROOT / "competition/configs/live_client.example.json")
    assert not report["checks"]["client_config"]
    assert "secret-marker" not in json.dumps(report)


def test_full_client_settings_are_bound_to_baseline():
    c = client([])
    baseline = {"provider": _identity(c.config)}
    validate_client(c, baseline)
    c.config = replace(c.config, maximum_output_tokens=1024)
    with pytest.raises(ValueError, match="differs"):
        validate_client(c, baseline)


def test_new_baseline_cannot_freeze_zero_rounds_as_complete():
    from test_m3_evidence import arms, resign
    from competition.services.arena_comparison_service import verify_arm
    _, b = arms()
    b["baseline"]["required_adversarial_rounds"] = 5
    b["baseline"] = resign(b["baseline"], "baseline_hash")
    b = resign(b)
    with pytest.raises(ValueError, match="five"):
        verify_arm(b)


def test_total_budget_spans_operations_and_restart(tmp_path):
    from types import SimpleNamespace
    calls = []
    class Transport:
        config = SimpleNamespace(maximum_output_tokens=32)
        _transport = None
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            return {}
    def operation(name):
        local = BudgetedClient(Transport(), tmp_path / (name + ".json"), max_calls=20, max_tokens=100000)
        return BudgetedClient(local, tmp_path / "total.json", max_calls=2, max_tokens=100000)
    operation("R000").complete_json(messages=[])
    operation("R001").complete_json(messages=[])
    with pytest.raises(RuntimeError, match="exhausted"):
        operation("strider-subset4").complete_json(messages=[])
    assert len(calls) == 2
    assert not (tmp_path / "strider-subset4.json").exists()


def test_final_case_resume_checks_raw_receipt_and_no_answer_leak(tmp_path):
    calls = []
    c = client(calls)
    provider = PolicyCandidateProvider(c, verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    service = ArenaEvaluationService(ROOT, tmp_path, provider=provider)
    original = read(ROOT / "competition/manifests/demo32_heldout.json")
    manifest = make_manifest([original["rows"][-1]], split="evaluation", metadata=original["metadata"])
    policy = service.repair._policy()
    first = service.evaluate_policy(policy, manifest, [1, 2, 3])
    count = len(calls)
    assert count == 9
    assert service.evaluate_policy(policy, manifest, [1, 2, 3]) == first
    assert len(calls) == count
    for request in calls:
        prompt = json.loads(request["messages"][1]["content"])
        assert not {"golden_rtl", "reference_rtl", "tb_sources", "fixed_rtl"} & set(prompt)
    receipt = tmp_path / first["cases"][0]["artifact_id"] / "receipt.json"
    altered = read(receipt)
    altered["oracle_ok"] = not altered["oracle_ok"]
    receipt.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="cached receipt"):
        service.evaluate_policy(policy, manifest, [1, 2, 3])
    assert len(calls) == count
