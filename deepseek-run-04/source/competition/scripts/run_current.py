"""One entry point for the current local A/B experiment; paid actions are explicit."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from competition.arena.cli import main as arena
from competition.arena.evidence import read, freeze, signed
from competition.arena.isolation import promotion_design_roles
from competition.scripts.run_arena_live import preflight, run

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "init", "probe", "status", "compare"):
        sub.add_parser(command)
    for command in ("a0", "a", "b", "screen"):
        action = sub.add_parser(command)
        action.add_argument("--max-calls", required=True, type=int)
        action.add_argument("--max-tokens", required=True, type=int)
    view = sub.add_parser("view")
    view.add_argument("--port", type=int, default=8083)
    args = parser.parse_args(argv)
    root = Path(root).resolve()
    run_dir = root.parent
    client = run_dir / "client.json"
    baseline = run_dir / "baseline.json"
    comparison = run_dir / "comparison.json"
    try:
        if args.command == "check":
            result = preflight(root, client)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 2
        if args.command == "init":
            report = preflight(root, client)
            if not report["ready"]:
                raise ValueError("本地检查未通过：" + json.dumps(report, ensure_ascii=False))
            result = arena(["arena-baseline", "--client-config", str(client),
                            "--image-hash", "local-env-deepseek-run-04",
                            "--output", str(baseline)], root)
            roles = promotion_design_roles(read(root / "competition/manifests/demo32_red_sources.json"))
            freeze(run_dir / "design_roles.json", signed({
                "baseline_hash": result["baseline_hash"], "roles": roles}))
        elif args.command == "screen":
            from competition.scripts.screen_cases import run as screen
            result = screen(root, max_calls=args.max_calls, max_tokens=args.max_tokens)
        elif args.command == "probe":
            return subprocess.call([sys.executable, "-m", "competition.scripts.probe_live_client",
                                    "--client-config", str(client)], cwd=root)
        elif args.command in {"a0", "a", "b"}:
            arm_name = "b" if args.command == "b" else "a"
            state = run_dir / ("arm-" + arm_name)
            result = run(root, SimpleNamespace(
                client_config=str(client), check=False,
                arm="static" if arm_name == "a" else "adversarial",
                baseline_only=args.command == "a0",
                baseline=str(baseline), state_root=str(state),
                max_calls=args.max_calls, max_tokens=args.max_tokens,
            ))
        elif args.command == "status":
            result = {}
            for arm in ("a", "b"):
                state = run_dir / ("arm-" + arm)
                if not (state / "machine_manifest.json").exists():
                    result[arm] = {"initialized": False}
                    continue
                value = arena(["arena-status", "--state-root", str(state)], root)
                value["completed_rounds"] = sorted(p.parent.name for p in (state / "rounds").glob("R*/round_summary.json"))
                value["frozen"] = (state / "frozen_arm.json").exists()
                if (state / "budgets/total.json").exists():
                    value["budget"] = read(state / "budgets/total.json")
                result[arm] = value
        elif args.command == "compare":
            result = arena(["arena-compare", "--left", str(run_dir / "arm-a/frozen_arm.json"),
                            "--right", str(run_dir / "arm-b/frozen_arm.json"),
                            "--output", str(comparison)], root)
            arena(["arena-validate", str(comparison)], root)
            result = {"valid": True, "output": str(comparison),
                      "metrics": result["metrics"]}
        else:
            evidence = ["--comparison", str(comparison)] if comparison.exists() else ["--arena-state", str(run_dir / "arm-b")]
            return subprocess.call([sys.executable, "-m", "competition.app.backend.api", "--observer",
                                    "--host", "127.0.0.1", "--port", str(args.port),
                                    "--output-root", str(run_dir / "ui"), *evidence], cwd=root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
