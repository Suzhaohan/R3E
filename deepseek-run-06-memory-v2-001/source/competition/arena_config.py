"""Strict, independent configuration for isolated M3 experiment arms."""
from dataclasses import dataclass
from pathlib import Path
import re
import yaml
from competition.config import _freeze
from r3e.protocol.hashing import hash_payload


@dataclass(frozen=True)
class ArenaConfig:
    raw: object
    config_hash: str

    @property
    def arm(self):
        return self.raw["experiment"]["arm"]

    @property
    def experiment_id(self):
        return self.raw["experiment"]["id"]


def validate_arena_config(raw):
    if not isinstance(raw, dict) or raw.get("schema_version") != "r3e-aic-arena-config-v1":
        raise ValueError("arena schema mismatch")
    for section in ("experiment", "policy", "red", "memory", "repair", "evaluation"):
        if not isinstance(raw.get(section), dict):
            raise ValueError(f"missing arena section: {section}")
    arm = raw["experiment"].get("arm")
    if arm not in {"static", "adversarial", "observer"}:
        raise ValueError("invalid arm")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", str(raw["experiment"].get("id", ""))):
        raise ValueError("invalid experiment id")
    evolving = arm == "adversarial"
    if raw["red"].get("enabled") is not evolving or raw["policy"].get("allow_promotion") is not evolving:
        raise ValueError("arm Red/promotion invariants violated")
    expected_mode = "evolving_registry" if evolving else "fixed"
    if raw["policy"].get("mode") != expected_mode:
        raise ValueError("policy mode does not match arm")
    if raw["memory"].get("enabled") is not evolving or raw["memory"].get("allow_activation") is not False:
        raise ValueError("Only B may use same-run experience; A must remain memory-free")
    if type(raw["repair"].get("candidate_budget")) is not int or raw["repair"]["candidate_budget"] != 3:
        raise ValueError("candidate budget must be exactly three")
    seeds = raw["evaluation"].get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 3 or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("at least three unique integer evaluation seeds required")
    return ArenaConfig(_freeze(raw), hash_payload(raw))


def load_arena_config(path):
    return validate_arena_config(yaml.safe_load(Path(path).read_text()))
