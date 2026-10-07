"""Adapt existing runner evidence to the v2 case-memory package.

No model calls, oracle source, Red labels, or policy changes belong here.
Only the visible mismatch and Blue's independently verified patches are used.
"""
from collections import OrderedDict
import re

from r3e.knowledge import build_repair_episode, RepairEpisode
from r3e.knowledge.schema import SignalDivergence, VisibleFeedback
from r3e.protocol.hashing import hash_payload
from r3e.blue.portfolio.runtime_evidence import verify_runtime_evidence


def visible_feedback(evidence):
    """Normalize the existing visible mismatch text without inferring a trace.

    The old runner exposes a bounded list of mismatches, not a complete trace;
    unobserved passing outputs, deltas and temporal patterns stay unknown.
    """
    observed = evidence.get("runtime_observations", {})
    raw = observed.get("raw_mismatches", "")
    found = OrderedDict()
    for match in re.finditer(r"([^\s;,@]+)@cycle(\d+): got ([^\s,;]+), expected ([^\s,;]+)", raw):
        name, cycle, actual, expected = match.groups()
        signal = re.sub(r"\[\d+\]$", "", name)
        if signal in found:
            continue
        symptom = "x_or_unknown" if any(c in actual.lower() for c in "xz?") else "variable_offset"
        found[signal] = SignalDivergence(signal=signal, width=max(len(actual), len(expected)),
            first_cycle=int(cycle), expected=expected, observed=actual, symptom=symptom)
    return VisibleFeedback(oracle_stage="functional", compile_ok=True,
                           divergences=tuple(found.values()))


def validated_episode(payload):
    episode = RepairEpisode.create(**{k: v for k, v in payload.items()
                                     if k not in {"schema_version", "episode_hash"}})
    if episode.to_dict() != payload:
        raise ValueError("case-memory episode hash/schema mismatch")
    return episode


def entry_from_evaluation(evaluation, *, receipt_hash, design_cluster):
    if evaluation.get("portfolio_execution_hash") != hash_payload({
            k: v for k, v in evaluation.items() if k != "portfolio_execution_hash"}):
        raise ValueError("case-memory evaluation hash mismatch")
    context = verify_runtime_evidence(evaluation["runtime_evidence"])
    feedback = visible_feedback({"runtime_observations": {
        "raw_mismatches": context["observations"]["raw_by_k"]["6"]}})
    if not feedback.divergences:
        raise ValueError("case-memory requires readable visible failure evidence")
    verdicts = {v["candidate_id"]: v for v in evaluation["candidate_verification_receipts"]}
    attempts, passing = [], None
    for proposal in evaluation["candidate_provider_receipts"]:
        patch = proposal["patch_payload"]
        verdict = verdicts[proposal["candidate_id"]]
        if (proposal["patch_payload_hash"] != hash_payload(patch)
                or verdict["patch_hash"] != proposal["patch_payload_hash"]):
            raise ValueError("case-memory patch/verdict binding mismatch")
        verified = bool(verdict["oracle_ok"] and verdict["compile_ok"] and verdict["scope_ok"])
        tier = "visible_pass" if verified else "visible_fail" if verdict["compile_ok"] else "compile_fail"
        attempts.append({"verdict_tier": tier, "edit": str(patch.get("edit", "")),
                         "candidate_id": proposal["candidate_id"]})
        if verified:
            passing = patch["replacement_rtl"]
            break  # a causal chain stops at its own first verified fix
    episode = build_repair_episode(case_id=context["case_id"], design_cluster=design_cluster,
        buggy_rtl=context["buggy_rtl_source"], feedback=feedback, attempts=attempts,
        passing_candidate_rtl=passing,
        provenance={"execution_hash": evaluation["portfolio_execution_hash"],
                    "attempt_count": len(attempts)})
    return {"receipt_hash": receipt_hash, "execution_hash": evaluation["portfolio_execution_hash"],
            "case_id": context["case_id"], "family": design_cluster,
            "oracle_ok": passing is not None, "episode": episode.to_dict()}
