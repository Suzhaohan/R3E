"""Public-design guidance shared across all Blue roles; Red uses online evidence only."""

VERSION = 'public_targeted_guidance_v1'

BLUE = {
    'prob001': (
        'Use the public specification and current RTL to check input history bit order, slice widths, '
        'comparison width/value, register update timing, asynchronous reset and nonmatching output hold/clear behavior. '
        'Internally trace a short input history clock by clock, including old and new register values; '
        'check every independent requirement before choosing the smallest justified repair. '
        'Fixing an obvious comparison constant alone may leave a separate defect. '
        'Prior public-passing examples are provisional: do not copy a constant-only repair into a different fault. '
        'Preserve specified output phase and legal behavior. Return only the required files/edit JSON; '
        'do not output your internal trace or extra fields.'),
    'prob003': (
        'Derive grouped input behavior from the public specification and visible stimulus. Internally trace '
        'clock number, position within the input group, pre-edge state, consumed input, next state and outputs. '
        'Check two consecutive groups and a matching/nonmatching pair: each sampled bit must be consumed exactly once, '
        'including the first bit after a group boundary. Nonoverlapping groups do not by themselves authorize '
        'an extra idle clock that discards a sampled bit. Do not rewrite all terminal states merely from the word '
        'nonoverlapping. Locate the actual incorrect transition and preserve correct transitions, reset and output phase. '
        'Return only the required files/edit JSON; do not output your internal trace or extra fields.'),
}

RED = {
    'prob001': [
        'Practice one reachable history slice/width or bit-order defect; preserve the output stage and reset. '
        'Use a distinct nearby variant rather than reproducing an excluded exam or validation implementation.',
        'Practice one registered comparison/output timing or hold/clear defect. Use a different mechanism '
        'from a previously repaired constant substitution and preserve the public reset guard.',
        'Practice comparison coverage together with history interpretation: distinguish a full pattern '
        'from a partial slice. Prefer a single new semantic fault and preserve already correct interfaces and timing.',
        'If preceding public repairs succeeded, combine two previously practiced mechanisms such as history '
        'interpretation and output hold. Otherwise use one simple new fault in the unresolved mechanism.',
        'Choose a new reachable follow-up that tests transfer across history and registered-output behavior; '
        'use a linked pair only after successful simpler repairs. Trace a concrete public failing input history.',
    ],
    'prob003': [
        'Begin with one simple intermediate-state transition defect, keeping terminal transitions, output '
        'decoding and reset unchanged. Pick a short public input path that exposes that one fault.',
        'Practice a different simple intermediate transition/path. If the latest online repair failed, '
        'reduce the diagnostic burden and avoid adding any boundary/output defect.',
        'After simpler public repairs succeed, practice the boundary following a matching group. Trace '
        'which clock consumes the last bit and the following first bit; keep output phase unchanged.',
        'After simpler public repairs succeed, practice the boundary following a nonmatching group with '
        'a different legal consecutive input history; preserve exclusive outputs and reset.',
        'Only after successful single-fault practice consider a linked transition/boundary defect. '
        'If repairs still fail, stay with one simple unresolved transition rather than stacking faults.',
    ],
}


def design_key(public_id):
    name = public_id.lower()
    return next((key for key in BLUE if key in name), None)


def blue_guidance(task_id):
    """No role, memory, validation result or evaluator input affects this instruction."""
    return BLUE.get(design_key(task_id), '')


def red_guidance(carrier_id, round_index, observations):
    key = design_key(carrier_id)
    if key is None:
        return None
    if not 1 <= round_index <= 5:
        raise ValueError('targeted curriculum requires five rounds')
    latest = observations[0].get('label') if observations else None  # bank is newest first
    failures = {'public_functional_failure_single_sample_unconfirmed', 'valid_no_op_single_sample_unconfirmed'}
    successes = sum(o.get('label') == 'public_pass_single_sample_hidden_unknown' for o in observations)
    adaptation = (
        'Latest online public repair failed: use exactly one simpler reachable semantic fault, '
        'prefer an intermediate path, and keep other mechanisms intact. Do not compound this failure.'
        if latest in failures else
        'Use actual prior online public repairs to choose a distinct follow-up. Public success is '
        'provisional and is not proof of mastery or of performance on unseen tasks.')
    if successes < 2:
        adaptation += ' Fewer than two public repair successes are recorded: keep this exercise single-fault.'
    return {
        'version': VERSION, 'design': key, 'round': round_index,
        'focus': RED[key][round_index - 1], 'adaptation': adaptation,
        'priority': 'Apply the feedback adaptation first; reduce complexity after a failed repair even when the scheduled focus suggests a later-stage combination.',
        'latest_online_public_label': latest,
        'diversity': (
            'Across the five rounds, use at most one pure comparison-constant substitution. '
            'Use the same numeric value as the same mutation even if underscores, leading zeros or radix spelling differ. '
            'Choose mechanisms, not cosmetic edits; correct parentheses and compilation before considering a proposal. '
            'Respect all excluded implementations and the unchanged public admission tests.'),
        'scope': 'Only public design, round schedule and prior online public observations; no exam answers, reference-arm outcomes or validation scores.',
    }
