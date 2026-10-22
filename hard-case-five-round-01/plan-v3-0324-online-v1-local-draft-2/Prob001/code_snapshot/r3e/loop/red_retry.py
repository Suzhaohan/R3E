"""Public-only retry diagnosis and hard mechanism switches; no model/evaluator calls."""
import re

VERSION = 'online_diagnose_switch_no_replacement_v1'
POLICY = {'version': VERSION, 'max_online_attempts': 2,
          'failed_functional_mechanisms': 'blocked_for_rest_of_slot',
          'maximum_candidates_per_request': 4, 'second_invalid_proposal': 'record_empty_practice_no_replacement'}
NUMBER = re.compile(r"(?i)(\d+)'(s?)([bodh])([0-9a-f_xz?]+)\Z")


def number(text):
    match = NUMBER.fullmatch(text)
    if not match or any(c in match[4].lower() for c in 'xz?'):
        return None
    width = int(match[1])
    if not 0 < width <= 4096:
        return None
    try:
        value = int(match[4].replace('_', ''), {'b': 2, 'o': 8, 'd': 10, 'h': 16}[match[3].lower()])
    except ValueError:
        return None
    return width, bool(match[2]), value & ((1 << width) - 1)


def canonical_tokens(tokens):
    # Preserve width/signedness and all unknown-valued literals. Only normalize
    # known numeric values for identity; never rewrite candidate source.
    return [('verilog_number', *n) if (n := number(t)) is not None else t for t in tokens]


def conditions(tokens):
    result = []
    for i, token in enumerate(tokens[:-1]):
        if token != 'if' or tokens[i + 1] != '(':
            continue
        depth = 1
        end = i + 2
        while end < len(tokens) and depth:
            depth += (tokens[end] == '(') - (tokens[end] == ')')
            end += 1
        if not depth:
            result.append(tokens[i + 2:end - 1])
    return result


def mechanism(proposal):
    from r3e.knowledge.verilog_utils import safe_tokenize
    kinds = set()
    edits=proposal.get('mutation_edits')
    for edit in edits if isinstance(edits,list) else []:
        if not isinstance(edit,dict) or not isinstance(edit.get('find'),str) or not isinstance(edit.get('replace'),str):
            continue
        old, new = edit.get('find', ''), edit.get('replace', '')
        before, after = ([t.value for t in safe_tokenize(s)] for s in (old, new))
        if canonical_tokens(before) == canonical_tokens(after):
            continue
        old_conditions, new_conditions = conditions(before), conditions(after)
        if len(old_conditions) == len(new_conditions) and any(
            sum(t in ('&&', '||', '&', '|') for t in b) > sum(t in ('&&', '||', '&', '|') for t in a)
            for a, b in zip(old_conditions, new_conditions)):
            kinds.add('added_condition_guard')
        elif 'nstate' in before or 'nstate' in after:
            kinds.add('state_transition')
        elif ('if' in before or 'if' in after) and old_conditions != new_conditions:
            kinds.add('comparison_change')
        elif re.search(r'a_tem\s*<=', old + new):
            kinds.add('history_update')
        elif re.search(r'(?:not_match|match)\s*(?:<=|=)', old + new):
            kinds.add('output_update')
        else:
            kinds.add('other')
    return sorted(kinds) or ['other']


def redundant_guard_details(proposal):
    """Explain only a narrow, provable implication; no guessed equivalence."""
    literal = r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+"
    equality = re.compile(r'\b([A-Za-z_]\w*)\s*==\s*(' + literal + r')')
    slice_eq = re.compile(r'\b([A-Za-z_]\w*)\s*\[\s*(\d+)\s*(?::\s*(\d+)\s*)?\]\s*==\s*(' + literal + r')')
    details = []
    edits=proposal.get('mutation_edits')
    for edit in edits if isinstance(edits,list) else []:
        if not isinstance(edit,dict) or not isinstance(edit.get('find'),str) or not isinstance(edit.get('replace'),str):
            continue
        old, new = edit.get('find', ''), edit.get('replace', '')
        if not re.search(r'&&|(?<!&)&(?!&)', new):
            continue
        for full in equality.finditer(old):
            if full[0] not in new:
                continue
            n = number(full[2])
            if n is None or n[1]:
                continue
            width, _, value = n
            for part in slice_eq.finditer(new):
                high, low = int(part[2]), int(part[3] or part[2])
                rhs = number(part[4])
                if part[1] != full[1] or not 0 <= low <= high < width or rhs is None or rhs[1]:
                    continue
                if rhs[0] != high - low + 1:
                    continue
                implied = (value >> low) & ((1 << (high - low + 1)) - 1)
                if implied == rhs[2]:
                    details.append(f'{full[0]} already guarantees {part[0]} (slice value {implied}). '
                                   'This added AND operand is already true whenever the original equality is true; '
                                   'it cannot create a fault by narrowing that equality. Remove this mutation route.')
    return details


def blocked_mechanisms(feedback, round_index):
    return sorted({m for f in feedback if f.get('round') == round_index
                   for m in f.get('retry_control', {}).get('blocked_mechanisms', [])})


def annotate(feedback, proposal, previous):
    actual = feedback['actual_public_results']
    blocked = set(blocked_mechanisms(previous, feedback['round']))
    kinds = mechanism(proposal)
    if feedback.get('reason') == 'blocked_failed_mechanism':
        kind = 'repeated_failed_mechanism'
    elif any(t == 'compile_fail' for t in actual.values()):
        kind = 'compilation_error'
    elif actual.get('W_bug') == 'pass':
        kind = 'no_observed_functional_fault'
        blocked.update(kinds)
    elif actual.get('W_preserve') == 'fail':
        kind = 'preserved_behavior_broken'
        blocked.update(kinds)
    else:
        kind = 'invalid_or_unavailable_proposal'
    reasons = redundant_guard_details(proposal) if kind == 'no_observed_functional_fault' else []
    if kind == 'repeated_failed_mechanism':
        reasons = ['Program blocked the previously failed mechanism: '+', '.join(sorted(set(kinds) & blocked))+'. Changing the operand did not change the mutation route. No further candidates using this failed mechanism are eligible in this slot.']
    if not reasons:
        reasons = [feedback['correction']]
    instruction = (
        'MANDATORY RETRY CONTROL, overriding the round curriculum and historical mechanism seed. '
        'The last proposal failed for the concrete reasons listed here. '
        'Change to an unblocked mechanism; changing a bit index, constant or operand within a blocked route is forbidden. '
        'If added_condition_guard is blocked, do not append ANY extra guard to an if condition. '
        'Instead mutate a reachable history update, comparison/slice, output assignment or state transition as appropriate. '
        'State a concrete triggering input/history and changed output in violated_requirement; it remains an unverified claim. '
        'For compilation_error, correct the reported syntax first without repeating the broken grammar. '
        'Return the required candidates JSON batch (each candidate has edits/violated_requirement/spec_basis), or abstain if no valid alternative exists. '
        'Only one corrective request is allowed; if both online candidate batches lack a qualified challenge, record an empty practice slot with no replacement.')
    feedback['retry_control'] = {'version': VERSION, 'round': feedback['round'], 'failure_kind': kind,
                                 'failed_mechanisms': kinds, 'blocked_mechanisms': sorted(blocked),
                                 'specific_diagnosis': reasons, 'instruction': instruction}
    feedback['correction'] = ' '.join(reasons) + ' ' + instruction
    return feedback
