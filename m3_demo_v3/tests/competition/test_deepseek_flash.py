"""DeepSeek wire compatibility and truthful sampling metadata; no network."""
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from competition.arena.cli import _identity
from competition.arena.evidence import freeze
from competition.scripts import run_arena_live
from competition.scripts.probe_live_client import probe
from competition.services.arena_comparison_service import compare_arms
from competition.services.arena_telemetry_service import ArenaTelemetryService
from r3e.protocol.hashing import hash_payload
from r3e.providers import openai_compatible as provider

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "competition/configs/deepseek_flash.example.json"


def config():
    return provider.OpenAICompatibleClientConfig.from_dict(json.loads(CONFIG.read_text()))


def test_profile_binds_wire_settings_without_changing_old_config_hashes():
    cfg = config()
    legacy = replace(cfg, request_profile="openai-compatible", require_seed=True)
    assert "request_profile" not in legacy.public_identity
    assert cfg.config_hash != legacy.config_hash
    assert cfg.config_hash == hash_payload(cfg.public_identity)
    identity = _identity(cfg)
    assert identity["provider_seed_sent"] is False
    assert identity["model_version_pinned"] is False
    assert "不能声称" in identity["sampling_note"]


@pytest.mark.parametrize("field,value", [
    ("require_seed", True), ("model_id", "deepseek-chat"),
    ("temperature", 1), ("request_profile", "unknown"),
])
def test_invalid_profile_is_rejected(field, value):
    raw = json.loads(CONFIG.read_text())
    raw[field] = value
    with pytest.raises(provider.OpenAICompatibleProviderViolation):
        provider.OpenAICompatibleClientConfig.from_dict(raw)


@pytest.mark.parametrize("use_sdk", [True, False])
def test_both_transports_disable_thinking_and_omit_seed(monkeypatch, use_sdk):
    requests = []
    envelope = {"id": "test", "choices": [
        {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5}}
    if use_sdk:
        def create(**request):
            # Custom vendor arguments must go via extra_body in the SDK.
            assert "thinking" not in request
            request.update(request.pop("extra_body"))
            requests.append(request)
            return SimpleNamespace(id="test", choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"ok": true}'), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5))
        def factory(**kwargs):
            assert kwargs["max_retries"] == 0
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=factory))
    else:
        monkeypatch.setitem(sys.modules, "openai", None)
        def urlopen(request, *, timeout):
            assert request.full_url == "https://api.deepseek.com/chat/completions"
            requests.append(json.loads(request.data))
            return io.BytesIO(json.dumps(envelope).encode())
        monkeypatch.setattr(provider.urllib_request, "urlopen", urlopen)
    client = provider.OpenAICompatibleJSONClient(config(), environ={
        "R3E_PILOT_API_KEY": "fake-test-secret", "R3E_PILOT_BASE_URL": "https://api.deepseek.com"})
    result = client.complete_json(messages=[{"role": "user", "content": 'JSON {"ok":true}'}], seed=17)
    assert result["result"] == {"ok": True}
    assert len(requests) == 1
    request = requests[0]
    assert request["thinking"] == {"type": "disabled"}
    assert request["temperature"] == 0 and "seed" not in request
    assert result["request_hash"] == hash_payload({
        "provider_config_hash": client.config.config_hash, "request": request})
    assert "fake-test-secret" not in json.dumps(result)


def test_preflight_requires_explicit_profile_for_unseeded_requests(monkeypatch, tmp_path):
    monkeypatch.setattr(run_arena_live, "portable_toolchain", lambda: {"tool": {"available": True}})
    monkeypatch.setattr(run_arena_live, "source_identity", lambda root: {"git_commit": "test", "dirty": False})
    monkeypatch.setenv("R3E_PILOT_API_KEY", "fake-test-secret")
    monkeypatch.setenv("R3E_PILOT_BASE_URL", "https://api.deepseek.com")
    report = run_arena_live.preflight(ROOT, CONFIG)
    assert report["ready"] and report["network_calls"] == 0
    assert report["sampling_note"] == config().sampling_note
    raw = json.loads(CONFIG.read_text())
    raw.pop("request_profile")
    target = tmp_path / "client.json"
    target.write_text(json.dumps(raw))
    assert not run_arena_live.preflight(ROOT, target)["checks"]["client_config"]


def test_observer_carries_sampling_limitation_from_verified_baseline(tmp_path):
    from test_m3_evidence import arms, resign
    a, b = arms()
    for arm in (a, b):
        arm["baseline"]["provider"] = _identity(config())
        arm["baseline"] = resign(arm["baseline"], "baseline_hash")
        for name, evaluation in arm["evaluations"].items():
            for index, row in enumerate(evaluation["cases"]):
                row.update(status="evaluated", resource_usage={})
                evaluation["cases"][index] = resign(row, "receipt_hash")
            arm["evaluations"][name] = resign(evaluation)
    a, b = resign(a), resign(b)
    target = tmp_path / "comparison.json"
    freeze(target, compare_arms(a, b))
    snapshot = ArenaTelemetryService(ROOT, target).snapshot()
    assert snapshot["available"]
    assert snapshot["sampling_note"] == config().sampling_note


def test_probe_sends_one_request_and_missing_credentials_sends_none():
    calls = []
    def transport(**request):
        calls.append(request)
        return {"content": '{"ok": true}', "input_tokens": 12,
                "output_tokens": 5, "provider_request_id": "test"}
    cfg = replace(config(), maximum_output_tokens=128)
    client = provider.OpenAICompatibleJSONClient(cfg, transport=transport, environ={})
    with pytest.raises(ValueError, match="API Key"):
        probe(client)
    assert not calls
    client = provider.OpenAICompatibleJSONClient(cfg, transport=transport, environ={
        "R3E_PILOT_API_KEY": "fake-test-secret", "R3E_PILOT_BASE_URL": "https://api.deepseek.com"})
    assert probe(client)["ok"]
    assert len(calls) == 1 and calls[0]["max_tokens"] == 128
