import io
import json
import pytest
import start
import errno
from urllib.error import URLError, HTTPError
from types import SimpleNamespace


def observer_fixture(monkeypatch, tmp_path, replies, *, exited=False):
    calls, spawned = [], []
    clock = [0.0]
    def open_status(url, timeout):
        calls.append((url, timeout))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            if isinstance(reply, TimeoutError) or isinstance(getattr(reply, 'reason', None), TimeoutError):
                clock[0] += timeout
            raise reply
        return io.StringIO(reply)
    def spawn(*args, **kwargs):
        spawned.append(args)
        return SimpleNamespace(poll=lambda: 1 if exited else None)
    monkeypatch.setattr(start, 'RUN', tmp_path)
    monkeypatch.setattr(start, 'build_opener', lambda *a: SimpleNamespace(open=open_status))
    monkeypatch.setattr(start.subprocess, 'Popen', spawn)
    monkeypatch.setattr(start.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(start.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n))
    return calls, spawned


@pytest.mark.parametrize('error', [TimeoutError('slow'), URLError(TimeoutError('slow'))])
def test_slow_existing_observer_is_retried_without_spawning(monkeypatch, tmp_path, error):
    calls, spawned = observer_fixture(monkeypatch, tmp_path, [error, '{"available": true}'])
    start.ensure_observer(8086)
    assert len(calls) == 2 and calls[0][1] == 15
    assert not spawned


def test_absent_observer_is_started_once_and_waits_for_readiness(monkeypatch, tmp_path):
    refused = URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'refused'))
    calls, spawned = observer_fixture(monkeypatch, tmp_path,
        [refused, refused, TimeoutError('slow'), '{"available": false}'])
    start.ensure_observer(8086)
    assert len(calls) == 4 and len(spawned) == 1


def test_observer_startup_exit_reports_log(monkeypatch, tmp_path):
    refused = URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'refused'))
    _, spawned = observer_fixture(monkeypatch, tmp_path, [refused, refused], exited=True)
    with pytest.raises(RuntimeError, match='logs/web.log'):
        start.ensure_observer(8086)
    assert len(spawned) == 1


@pytest.mark.parametrize('reply', ['not json', '{}',
    HTTPError('http://localhost', 500, 'error', {}, None), PermissionError('denied')])
def test_occupied_or_invalid_endpoint_does_not_spawn(monkeypatch, tmp_path, reply):
    _, spawned = observer_fixture(monkeypatch, tmp_path, [reply])
    with pytest.raises(RuntimeError, match='状态检查失败'):
        start.ensure_observer(8086)
    assert not spawned


def test_persistent_timeout_is_bounded_and_does_not_spawn(monkeypatch, tmp_path):
    calls, spawned = observer_fixture(monkeypatch, tmp_path, [TimeoutError('slow')] * 4)
    with pytest.raises(RuntimeError, match='60 秒'):
        start.ensure_observer(8086)
    assert len(calls) == 4 and not spawned


@pytest.mark.parametrize('failure',[None,'b','missing_key'])
def test_original_command_order_and_stop_on_failure(tmp_path,monkeypatch,failure):
    class Opener:
        def open(self,*args,**kwargs):return io.StringIO('{"available": false}')
    monkeypatch.setattr(start,'RUN',tmp_path)
    monkeypatch.setattr(start,'build_opener',lambda *a:Opener())
    monkeypatch.setattr(start.launcher,'preflight',lambda *a:{'ready':failure!='missing_key',
        'checks':{'credentials':failure!='missing_key'}})
    events=[]
    def launch(argv):
        events.append(argv[0])
        return 1 if argv[0]==failure else 0
    monkeypatch.setattr(start.launcher,'main',launch)
    result=start.main([])
    if failure=='missing_key':
        assert result==2 and not events
    elif failure=='b':
        assert result==1 and events==['init','a0','b']
        assert json.loads((tmp_path/'pipeline.json').read_text())['status']=='stopped'
    else:
        assert result==0 and events==['init','a0','b','a','compare']
        assert json.loads((tmp_path/'pipeline.json').read_text())['status']=='complete'
