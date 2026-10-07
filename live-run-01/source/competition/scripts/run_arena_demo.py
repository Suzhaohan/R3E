"""Generate an offline arena run, then serve its audited evidence locally."""
import argparse
from pathlib import Path
import sys

from competition.arena.demo import run_demo, verify_demo, NOTICE


def main():
    parser = argparse.ArgumentParser(description=NOTICE)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--output-root", help="Empty output directory (default: unique /tmp directory)")
    source.add_argument("--evidence", help="Reuse an existing complete demo.json without rerunning EDA")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-serve", action="store_true", help="Generate/validate evidence and exit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    print(NOTICE, flush=True)
    try:
        if args.evidence:
            artifact = str(Path(args.evidence).resolve())
            verify_demo(artifact)
        else:
            artifact = run_demo(root, args.output_root, rounds=args.rounds)["artifact"]
        print(f"Evidence: {artifact}", flush=True)
        if args.no_serve:
            return 0
        from competition.app.backend.api import main as serve
        sys.argv = [sys.argv[0], "--host", args.host, "--port", str(args.port), "--arena-demo", artifact,
                    "--output-root", str(Path(artifact).parent/"repair-studio")]
        print(f"Open http://{args.host}:{args.port} and select Adversarial Arena", flush=True)
        return serve()
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"Demo stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
