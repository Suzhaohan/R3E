import importlib.util
import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prob003_dashboard', HERE/'dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


@pytest.fixture(autouse=True)
def disable_browser(monkeypatch):
    monkeypatch.setattr(dashboard, 'open_browser', lambda url: None)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_viewing_absent_run_does_not_create_it(tmp_path):
    run = tmp_path/'not-started'
    status = dashboard.snapshot(run)
    assert status['status'] == 'waiting'
    assert status['calls'] == 0
    assert not run.exists()


def test_finished_mock_is_explicitly_labelled_and_aggregated():
    status = dashboard.snapshot(HERE/'smoke-v4')
    assert status['mock']
    assert status['status'] == 'complete'
    assert status['calls'] == 41
    assert status['max_calls'] == 88
    assert status['completed_rounds'] == 5
    assert status['probes_completed'] == 24
    assert len(status['final']) == 6
    assert status['report_available'] and status['audits_available']
    assert status['schema_version'] == 2
    assert status['admitted_challenges'] == 5
    assert len(status['memory']) == 5


def test_live_usage_does_not_double_count_or_expose_secrets(tmp_path):
    save(tmp_path/'collection/plan.json', {'client_config': {'model_id': 'deepseek-v4-flash'}})
    (tmp_path/'collection/calls.jsonl').write_text('{"input_tokens": 100, "output_tokens": 20}\n')
    events = [{'event': 'started', 'http_attempt': 1},
              {'event': 'response', 'input_tokens': 100, 'output_tokens': 20},
              {'event': 'started', 'http_attempt': 2, 'diagnostics': 'SECRET'}]
    (tmp_path/'usage_guard.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in events)+'{"event":')
    status = dashboard.snapshot(tmp_path)
    assert status['status'] == 'running'
    assert status['calls'] == 2
    assert status['input_tokens'] == 100 and status['output_tokens'] == 20
    assert '等待返回' in status['phase']
    assert 'SECRET' not in json.dumps(status)


def test_launch_stop_is_not_shown_as_running(tmp_path):
    save(tmp_path/'launch_stop.json', {'error_type': 'RuntimeError', 'diagnostics': 'PRIVATE'})
    status = dashboard.snapshot(tmp_path)
    assert status['status'] == 'aborted'
    assert 'PRIVATE' not in json.dumps(status)


def test_provider_failure_is_not_a_successful_repair_round(tmp_path):
    save(tmp_path/'launch_stop.json', {'diagnostics': {
        'http_status': 503, 'error_code': 'service_unavailable_error',
        'error_message': 'PRIVATE', 'billing': 'unknown'}})
    save(tmp_path/'collection/rounds/1/commit.json', {'blue': {'entries': [], 'snapshot_id': 'B_1'}})
    (tmp_path/'collection/slots.jsonl').write_text(json.dumps({
        'round': 1, 'admission': 'provider_failure', 'trials': {}})+'\n')
    (tmp_path/'collection/calls.jsonl').write_text(json.dumps({
        'slot_id': 'r2_s0', 'ok': False, 'role': 'red', 'error': 'ProviderHalt'})+'\n')
    (tmp_path/'usage_guard.jsonl').write_text('{"event":"started"}\n{"event":"transport_error"}\n')
    status = dashboard.snapshot(tmp_path)
    assert status['status'] == 'aborted'
    assert '503' in status['phase']
    assert status['completed_rounds'] == 1
    assert status['admitted_challenges'] == 0
    assert status['successful_responses'] == 0
    assert status['unknown_usage_requests'] == 1
    assert status['rounds'][1]['admission'] == 'provider_failure'
    assert not status['report_available']
    assert 'PRIVATE' not in json.dumps(status)


def test_original_styles_and_navigation_are_restored():
    original = (HERE.parent/'deepseek-run-01/source/competition/app/frontend/styles.css').read_text()
    assert (HERE/'dashboard.css').read_text().startswith(original)
    html = (HERE/'dashboard.html').read_text()
    for page in ('repair', 'verification', 'arena', 'evolution', 'memory', 'benchmarks'):
        assert f'data-page="{page}"' in html
        assert f'id="{page}"' in html
    assert 'src="/static/prob003.js"' in html


def test_view_never_launches_experiment(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['dashboard', 'view', '--run-dir', str(tmp_path/'absent')])
    monkeypatch.setattr(dashboard, 'ensure_viewer', lambda *args: 'http://127.0.0.1:8093/')
    monkeypatch.setattr(dashboard, 'run_step', lambda *args: pytest.fail('view called experiment'))
    assert dashboard.main() == 0


def test_start_runs_reports_only_after_completed_collection(monkeypatch, tmp_path):
    env = tmp_path/'credentials'
    env.write_text('not a real key')
    run = tmp_path/'fresh'
    monkeypatch.setattr(sys, 'argv', ['dashboard', 'start', '--run-dir', str(run), '--env-file', str(env)])
    monkeypatch.setattr(dashboard, 'ensure_viewer', lambda *args: 'http://127.0.0.1:8093/')
    actions = []

    def step(action, args):
        actions.append(action)
        if action == 'collect':
            save(run/'collection/collection.json', {'status': 'complete'})
        return 0

    monkeypatch.setattr(dashboard, 'run_step', step)
    assert dashboard.main() == 0
    assert actions == ['collect', 'report', 'audits']


def test_failed_collection_does_not_run_reports_or_retry(monkeypatch, tmp_path):
    env = tmp_path/'credentials'
    env.write_text('not a real key')
    monkeypatch.setattr(sys, 'argv', ['dashboard', '--run-dir', str(tmp_path/'fresh'), '--env-file', str(env)])
    monkeypatch.setattr(dashboard, 'ensure_viewer', lambda *args: 'http://127.0.0.1:8093/')
    actions = []

    def step(action, args):
        actions.append(action)
        return 1

    monkeypatch.setattr(dashboard, 'run_step', step)
    assert dashboard.main() == 1
    assert actions == ['collect']


def test_existing_run_cannot_be_restarted(monkeypatch, tmp_path):
    env = tmp_path/'credentials'
    env.write_text('not a real key')
    monkeypatch.setattr(sys, 'argv', ['dashboard', '--run-dir', str(tmp_path), '--env-file', str(env)])
    monkeypatch.setattr(dashboard, 'ensure_viewer', lambda *args: pytest.fail('must fail before viewer'))
    with pytest.raises(SystemExit) as error:
        dashboard.main()
    assert error.value.code == 2


def test_interactive_key_reaches_frozen_loader_without_disk_or_command_line(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import os
    import subprocess

    secret = 'test-only-key'
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(dashboard.getpass, 'getpass', lambda prompt: secret)
    real_run = subprocess.run
    observed_fds = []

    def child(command, **kwargs):
        assert secret not in ' '.join(command)
        fd = kwargs['pass_fds'][0]
        observed_fds.append(fd)
        path = command[command.index('--env-file') + 1]
        # Exercise the actual frozen file loader in a child process.
        code = (
            'import sys; sys.path.insert(0, sys.argv[1]); '
            'from r3e.loop.env import load_llm_env; '
            'env=load_llm_env(sys.argv[2]); '
            'assert env["DEEPSEEK_API_KEY"] == "test-only-key"; '
            'assert env["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"'
        )
        return real_run([sys.executable, '-c', code, str(HERE/'source'), path], **kwargs)

    monkeypatch.setattr(dashboard.subprocess, 'run', child)
    args = SimpleNamespace(run_dir=tmp_path/'fresh', plan_dir=HERE/'plan-v4', env_file=None)
    assert dashboard.run_step('collect', args) == 0
    assert not list(tmp_path.iterdir())
    with pytest.raises(OSError):
        os.fstat(observed_fds[0])


def test_interactive_key_requires_terminal(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)
    monkeypatch.setattr(dashboard.getpass, 'getpass', lambda *args: pytest.fail('must not prompt'))
    args = SimpleNamespace(run_dir=tmp_path/'fresh', plan_dir=HERE/'plan-v4', env_file=None)
    with pytest.raises(ValueError, match='交互终端'):
        dashboard.run_step('collect', args)


def test_start_without_env_file_accepts_interactive_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['dashboard', '--run-dir', str(tmp_path/'fresh')])
    monkeypatch.setattr(dashboard, 'ensure_viewer', lambda *args: 'http://127.0.0.1:8095/')
    actions = []
    def step(action, args):
        assert args.env_file is None
        actions.append(action)
        return 1
    monkeypatch.setattr(dashboard, 'run_step', step)
    assert dashboard.main() == 1
    assert actions == ['collect']


def test_occupied_port_automatically_uses_next_port(monkeypatch, tmp_path, capsys):
    ports = []
    def ensure(run_dir, port):
        ports.append(port)
        if port == 8095:
            raise dashboard.ViewerPortOccupied('端口 8095 已展示其他运行')
        return f'http://127.0.0.1:{port}/'
    monkeypatch.setattr(dashboard, 'ensure_viewer', ensure)
    assert dashboard.available_viewer(tmp_path, 8095) == 'http://127.0.0.1:8096/'
    assert ports == [8095, 8096]
    assert '自动尝试下一端口' in capsys.readouterr().out


def test_port_search_is_bounded_and_does_not_hide_other_errors(monkeypatch, tmp_path):
    ports = []
    def occupied(run_dir, port):
        ports.append(port)
        raise dashboard.ViewerPortOccupied('occupied')
    monkeypatch.setattr(dashboard, 'ensure_viewer', occupied)
    with pytest.raises(RuntimeError, match='候选端口'):
        dashboard.available_viewer(tmp_path, 8095)
    assert len(ports) == 20
    def broken(*args):
        raise RuntimeError('viewer failed')
    monkeypatch.setattr(dashboard, 'ensure_viewer', broken)
    with pytest.raises(RuntimeError, match='viewer failed'):
        dashboard.available_viewer(tmp_path, 8095)
