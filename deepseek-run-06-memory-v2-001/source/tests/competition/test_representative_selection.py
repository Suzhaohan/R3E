"""Selected cases, family separation and immutable five-round budget contract."""
from collections import Counter
from pathlib import Path

from competition.arena.evidence import read
from competition.arena.cli import _split_certificate
from competition.scripts.run_arena_live import ROUND_IDS
from competition.arena.isolation import promotion_design_roles
from r3e.arena.manifests import make_manifest, split_for_promotion

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "competition/manifests"


def test_two_per_family_without_aliases_or_extra_synthetic_cases():
    names = ["demo18_supplied_assets", "demo18_regression", "demo18_heldout", "demo18_strider"]
    pools = [read(DIR / (name + ".json")) for name in names]
    rows = [r for m in pools for r in m["rows"]]
    assert [len(m["rows"]) for m in pools] == [10, 2, 2, 4]
    assert len({r["case_id"] for r in rows}) == 18
    assert Counter(Counter(r["design"] for r in rows).values()) == {2: 9}
    assert not any(r["case_id"].startswith("m3_synthetic") for r in rows)
    for i, left in enumerate(pools):
        for right in pools[i+1:]:
            assert {r["design"] for r in left["rows"]}.isdisjoint(r["design"] for r in right["rows"])
    certificate = _split_certificate(ROOT, {"evaluation_manifests": {
        "red-heldout": pools[2]["manifest_hash"], "strider-subset4": pools[3]["manifest_hash"]}})
    assert certificate["split_level"] == "upstream_design_disjoint"


def test_reduced_pool_can_still_hold_a_valid_promotion_exam():
    evolve = read(DIR / "demo18_red_sources.json")
    bank = read(DIR / "demo18_repair_bank.json")
    roles = promotion_design_roles(evolve)
    assert Counter(roles.values()) == {"adaptation": 2, "target": 3}
    # One admitted generated failure plus supplied cases must not require the
    # old ten-design pool or move practice families over to the exam side.
    generated = dict(bank["rows"][0], case_id="generated-test", poison_id="generated-test",
                     normalized_diff_hash="generated-diff", failure_signature="generated-failure")
    practice, exam = split_for_promotion(make_manifest([generated], split="residual"),
        min_target_designs=2, design_roles=roles, supplied_manifest=bank)
    assert exam["metadata"]["promotion_eligible"]
    assert {r["design"] for r in practice["rows"]}.isdisjoint(r["design"] for r in exam["rows"])
    assert len({r["design"] for r in exam["rows"]}) == 3
    assert ROUND_IDS == ["R000", "R001", "R002", "R003", "R004"]
