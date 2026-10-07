"""Rebuild the frozen 32-case profile, including 16 cross-family regression cases.

Historical results inform the input selection; this builder never reads live
results or drops cases based on the current experiment outcomes.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json

from competition.arena.evidence import read
from competition.arena.isolation import check_separation, promotion_design_roles, verify_evaluation_manifest
from r3e.arena.manifests import make_manifest, freeze_manifest
from r3e.protocol.hashing import hash_payload, atomic_write_json


def build(root):
    root = Path(root).resolve()
    directory = root / "competition/manifests"
    source = read(directory / "inputs/demo32_sources.json")
    if source["input_hash"] != hash_payload({k: v for k, v in source.items() if k != "input_hash"}):
        raise ValueError("representative source snapshot changed")
    selected = deepcopy(source["rows"])
    for row in selected["strider"]:
        row["dataset_name"] = "strider-subset4"
    ledger = source["ledger"]
    counts = Counter(r["design"] for r in ledger)
    if len(counts) != 16 or set(counts.values()) != {2} or len({r["case_id"] for r in ledger}) != 32:
        raise ValueError("demo requires sixteen design families with two bugs each")
    if {role: len(rows) for role, rows in selected.items()} != {"bank": 10, "regression": 16, "heldout": 2, "strider": 4}:
        raise ValueError("demo role sizes changed")
    selection_hash = hash_payload(ledger)
    common = {"sealed": True, "selection_hash": selection_hash, "profile": "competition-demo32",
              "split_level": "upstream_design_disjoint", "cases_per_design": 2,
              "source_snapshot_hash": source["input_hash"]}
    def manifest(role, split, dataset, **extra):
        return make_manifest(selected[role], split=split, metadata={**common,
            "allowed_usage": "final_evaluation_only" if split == "evaluation" else "evolution_only",
            "dataset": dataset, "design_count": len({r["design"] for r in selected[role]}), **extra})
    assets = manifest("bank", "evolve", "supplied-existing-defects", red_generated=False)
    regression = manifest("regression", "non_target", "red-regression")
    heldout = manifest("heldout", "evaluation", "red-heldout", source_note="Selected supplied defects; not generated Red discoveries.")
    strider = manifest("strider", "evaluation", "strider-subset4", benchmark_note="4-case subset; not full Strider-14")
    qualifications = source["qualifications"]
    qualified_ids = {r["case_id"] for r in qualifications if r["qualified"]}
    if len(qualified_ids) != 10 or qualified_ids != {r["case_id"] for r in selected["bank"]}:
        raise ValueError("selected bank lacks qualification")
    bank = make_manifest(source["bank_rows"], split="evolve", metadata={**common,
        "allowed_usage": "evolution_only", "dataset": "supplied-repair-bank", "red_generated": False,
        "assets_manifest_hash": assets["manifest_hash"], "qualification_hash": hash_payload(qualifications)})
    red_rows = list({r["design"]: r for r in reversed(selected["bank"])}.values())
    evolve = make_manifest(red_rows, split="evolve", metadata={
        **common, "allowed_usage": "evolution_only", "dataset": "red-evolve", "design_count": 5,
        "usage_note": "One reference per family for Red generation; no additional static cases."})
    for left, right in ((assets, regression), (assets, heldout), (regression, heldout)):
        check_separation(left, right)
    for m in (heldout, strider):
        verify_evaluation_manifest(m, root)
    roles = promotion_design_roles(evolve)
    if Counter(roles.values()) != {"adaptation": 2, "target": 3}:
        raise ValueError("demo requires two practice and three promotion designs")
    for name, value in {"demo32_red_sources": evolve, "demo32_regression": regression,
                        "demo32_heldout": heldout, "demo32_strider": strider,
                        "demo32_supplied_assets": assets, "demo32_repair_bank": bank}.items():
        freeze_manifest(directory / (name + ".json"), value)
    atomic_write_json(directory / "demo32_qualification.json", {
        "schema_version": "r3e-supplied-qualification-v1", "network_calls": 0,
        "qualification_hash": hash_payload(qualifications), "rows": qualifications})
    report = {"schema_version": "r3e-representative-selection-v1", "selection_hash": selection_hash,
        "profile": "competition-demo32", "total_cases": 32, "selected_designs": 16,
        "evolution_designs": 5, "regression_designs": 8, "final_designs": 3,
        "rounds": 5, "selection_uses_model_outcomes": True, "rows": ledger,
        "promotion_design_roles": roles, "source_snapshot_hash": source["input_hash"],
        "original_resource_inventory": source["original_resource_inventory"],
        "syntax_only_cases": "RTLFixer is a separate syntax task, excluded from functional scoring",
        "extra_static_cases": 0, "red_generated_cases": "Separate runtime discoveries; proposal budget remains 4 per round"}
    atomic_write_json(directory / "demo32_selection.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(build(Path(__file__).resolve().parents[2]), ensure_ascii=False, indent=2))
