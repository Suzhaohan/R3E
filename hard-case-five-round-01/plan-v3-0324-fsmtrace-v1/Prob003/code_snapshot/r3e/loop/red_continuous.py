"""No-prediction Red generation from a frozen public observation bank."""
from __future__ import annotations

import os
import re
from copy import deepcopy
import time

from .blue_provider import apply_text_edits, BlueOutputViolation
from .red_design import validate_design, actual_diff, RedDesignOutputViolation
from .red_regression import save_new
from .targeted_prompts import red_guidance, transition_inventory, design_key
from .red_syntax import normalize_condition_edits
from . import red_retry, online_mutation
from r3e.protocol.hashing import canonical_json, hash_payload
from r3e.providers.openai_compatible import OpenAICompatibleProviderViolation

VERSION = "continuous_red_public_feedback_v1"
FOCUS_FIELDS = {"version", "carrier_id", "mechanism", "selection", "seed_edits", "history", "provenance"}
TARGET_FIELDS = {"version", "snapshot_id", "committed_round", "snapshot_hash", "state_hash",
                 "repair_budget", "learning_policy", "retrieval_policy", "eligible_entry_count",
                 "spec_selected_experience"}
TARGET_TOKEN_CAP = 6144
SYSTEM = """Generate one coherent defective RTL implementation from the clean carrier and unchanged spec.
Use actual prior public repair observations to challenge the incoming Blue state. You may revisit an
unresolved behavior, test a previously repaired mechanism with a new case, or explore uncovered behavior.
Public passes are not proofs of correctness; single failures are unconfirmed observations, not stable weaknesses.
Blue may now have additional experience. Do not assume a previous failure still applies to its current state.
The target_blue view states the actual incoming repair budget, update/retrieval policy and spec-selected
experience. Challenge what that state has not demonstrated it can handle. Its entries are provisional
public-passing episodes, not verified general rules. The view is not a prediction of Blue's next patch.
Return one JSON object: {"candidates":[{"edits":[{"find":"unique clean RTL text","replace":"mutated text"}],
"violated_requirement":"concrete triggering history and changed output","spec_basis":"short spec citation"}, ...]},
with up to FOUR distinct candidates using eligible sites/mechanisms within the actual current stage, or {"abstain":"reason"}.
Obey round_curriculum hard_constraints and its current stage before choosing a defect.
Do not escalate difficulty merely because the round number increases.
Obey mutation_constraints. Only change at most two existing compatible operand/operator tokens, or swap
one existing two-operand concatenation. In Prob003 a swap of the two existing ternary
state targets in ONE eligible next-state RHS is one local fault within the two-token cap.
Respect eligible_transition_sites and prefer untried locations. Do not add syntax tokens, new if guards, branches or declarations.
The program checks every candidate using public EDA and chooses the first qualified one; a written claim
is insufficient. Diversify within the current stage. In Prob003 local stage vary eligible intermediate transition
sites/target mappings; do not move to protected boundary/output sites to satisfy diversity.
For other designs use eligible history, comparison/slice, output or transition mechanisms as appropriate. Every candidate starts from the same unchanged clean RTL.
Preserve interfaces, parameters, dependencies, directives and all comments verbatim and in order.
Stay within the supplied edit budget. The mutant must compile, fail W_bug and pass W_preserve.
Use linked changes where useful; more changed code is not a reward. Start from clean RTL, not an old mutant.
When mechanism_focus is supplied, use its historical seed as a starting example, not a current failure
claim. Explore new variants of that mechanism and use the real previous-round observations to choose
the next challenge. Do not merely reproduce an earlier mutant or change formatting. Preserve the
unchanged spec and public checks. Initial source selection is human work, not automatic discovery.
Do not output a hypothetical Blue patch, guessed reasoning, an entire file, or extra fields.
Every find string must occur exactly once in clean_rtl; include surrounding lines to disambiguate.
Read generation_feedback and correct the stated rejection before proposing again.
When retry_control is supplied, obey its blocked_mechanisms and specific_diagnosis as mandatory
constraints overriding round_curriculum and mechanism_focus. Do not disguise the same failed
mechanism by changing only a bit, constant or operand. For Prob003, obey blocked_site_ids instead:
another eligible intermediate transition site remains legal; do not ban the entire state-transition class.
There is at most one corrective request. Never repeat an
excluded previous proposal, even across rounds. If no valid distinct defect is available, abstain.
You are breaking a correct implementation, not repairing it. A textual change alone is not a defect.
First trace a reachable input history from reset using the supplied public W_bug test. Identify an
executed expression or transition whose mutation changes a checked output compared with clean RTL.
Do not add dead code: an else-if repeating an earlier if condition is unreachable and changes nothing.
Do not insert redundant assignments or conditions that preserve behavior on the public stimulus.
In violated_requirement state the concrete behavior and triggering input/history you intend to break;
this remains an unverified claim, not a test result. Actual compilation and simulation decide admission.
Use generation_feedback.expected_public_results and actual_public_results to correct the mutation.
If W_bug still passes, choose a different reachable operation; do not repeat or reformat the same edit.
If W_preserve fails, preserve that behavior while moving the defect elsewhere. Compilation failures
are not functional defects. A compound condition must be INSIDE one complete if parenthesis:
use `if ((condition_a) && (condition_b))`, never `if (condition_a) && (condition_b)`.
Apply this check to else-if as well. Keep bitwise and logical operators distinct. On retry, consider a different mechanism: bit order/slice, Boolean polarity,
comparison boundary, state transition target, or update phase, as appropriate to the public design.
"""
OBSERVATION_FIELDS = {"round", "slot_id", "carrier_id", "target_snapshot_hash", "mutant_hash",
                      "mutation_edits", "blue_patch", "public_rows", "public_evidence", "label", "source_hash"}


def admission_feedback(admission, proposal, *, round_index, attempt):
    """Only public admission evidence; no independent validation/exam evaluator input."""
    actual = {}
    evidence = {}
    for name in ("W_bug", "W_preserve"):
        cell = admission.get("suites", {}).get(name, {})
        if cell:
            actual[name] = cell.get("tier", "unknown")
            # Keep the earliest failure, rather than letting long traces crowd out feedback.
            lines = str(cell.get("log", "")).splitlines()
            important = [line for line in lines if "CHECK_FAIL" in line or "TESTBENCH PASS" in line]
            evidence[name] = "\n".join(important or lines)[:1800]
    reason = admission.get("reason", proposal.get("status", "unknown"))
    instructions = []
    if reason in {"curriculum_stage_violation","blocked_failed_transition_site"}:
        instructions.append(admission["note"])
    if proposal.get('grammar_error'):
        instructions.append(proposal['grammar_error'])
    if reason in {"duplicate_within_arm", "repeated_rejected_proposal"}:
        instructions.append("This implementation was already attempted. Generate a different functional mutation, not different formatting or a new explanation of the same edit.")
    if actual.get("W_bug") == "pass":
        instructions.append("W_bug still passes: the public test did not detect the intended bug. A text edit is insufficient. Change a reachable executed operation and trace a concrete checked output difference; do not insert dead or redundant branches. Public passing does not prove equivalence for all inputs.")
    if actual.get("W_preserve") == "fail":
        instructions.append("W_preserve fails: required preserved behavior was broken. Keep reset/guard behavior intact while introducing a distinct defect detected by W_bug.")
    if any(t not in ("pass", "fail") for t in actual.values()):
        instructions.append("Fix compilation or operational failures first: they do not qualify as functional defects. For a compound if/else-if, all operands and operators must be inside the condition parentheses: if ((A) && (B)), not if (A) && (B). Do not repeat a syntax error by changing only an operand.")
    if not instructions:
        instructions.append("Correct the stated rejection and obey unique find locations, interfaces, edit budget and the public test contract; do not repeat excluded proposals.")
    feedback = {"round": round_index, "attempt": attempt, "reason": reason,
                "edits": proposal.get("mutation_edits"),
                "expected_public_results": {"W_bug": "fail", "W_preserve": "pass"},
                "actual_public_results": actual, "public_test_evidence": evidence,
                "correction": " ".join(instructions)}
    if admission.get("original_reason"):
        feedback["original_reason"] = admission["original_reason"]
    if admission.get("reused_from"):
        feedback["reused_from"] = admission["reused_from"]
    if any(t == 'compile_fail' for t in actual.values()):
        source = proposal.get('buggy_rtl', '')
        lines = source.splitlines()
        diagnostics = []
        for suite, log in evidence.items():
            for line in log.splitlines():
                # Only the visible candidate source, not testbench/dependency
                # lines or evaluator paths. Keep original compiler wording.
                location = re.search(r'(?:^|\s)rtl/[^:\s]+:(\d+)(?::\d+)?:', line)
                if location:
                    number = int(location[1])
                    diagnostics.append({'suite': suite, 'line': number, 'message': line,
                        'source_context': [{'line': i + 1, 'text': lines[i]}
                            for i in range(max(0, number - 3), min(len(lines), number + 2))]})
        feedback['compilation_correction'] = {
            'kind': 'compiler_error', 'failed_edits': proposal.get('mutation_edits'),
            'candidate_source': source, 'diagnostics': diagnostics,
            'compiler_logs': evidence,
            'instruction': (
                'PRIORITY: correct the compiler errors in this failed proposal before selecting another mechanism. '
                'Use the exact source lines and compiler logs below. Keep the intended functional mutation; '
                'repair its syntax rather than changing a constant or operand while retaining the broken grammar. '
                'For if/else-if, put the complete expression inside the condition parentheses: '
                'if ((A) && (B)), never if (A) && (B). Do not alter && to & or change operands just to compile. '
                'Start edits from carrier.clean_rtl (not from candidate_source), returning the standard '
                'candidates JSON batch, each containing edits/violated_requirement/spec_basis. No full-file output. '
                'If syntax correction removes the intended functional defect, choose another reachable defect; '
                'compilation alone is insufficient. Local compiler and unchanged public tests will verify the result.')}
    return feedback


def validate_focus(focus, public):
    if focus is None:
        return
    if (not isinstance(focus, dict) or set(focus) != FOCUS_FIELDS or focus["version"] != "continuous_mechanism_seed_v1"
            or focus["carrier_id"] != public["carrier_id"] or focus["selection"] != "human_selected_development_seed"
            or not isinstance(focus["mechanism"], str) or not focus["mechanism"].strip()
            or set(focus["history"]) != {"challenge_id", "runs", "unrepaired", "label"}
            or focus["history"]["label"] != "historical_budgeted_failure_not_current_confirmation"):
        raise ValueError("invalid mechanism focus or historical evidence boundary")
    if (any(type(focus["history"][k]) is not int for k in ("runs", "unrepaired"))
            or not 0 <= focus["history"]["unrepaired"] <= focus["history"]["runs"]
            or focus["history"]["runs"] < 1):
        raise ValueError("invalid historical run counts")
    mutant = apply_text_edits(public["clean_rtl"], focus["seed_edits"])
    validate_design(public["clean_rtl"], mutant, public["top_module"])
    if (set(focus["provenance"]) != {"clean_hash", "seed_hash", "record_hashes"}
            or focus["provenance"]["clean_hash"] != hash_payload(public["clean_rtl"])
            or focus["provenance"]["seed_hash"] != hash_payload(mutant)
            or not focus["provenance"]["record_hashes"]):
        raise ValueError("mechanism seed provenance mismatch")


def materialize(raw, public):
    if isinstance(raw, dict) and set(raw) == {"abstain"} and isinstance(raw["abstain"], str) and raw["abstain"].strip():
        return {"status": "abstained", "reason": raw["abstain"]}
    if (not isinstance(raw, dict) or set(raw) != {"edits", "violated_requirement", "spec_basis"}
            or any(not isinstance(raw[k], str) or not raw[k].strip() for k in ("violated_requirement", "spec_basis"))):
        return {"status": "rejected", "reason": "output_schema"}
    raw = deepcopy(raw)
    original_edits = deepcopy(raw['edits'])
    raw['edits'], syntax_corrections = normalize_condition_edits(raw['edits'])
    try:
        mutant = apply_text_edits(public["clean_rtl"], raw["edits"])
        budget = validate_design(public["clean_rtl"], mutant, public["top_module"])
    except (BlueOutputViolation, RedDesignOutputViolation) as exc:
        return {"status": "rejected", "reason": str(exc), "mutation_edits": raw["edits"]}
    return {"status": "proposal", "buggy_rtl": mutant, "buggy_rtl_hash": hash_payload(mutant),
            "edit_budget": budget, "diff": actual_diff(public["clean_rtl"], mutant),
            "claims": {k: raw[k] for k in ("violated_requirement", "spec_basis")}, "mutation_edits": raw["edits"],
            "syntax_corrections": syntax_corrections, "original_mutation_edits": original_edits}


def materialize_batch(raw, public):
    if isinstance(raw, dict) and set(raw)=={'abstain'}:
        return materialize(raw,public)
    if isinstance(raw, dict) and set(raw)=={'candidates'} and isinstance(raw['candidates'],list) and 1<=len(raw['candidates'])<=4:
        raws=raw['candidates']
    elif isinstance(raw,dict) and set(raw)=={'edits','violated_requirement','spec_basis'}:
        # Legacy single output remains eligible, but receives the same hard gate.
        raws=[raw]
    else:
        return {'status':'rejected','reason':'candidate_batch_schema'}
    candidates=[]
    for raw in raws:
        proposal=materialize(raw,public)
        error=online_mutation.violation(public,proposal)
        if error:
            proposal.update(status='rejected',reason='mutation_grammar_violation',grammar_error=error)
        candidates.append(proposal)
    return {'status':'candidate_batch','candidates':candidates}


def observation_bank(observations, round_index, counter, cap=8192):
    """Most recent prior public observations first, whole records only; omissions stay audit-only."""
    bank, omissions = [], []
    for obs in reversed(observations):
        if set(obs) != OBSERVATION_FIELDS or not 0 < obs["round"] < round_index:
            raise ValueError("Red observation schema or round boundary mismatch")
        if counter.count(canonical_json([*bank, obs])) > cap:
            omissions.append({"source_hash": obs["source_hash"], "reason": "bank_token_limit"})
        else:
            bank.append(obs)
    return bank, omissions


def propose(public, observations, *, round_index, snapshot_hash, red_state_hash, seed,
            directory, client, counter, target_blue, target_omissions=(),
            context_tokens=131072, output_tokens=65536, mechanism_focus=None, rejected_edits=(), generation_feedback=()):
    validate_focus(mechanism_focus, public)
    if (set(target_blue) != TARGET_FIELDS or target_blue["version"] != "continuous_red_target_v1"
            or target_blue["snapshot_hash"] != snapshot_hash
            or target_blue["committed_round"] != round_index - 1
            or target_blue["snapshot_id"] != f"B_{round_index - 1}"):
        raise ValueError("Red target state does not match incoming Blue snapshot")
    directory.mkdir(parents=True, exist_ok=False)
    bank, omissions = observation_bank(observations, round_index, counter)
    payload = {"carrier": public, "target_blue": target_blue, "prior_public_observations": bank, 'mutation_constraints':online_mutation.CONTRACT}
    curriculum = red_guidance(public['carrier_id'], round_index, observations)
    if curriculum is not None:
        payload['round_curriculum'] = curriculum
    if generation_feedback:
        payload["generation_feedback"] = list(generation_feedback)
        # Current-slot retry controls are enforced by the scheduler as well as prompted.
        for feedback in reversed(generation_feedback):
            control=feedback.get('retry_control')
            if control and control.get('round')==round_index:
                payload['retry_control']=control
                if curriculum is not None:
                    payload['round_curriculum']['focus']=('Correct the diagnosed failure within the actual current stage, using an eligible unblocked transition site. Do not repeat excluded implementations or move to protected boundary/output sites.' if design_key(public['carrier_id'])=='prob003' else 'Correct the diagnosed failure using a different, unblocked reachable mechanism. The original round focus is suspended for this retry.')
                break
        # A transport failure must not erase the last actionable compiler error.
        for feedback in reversed(generation_feedback):
            if feedback.get('round') != round_index:
                continue
            if feedback.get('compilation_correction'):
                payload['compilation_correction'] = feedback['compilation_correction']
                break
            if feedback.get('actual_public_results'):
                break
    inventory=transition_inventory(public,round_index,observations,rejected_edits,
        red_retry.blocked_sites(generation_feedback,round_index))
    if inventory is not None:
        payload['eligible_transition_sites']=inventory
    if rejected_edits:
        payload["excluded_previous_proposals"] = {
            "instruction": "Generate a different defect from clean RTL. Do not repeat these previous proposals, including formatting-only variants.",
            "edits": list(rejected_edits)}
    if mechanism_focus is not None:
        payload["mechanism_focus"] = mechanism_focus
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": canonical_json(payload)}]
    size = counter.request(messages)
    record = {"version": VERSION, "round": round_index, "target_snapshot_hash": snapshot_hash,
              "red_state_hash": red_state_hash, "messages": messages, "request_hash": hash_payload(messages),
              "bank_bytes": canonical_json(bank), "bank_hash": hash_payload(bank), "omissions": omissions,
              "target_view_hash": hash_payload(target_blue), "target_omissions": list(target_omissions),
              "seed": seed, "counted_request_tokens": size, "output_tokens": output_tokens}
    # Exclusive durable record must precede any provider request.
    with (directory / "request.json").open("x") as f:
        f.write(canonical_json(record))
        f.flush()
        os.fsync(f.fileno())
    if counter.count(canonical_json(target_blue)) > TARGET_TOKEN_CAP:
        result = {"status": "request_too_large", "reason": "red_target_state_limit"}
    elif size + output_tokens > context_tokens:
        result = {"status": "request_too_large", "reason": "red_context_limit"}
    else:
        try:
            start = time.monotonic()
            with client.in_phase("red"):
                response = client.complete_json(messages=messages, seed=seed, maximum_output_tokens=output_tokens)
            save_new(directory / "response.json", {**response, "model_seconds": time.monotonic() - start})
            result = ({"status": "no_answer", "reason": "output_limit"}
                      if response.get("response_diagnostics", {}).get("finish_reason") == "length"
                      else materialize_batch(response["result"], public))
        except OpenAICompatibleProviderViolation as exc:
            diag = getattr(exc, "diagnostics", {}) or {}
            result = {"status": "no_answer" if diag.get("finish_reason") == "length" else "provider_failure",
                      "reason": type(exc).__name__, "diagnostics": diag}
    save_new(directory / "result.json", result)
    return result
