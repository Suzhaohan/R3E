"""Transport recovery for run.sh; frozen source, policy and budgets stay intact."""
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN / "source"
sys.path.insert(0, str(ROOT))

from competition.arena.baseline import source_identity, load_runtime
from competition.arena.cli import _client, main as arena
from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.arena.runtime import validate_client
from competition.scripts import run_current
from competition.scripts.run_arena_live import preflight
from r3e.protocol.hashing import hash_file, hash_payload, atomic_write_json, utc_now
from r3e.providers.openai_compatible import OpenAICompatibleJSONClient
from resilience import Recovery
from round_messages import completed_messages, progress_messages, serve_observer


def configure_route(base_url, route):
    """Bypass proxies for the API host only; certificate verification stays on."""
    if route not in {"direct", "environment"}:
        raise ValueError("R3E_NETWORK_ROUTE 必须为 direct 或 environment")
    parsed = urlsplit(base_url)
    if not parsed.hostname or parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("需要有效的 HTTPS API 地址，且地址不能包含凭据")
    if route == "environment":
        return
    entries = []
    for name in ("NO_PROXY", "no_proxy"):
        entries.extend(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())
    entries.append(parsed.hostname)
    value = ",".join(dict.fromkeys(entries))
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = value


def network_check(base_url, route):
    """Use the same HTTP library as the SDK, without a key or model request."""
    configure_route(base_url, route)
    started = time.monotonic()
    try:
        try:
            import httpx
        except ImportError:
            from urllib.request import Request, urlopen
            from urllib.error import HTTPError
            try:
                with urlopen(Request(base_url, method="HEAD"), timeout=20) as response:
                    status = response.status
            except HTTPError as response:
                status = response.code
                response.close()
        else:
            with httpx.Client(timeout=20, verify=True, trust_env=True) as client:
                status = client.head(base_url).status_code
        # An unauthenticated API commonly returns 401; TLS still succeeded.
        return {"tls_connected": True, "http_status": status,
                "network_route": route, "certificate_verification": True,
                "model_calls": 0, "elapsed_seconds": round(time.monotonic()-started, 3)}
    except Exception as exc:
        return {"tls_connected": False, "network_route": route, "model_calls": 0,
                "error": OpenAICompatibleJSONClient._safe_error_label(exc)}


def record_recovery_manifest(directory, manifest):
    """Keep the original overlay evidence and append audited code revisions."""
    original = Path(directory) / "manifest.json"
    if not original.exists():
        return freeze(original, manifest)
    previous = verify_signed(read(original))
    # Only overlay implementation files may change during recovery. Experiment,
    # endpoint, route, launcher and retry policy retain their sealed bindings.
    stable = lambda value: {k: v for k, v in value.items() if k not in {"files", "result_hash"}}
    if stable(previous) != stable(manifest):
        raise ValueError("recovery manifest experiment/transport binding changed")
    if previous != manifest:
        revision = signed({"previous_manifest_hash": previous["result_hash"], "manifest": manifest})
        freeze(Path(directory) / "manifest_revisions" / (manifest["result_hash"].split(":")[-1] + ".json"), revision)
    return manifest


def resilient_run(root, args, progress=print):
    report = preflight(root, args.client_config)
    if args.check:
        return report
    if not report["ready"]:
        raise ValueError("真实实验尚未就绪：" + json.dumps(report, ensure_ascii=False))
    baseline = verify_signed(read(args.baseline), "baseline_hash")
    identity = source_identity(root)
    if identity["dirty"] or any(identity[k] != baseline[k] for k in ("git_commit", "source_hash")):
        raise ValueError("冻结源码与 baseline 不一致；不会跳过源码校验")
    client = _client(args.client_config)
    validate_client(client, baseline)
    state = Path(args.state_root).resolve()
    route = os.environ.get("R3E_NETWORK_ROUTE", "direct")
    endpoint = os.environ[client.config.base_url_env]
    configure_route(endpoint, route)
    with ExitStack() as locks:
        stream = locks.enter_context((state.parent / (state.name + ".recovery.lock")).open("a+"))
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (state.parent / (state.name + ".launcher.lock")).open("a+") as launch_lock:
            fcntl.flock(launch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Initialize before adding recovery files to the empty arm directory.
            if not (state / "machine_manifest.json").exists():
                arena(["arena-init", "--config", str(Path(root) / f"competition/configs/arena/{args.arm}.yaml"),
                       "--baseline", args.baseline, "--state-root", str(state)], root)
            _, machine, stored = load_runtime(state)
            if stored != baseline or machine["arm"] != args.arm:
                raise ValueError("恢复目录、实验组或 baseline 不匹配")
            budget_path = state / "budgets/total.json"
            if budget_path.exists():
                budget = read(budget_path)
                if (budget["max_calls"], budget["max_tokens"]) != (args.max_calls, args.max_tokens):
                    raise ValueError("预算必须与原命令一致")
            recovery = Recovery(state, client.config, endpoint=endpoint, report=progress)
            manifest = signed({"schema_version": "r3e-current-transport-recovery-v1",
                "baseline_hash": baseline["baseline_hash"], "frozen_core_identity": identity,
                "files": {p.name: hash_file(p) for p in sorted(Path(__file__).parent.glob("*.py"))
                          if not p.name.startswith("test_")},
                "launcher_hash": hash_file(RUN / "run.sh"), "network_route": route,
                "endpoint_hash": hash_payload(endpoint), "retry_delays_seconds": [2, 4, 8, 16],
                "cache_policy": "operation, checkpoint, exact case/policy/seed and request slot; no cross-arm reuse",
                "source_changed": False, "baseline_changed": False})
            record_recovery_manifest(recovery.root, manifest)
        progress(f"连接恢复已启用：API 路径={route}；TLS 校验开启；连接失败最多重试 4 次。", flush=True)
        recovery.event("session_started", manifest_hash=manifest["result_hash"])
        result = recovery.run(lambda: _original_run(root, args, progress=progress_messages(state, progress)))
        phase = "T0" if getattr(args, "baseline_only", False) else "T1"
        evidence = {}
        if phase == "T0":
            directory = state.parent / "baseline-evaluations" / machine["arm"]
            evidence = {name: hash_file(directory / (name + ".json")) for name in baseline["evaluation_manifests"]}
        else:
            evidence = {"frozen_arm": hash_file(state / "frozen_arm.json")}
        completion = signed({"completed_at": utc_now(), "phase": phase,
            "manifest_hash": manifest["result_hash"], "evidence": evidence,
            "events_hash": hash_file(recovery.root / "events.jsonl"),
            "cache_files": {str(p.relative_to(recovery.root)): hash_file(p)
                            for p in sorted(recovery.root.rglob("*.json")) if not p.name.startswith("completion_")},
            "session_statistics": dict(recovery.stats)})
        atomic_write_json(recovery.root / f"completion_{phase}.json", completion)
        return {**result, "recovery": dict(recovery.stats)}


_original_run = run_current.run


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "view":
        return serve_observer(RUN, argv[1:])
    if argv == ["status"]:
        from unittest.mock import patch
        original_arena = run_current.arena

        def status_arena(arguments, root):
            value = original_arena(arguments, root)
            if arguments[0] == "arena-status":
                state = arguments[arguments.index("--state-root") + 1]
                value = {**value, "round_messages": completed_messages(state)}
            return value

        with patch.object(run_current, "arena", status_arena):
            return run_current.main(argv, root=ROOT)
    client = _client(RUN / "client.json")
    endpoint = os.environ.get(client.config.base_url_env, "")
    route = os.environ.get("R3E_NETWORK_ROUTE", "direct")
    if argv == ["network-check"]:
        if not endpoint:
            raise ValueError("请先设置 R3E_PILOT_BASE_URL")
        result = network_check(endpoint, route)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["tls_connected"] else 2
    if argv and argv[0] in {"a0", "a", "b", "probe"} and endpoint:
        configure_route(endpoint, route)
    run_current.run = resilient_run
    try:
        return run_current.main(argv, root=ROOT)
    finally:
        run_current.run = _original_run


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
