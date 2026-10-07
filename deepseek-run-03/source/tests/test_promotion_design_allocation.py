"""The promotion exam must be able to satisfy its distinct-design gate."""
import pytest

from r3e.arena.manifests import (
    ManifestViolation, grouped_split, make_manifest, split_for_promotion,
)


def residual(count, variants=1):
    return make_manifest([
        {"case_id": f"d{design}-bug{bug}", "design": f"d{design}"}
        for design in range(count) for bug in range(variants)
    ], split="residual")


def designs(manifest):
    return {row["design"] for row in manifest["rows"]}


@pytest.mark.parametrize("count,practice,exam", [(3, 1, 2), (4, 2, 2), (5, 2, 3), (10, 5, 5)])
def test_reserve_exam_designs_and_keep_every_variant(count, practice, exam):
    source = residual(count, variants=4)
    left, right = split_for_promotion(source, min_target_designs=2, seed=4)
    assert (len(designs(left)), len(designs(right))) == (practice, exam)
    assert designs(left).isdisjoint(designs(right))
    assert sorted(left["rows"] + right["rows"], key=lambda row: row["case_id"]) == source["rows"]
    assert left["row_count"] == practice * 4
    assert right["row_count"] == exam * 4
    assert right["metadata"]["promotion_eligible"]
    repeated = split_for_promotion(source, min_target_designs=2, seed=4)
    assert [m["manifest_hash"] for m in repeated] == [left["manifest_hash"], right["manifest_hash"]]


@pytest.mark.parametrize("count", [0, 1, 2])
def test_more_variants_do_not_replace_independent_exam_designs(count):
    left, right = split_for_promotion(residual(count, variants=14), min_target_designs=2)
    assert right["rows"] == []
    assert left["row_count"] == count * 14
    assert right["metadata"]["promotion_eligible"] is False
    assert right["metadata"]["defer_reason"] == "insufficient_residual_designs"
    allocation = right["metadata"]["design_allocation"]
    assert allocation["missing_design_count"] == 3 - count
    assert allocation["required_residual_designs"] == 3


def test_gate_override_takes_priority_over_practice_fraction():
    left, right = split_for_promotion(
        residual(4), min_target_designs=3, adaptation_fraction=0.9,
    )
    assert len(designs(left)) == 1
    assert len(designs(right)) == 3
    left, right = split_for_promotion(residual(2), min_target_designs=1)
    assert len(designs(left)) == len(designs(right)) == 1


def test_explicit_target_requirement_cannot_produce_an_impossible_exam():
    with pytest.raises(ManifestViolation, match="not enough designs"):
        grouped_split(residual(2), min_target_designs=2)
    with pytest.raises(ManifestViolation, match="positive integer"):
        split_for_promotion(residual(3), min_target_designs=0)


def test_legacy_split_default_is_unchanged():
    left, right = grouped_split(residual(3), seed=4)
    assert len(designs(left)) == 2
    assert len(designs(right)) == 1
