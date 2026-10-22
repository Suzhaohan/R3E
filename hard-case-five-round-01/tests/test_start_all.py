import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('all_launcher', HERE / 'start_all.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['start_all.py', '--run-dir', str(tmp_path / 'fresh')])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(launcher.getpass, 'getpass', lambda _: 'test-only-not-a-key')
    viewers = []
    monkeypatch.setitem(sys.modules, 'dashboard', SimpleNamespace(
        available_viewer=lambda root, port: viewers.append((root, port)) or f'http://127.0.0.1:{port}/',
        open_browser=lambda _: None))
    return viewers


def completed_collect(action, root, decision='continue'):
    if action == 'collect':
        root.mkdir(parents=True, exist_ok=True)
        (root/'initial_exam_gate.json').write_text(json.dumps(dict(decision=decision,passed=6 if decision=='stop_saturated' else 0,samples=6)))
    return 0


def test_one_collect_then_reports_and_audits(monkeypatch, tmp_path):
    viewers = setup(monkeypatch, tmp_path)
    calls = []
    def step(action, root, env_file=None, pass_fds=()):
        calls.append(action)
        if action == 'collect':
            assert env_file.startswith('/proc/self/fd/') and len(pass_fds) == 1
        return completed_collect(action,root)
    monkeypatch.setattr(launcher, 'step', step)
    assert launcher.main() == 0
    assert calls == ['check', 'collect', 'results']
    assert len(viewers) == 3


def test_collect_failure_does_not_retry(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    calls = []
    def step(action, *args):
        calls.append(action)
        return 17 if action == 'collect' else 0
    monkeypatch.setattr(launcher, 'step', step)
    assert launcher.main() == 17
    assert calls == ['check', 'collect', 'results']


def test_check_only_does_not_request_credentials_or_start_viewers(monkeypatch, tmp_path):
    viewers = setup(monkeypatch, tmp_path)
    sys.argv.append('--check-only')
    monkeypatch.setattr(launcher.getpass, 'getpass', lambda _: (_ for _ in ()).throw(AssertionError('unexpected credentials')))
    monkeypatch.setattr(launcher, 'step', lambda *args: 0)
    assert launcher.main() == 0
    assert viewers == []


def test_viewer_failure_still_collects_and_reports(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    def unavailable(*args):
        raise RuntimeError('viewer unavailable')
    monkeypatch.setattr(sys.modules['dashboard'], 'available_viewer', unavailable)
    calls = []
    monkeypatch.setattr(launcher, 'step', lambda action, root, *args: calls.append(action) or completed_collect(action,root))
    assert launcher.main() == 0
    assert calls == ['check', 'collect', 'results']


def test_occupied_port_range_falls_back_to_system_port(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('viewer_under_test', HERE / 'dashboard.py')
    dashboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard)
    ports = []
    def ensure(root, port):
        ports.append(port)
        if len(ports) <= 20:
            raise dashboard.ViewerPortOccupied('occupied')
        return f'http://127.0.0.1:{port}/'
    class Probe:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): assert address == ('127.0.0.1', 0)
        def getsockname(self): return ('127.0.0.1', 49152)
    monkeypatch.setattr(dashboard, 'ensure_viewer', ensure)
    monkeypatch.setattr(dashboard.socket, 'socket', Probe)
    assert dashboard.available_viewer(tmp_path, 8098) == 'http://127.0.0.1:49152/'
    assert ports == list(range(8098, 8118)) + [49152]


def test_saturated_pretest_is_normal_stop_message(monkeypatch,tmp_path,capsys):
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(launcher,'step',lambda action,root,*args:completed_collect(action,root,'stop_saturated'))
    assert launcher.main()==0
    output=capsys.readouterr().out
    assert '前测 6/6 全对，本批已停止，未开始训练' in output
    assert '本批训练和统一考试已结束' not in output
