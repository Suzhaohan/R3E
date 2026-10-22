"""A source-derived edit grammar, not prepared questions or qualification results.

The model chooses an action and supplies its own public-spec rationale. No action
is admitted, simulated, ranked by private answers or substituted automatically here.
"""
import re
from . import targeted_prompts as lessons
from .blue_provider import apply_text_edits, BlueOutputViolation
from .online_mutation import tokens
from .red_retry import canonical_tokens
from r3e.knowledge.verilog_utils import safe_tokenize
from r3e.protocol.hashing import hash_payload

VERSION='source_transition_actions_v1'
SYSTEM='''Author a learnable functional RTL defect by selecting existing-token transition actions.
Return only one strict JSON object: {"candidate_actions":[{"action_id":"id from structured_transition_actions.available_actions","violated_requirement":"your concrete triggering history and output difference","spec_basis":"public spec basis"}, ...]} with 1 to 4 distinct actions, or {"abstain":"reason"}.
Do not return edits, replacement source or new expressions. Choose ONLY an available action from the current request. All actions start from the same clean public source. The program will render your choice literally and still require compilation, public functional witnesses, structural checks and exam/validation isolation. The list is an edit grammar, not a list of verified questions. Do not assume an action qualifies merely because it is listed.
Follow the current lesson, prior online public repairs and actual admission feedback. An unsuccessful action does not exhaust other replacements at that site. Prefer different actions across sites in a batch. Do not repeat actions, infer performance on private exams, or predict Blue's repair. No prepared replacement is supplied. Use only current public information and current-run observations.'''


def _render(public, site, positions, replacements):
    clean=public['clean_rtl'];lex=safe_tokenize(clean)
    arm=list(re.finditer(r'(?m)^\s*'+re.escape(site['state'])+r'\s*:',clean))
    if len(arm)!=1:raise ValueError('state arm is not unique')
    start=arm[0].start();end=clean.find(';',max(lex[i].end for i in positions))+1
    if end<=start:raise ValueError('missing statement end')
    old=clean[start:end];new=old
    for position,replacement in sorted(zip(positions,replacements),reverse=True):
        t=lex[position];new=new[:t.start-start]+replacement+new[t.end-start:]
    if clean.count(old)!=1:raise ValueError('generated context is not unique')
    return [{'find':old,'replace':new}]


def inventory(public, round_index, observations, rejected_edits=()):
    stage=lessons.curriculum_stage(public['carrier_id'],round_index,observations)
    lex=safe_tokenize(public['clean_rtl']);constants=set()
    for block in re.finditer(r'\b(?:parameter|localparam)\b([^;]+);',public['clean_rtl'],re.S):
        constants.update(re.findall(r'\b([A-Za-z_]\w*)\s*=',block[1]))
    previous=set()
    for edits in rejected_edits:
        try:previous.add(tuple(canonical_tokens(tokens(apply_text_edits(public['clean_rtl'],edits)))))
        except (BlueOutputViolation,KeyError,TypeError,ValueError):continue
    actions=[];omitted=0
    for site in lessons.transition_sites(public):
        if not lessons.sequence_site_allowed(site,stage):continue
        indices=[i for i in range(site['token_start'],site['token_end']) if lex[i].value in constants]
        operations=[('replace_target',[i],[target]) for i in indices for target in sorted(constants) if target!=lex[i].value]
        if len(indices)==2 and lex[indices[0]].value!=lex[indices[1]].value:
            operations.append(('swap_targets',indices,[lex[indices[1]].value,lex[indices[0]].value]))
        for operation,positions,replacements in operations:
            edits=_render(public,site,positions,replacements)
            rtl=apply_text_edits(public['clean_rtl'],edits)
            if tuple(canonical_tokens(tokens(rtl))) in previous:
                omitted+=1;continue
            body={'site_id':site['site_id'],'state':site['state'],'operation':operation,
                'token_indices':positions,'old_targets':[lex[i].value for i in positions],'new_targets':replacements}
            action={'action_id':hash_payload([public['clean_rtl'],body]),**body}
            actions.append(action)
    return {'version':VERSION,'stage':stage,'available_actions':actions,'previous_implementations_omitted':omitted,
        'instruction':'Select 1-4 distinct available action IDs and supply your own public-spec rationale. This list describes grammar-safe edits only; no qualification or expected Blue response is precomputed. Do not insert a condition or replace an entire RHS. A failed action does not block other targets at its site.'}


def decode(raw, public, available):
    if isinstance(raw,dict) and set(raw)=={'abstain'} and isinstance(raw['abstain'],str) and raw['abstain'].strip():return raw
    if not isinstance(raw,dict) or set(raw)!={'candidate_actions'} or not isinstance(raw['candidate_actions'],list) or not 1<=len(raw['candidate_actions'])<=4:
        raise ValueError('Return candidate_actions with 1-4 listed action IDs, not free-form edits or source.')
    known={a['action_id']:a for a in available['available_actions']};seen=set();candidates=[]
    sites={s['site_id']:s for s in lessons.transition_sites(public)}
    for choice in raw['candidate_actions']:
        if (not isinstance(choice,dict) or set(choice)!={'action_id','violated_requirement','spec_basis'}
            or any(not isinstance(choice[k],str) or not choice[k].strip() for k in choice)):
            raise ValueError('Each action needs action_id, violated_requirement and spec_basis strings.')
        key=choice['action_id']
        if key not in known or key in seen:raise ValueError('Action is unavailable, already attempted or duplicated in this batch; select distinct available IDs.')
        seen.add(key);a=known[key]
        candidates.append({'edits':_render(public,sites[a['site_id']],a['token_indices'],a['new_targets']),
            'violated_requirement':choice['violated_requirement'],'spec_basis':choice['spec_basis']})
    return {'candidates':candidates}
