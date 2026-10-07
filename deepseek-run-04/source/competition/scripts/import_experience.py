"""Import every available signed historical repair receipt before initialization."""
import json
from pathlib import Path

from competition.services.experience_memory import collect, bank, family
from competition.arena.evidence import read, freeze, signed


def build(root, historical_runs):
    root = Path(root)
    if (root.parent / "baseline.json").exists():
        raise ValueError("history must be frozen before the baseline")
    final = [r for name in ("demo32_heldout", "demo32_strider")
             for r in read(root / "competition/manifests" / (name + ".json"))["rows"]]
    excluded = {family(r["design"]) for r in final}
    paths = [p for run in historical_runs for p in Path(run).rglob("receipt.json")
             if "source" not in p.relative_to(run).parts and "validation" not in str(p)]
    entries, rejected = collect(paths, forbidden_families=excluded)
    value = bank(entries)
    freeze(root / "competition/manifests/history_memory.json", value)
    report = signed({"historical_runs": [Path(p).name for p in historical_runs],
                     "scanned_receipts": len(paths), "imported_experiences": len(entries),
                     "excluded_final_families": sorted(excluded), "rejected": rejected,
                     "memory_hash": value["result_hash"], "network_calls": 0,
                     "reference_rtl_imported": False})
    freeze(root / "competition/manifests/history_import.json", report)
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    project = root.parent.parent
    runs = sorted(p for p in project.glob("*-run-*") if p != root.parent and p.is_dir())
    print(json.dumps(build(root, runs), ensure_ascii=False, indent=2))
