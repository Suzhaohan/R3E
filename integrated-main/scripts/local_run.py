"""Local run06-style commands for the upstream loop, without legacy imports.

Start defaults to fake models. Explicit real-call flags are passed through to
the upstream CLI unchanged. No automatic retries or old-state conversion.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from r3e.loop.budget import cost_from_calls
from r3e.protocol.hashing import atomic_write_json
from r3e.protocol.ledger import read_ledger


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def check() -> int:
    tools = {name: shutil.which(name) is not None for name in ("iverilog", "vvp", "yosys")}
    modules = {name: importlib.util.find_spec(name) is not None for name in ("openai", "pytest")}
    result = {"python_ok": sys.version_info >= (3, 11), "tools": tools, "modules": modules,
              "core": "r3e.loop", "model_calls": 0}
    result["ready"] = result["python_ok"] and all(tools.values()) and all(modules.values())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


def status(state: Path) -> dict:
    """Read and verify ledgers; do not initialize or change the run."""
    launch = state / "local-launch.json"
    checkpoint = state / "checkpoint.json"
    calls = read_ledger(state / "calls.jsonl")
    rounds = read_ledger(state / "rounds.jsonl")
    metadata = json.loads(launch.read_text()) if launch.exists() else {}
    progress = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    return {"initialized": checkpoint.exists() or bool(rounds) or bool(calls),
            "mode": metadata.get("mode", "unknown"),
            "completed_rounds": progress.get("completed_rounds", 0),
            "round_records": len(rounds), "cost": cost_from_calls(calls),
            "latest_round": {key: rounds[-1][key] for key in (
                "round", "admitted", "followups", "solved_within_budget", "solved_by_escalation",
                "candidates", "decisions", "suspended", "lineages_by_status", "ledger_entry_hash",
            ) if key in rounds[-1]} if rounds else None}


@contextmanager
def offline_environment():
    """Block Python socket connections in this command and its Python children."""
    with tempfile.TemporaryDirectory(prefix="r3e-offline-") as directory:
        Path(directory, "sitecustomize.py").write_text(
            "import sys\n"
            "def deny_network(event, args):\n"
            "    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):\n"
            "        raise RuntimeError('network disabled for offline checks')\n"
            "sys.addaudithook(deny_network)\n", encoding="utf-8")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
               "PYTHONPATH": os.pathsep.join((directory, str(ROOT)))}
        yield env


def stream(command: list[str], *, log: Path, env: dict) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    print(f"日志：{log}", flush=True)
    with log.open("a", encoding="utf-8") as output:
        with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, start_new_session=True) as child:
            try:
                for line in child.stdout:
                    output.write(line)
                    output.flush()
                    print(line, end="", flush=True)
                return child.wait()
            except BaseException:
                # A terminal interrupt must not leave the loop or its simulators running.
                import signal
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                raise


def run_loop(state: Path, extra: list[str], *, plan: bool = False) -> int:
    command = [sys.executable, "-u", "-m", "r3e.loop.cli", "--state-dir", str(state),
               "--curriculum", *extra]
    real = "--allow-real-calls" in extra
    fake = "--fake" in extra or not real
    if real and "--fake" in extra:
        raise ValueError("不要同时指定 --fake 和 --allow-real-calls")
    if fake and "--fake" not in extra:
        command.append("--fake")
    if plan:
        command.append("--plan")
        with offline_environment() as env:
            return subprocess.call(command, cwd=ROOT, env=env)
    if (state / "rounds").is_dir() or (state / "arena_config.json").exists():
        raise ValueError("这是旧版 arena 状态目录，请给新版选择独立目录")
    state.mkdir(parents=True, exist_ok=True)
    with (state / ".local-run.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("这个状态目录已有任务运行，请先用 status 查看") from exc
        metadata_path = state / "local-launch.json"
        mode = "fake" if fake else "real"
        if metadata_path.exists():
            previous = json.loads(metadata_path.read_text())
            if previous["mode"] != mode:
                raise ValueError("模拟运行和真实运行必须使用不同状态目录")
        elif any((state / name).exists() for name in ("checkpoint.json", "calls.jsonl", "rounds.jsonl")):
            raise ValueError("状态目录不是由此入口建立，无法确认 fake/real 模式；请使用原入口或新目录")
        atomic_write_json(metadata_path, {"mode": mode, "core": "r3e.loop"})
        print("运行模式：" + ("本地模拟，不调用模型 API" if fake else "显式授权的真实模型调用"), flush=True)
        log = state / "logs" / f"session-{stamp()}.log"
        if fake:
            with offline_environment() as env:
                return stream(command, log=log, env=env)
        return stream(command, log=log, env={**os.environ, "PYTHONPATH": str(ROOT)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("check", "plan", "smoke", "start", "status", "test"))
    parser.add_argument("--state-dir", type=Path)
    args, extra = parser.parse_known_args(argv)
    if args.command in ("check", "status", "smoke", "test") and extra:
        parser.error("这个命令不接受额外参数；start/plan 的额外参数会传给新版 CLI")
    state = (args.state_dir or ROOT / "runtime" / "local-main").resolve()
    try:
        if args.command == "check":
            return check()
        if args.command == "status":
            print(json.dumps(status(state), ensure_ascii=False, indent=2))
            return 0
        if args.command == "test":
            with offline_environment() as env:
                return subprocess.call([sys.executable, "-m", "pytest", "-m", "not network", "-q"],
                                       cwd=ROOT, env=env)
        if args.command == "smoke":
            if check():
                return 1
            state = args.state_dir.resolve() if args.state_dir else ROOT / "runtime" / f"smoke-{stamp()}"
            result = run_loop(state, ["--fake", "--rounds", "2", "--proposals", "1",
                                     "--max-carriers", "3", "2", "2", "--no-learning"])
            if result == 0:
                print(json.dumps(status(state), ensure_ascii=False, indent=2))
            return result
        return run_loop(state, extra, plan=args.command == "plan")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已停止；日志和已写入的新版状态保留。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
