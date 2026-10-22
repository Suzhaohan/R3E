"""Constrain online Red edits to grammar-preserving operations, not prepared bugs."""
import re
from r3e.knowledge.verilog_utils import safe_tokenize
from .red_retry import number, canonical_tokens

VERSION = 'online_constrained_candidate_batch_v1'
CONTRACT = {
    'version': VERSION, 'maximum_candidates_per_request': 4, 'maximum_token_substitutions': 2,
    'allowed_operations': ['same-width known-value literal substitution', 'integer index substitution',
        'operator substitution within an allowed group', 'declared state-constant substitution',
        'swap the two existing identifier/slice operands of one concatenation'],
    'operator_groups': [['==','!=','===','!=='],['^','&','|'],['&&','||'],['+','-'],['<<','>>'],['~','!']],
    'forbidden': ['insert/delete syntax tokens', 'append redundant if guards', 'change interfaces or declarations',
                  'reuse exam/validation/development-seed implementations', 'repeat attempted implementations'],
    'qualification': 'compile; W_bug must fail, W_preserve must pass; structural check required',
    'no_human_prepared_replacement': True,
}


def tokens(text):
    return [t.value for t in safe_tokenize(text)]


def violation(public, proposal):
    if proposal.get('status') != 'proposal':
        return None
    clean, mutant = public['clean_rtl'], proposal['buggy_rtl']
    before, after = tokens(clean), tokens(mutant)
    if canonical_tokens(before) == canonical_tokens(after):
        return 'The proposed change only changes numeric spelling/formatting; it creates no new mutation.'
    operand = r'[A-Za-z_]\w*(?:\[\s*\d+(?:\s*:\s*\d+)?\s*\])?'
    concat = re.compile(r'\{\s*('+operand+r')\s*,\s*('+operand+r')\s*\}')
    for match in concat.finditer(clean):
        swapped = clean[:match.start()] + '{'+match[2]+','+match[1]+'}' + clean[match.end():]
        if tokens(swapped) == after:
            return None
    if len(before) != len(after):
        return 'Syntax-token insertion/deletion is forbidden. Replace at most two existing operands/operators, or swap one existing two-operand concatenation. Do not append an if guard.'
    changed = [(a,b) for a,b in zip(before,after) if a!=b]
    if len(changed) > CONTRACT['maximum_token_substitutions']:
        return 'More than two token substitutions; choose a smaller reachable mutation.'
    constants = set()
    for block in re.finditer(r'\b(?:localparam|parameter)\b([^;]+);', clean, re.S):
        constants.update(re.findall(r'\b([A-Za-z_]\w*)\s*=', block[1]))
    groups = [set(g) for g in CONTRACT['operator_groups']]
    for old,new in changed:
        a,b=number(old),number(new)
        if a is not None and b is not None and a[:2]==b[:2] and a[2]!=b[2]:
            continue
        if re.fullmatch(r'\d[\d_]*',old) and re.fullmatch(r'\d[\d_]*',new):
            continue
        if any(old in group and new in group for group in groups):
            continue
        if old in constants and new in constants:
            continue
        return f'Unsupported token substitution {old!r} -> {new!r}. Use an allowed operator/literal/state-constant operation without changing grammar.'
    return None
