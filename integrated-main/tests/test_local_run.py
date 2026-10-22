"""Local launcher boundaries: offline execution, provenance, and read-only status."""
import fcntl
import json
import subprocess
import sys

import pytest

from scripts import local_run
from r3e.protocol.ledger import append_ledger, LedgerViolation


def test_status_does_not_initialize_missing_state(tmp_path):
    state = tmp_path / "absent"
    assert not local_run.status(state)["initialized"]
    assert not state.exists()


def test_status_reconstructs_cost_and_rejects_corruption(tmp_path):
    append_ledger(tmp_path / "calls.jsonl", {"phase": "red", "ok": True,
                  "input_tokens": 10, "output_tokens": 2})
    (tmp_path / "checkpoint.json").write_text(json.dumps({"completed_rounds": 2}))
    report = local_run.status(tmp_path)
    assert report["completed_rounds"] == 2
    assert report["cost"]["total_calls"] == 1
    assert report["cost"]["learning"]["input_tokens"] == 10
    path = tmp_path / "calls.jsonl"
    path.write_text(path.read_text().replace('"input_tokens":10', '"input_tokens":999'))
    with pytest.raises(LedgerViolation):
        local_run.status(tmp_path)


def test_offline_python_children_cannot_connect():
    with local_run.offline_environment() as env:
        result = subprocess.run([sys.executable, "-c",
            "import socket; socket.getaddrinfo('localhost', 9)"],
            env=env, text=True, capture_output=True)
    assert result.returncode != 0
    assert "network disabled for offline checks" in result.stderr


def test_default_start_uses_new_core_fake_transport_and_logs(tmp_path, monkeypatch):
    observed = {}
    def capture(command, *, log, env):
        observed.update(command=command, log=log, env=env)
        return 0
    monkeypatch.setattr(local_run, "stream", capture)
    assert local_run.run_loop(tmp_path, ["--rounds", "3"]) == 0
    command = observed["command"]
    assert "r3e.loop.cli" in command and "--fake" in command
    assert "--allow-real-calls" not in command
    assert observed["log"].parent == tmp_path / "logs"
    assert str(local_run.ROOT) in observed["env"]["PYTHONPATH"]
    assert json.loads((tmp_path / "local-launch.json").read_text())["mode"] == "fake"


def test_fake_state_cannot_be_reused_for_real_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(local_run, "stream", lambda *a, **kw: 0)
    local_run.run_loop(tmp_path, [])
    before = (tmp_path / "local-launch.json").read_bytes()
    with pytest.raises(ValueError, match="不同状态目录"):
        local_run.run_loop(tmp_path, ["--allow-real-calls", "--max-calls", "10"])
    assert (tmp_path / "local-launch.json").read_bytes() == before


def test_refuses_legacy_and_unidentified_existing_state(tmp_path):
    legacy = tmp_path / "legacy"
    (legacy / "rounds").mkdir(parents=True)
    with pytest.raises(ValueError, match="旧版"):
        local_run.run_loop(legacy, [])
    assert not (legacy / "local-launch.json").exists()
    unidentified = tmp_path / "other"
    unidentified.mkdir()
    (unidentified / "calls.jsonl").write_text("")
    with pytest.raises(ValueError, match="无法确认"):
        local_run.run_loop(unidentified, [])


def test_second_writer_is_refused(tmp_path):
    with (tmp_path / ".local-run.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="已有任务"):
            local_run.run_loop(tmp_path, [])


def test_plan_keeps_state_absent_and_offline(tmp_path, monkeypatch):
    state = tmp_path / "plan"
    def capture(command, *, cwd, env):
        assert "--plan" in command
        assert "r3e-offline-" in env["PYTHONPATH"]
        return 0
    monkeypatch.setattr(local_run.subprocess, "call", capture)
    assert local_run.run_loop(state, [], plan=True) == 0
    assert not state.exists()


def test_offline_commands_reject_live_options_before_dispatch(tmp_path):
    with pytest.raises(SystemExit) as exc:
        local_run.main(["smoke", "--state-dir", str(tmp_path), "--allow-real-calls"])
    assert exc.value.code == 2
    assert not (tmp_path / "local-launch.json").exists()
