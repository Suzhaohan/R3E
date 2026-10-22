#!/usr/bin/env python3
"""Handoff entry point. check/freeze are offline; collect is an explicit paid action."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import site
import sys

BUNDLE = Path(__file__).resolve().parent


def verify_bundle():
    manifest = json.loads((BUNDLE / "handoff_manifest.json").read_text())
    for rel, digest in manifest["files_sha256"].items():
        path = BUNDLE / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"handoff file changed or missing: {rel}")
    return manifest


def local_materials(directory):
    material = json.loads((directory / "materials.json").read_text())
    material["carriers"] = [{"package": str(directory / "package"),
        "suite_freeze": str(directory / "suite_freeze.json"),
        "evaluator_freeze": str(directory / "evaluator_freeze.json"), "evaluator_root": str(directory)}]
    for anchor in material["anchors"]:
        name = Path(anchor["task_dir"]).name
        if name not in {"eval_match_branch", "eval_miss_branch"}:
            raise ValueError("unexpected reserved variant")
        anchor["task_dir"] = str(directory / "reserved" / name)
    path = directory / "materials.local.json"
    if path.exists() and json.loads(path.read_text()) != material:
        raise ValueError("local material bindings already exist and differ")
    if not path.exists():
        path.write_text(json.dumps(material, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "freeze", "collect", "report", "audits"))
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, default=BUNDLE / "plan")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    verify_bundle()
    repo = args.repo_root.resolve()
    if not (repo / "r3e/loop/continuous_state.py").is_file():
        parser.error("--repo-root must point to the published R3E checkout")
    # Pin source bytes even when a new machine needs a new runtime/path freeze.
    code = json.loads((BUNDLE / "plan/code_snapshot_manifest.json").read_text())["files_sha256"]
    for rel, digest in code.items():
        if hashlib.sha256((repo / rel).read_bytes()).hexdigest() != digest:
            raise ValueError(f"repository differs from the delivered code: {rel}")
    site.addsitedir(site.getusersitepackages())
    sys.path.insert(0, str(repo))
    os.environ["R3E_TOKENIZER"] = str(BUNDLE / "tokenizer/tokenizer.json")
    from experiments.loop_probes import continuous_launch, continuous_loop, sequence_curriculum
    os.chdir(repo)
    if args.action == "freeze":
        material = local_materials((BUNDLE / "materials").resolve())
        plan = continuous_launch.freeze(json.loads(material.read_text()), args.plan_dir.resolve(), profile="sequence")
        print(f"PASS: new offline freeze; {plan['max_calls']} calls maximum; no model calls")
    elif args.action == "check":
        plan, _ = continuous_launch.check_bundle(args.plan_dir.resolve(), repo)
        print(f"PASS: frozen source/runtime/materials; {plan['max_calls']} calls; no model calls")
    elif args.action == "collect":
        if args.env_file is None or args.run_dir is None:
            parser.error("collect requires --env-file and a fresh --run-dir")
        sys.argv = [str(continuous_launch.__file__), "collect", "--repo-root", str(repo),
            "--plan-dir", str(args.plan_dir.resolve()), "--env-file", str(args.env_file.resolve()),
            "--run-dir", str(args.run_dir.resolve())]
        return continuous_launch.main()
    else:
        if args.run_dir is None:
            parser.error("report/audits requires --run-dir")
        run = args.run_dir.resolve() / "collection"
        continuous_loop.validate_plan(continuous_loop.read(run / "plan.json"))
        if args.action == "report":
            result = sequence_curriculum.report(run)
            print(json.dumps({k: result[k] for k in ("scheduled_generation", "admitted", "distinct_admitted")}))
        else:
            from experiments.loop_probes.continuous_audit import exposure_audit, source_audit
            exposure_audit(run)
            source_audit(run)
            print("PASS: post-run exposure and source audits; no model calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
