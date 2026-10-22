import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prob003_v3', ROOT/'experiment.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_only_model_adapter_changes_and_same_experiment():
    plan, _ = experiment.check(ROOT/'plan-v3-0324-ready')
    original = experiment.read(ROOT.parent/'prob003-five-round-01/real-v2/collection/plan.json')
    for field in ('slots', 'anchor_probes', 'blue_config', 'learning', 'retrieval',
                  'mechanism_focus', 'red_output_tokens', 'max_calls'):
        assert plan[field] == original[field]
    assert plan['client_config']['model_id'] == 'deepseek/deepseek-chat-v3-0324'
    changes = experiment.read(ROOT/'protocol_changes.json')['files_sha256']
    assert set(changes) == {'experiments/loop_probes/continuous_launch.py',
                            'experiments/loop_probes/red907_launch.py', 'r3e/loop/env.py'}
    for rel, digest in original['code'].items():
        if rel not in changes:
            assert experiment.sha(ROOT/'source'/rel) == digest


def test_guard_accepts_v3_red_and_blue_and_rejects_v4(tmp_path):
    _, loop, shared, _, _ = experiment.modules()
    plan, counter = experiment.check(ROOT/'plan-v3-0324-ready')
    seen = []
    def transport(**request):
        seen.append(request)
        return {'content': '{}', 'input_tokens': counter.request(request['messages']),
                'output_tokens': 1, 'provider_request_id': 'offline'}
    limits = {loop.red.SYSTEM: 16384, loop.rb.SYSTEM_REPAIR: 32768}
    guard = shared.UsageGuard(transport, counter, tmp_path, envelope='Infinity',
                              direct_only=True, allowed_systems=limits)
    for system, limit in limits.items():
        guard(model=plan['client_config']['model_id'], max_tokens=limit,
              messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': '{}'}])
    assert len(seen) == 2
    with pytest.raises(shared.UsageStop):
        guard(model='deepseek-v4-flash', max_tokens=16384,
              messages=[{'role': 'system', 'content': loop.red.SYSTEM}])
    assert len(seen) == 2
    client = shared.build_launch_client({'OPENROUTER_API_KEY': 'offline-only',
                                        'OPENROUTER_BASE_URL': 'https://openrouter.ai/api/v1'}, plan, guard)
    assert client.config.public_identity == plan['client_config']


def test_v3_transport_routes_without_v4_thinking_and_keeps_raw_response(monkeypatch, tmp_path):
    experiment.modules()
    from r3e.loop.env import ThinkingTransport
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(model='deepseek/deepseek-chat-v3-0324', id='offline-test',
            provider='SiliconFlow',
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"edits": []}', refusal=None),
                                     finish_reason='stop')],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10,
                                  model_dump=lambda: {'prompt_tokens': 100, 'completion_tokens': 10, 'cost': 0.000035}))
    def fake_client(**kwargs):
        assert kwargs['max_retries'] == 0
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr('openai.OpenAI', fake_client)
    transport = ThinkingTransport({'OPENROUTER_API_KEY': 'offline-secret',
        'OPENROUTER_BASE_URL': 'https://openrouter.ai/api/v1'},
        key_name='OPENROUTER_API_KEY', url_name='OPENROUTER_BASE_URL',
        thinking='default', timeout_seconds=1500, failure_dir=tmp_path/'unparseable')
    result = transport(model='deepseek/deepseek-chat-v3-0324', max_tokens=32768, messages=[])
    assert 'reasoning_effort' not in captured
    assert captured['extra_body']['provider'] == {
        'only': ['siliconflow'], 'allow_fallbacks': False, 'require_parameters': True}
    assert result['output_tokens'] == 10
    raw = (tmp_path/'provider_responses.jsonl').read_text()
    assert 'offline-secret' not in raw
    assert json.loads(raw)['usage']['cost'] == 0.000035


def test_old_v4_records_preserved():
    for rel, digest in experiment.read(ROOT/'preserved_v4_records.json').items():
        assert experiment.sha(ROOT.parent/rel) == digest
