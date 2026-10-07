"""Immutable, hash-bound manifests and design-disjoint splits."""
from __future__ import annotations

import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from r3e.protocol.hashing import atomic_write_json, hash_payload, read_json, utc_now


MANIFEST_SCHEMA_VERSION = "r3e-frozen-manifest-v1"


class ManifestViolation(RuntimeError):
    """Raised when a frozen manifest changes or leaks a design split."""


def _canonical_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (deepcopy(row) for row in rows),
        key=lambda row: (
            str(row.get("design") or row.get("design_id") or ""),
            str(row.get("case_id") or row.get("poison_id") or ""),
            int(row.get("seed") or 0),
        ),
    )


def make_manifest(
    rows: list[dict[str, Any]],
    *,
    split: str,
    source_manifest_hash: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = _canonical_rows(rows)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "split": split,
        "source_residual_manifest_hash": source_manifest_hash,
        "rows": canonical,
        "row_count": len(canonical),
        "metadata": deepcopy(metadata or {}),
        "frozen_at": utc_now(),
    }
    # Timestamps are audit metadata, not manifest membership.
    payload["manifest_hash"] = hash_payload({
        key: value for key, value in payload.items() if key not in {"frozen_at", "manifest_hash"}
    })
    return payload


def verify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestViolation("manifest schema mismatch")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or manifest.get("row_count") != len(rows):
        raise ManifestViolation("manifest row count mismatch")
    expected = hash_payload({
        key: value for key, value in manifest.items() if key not in {"frozen_at", "manifest_hash"}
    })
    if manifest.get("manifest_hash") != expected:
        raise ManifestViolation("manifest hash mismatch")
    if rows != _canonical_rows(rows):
        raise ManifestViolation("manifest rows are not canonical")
    return manifest


def freeze_manifest(path: str | Path, manifest: dict[str, Any]) -> dict[str, Any]:
    target = Path(path)
    verify_manifest(manifest)
    if target.exists():
        existing = verify_manifest(read_json(target))
        if existing["manifest_hash"] != manifest["manifest_hash"]:
            raise ManifestViolation(f"refusing to overwrite frozen manifest: {target}")
        return existing
    atomic_write_json(target, manifest)
    return verify_manifest(read_json(target))


def grouped_split(
    residual_manifest: dict[str, Any],
    *,
    adaptation_fraction: float = 0.5,
    seed: int = 0,
    min_target_designs: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_manifest(residual_manifest)
    if not 0.0 < adaptation_fraction < 1.0:
        raise ManifestViolation("adaptation_fraction must be between zero and one")
    if type(min_target_designs) is not int or min_target_designs < 1:
        raise ManifestViolation("min_target_designs must be a positive integer")
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in residual_manifest["rows"]:
        design = str(row.get("design") or row.get("design_id") or "")
        if not design:
            raise ManifestViolation("residual row missing design")
        groups.setdefault(design, []).append(row)
    if len(groups) < 2:
        raise ManifestViolation("design-disjoint split requires at least two designs")
    if len(groups) < min_target_designs + 1:
        raise ManifestViolation("not enough designs for adaptation and promotion target")
    designs = sorted(groups)
    random.Random(seed).shuffle(designs)
    cut = min(
        len(designs) - min_target_designs,
        max(1, round(len(designs) * adaptation_fraction)),
    )
    adaptation_designs = set(designs[:cut])
    adaptation_rows = [
        row for design in designs if design in adaptation_designs for row in groups[design]
    ]
    target_rows = [
        row for design in designs if design not in adaptation_designs for row in groups[design]
    ]
    source = residual_manifest["manifest_hash"]
    adaptation = make_manifest(
        adaptation_rows,
        split="adaptation",
        source_manifest_hash=source,
        metadata={"group_key": "design", "seed": seed},
    )
    target = make_manifest(
        target_rows,
        split="target",
        source_manifest_hash=source,
        metadata={"group_key": "design", "seed": seed},
    )
    left = {
        str(row.get("design") or row.get("design_id")) for row in adaptation["rows"]
    }
    right = {str(row.get("design") or row.get("design_id")) for row in target["rows"]}
    if left & right:
        raise ManifestViolation("grouped split leaked designs")
    return adaptation, target


def split_for_promotion(
    residual_manifest: dict[str, Any],
    *,
    min_target_designs: int,
    adaptation_fraction: float = 0.5,
    seed: int = 0,
    design_roles: dict[str, str] | None = None,
    supplied_manifest: dict[str, Any] | None = None,
    allow_supplied_only: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reserve the gate's required target designs before assigning practice rows.

    Insufficient residuals remain available for later rounds, without starting
    a search that cannot pass the distinct-design promotion gate.
    """
    verify_manifest(residual_manifest)
    pool_rows = list(residual_manifest["rows"])
    supplied_metadata = {}
    if supplied_manifest is not None:
        verify_manifest(supplied_manifest)
        if (supplied_manifest["split"] != "evolve"
                or supplied_manifest.get("metadata", {}).get("allowed_usage") != "evolution_only"
                or design_roles is None):
            raise ManifestViolation("supplied repair bank requires frozen evolution roles")
        identities = {(r.get("case_id"), r.get("poison_id")) for r in pool_rows}
        for row in supplied_manifest["rows"]:
            identity = (row.get("case_id"), row.get("poison_id"))
            if identity in identities:
                raise ManifestViolation("supplied repair bank duplicates a residual identity")
            identities.add(identity)
            pool_rows.append(row)
        supplied_metadata = {"supplied_manifest_hash": supplied_manifest["manifest_hash"],
                             "supplied_case_count": supplied_manifest["row_count"],
                             "generated_residual_case_count": residual_manifest["row_count"],
                             "provided_cases_are_not_claimed_as_red_discoveries": True}
    if type(min_target_designs) is not int or min_target_designs < 1:
        raise ManifestViolation("min_target_designs must be a positive integer")
    if not 0.0 < adaptation_fraction < 1.0:
        raise ManifestViolation("adaptation_fraction must be between zero and one")
    designs = {
        str(row.get("design") or row.get("design_id") or "")
        for row in pool_rows
    }
    if "" in designs:
        raise ManifestViolation("residual row missing design")
    if design_roles is not None:
        if (not design_roles or any(role not in {"adaptation", "target"} for role in design_roles.values())
                or not designs <= set(design_roles)):
            raise ManifestViolation("invalid or incomplete frozen design roles")
        if (sum(role == "adaptation" for role in design_roles.values()) < 1
                or sum(role == "target" for role in design_roles.values()) < min_target_designs):
            raise ManifestViolation("frozen design roles cannot satisfy promotion gate")
        by_role = {
            role: [row for row in pool_rows
                   if design_roles[str(row.get("design") or row.get("design_id"))] == role]
            for role in ("adaptation", "target")
        }
        counts = {role: len({str(row.get("design") or row.get("design_id")) for row in rows})
                  for role, rows in by_role.items()}
        missing_practice = max(0, 1 - counts["adaptation"])
        missing_exam = max(0, min_target_designs - counts["target"])
        eligible = missing_practice + missing_exam == 0
        no_red_failure = supplied_manifest is not None and not residual_manifest["rows"]
        eligible = eligible and (not no_red_failure or allow_supplied_only)
        metadata = {
            **supplied_metadata,
            "group_key": "design", "seed": seed,
            "search_trigger": "supplied_bank" if no_red_failure and allow_supplied_only else "red_residual",
            "split_protocol": "frozen_design_roles_v2",
            "design_roles_hash": hash_payload(design_roles),
            "promotion_eligible": eligible,
            "defer_reason": "" if eligible else ("no_admitted_red_failure" if no_red_failure else "insufficient_residual_designs"),
            "design_allocation": {
                "residual_design_count": len(designs),
                "adaptation_design_count": counts["adaptation"],
                "target_design_count": counts["target"],
                "required_target_designs": min_target_designs,
                "required_residual_designs": min_target_designs + 1,
                "missing_adaptation_designs": missing_practice,
                "missing_target_designs": missing_exam,
                "missing_design_count": missing_practice + missing_exam,
                "roles_frozen": True,
            },
        }
        return tuple(make_manifest(rows, split=role,
                                   source_manifest_hash=residual_manifest["manifest_hash"],
                                   metadata=metadata) for role, rows in by_role.items())
    eligible = len(designs) >= min_target_designs + 1
    if eligible:
        adaptation, target = grouped_split(
            residual_manifest,
            adaptation_fraction=adaptation_fraction,
            seed=seed,
            min_target_designs=min_target_designs,
        )
        adaptation_rows, target_rows = adaptation["rows"], target["rows"]
    else:
        adaptation_rows, target_rows = residual_manifest["rows"], []
    allocation = {
        "residual_design_count": len(designs),
        "adaptation_design_count": len({
            str(row.get("design") or row.get("design_id")) for row in adaptation_rows
        }),
        "target_design_count": len({
            str(row.get("design") or row.get("design_id")) for row in target_rows
        }),
        "required_target_designs": min_target_designs,
        "required_residual_designs": min_target_designs + 1,
        "missing_design_count": max(0, min_target_designs + 1 - len(designs)),
    }
    metadata = {
        "group_key": "design",
        "seed": seed,
        "split_protocol": "promotion_design_reserve_v1",
        "promotion_eligible": eligible,
        "defer_reason": "" if eligible else "insufficient_residual_designs",
        "design_allocation": allocation,
    }
    return tuple(
        make_manifest(
            rows, split=split,
            source_manifest_hash=residual_manifest["manifest_hash"],
            metadata=metadata,
        )
        for split, rows in (("adaptation", adaptation_rows), ("target", target_rows))
    )
