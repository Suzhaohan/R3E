import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from competition.arena.budget import BudgetedClient
from competition.arena.evidence import read
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.adapters.policy_provider import PolicyCandidateProvider
from r3e.arena.manifests import make_manifest
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.providers.openai_compatible import OpenAICompatibleProviderViolation
from resilience import Recovery, connection_failure
from run_resilient import configure_route
from test_m3_arena import client as fixture_client, ROOT


class ConnectError(Exception):
    pass


class ReadTimeout(Exception):
    pass


def test_direct_route_is_scoped_to_api_host_and_preserves_other_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:2080")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    configure_route("https://api.deepseek.com/v1", "direct")
    import os
    from urllib.request import proxy_bypass
    assert proxy_bypass("api.deepseek.com")
    assert not proxy_bypass("example.org")
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:2080"
    assert os.environ["NO_PROXY"] == os.environ["no_proxy"] == "localhost,127.0.0.1,api.deepseek.com"


def test_stdlib_open_connection_ssl_eof_is_retryable_but_read_eof_is_not():
    import ssl
    from urllib.error import URLError
    error = ssl.SSLEOFError("EOF while establishing TLS")
    assert connection_failure(URLError(error))
    assert not connection_failure(error)


def disconnected():
    try:
        raise ConnectError("TLS EOF")
    except ConnectError as cause:
        raise OpenAICompatibleProviderViolation("connection failed") from cause


def budgeted(state, client, operation="R002", max_calls=50):
    inner = BudgetedClient(client, state / "budgets" / f"{operation}.json", max_calls=max_calls, max_tokens=10000000)
    return BudgetedClient(inner, state / "budgets/total.json", max_calls=max_calls, max_tokens=10000000)


def test_connect_failure_recovers_and_identical_invocations_stay_distinct(tmp_path):
    calls = []
    raw = fixture_client([])
    def transport(**request):
        calls.append(request)
        if len(calls) == 2:
            disconnected()
        return {"content": json.dumps({"n": len(calls)}), "input_tokens": 10,
                "output_tokens": 2, "provider_request_id": str(len(calls))}
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    recovery = Recovery(tmp_path, raw.config)
    sleeps = []
    operation = lambda: [client.complete_json(messages=[{"role": "user", "content": "same"}], seed=1) for _ in range(3)]
    result = recovery.run(operation, sleep=sleeps.append)
    assert [r["result"]["n"] for r in result] == [1, 3, 4]
    assert sleeps == [2] and len(calls) == 4
    assert read(tmp_path / "budgets/total.json")["calls"] == 4
    assert read(tmp_path / "budgets/R002.json")["calls"] == 4
    restarted = Recovery(tmp_path, raw.config)
    assert restarted.run(operation) == result
    assert len(calls) == 4


def test_retry_limit_and_budget_count_every_attempt(tmp_path):
    raw = fixture_client([])
    calls = []
    def transport(**request):
        calls.append(request)
        disconnected()
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    recovery = Recovery(tmp_path, raw.config)
    with pytest.raises(RuntimeError, match="连接连续失败"):
        recovery.run(lambda: client.complete_json(messages=[{"role": "user", "content": "JSON"}], seed=1), sleep=lambda n: None)
    assert len(calls) == 5
    assert read(tmp_path / "budgets/total.json")["calls"] == 5


def test_retry_cannot_bypass_total_budget(tmp_path):
    raw = fixture_client([])
    raw._transport = lambda **kw: disconnected()
    client = budgeted(tmp_path, raw, max_calls=1)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        Recovery(tmp_path, raw.config).run(
            lambda: client.complete_json(messages=[{"role": "user", "content": "JSON"}], seed=1), sleep=lambda n: None)
    assert read(tmp_path / "budgets/total.json")["calls"] == 1


@pytest.mark.parametrize("error", [ReadTimeout("ambiguous"), ValueError("bad schema"),
    OpenAICompatibleProviderViolation("ConnectError appears only in text")])
def test_ambiguous_or_content_errors_are_not_retried(tmp_path, error):
    calls = []
    def fail():
        calls.append(1)
        raise error
    with pytest.raises(type(error)):
        Recovery(tmp_path, fixture_client([]).config).run(fail, sleep=lambda n: None)
    assert len(calls) == 1 and not connection_failure(error)


def test_modified_request_or_cached_response_fails_closed(tmp_path):
    raw = fixture_client([])
    raw._transport = lambda **kw: {"content": '{"ok":true}', "input_tokens": 10, "output_tokens": 2, "provider_request_id": "id"}
    client = budgeted(tmp_path, raw)
    Recovery(tmp_path, raw.config).run(lambda: client.complete_json(messages=[{"role": "user", "content": "a"}], seed=1))
    with pytest.raises(ValueError, match="binding changed"):
        Recovery(tmp_path, raw.config).run(lambda: client.complete_json(messages=[{"role": "user", "content": "b"}], seed=1))
    cache = next((tmp_path / "recovery").rglob("requests/000000.json"))
    value = read(cache); value["response"]["result"] = {"forged": True}
    cache.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid result_hash"):
        Recovery(tmp_path, raw.config).run(lambda: client.complete_json(messages=[{"role": "user", "content": "a"}], seed=1))
    assert read(tmp_path / "budgets/total.json")["calls"] == 1


@pytest.mark.parametrize("final", [True, False])
def test_real_eda_mid_case_disconnect_preserves_completed_work(tmp_path, final):
    calls = []
    raw = fixture_client([])
    original_transport = raw._transport
    def transport(**request):
        calls.append(request)
        if len(calls) == 6:  # First pair done; second pair has two paid responses.
            disconnected()
        return original_transport(**request)
    raw._transport = transport
    operation = "red-heldout" if final else "R002"
    client = budgeted(tmp_path, raw, operation)
    provider = PolicyCandidateProvider(client, verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    output = tmp_path / "eval/red-heldout" if final else tmp_path / "replays"
    service = ArenaEvaluationService(ROOT, output, provider=provider)
    manifest = read(ROOT / "competition/manifests/red_heldout_v2.json")
    row = manifest["rows"][-1]
    manifest = make_manifest([row], split="evaluation", metadata=manifest["metadata"])
    policy = service.repair._policy()
    recovery = Recovery(tmp_path, raw.config)
    if final:
        perform = lambda: service.evaluate_policy(policy, manifest, [1, 2])
    else:
        checkpoint = tmp_path / "rounds/R002/round_state.json"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text(json.dumps({"checkpoints": [{"stage": "FREEZE_PROMOTION_MANIFEST", "completed_at": datetime.now(timezone.utc).isoformat()}]}))
        # Identical logical requests in separate replay slots retain distinct
        # outcomes; only the same interrupted invocation is replayed.
        perform = lambda: [service.evaluate_case_with_policy(policy, row, 1) for _ in range(2)]
    result = recovery.run(perform, sleep=lambda n: None)
    assert len(calls) == 7  # Six successes + one failed connection, no duplicate generation.
    assert recovery.stats["reused_responses"] == 2
    if not final:
        assert recovery.stats["reused_cases"] == 1
    before = read(tmp_path / "budgets/total.json")
    assert Recovery(tmp_path, raw.config).run(perform) == result
    assert read(tmp_path / "budgets/total.json") == before
