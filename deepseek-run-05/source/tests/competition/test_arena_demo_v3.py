from copy import deepcopy
from pathlib import Path

import pytest

from competition.arena.demo import run_demo, verify_demo, demo_snapshot, MODE
from competition.arena.evidence import read, signed, freeze
from competition.services.arena_comparison_service import verify_comparison, verify_evaluation
from competition.services.arena_telemetry_service import ArenaTelemetryService
from r3e.arena.round_state import STAGES
from r3e.memory.episode_builder import episode_from_challenge
from r3e.policy.schema import PolicyState
from r3e.protocol.hashing import hash_payload
from r3e.red.poison_payload import bind_poison_payload

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def demo_artifact(tmp_path_factory):
    out = tmp_path_factory.mktemp("arena-demo-v3")
    return Path(run_demo(ROOT, out)["artifact"])


def test_demo_runs_real_eda_and_separates_formal_evidence(demo_artifact):
    value = verify_demo(demo_artifact)
    snapshot = demo_snapshot(demo_artifact)
    assert snapshot["available"] and snapshot["mode"] == MODE
    assert [r["round_id"] for r in snapshot["rounds"]] == [f"R{i:03d}" for i in range(5)]
    imported = {d for r in snapshot["rounds"] for d in r["designs"] if not d.startswith("m3_synthetic")}
    assert imported == {"assignment4v:JG3", "assignment4v:decl7s", "assignment4v:decoder3e",
                        "assignment4v:fa_behavioral", "assignment4v:mux21", "cirfix:decoder_3_to_8"}
    assert all(r["proposed_count"] >= r["valid_count"] >= r["repaired_count"] for r in snapshot["rounds"])
    assert all(len(r["cases"]) == r["proposed_count"] for r in snapshot["rounds"])
    assert sum(len(c["seeds"]) for r in snapshot["rounds"] for c in r["cases"]) == 60
    assert all(len(s["candidates"]) == 3 for r in snapshot["rounds"] for c in r["cases"] for s in c["seeds"])
    assert len(next(iter(snapshot["case_results"].values()))) == 18
    for forbidden in ("replacement_rtl", "current_buggy_rtl", "api_key", "golden_rtl"):
        import json
        assert forbidden not in json.dumps(snapshot)
    assert snapshot["machines"]["static"]["promotion_count"] == 0
    assert snapshot["machines"]["adversarial"]["promotion_count"] >= 1
    assert all(row["stages"] == STAGES for row in snapshot["rounds"])
    for arm in ("static", "adversarial"):
        with pytest.raises(ValueError, match="injected"):
            verify_evaluation(value["evaluations"][arm], live_only=True)
    with pytest.raises((ValueError, KeyError)):
        verify_comparison(value)
    assert ArenaTelemetryService(ROOT, demo_artifact).snapshot()["available"] is False
    assert ArenaTelemetryService(ROOT, demo_path=demo_artifact).snapshot()["available"] is True
    with pytest.raises(ValueError, match="empty"):
        run_demo(ROOT, demo_artifact.parent)


def test_tampered_demo_summary_fails_closed(demo_artifact, tmp_path):
    value = deepcopy(read(demo_artifact))
    value["rounds"][0]["promoted"] = not value["rounds"][0]["promoted"]
    freeze(tmp_path/"tampered.json", value)
    assert not ArenaTelemetryService(ROOT, demo_path=tmp_path/"tampered.json").snapshot()["available"]
    # Rehashing an invented summary is insufficient: raw round authority is required.
    value.pop("result_hash")
    freeze(tmp_path/"rehash.json", signed(value))
    assert not ArenaTelemetryService(ROOT, demo_path=tmp_path/"rehash.json").snapshot()["available"]


def test_demo_source_modes_are_exclusive():
    with pytest.raises(ValueError, match="not both"):
        ArenaTelemetryService(ROOT, "formal.json", demo_path="demo.json")


@pytest.mark.parametrize("hashes,expected", [
    (["a", "a"], "resolved"), (["a", "b"], "inconclusive"),
    (["a", ""], "inconclusive"), (["", ""], "inconclusive"),
])
def test_multiple_verified_patch_identities_do_not_abort_round(hashes, expected):
    policy = PolicyState.from_dict(read(ROOT/"configs/base_policy/frozen_base_policy_v1.json"))
    challenge = bind_poison_payload({"poison_id": "P-demo", "challenged_policy_hash": policy.policy_hash,
        "buggy_rtl_hash": hash_payload("buggy")})
    challenge["blue_results"] = [{"oracle_ok": True,
        "successful_patch_hash": hash_payload(h) if h else ""} for h in hashes]
    challenge["validity"] = {"result_hash": hash_payload("verified-validity")}
    challenge["challenge_result_hash"] = hash_payload(challenge)
    episode = episode_from_challenge(challenge, policy=policy, round_id="R000")
    assert episode.final_outcome == expected
    assert bool(episode.successful_patch_hash) == (expected == "resolved")
    assert len(episode.blue_attempts) == 2
