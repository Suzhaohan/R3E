"""B-only v2 case memory, activated through the existing round snapshots."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import re

from competition.arena.evidence import read, signed, verify_signed, freeze
from r3e.protocol.hashing import hash_payload, atomic_write_json
from r3e.knowledge import (CaseMemoryAuthor, BugTypeInference, KnowledgeMatcher,
                           analyze_rtl, build_profile, build_bundle)
from .case_memory import entry_from_evaluation, validated_episode, visible_feedback

BANK_SCHEMA = "r3e-experience-bank-v2-cases"


def family(value):
    value = str(value).split(":")[-1]
    value = re.sub(r"(?:__.*|_\d+)$", "", value)
    value = re.sub(r"_test$", "", value)
    return {"first_counter": "first_counter_overflow", "tff": "flip_flop",
            "keccak": "sha3", "padder": "sha3", "BM_lamda": "reed",
            "out_stage": "reed"}.get(value, value)


def collect(paths, *, forbidden_families=()):
    """Import only signed, completed model executions, deduplicated by receipt."""
    entries, rejected = {}, Counter()
    for path in sorted(paths):
        try:
            receipt = verify_signed(read(path), "receipt_hash")
            if receipt.get("source_kind") != "live_model" or receipt.get("status") != "evaluated":
                rejected["not_completed_live_model"] += 1
                continue
            design = family(receipt.get("design") or receipt["case_id"])
            if design in forbidden_families:
                rejected["final_family"] += 1
                continue
            evaluation = read(path.parent / "evaluation.json")
            if (evaluation["portfolio_execution_hash"] != receipt["portfolio_execution_hash"]
                    or evaluation["oracle_ok"] != receipt["oracle_ok"]):
                raise ValueError("evaluation/receipt mismatch")
            if evaluation["portfolio_execution_hash"] != hash_payload({
                k: v for k, v in evaluation.items() if k != "portfolio_execution_hash"
            }):
                raise ValueError("evaluation hash mismatch")
            entry = entry_from_evaluation(evaluation, receipt_hash=receipt["receipt_hash"],
                                          design_cluster=design)
            entries[receipt["receipt_hash"]] = entry
        except (ValueError, OSError, KeyError, TypeError):
            rejected["invalid_evidence"] += 1
    return list(entries.values()), dict(rejected)


def bank(entries):
    unique = {}
    for entry in entries:
        validated_episode(entry["episode"])
        key = entry["receipt_hash"]
        if key in unique and unique[key] != entry:
            raise ValueError("conflicting case-memory receipt")
        unique[key] = entry
    ordered = [unique[key] for key in sorted(unique)]
    episodes = {e["episode"]["episode_hash"]: validated_episode(e["episode"]) for e in ordered}
    items = CaseMemoryAuthor().author(episodes.values())
    return signed({"schema_version": BANK_SCHEMA, "enabled": bool(items),
                   "entries": ordered, "items": [item.to_dict() for item in items]})


def archive(root, state):
    """Keep every local replay outcome, including failures, without extra model calls."""
    state = Path(state).resolve()
    machine = verify_signed(read(state / "machine_manifest.json"), "machine_hash")
    if machine["arm"] != "adversarial":
        return bank([])
    entries, rejected = collect((state / "replays").glob("*/receipt.json"))
    entries.extend(completed_challenges(state))
    value = signed({"baseline_hash": machine["baseline_hash"], "scope": "same_run_B_only",
                    "memory": bank(entries), "rejected": rejected})
    atomic_write_json(state / "experience/archive/library.json", value)
    return value["memory"]


def completed_challenges(state, before=None):
    """Read only this arm's audited earlier rounds, never other runs or heldout tests."""
    import json
    from r3e.arena.audit import verify_frozen_round
    entries = []
    for completed in sorted((state / "rounds").glob("R*/round_summary.json")):
        if before is not None and completed.parent.name >= before:
            continue
        audit = verify_frozen_round(completed.parent)
        for line in (completed.parent / "blue_challenge_results.jsonl").read_text().splitlines():
            if not line.strip(): continue
            row = json.loads(line)
            for evaluation in row.get("blue_results", []):
                entries.append(entry_from_evaluation(evaluation,
                    receipt_hash=hash_payload({"audit": audit["audit_record_hash"],
                        "execution": evaluation["portfolio_execution_hash"]}),
                    design_cluster=family(row["design"])))
    return entries


def snapshot(root, state, operation, *, evolving=False, approve=None):
    """New observations become eligible at the next round, never mid-round."""
    root, state = Path(root), Path(state)
    machine = verify_signed(read(state / "machine_manifest.json"), "machine_hash")
    if evolving and machine["arm"] != "adversarial":
        raise ValueError("A cannot activate experience")
    target = state / "experience" / (operation + ".json")
    if target.exists():
        value = verify_signed(read(target))
        ExperienceMemory(value)  # refuse legacy note banks rather than silently mixing formats
        return value
    initial = bank([])
    entries = []
    previous = initial
    if evolving and operation.startswith("R"):
        entries = completed_challenges(state, before=operation)
        completed_contexts = sorted(p for p in (state / "experience").glob("R[0-9][0-9][0-9].json")
                                    if p.stem < operation)
        if completed_contexts:
            previous = verify_signed(read(completed_contexts[-1]))
            ExperienceMemory(previous)
        # Read only replay indexes of earlier *completed* rounds. Interrupted
        # work and final/T0 evaluations never feed back into development.
        paths = []
        for completed in sorted((state / "rounds").glob("R*/round_summary.json")):
            if completed.parent.name >= operation:
                continue
            from r3e.arena.audit import verify_frozen_round
            verify_frozen_round(completed.parent)
            indexes = [*(completed.parent / "replay_cache").glob("*.json"),
                       *(state / "experience/guards" / completed.parent.name / "cache").glob("*.json")]
            for index in indexes:
                receipt = verify_signed(read(index), "receipt_hash")
                replay = (state / "replays" / receipt["artifact_id"]).resolve()
                if replay.parent != (state / "replays").resolve():
                    raise ValueError("experience receipt escapes current run")
                paths.append(replay / "receipt.json")
        extra, _ = collect(paths)
        entries.extend(extra)
    elif evolving and operation == "T1":
        # Freeze exactly the context used by the last promotion gate. Final
        # evaluation does not activate an untested new experience snapshot.
        contexts = sorted((state / "experience").glob("R[0-9][0-9][0-9].json"))
        if contexts:
            final = verify_signed(read(contexts[-1]))
            ExperienceMemory(final)
            return freeze(target, final)
    proposed = bank(entries)
    if not evolving and proposed["entries"]:
        raise ValueError("static experience must stay empty")
    if evolving and operation.startswith("R") and proposed != previous:
        freeze(state / "experience/proposals" / (operation + ".json"), proposed)
        if approve is None:
            raise ValueError("new case memory requires paired transfer-gain validation")
        if not approve(previous, proposed):
            proposed = previous
    return freeze(target, proposed)


class ExperienceMemory:
    def __init__(self, value):
        self.value = deepcopy(verify_signed(value))
        if value.get("schema_version") != BANK_SCHEMA:
            raise ValueError("legacy experience bank requires a fresh v2 memory run")
        rebuilt = bank(value["entries"])
        if rebuilt != value:
            raise ValueError("case-memory bank cannot be reconstructed from its episodes")
        self.memory_hash = value["result_hash"]
        self.episodes = list({e["episode"]["episode_hash"]: validated_episode(e["episode"])
                              for e in value["entries"]}.values())

    def bundle(self, artifact, *, evidence=None, limit=3):
        source = artifact.get("buggy_rtl_source", "")
        feedback = visible_feedback(evidence or {})
        if not source or not feedback.divergences:
            return None
        design = family(artifact.get("design_group") or artifact.get("top_module")
                        or artifact.get("case_id", ""))
        # Rebuild from eligible episodes so a mixed group cannot leak its own
        # source design through another member. Filenames never rank matches.
        eligible = [e for e in self.episodes
                    if family(e.get("design_cluster")) != design
                    and e.get("case_id") != artifact.get("case_id")
                    and e.get("buggy_rtl_hash") != hash_payload(source)]
        pool = CaseMemoryAuthor().author(eligible)
        profile = build_profile(feedback, analyze_rtl(source))
        inference = BugTypeInference().fit(eligible)
        return build_bundle("matched", profile=profile,
            type_posterior=inference.posterior(profile), pool=pool,
            matcher=KnowledgeMatcher(top_k=max(1, min(3, limit))),
            case_id=artifact.get("case_id", ""))

    def retrieve(self, artifact, *, evidence=None, limit=3, max_chars=18000):
        bundle = self.bundle(artifact, evidence=evidence, limit=limit)
        if bundle is None:
            return []
        selected, size = [], 0
        for item in bundle.items:
            length = len(str(item))
            if size + length <= max_chars:
                selected.append(item)
                size += length
        return selected
