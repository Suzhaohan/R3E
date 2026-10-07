"""Freeze final-only membership and reject overlap before any evolution."""
from pathlib import Path
import json
from r3e.arena.manifests import make_manifest, verify_manifest, freeze_manifest
from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
from r3e.protocol.hashing import hash_file

IDENTITIES = ("case_id", "poison_id", "normalized_diff_hash", "failure_signature")


def validate_membership(rows, *, unique_cases=True):
    if not rows:
        raise ValueError("empty manifest")
    for field in IDENTITIES:
        if field == "case_id" and not unique_cases:
            continue
        values = [r[field] for r in rows if r.get(field)]
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {field}")
    if any(not row.get("case_id") for row in rows):
        raise ValueError("case_id required")


def check_separation(evolve, heldout, *, design_disjoint=True):
    for manifest in (evolve, heldout):
        verify_manifest(manifest)
        validate_membership(manifest["rows"])
    fields = (*IDENTITIES, "design") if design_disjoint else IDENTITIES
    for field in fields:
        if any(not r.get(field) for m in (evolve, heldout) for r in m["rows"]):
            raise ValueError(f"missing separation identity: {field}")
        left = {r[field] for r in evolve["rows"]}
        right = {r[field] for r in heldout["rows"]}
        if left & right:
            raise ValueError(f"evolution/evaluation overlap: {field}")


def require_evolution_manifest(manifest):
    verify_manifest(manifest)
    if manifest.get("metadata", {}).get("allowed_usage") == "final_evaluation_only" or manifest["split"] not in {"evolve", "adaptation", "target", "non_target", "residual"}:
        raise ValueError("final evaluation data forbidden in evolution")
    validate_membership(manifest["rows"], unique_cases=manifest["split"] in {"evolve", "non_target"})
    return manifest


def seal_evaluation_manifest(source, target, *, project_root, dataset):
    rows = [json.loads(line) for line in Path(source).read_text().splitlines() if line.strip()]
    validate_membership(rows)
    frozen = []
    for row in rows:
        for asset in row.get("files", []):
            path = (Path(project_root) / asset["path"]).resolve()
            if Path(project_root).resolve() not in path.parents or hash_file(path).removeprefix("sha256:") != asset["sha256"].removeprefix("sha256:"):
                raise ValueError("upstream manifest asset changed")
        case = public_case_from_manifest(row, project_root=project_root)
        frozen.append({**row, "manifest_file_hashes": case["manifest_file_hashes"]})
    manifest = make_manifest(frozen, split="evaluation", metadata={
        "sealed": True, "allowed_usage": "final_evaluation_only", "dataset": dataset,
        "source_hash": hash_file(source)})
    return freeze_manifest(target, manifest)


def verify_evaluation_manifest(manifest, project_root):
    verify_manifest(manifest)
    validate_membership(manifest["rows"])
    meta = manifest["metadata"]
    if manifest["split"] != "evaluation" or meta.get("sealed") is not True or meta.get("allowed_usage") != "final_evaluation_only":
        raise ValueError("sealed final-evaluation manifest required")
    for row in manifest["rows"]:
        actual = public_case_from_manifest(row, project_root=project_root)
        if not row.get("manifest_file_hashes") or actual["manifest_file_hashes"] != row["manifest_file_hashes"]:
            raise ValueError("sealed evaluation asset changed")
    return manifest
