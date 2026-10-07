"""Run reference/bug differential checks without changing dataset membership."""
from pathlib import Path
import argparse
import json

from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
from r3e.semantic_repair_bench.oracle_gate import judge
from r3e.protocol.hashing import hash_file


def qualify(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    path = root / "datasets/manifests/assignment4v57.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    results = []
    for row in rows:
        case = public_case_from_manifest(row, project_root=root)
        result = judge(case, case["buggy_rtl_path"], output / row["case_id"].replace(":", "_"))
        status = ("not_detected" if result.ok else "functional_failure" if result.stage == "compare"
                  else "reference_unavailable" if result.stage == "golden_sim" else "candidate_compile_or_sim_failure")
        results.append({"case_id": row["case_id"], "design": row["design"], "status": status,
                        "stage": result.stage, "mismatch": result.mismatch, "error": result.err})
        print(row["case_id"], status, flush=True)
    report = {"manifest_hash": hash_file(path), "cases": results,
              "counts": {s: sum(r["status"] == s for r in results) for s in sorted({r["status"] for r in results})},
              "note": "Input qualification only; not repair results. All 57 cases retained."}
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    print(json.dumps(qualify(Path(__file__).resolve().parents[2], args.output)["counts"], indent=2))
