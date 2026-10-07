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
from resilience import (Recovery, connection_failure, response_failure, error_report,
                        ProviderResponseRecoveryExhausted, RESPONSE_RECOVERY_POLICY,
                        OutputLengthRecoveryExhausted, LENGTH_RECOVERY_POLICY)
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


@pytest.mark.parametrize("content,reason", [
    ('```json\n{"ok":true}\n```', "stop"),
    ('{"replacement_rtl":"private-invalid-\\q"}', "stop"),
    ("", "stop"), (None, "stop"),
])
def test_invalid_response_recovers_same_request_and_replays_paid_work(tmp_path, content, reason):
    calls = []
    raw = fixture_client([])
    def transport(**request):
        calls.append(request)
        return {"content": content if len(calls) == 2 else json.dumps({"n": len(calls)}),
                "finish_reason": reason if len(calls) == 2 else "stop",
                "input_tokens": 10, "output_tokens": 4096 if reason == "length" else 20,
                "provider_request_id": "private-request-id"}
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    recovery = Recovery(tmp_path, raw.config)
    sleeps = []
    perform = lambda: [client.complete_json(messages=[{"role": "user", "content": str(i)}], seed=1)
                       for i in range(3)]
    result = recovery.run(perform, sleep=sleeps.append)
    assert [r["result"]["n"] for r in result] == [1, 3, 4]
    assert calls[1] == calls[2] and sleeps == [2]
    for name in ("total", "R002"):
        assert read(tmp_path / f"budgets/{name}.json")["calls"] == 4
    assert recovery.stats["invalid_responses"] == 1
    assert recovery.stats["reused_responses"] == 1
    events_text = (tmp_path / "recovery/events.jsonl").read_text()
    failure = next(json.loads(line) for line in events_text.splitlines()
                   if json.loads(line)["event"] == "provider_response_failure")
    assert failure["failure"]["diagnostics"]["finish_reason"] == reason
    assert failure["retry_scheduled"] is True
    assert "private-" not in events_text
    assert Recovery(tmp_path, raw.config).run(perform) == result
    assert len(calls) == 4


def test_persistent_invalid_json_stops_with_diagnostics_and_counts_failed_calls(tmp_path):
    raw = fixture_client([])
    calls = []
    def transport(**request):
        calls.append(request)
        return {"content": '{"private-body":"', "finish_reason": "stop",
                "input_tokens": 10, "output_tokens": 4096, "provider_request_id": "private-id"}
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    sleeps = []
    with pytest.raises(ProviderResponseRecoveryExhausted, match="连续返回无效内容") as caught:
        Recovery(tmp_path, raw.config).run(
            lambda: client.complete_json(messages=[{"role": "user", "content": "JSON"}], seed=1),
            sleep=sleeps.append)
    assert len(calls) == 4 and sleeps == [2, 4, 8]
    assert all(call == calls[0] for call in calls)
    assert read(tmp_path / "budgets/total.json")["calls"] == 4
    assert not list((tmp_path / "recovery").rglob("requests/*.json"))
    report = error_report(caught.value)
    assert report["provider_diagnostics"]["finish_reason"] == "stop"
    assert report["response_failure"]["json_error"]["line"] == 1
    assert "private-" not in json.dumps(report)
    events = [json.loads(line) for line in (tmp_path / "recovery/events.jsonl").read_text().splitlines()]
    assert len(events) == 4 and events[-1]["retry_scheduled"] is False


def truncated(request, *, valid_json=False):
    return {"content": '{"ok":true}' if valid_json else '{"private-body":"',
            "finish_reason": "length", "input_tokens": 10,
            "output_tokens": request["max_tokens"], "provider_request_id": "private-id"}


@pytest.mark.parametrize("valid_json", [False, True])
def test_truncation_grows_only_current_request_and_accounts_effective_budget(tmp_path, valid_json):
    raw = fixture_client([])
    original_config = raw.config
    calls = []
    def transport(**request):
        calls.append(request)
        if request["messages"][0]["content"] == "long" and request["max_tokens"] < 16384:
            return truncated(request, valid_json=valid_json)
        return {"content": '{"ok":true}', "finish_reason": "stop", "input_tokens": 10,
                "output_tokens": 5, "provider_request_id": "id"}
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    recovery = Recovery(tmp_path, raw.config)
    def perform():
        return [client.complete_json(messages=[{"role": "user", "content": x}], seed=1)
                for x in ("short", "long", "after")]
    results = recovery.run(perform, sleep=lambda _: pytest.fail("length recovery must not replay the round"))
    assert [c["max_tokens"] for c in calls] == [4096, 4096, 8192, 16384, 4096]
    assert all({k:v for k,v in c.items() if k != "max_tokens"} ==
               {k:v for k,v in calls[1].items() if k != "max_tokens"} for c in calls[1:4])
    expected = sum(len(json.dumps(c["messages"], ensure_ascii=False).encode()) + 1024 + c["max_tokens"]
                   for c in calls)
    for name in ("total", "R002"):
        assert read(tmp_path / f"budgets/{name}.json")["reserved_tokens"] == expected
        assert read(tmp_path / f"budgets/{name}.json")["calls"] == 5
    assert client.config is client.client.config is raw.config is original_config
    assert recovery.stats["truncated_responses"] == 2
    assert recovery.stats["reused_responses"] == 0
    assert Recovery(tmp_path, raw.config).run(perform) == results
    assert len(calls) == 5
    records = [read(p) for p in (tmp_path / "recovery/R002/FINAL_EVALUATION/requests").glob('*.json')]
    assert sorted(r["output_recovery"]["effective_output_tokens"] for r in records) == [4096,4096,16384]
    assert "private-" not in (tmp_path / "recovery/events.jsonl").read_text()


def test_persistent_truncation_stops_at_cap_and_restart_makes_no_paid_call(tmp_path):
    raw = fixture_client([])
    calls = []
    raw._transport = lambda **kw: (calls.append(kw) or truncated(kw))
    client = budgeted(tmp_path, raw)
    perform = lambda: client.complete_json(messages=[{"role":"user", "content":"long"}], seed=1)
    for _ in range(2):
        with pytest.raises(OutputLengthRecoveryExhausted, match="16384") as caught:
            Recovery(tmp_path, raw.config).run(perform)
        assert [c["max_tokens"] for c in calls] == [4096,8192,16384]
    assert error_report(caught.value)["maximum_output_tokens"] == 16384
    assert not list((tmp_path / "recovery/R002/FINAL_EVALUATION/requests").glob('*.json'))
    assert raw.config.maximum_output_tokens == client.config.maximum_output_tokens == 4096


def test_length_escalation_survives_disconnect_and_process_restart(tmp_path):
    raw = fixture_client([])
    calls = []
    def transport(**kw):
        calls.append(kw)
        if len(calls) == 1:
            return truncated(kw)
        if len(calls) == 2:
            raise ReadTimeout("interrupted")
        return {"content": '{"ok":true}', "input_tokens":10, "output_tokens":1, "provider_request_id":"id"}
    raw._transport = transport
    client = budgeted(tmp_path, raw)
    perform = lambda: client.complete_json(messages=[{"role":"user", "content":"long"}], seed=1)
    with pytest.raises(ReadTimeout):
        Recovery(tmp_path, raw.config).run(perform)
    assert raw.config.maximum_output_tokens == 4096
    Recovery(tmp_path, raw.config).run(perform)
    assert [c["max_tokens"] for c in calls] == [4096,8192,8192]


def test_length_escalation_cannot_bypass_token_budget(tmp_path):
    raw = fixture_client([])
    calls = []
    raw._transport = lambda **kw: (calls.append(kw) or truncated(kw))
    client = BudgetedClient(raw, tmp_path/'budgets/R002.json', max_calls=50, max_tokens=10000)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        Recovery(tmp_path, raw.config).run(
            lambda: client.complete_json(messages=[{"role":"user", "content":"long"}], seed=1))
    assert len(calls) == 1
    assert read(client.path)["calls"] == 1
    assert raw.config.maximum_output_tokens == client.config.maximum_output_tokens == 4096


def test_json_retry_cannot_bypass_budget(tmp_path):
    raw = fixture_client([])
    calls = []
    raw._transport = lambda **kw: (calls.append(kw) or {
        "content": "broken", "input_tokens": 10, "output_tokens": 1, "provider_request_id": "id"})
    client = budgeted(tmp_path, raw, max_calls=1)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        Recovery(tmp_path, raw.config).run(
            lambda: client.complete_json(messages=[{"role": "user", "content": "JSON"}], seed=1),
            sleep=lambda n: None)
    assert len(calls) == 1
    assert read(tmp_path / "budgets/total.json")["calls"] == 1


@pytest.mark.parametrize("content,reason,refusal", [
    ("[]", "stop", None),  # Valid JSON, wrong schema is not a retry condition.
    ("broken", "content_filter", None),
    ("broken", "stop", "refused"),
    ("", "stop", "refused"),
])
def test_json_recovery_does_not_retry_schemas_or_refusals(tmp_path, content, reason, refusal):
    raw = fixture_client([])
    calls = []
    raw._transport = lambda **kw: (calls.append(kw) or {
        "content": content, "finish_reason": reason, "refusal": refusal,
        "input_tokens": 10, "output_tokens": 1, "provider_request_id": "id"})
    client = budgeted(tmp_path, raw)
    with pytest.raises(OpenAICompatibleProviderViolation) as caught:
        Recovery(tmp_path, raw.config).run(
            lambda: client.complete_json(messages=[{"role": "user", "content": "JSON"}], seed=1),
            sleep=lambda n: None)
    assert len(calls) == 1 and response_failure(caught.value) is None
    assert "provider_diagnostics" in error_report(caught.value)


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


@pytest.mark.parametrize("phase", ["T0", "T1", "round"])
@pytest.mark.parametrize("failure_mode", ["connection", "json"])
def test_real_eda_mid_case_disconnect_preserves_completed_work(tmp_path, phase, failure_mode):
    final = phase != "round"
    tmp_path = tmp_path / "arm-b"
    calls = []
    raw = fixture_client([])
    original_transport = raw._transport
    def transport(**request):
        calls.append(request)
        if len(calls) == 6:  # First pair done; second pair has two paid responses.
            if failure_mode == "json":
                return {"content": "invalid JSON", "finish_reason": "stop",
                        "input_tokens": 10, "output_tokens": 2, "provider_request_id": "bad"}
            disconnected()
        return original_transport(**request)
    raw._transport = transport
    operation = "T0-red-heldout" if phase == "T0" else "red-heldout" if final else "R002"
    client = budgeted(tmp_path, raw, operation)
    provider = PolicyCandidateProvider(client, verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    output = (tmp_path.parent / "baseline-evaluations/adversarial/red-heldout" if phase == "T0"
              else tmp_path / "eval/red-heldout" if final else tmp_path / "replays")
    service = ArenaEvaluationService(ROOT, output, provider=provider)
    manifest = read(ROOT / "competition/manifests/demo32_heldout.json")
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
        # Current Core reuses the same policy/case/seed per round.
        # Different repetitions retain separate response slots.
        perform = lambda: [service.evaluate_case_with_policy(policy, row, seed) for seed in (1, 2)]
    result = recovery.run(perform, sleep=lambda n: None)
    assert len(calls) == 7  # Six successes + one failed connection, no duplicate generation.
    assert recovery.stats["reused_responses"] == (2 if failure_mode == 'connection' else 0)
    if not final and failure_mode == 'connection':
        assert recovery.stats["reused_cases"] == 1
    before = read(tmp_path / "budgets/total.json")
    assert Recovery(tmp_path, raw.config).run(perform) == result
    assert read(tmp_path / "budgets/total.json") == before


def test_current_launcher_T0_records_overlay_without_changing_baseline(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from test_m3_arena import setup_arm
    from competition.arena.evidence import freeze
    from r3e.protocol.hashing import hash_file
    import run_resilient as launcher
    _, baseline, state = setup_arm(tmp_path, "static")
    c = fixture_client([])
    monkeypatch.setattr(launcher, "_client", lambda path: c)
    monkeypatch.setattr(launcher, "preflight", lambda *args: {"ready": True})
    monkeypatch.setenv(c.config.base_url_env, "https://api.deepseek.com")
    monkeypatch.setenv("R3E_NETWORK_ROUTE", "direct")
    original_baseline_hash = hash_file(state / "baseline.json")
    attempts = []
    def perform(root, args, progress=print):
        attempts.append(args.baseline_only)
        directory = state.parent / "baseline-evaluations/static"
        for dataset in baseline["evaluation_manifests"]:
            freeze(directory / (dataset + ".json"), {"fixture": dataset})
        return {"phase": "T0", "baseline_complete": True}
    monkeypatch.setattr(launcher, "_original_run", perform)
    args = SimpleNamespace(check=False, client_config="unused", baseline=str(state / "baseline.json"),
        state_root=str(state), arm="static", baseline_only=True, max_calls=2000, max_tokens=50000000)
    result = launcher.resilient_run(ROOT, args)
    assert result["baseline_complete"] and attempts == [True]
    assert hash_file(state / "baseline.json") == original_baseline_hash
    assert not (state / "frozen_arm.json").exists()
    assert (state / "recovery/completion_T0.json").exists()
    assert not (state / "recovery/completion_T1.json").exists()
    from competition.arena.evidence import verify_signed
    policy = verify_signed(read(state / "recovery/response_recovery_policy.json"))
    assert {k: v for k, v in policy.items() if k != "result_hash"} == RESPONSE_RECOVERY_POLICY
    assert read(state / "recovery/completion_T0.json")["response_recovery_policy_hash"] == policy["result_hash"]


def test_completed_core_replays_do_not_shift_remaining_response_slots(tmp_path):
    state = tmp_path / "arm-b"
    raw = fixture_client([])
    calls = []
    transport = raw._transport
    def fail_once(**request):
        calls.append(request)
        if len(calls) == 6:
            disconnected()
        return transport(**request)
    raw._transport = fail_once
    provider = PolicyCandidateProvider(budgeted(state, raw, "R000"),
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
    service = ArenaEvaluationService(ROOT, state / "replays", provider=provider)
    row = read(ROOT / "competition/manifests/demo32_red_sources.json")["rows"][0]
    policy = service.repair._policy()
    checkpoint = state / "rounds/R000/round_state.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps({"checkpoints": [{"stage": "SCREEN_CHILDREN",
        "completed_at": datetime.now(timezone.utc).isoformat()}]}))
    def perform():
        return [service.evaluate_case_cached(policy, row, seed,
            cache_root=state / "rounds/R000/replay_cache") for seed in (1, 2)]
    recovery = Recovery(state, raw.config)
    result = recovery.run(perform, sleep=lambda seconds: None)
    assert len(calls) == 7 and recovery.stats["reused_responses"] == 2
    assert Recovery(state, raw.config).run(perform) == result
    assert len(calls) == 7


def red_fixture(tmp_path):
    from types import SimpleNamespace
    from competition.arena.evidence import signed
    calls = []
    raw = fixture_client([])
    raw._transport = lambda **kw: (calls.append(kw) or {
        "content": '{"ok":true}', "input_tokens": 10, "output_tokens": 2,
        "provider_request_id": "red-id"})
    adapter = SimpleNamespace(client=budgeted(tmp_path, raw), _round_id="R002-intent",
                              _cases=[{"case_id": "example"}])
    parent = SimpleNamespace(policy_hash="policy")
    artifact = tmp_path / "poison.v"
    artifact.write_text("module m; endmodule\n")
    elapsed = [1200]
    def generate(adapter, parent, config, context):
        response = adapter.client.complete_json(messages=[{"role": "user", "content": "red"}], seed=17)
        choice = signed({"wall_time_ms": elapsed[0], "response": response}, "choice_hash")
        return [signed({"poison_id": "R002-intent:example:grd", "buggy_rtl": str(artifact),
                        "grounded_choice_receipt": choice, "family": "original",
                        "grounded_generation_usage": {"wall_time_ms": elapsed[0]}})]
    return raw, adapter, parent, artifact, elapsed, generate, calls


@pytest.mark.parametrize("legacy_index", [False, True])
def test_red_restart_preserves_original_receipt_and_request_slots(tmp_path, legacy_index):
    from competition.arena.evidence import signed, freeze
    from r3e.protocol.hashing import hash_file
    raw, adapter, parent, artifact, elapsed, generate, calls = red_fixture(tmp_path)
    first = Recovery(tmp_path, raw.config)
    if legacy_index:
        # Old overlay cached responses and indexed the row, but no Red cache.
        rows = first.run(lambda: generate(adapter, parent, {}, {}))
        freeze(tmp_path / "generated_cases.json", signed({"cases": {
            rows[0]["poison_id"]: {**rows[0], "generated_poison_sha256": hash_file(artifact)}}}))
    else:
        # Interrupt before the aggregate index is written (a later target fails).
        rows = first.run(lambda: first.generate_red(generate, adapter, parent, {}, {}))
    elapsed[0] = 0
    restarted = Recovery(tmp_path, raw.config)
    def perform():
        result = restarted.generate_red(generate, adapter, parent, {}, {})
        followup = adapter.client.complete_json(messages=[{"role": "user", "content": "next"}], seed=17)
        return result, followup
    recovered, _ = restarted.run(perform)
    assert recovered == rows
    assert recovered[0]["grounded_generation_usage"]["wall_time_ms"] == 1200
    assert restarted.stats["reused_red_generations"] == 1
    assert len(calls) == 2  # Original Red + distinct next request, no resampling.
    assert len(list((tmp_path / "recovery").rglob("requests/*.json"))) == 2


@pytest.mark.parametrize("change", ["artifact", "row", "response", "missing_response", "binding"])
def test_red_recovery_rejects_changes_without_new_calls(tmp_path, change):
    from competition.arena.evidence import signed
    raw, adapter, parent, artifact, elapsed, generate, calls = red_fixture(tmp_path)
    first = Recovery(tmp_path, raw.config)
    first.run(lambda: first.generate_red(generate, adapter, parent, {}, {}))
    request = next((tmp_path / "recovery").rglob("requests/000000.json"))
    original = generate
    context = {}
    if change == "artifact":
        artifact.write_text("tampered")
    elif change == "row":
        def generate(*args):
            row = original(*args)[0]
            row["family"] = "changed"
            return [signed({k: v for k, v in row.items() if k != "result_hash"})]
    elif change == "response":
        value = read(request)
        value["response"]["result"] = {"changed": True}
        request.write_text(json.dumps(value))
    elif change == "missing_response":
        request.unlink()
    else:
        context = {"changed": True}
    restarted = Recovery(tmp_path, raw.config)
    with pytest.raises(ValueError):
        restarted.run(lambda: restarted.generate_red(generate, adapter, parent, {}, context))
    assert len(calls) == 1


def test_overlay_revision_preserves_old_manifest_and_experiment_binding(tmp_path):
    from competition.arena.evidence import signed, verify_signed
    from run_resilient import record_recovery_manifest
    original = signed({"files": {"resilience.py": "old"}, "baseline_hash": "sealed"})
    updated = signed({"files": {"resilience.py": "new"}, "baseline_hash": "sealed"})
    record_recovery_manifest(tmp_path, original)
    record_recovery_manifest(tmp_path, updated)
    record_recovery_manifest(tmp_path, updated)
    assert read(tmp_path / "manifest.json") == original
    revisions = list((tmp_path / "manifest_revisions").glob("*.json"))
    assert len(revisions) == 1
    assert verify_signed(read(revisions[0]))["manifest"] == updated
    with pytest.raises(ValueError, match="binding changed"):
        record_recovery_manifest(tmp_path, signed({"files": {}, "baseline_hash": "changed"}))
