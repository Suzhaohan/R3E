"""Hash-bound retrieval of verified model experience; never import reference RTL.

All historical receipts are searchable. Context is frozen for a whole paired
round and for final evaluation, so retries cannot silently change the prompt.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import re

from competition.arena.evidence import read, signed, verify_signed, freeze
from r3e.protocol.hashing import hash_payload


def family(value):
    value = str(value).split(":")[-1]
    value = re.sub(r"(?:__.*|_\d+)$", "", value)
    value = re.sub(r"_test$", "", value)
    return {"first_counter": "first_counter_overflow", "tff": "flip_flop",
            "keccak": "sha3", "padder": "sha3", "BM_lamda": "reed",
            "out_stage": "reed"}.get(value, value)


def category(value):
    value = value.lower()
    for key, words in {
        "fsm": ("fsm", "state"), "counter": ("counter",),
        "mux": ("mux",), "decoder": ("decoder", "decl7", "jg3"),
        "arithmetic": ("fa_", "adder", "reed", "bm_lamda", "out_stage"),
        "storage": ("latch", "flop", "shift"),
        "protocol": ("sdram", "i2c"), "crypto": ("sha3", "keccak", "padder"),
    }.items():
        if any(word in value for word in words):
            return key
    return "other"


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
            verdicts = {v["candidate_id"]: v for v in evaluation["candidate_verification_receipts"]}
            notes = []
            for proposal in evaluation["candidate_provider_receipts"]:
                verdict = verdicts[proposal["candidate_id"]]
                notes.append({
                    "edit": str(proposal["patch_payload"].get("edit", ""))[:400],
                    "verified": bool(verdict["oracle_ok"]),
                    "compile_ok": bool(verdict["compile_ok"]),
                    "scope_ok": bool(verdict["scope_ok"]),
                })
            entry = {"receipt_hash": receipt["receipt_hash"],
                     "execution_hash": receipt["portfolio_execution_hash"],
                     "case_id": receipt["case_id"], "family": design,
                     "category": category(design), "oracle_ok": receipt["oracle_ok"],
                     "notes": notes}
            entries[receipt["receipt_hash"]] = entry
        except (ValueError, OSError, KeyError, TypeError):
            rejected["invalid_evidence"] += 1
    return list(entries.values()), dict(rejected)


def bank(entries):
    unique = {e["receipt_hash"]: e for e in entries}
    return signed({"schema_version": "r3e-experience-bank-v1", "enabled": True,
                   "entries": [unique[key] for key in sorted(unique)]})


def initial_bank(root):
    return verify_signed(read(Path(root) / "competition/manifests/history_memory.json"))


def snapshot(root, state, operation, *, evolving=False, approve=None):
    """New observations become eligible at the next round, never mid-round."""
    root, state = Path(root), Path(state)
    target = state / "experience" / (operation + ".json")
    if target.exists():
        return verify_signed(read(target))
    # Exploration uses one validated memory version. All later observations are
    # archived separately, never silently injected into the next round's prompt.
    if evolving and operation.startswith("R") and operation != "R000":
        first = state / "experience/R000.json"
        if first.exists():
            return freeze(target, verify_signed(read(first)))
    if evolving and operation == "T1" and (state / "final_selection.json").exists():
        from competition.services.balanced_final import verify_selection
        selection = verify_selection(read(state / "final_selection.json"))
        return freeze(target, selection["selected_memory"])
    initial = bank([])
    entries = []
    previous = initial
    if evolving and operation.startswith("R"):
        entries = list(initial_bank(root)["entries"])
        completed_contexts = sorted(p for p in (state / "experience").glob("R[0-9][0-9][0-9].json")
                                    if p.stem < operation)
        if completed_contexts:
            previous = verify_signed(read(completed_contexts[-1]))
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
                paths.append(state / "replays" / receipt["artifact_id"] / "receipt.json")
        extra, _ = collect(paths)
        entries.extend(extra)
    elif evolving and operation == "T1":
        # Freeze exactly the context used by the last promotion gate. Final
        # evaluation does not activate an untested new experience snapshot.
        contexts = sorted((state / "experience").glob("R[0-9][0-9][0-9].json"))
        if contexts:
            return freeze(target, verify_signed(read(contexts[-1])))
    proposed = bank(entries)
    if evolving and operation.startswith("R") and proposed != previous:
        freeze(state / "experience/proposals" / (operation + ".json"), proposed)
        if approve is None:
            raise ValueError("new experience requires paired no-regression validation")
        if not approve(previous, proposed):
            proposed = previous
    return freeze(target, proposed)


class ExperienceMemory:
    def __init__(self, value):
        self.value = deepcopy(verify_signed(value))
        self.memory_hash = value["result_hash"]

    def retrieve(self, artifact, *, limit=6, max_chars=5000):
        name = family(artifact.get("top_module") or artifact.get("case_id", ""))
        kind = category(name)
        ranked = sorted(self.value["entries"], key=lambda e: (
            e["family"] != name, e["category"] != kind, not e["oracle_ok"], e["receipt_hash"]))
        selected, seen, size = [], set(), 0
        for entry in ranked:
            if entry["family"] != name and entry["category"] != kind:
                continue
            for note in entry["notes"]:
                key = hash_payload(note)
                if key in seen:
                    continue
                item = {"family": entry["family"], **note}
                length = len(str(item))
                if size + length > max_chars:
                    continue
                seen.add(key); selected.append(item); size += length
                if len(selected) == limit:
                    return selected
        return selected
