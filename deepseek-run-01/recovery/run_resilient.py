"""Resume a frozen arena through an explicitly recorded recovery overlay."""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(ROOT))

from competition.arena.baseline import source_identity, load_runtime
from competition.arena.cli import _client
from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.arena.runtime import validate_client
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.scripts.run_arena_live import run
from r3e.arena.audit import verify_frozen_round
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.protocol.hashing import hash_file, utc_now
from resilience import Recovery


def configure_route(base_url, route):
    """Bypass the local proxy for this API host only; retain TLS verification."""
    if route == "environment":
        return
    host = urlsplit(base_url).hostname
    if not host or urlsplit(base_url).scheme != "https":
        raise ValueError("直连模式需要有效的 HTTPS Base URL")
    entries = []
    for name in ("NO_PROXY", "no_proxy"):
        entries.extend(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())
    entries.append(host)
    value = ",".join(dict.fromkeys(entries))
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = value


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm", choices=["static", "adversarial"], required=True)
    p.add_argument("--client-config", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--state-root", required=True)
    p.add_argument("--max-calls", type=int, required=True)
    p.add_argument("--max-tokens", type=int, required=True)
    p.add_argument("--prepare-only", action="store_true", help="Verify/import saved results only; zero API calls")
    p.add_argument("--network-route", choices=["direct", "environment"], default="direct",
                   help="默认仅让模型 API 主机绕过代理；environment 使用原终端代理设置")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    args.check = False
    state = Path(args.state_root).resolve()
    baseline = verify_signed(read(args.baseline), "baseline_hash")
    identity = source_identity(ROOT)
    if identity["dirty"] or any(identity[k] != baseline[k] for k in ("git_commit", "source_hash")):
        raise ValueError("冻结源码与 baseline 不一致；恢复入口不会跳过源码校验。")
    runtime, machine, stored = load_runtime(state)
    if stored != baseline or machine["arm"] != args.arm:
        raise ValueError("existing arm/baseline mismatch")
    client = _client(args.client_config)
    validate_client(client, baseline)
    budget = read(state / "budgets/total.json")
    if (budget["max_calls"], budget["max_tokens"]) != (args.max_calls, args.max_tokens):
        raise ValueError("预算必须与原命令一致")
    if (state / "frozen_arm.json").exists():
        from competition.services.arena_comparison_service import verify_arm
        final = verify_arm(read(state / "frozen_arm.json"))
        print(json.dumps({"already_complete": True, "result_hash": final["result_hash"], "network_calls": 0}))
        return 0
    # Fail promptly if another launcher is active. Core retains its own locks
    # during every resumed attempt; this extra lock covers recovery backoff.
    with ExitStack() as locks:
        stream = locks.enter_context((state.parent / (state.name + ".recovery.lock")).open("a+"))
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Preparation reads mutable checkpoint state and must not race core.
        with (state.parent / (state.name + ".launcher.lock")).open("a+") as launch_lock:
            fcntl.flock(launch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            recovery = Recovery(state, client.config,
                                endpoint=os.environ.get(client.config.base_url_env, ""))
            manifest = signed({"schema_version": "r3e-recovery-overlay-v1",
                "baseline_hash": baseline["baseline_hash"], "frozen_core_identity": identity,
                "files": {p.name: hash_file(p) for p in sorted(Path(__file__).parent.glob("*.py")) if not p.name.startswith("test_")},
                "launcher_hash": hash_file(ROOT.parent / "run_arena_resilient.sh"),
                "retry_delays_seconds": [2, 4, 8, 16],
                "network_route": args.network_route,
                "cache_policy": "stage and invocation ordinal; exact binding; no cross-arm reuse",
                "source_changed": False, "baseline_changed": False})
            freeze(recovery.root / "manifest.json", manifest)
            pending = None
            if args.arm == "adversarial":
                for number in range(5):
                    name = f"R{number:03d}"
                    directory = state / "rounds" / name
                    if (directory / "round_summary.json").exists():
                        verify_frozen_round(directory)
                    else:
                        pending = name
                        break
            if pending and (state / "rounds" / pending / "round_state.json").exists():
                checkpoint = read(state / "rounds" / pending / "round_state.json")["checkpoints"][-1]
                from datetime import datetime
                scope = (pending, checkpoint["stage"], datetime.fromisoformat(checkpoint["completed_at"]).timestamp())
                provider = PolicyCandidateProvider(client, verifier_id=PublicManifestOracleVerifier.verifier_id,
                    verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version="m3-policy-v1")
                service = ArenaEvaluationService(ROOT, state / "replays", provider=provider, artifact_roots=(state / "rounds",))
                recovery.prepare(service, scope)
            if args.prepare_only:
                print(json.dumps({"prepared": True, "pending_round": pending, "network_calls": 0,
                                  "manifest": str(recovery.root / "manifest.json")}, ensure_ascii=False))
                return 0
            if not client.readiness()["ready"]:
                raise ValueError("当前终端缺少 API Key 或 Base URL 环境变量；尚未调用 API。")
            configure_route(os.environ[client.config.base_url_env], args.network_route)
            freeze(recovery.root / "connection.json", signed({
                "client_config_hash": client.config.config_hash,
                "endpoint_hash": recovery.endpoint_hash, "network_route": args.network_route}))
        print("恢复模式：保留冻结源码和已有检查点；成功响应即时缓存，连接失败最多自动重试 4 次。", flush=True)
        print(f"网络路径：{args.network_route}；Python：{sys.executable}", flush=True)
        recovery.event("session_started", manifest_hash=manifest["result_hash"])
        result = recovery.run(lambda: run(ROOT, args))
        final_path = state / "frozen_arm.json"
        # Do not rewrite frozen core evidence. Bind the overlay and its recovery
        # events to the final result in a separate, explicit provenance record.
        freeze(recovery.root / "completion.json", signed({
            "completed_at": utc_now(), "manifest_hash": manifest["result_hash"],
            "frozen_arm_hash": read(final_path)["result_hash"],
            "events_hash": hash_file(recovery.root / "events.jsonl"),
            "cache_files": {str(p.relative_to(recovery.root)): hash_file(p)
                            for p in sorted(recovery.root.rglob("*.json")) if p.name != "completion.json"},
            "session_statistics": dict(recovery.stats),
            "note": "Core baseline covers the unchanged core; this sidecar records the recovery transport overlay."}))
        print(json.dumps({**result, "recovery": dict(recovery.stats)}, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        # Exception messages may contain transport URLs; never print credentials.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
