"""Red-only public-design curricula; no authored design advice is delivered to Blue."""

import re

VERSION = 'public_fsm_trace_curriculum_v4'
CURRICULUM_POLICY = {
    'version':VERSION,'designs':['prob023','prob003','prob017'],'source':'prior online public observations only',
    'first_two_rounds':'one localized fault; preserve timing and group boundaries',
    'after_failure':'single localized fault, regardless of scheduled round',
    'boundary_gate':'at least two distinct successful online public repairs and the immediately preceding round repaired successfully',
    'linked_fault_gate':'round five plus boundary gate',
    'enforcement':'reject candidates outside stage before public admission; no prepared replacement',
    'prob003_local_fault_unit':'one eligible next-state RHS expression, including a two-target branch swap within the global two-token limit',
    'prob003_retry_scope':'ban failed public transition sites, never the entire transition class',
    'prob003_curriculum':{'version':'late_bit_miss_path_boundary_v1',
        'rounds':['late_bit_decision','late_miss_progression','earlier_miss_progression','single_boundary_if_public_success','distinct_boundary_transfer_if_public_success'],
        'boundary_gate':'round four or five and at least one distinct prior online public repair success',
        'compound_faults':False,'development_seed':None,'sources':'clean public design and current-run online public evidence only'},
    'candidate_identity':'all materialized proposals are remembered, including deterministic rejected candidates',
}


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
    'prob023': (
        'Analyze the public Gray-counter specification together with the visible testbench. Internally trace '
        'the first eight rising edges after reset: old/new binary decode, increment register, Gray wire and output. '
        'A multi-register feedback implementation may already produce the required two-clock cadence; '
        'do not add a toggle/enable simply because the specification says every two cycles. '
        'Check output phase against public expected values before altering correct registers or latency. '
        'Gray-to-binary decoding has dependencies between bits: blindly replacing chained blocking assignments '
        'with nonblocking assignments makes later bits read old register values. Evaluate dependent expressions '
        'from the intended same-cycle inputs. Prefer the smallest repair supported by public evidence, '
        'then recheck all bits, wraparound, asynchronous reset and output hold. '
        'On correction, address the actual public failing cycle instead of repeating a generic rewrite. '
        'Return only complete files/edit JSON; do not output your internal trace.'),
    'prob003': (
        'Build a consumption table from the public specification BEFORE editing the FSM: for each bit '
        'position record the consumed prefix, whether it still matches the target prefix, and the current '
        'candidate successor for input 0 and input 1. Every rising edge consumes exactly one bit; '
        'a mismatch changes prefix validity but must not restart the group position. '
        'Use public_group_worksheet, public_fault_focus and public_previous_patch_feedback when available. '
        'Read the mechanically decoded input-0/input-1 branch table before changing ternary polarity; '
        'your prose description must agree with the actual code. A repeated unchanged failure or a '
        'formatting-only patch is not progress. A state-context conflict is a localization hint, not a reference answer. '
        'Use PUBLIC_FSM_TRACE records as observed evidence. Trace both a matching '
        'group and a following mismatching group without reset. A terminal state already means the last '
        'group has completed: the NEXT rising edge must consume the next group first bit, rather than '
        'discarding it in a return-to-idle bubble. Derive the destination from consumed input, not state names. '
        'For a failure on the first group, check earlier prefix transitions before changing terminal arms; '
        'for a later-group failure, follow the trace across the boundary. Repair every independently '
        'demonstrated fault, while preserving unaffected transitions, reset and output phase. '
        'Changing an unused sensitivity-list input does not repair a wrong transition. After correction, '
        'do not repeat an unchanged failed implementation or flip an unrelated earlier branch; identify '
        'the first observed state/prefix divergence using the supplied public trace. '
        'Return complete files/edit JSON only; keep your working table internal.'),
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
    'prob023': [
        'Begin with one reachable combinational conversion-expression fault. Keep every register, reset and output stage intact.',
        'Use a different single conversion operand/operator fault. Preserve clock cadence and output phase.',
        'After public success, vary a conversion bit or direction while preserving the register schedule; after failure stay localized.',
        'Test a new conversion/increment expression only if the success gate allows it; otherwise use one conversion fault.',
        'Only after two public repair successes and a latest pass consider two linked expression faults; otherwise keep one localized fault.',
    ],
    'prob003': [
        'Begin with one reachable prefix-depth error in an intermediate-state transition, keeping terminal transitions, output '
        'decoding and reset unchanged. Pick a short public input path that exposes that one fault.',
        'Practice a different prefix transition on the failure path or a swapped true/false target within one RHS. If the latest online repair failed, '
        'reduce the diagnostic burden and avoid adding any boundary/output defect.',
        'After simpler public repairs succeed, practice the boundary following a matching group. Trace '
        'which clock consumes the last bit and the following first bit; keep output phase unchanged.',
        'After simpler public repairs succeed, practice the boundary following a nonmatching group with '
        'a different legal consecutive input history; preserve exclusive outputs and reset.',
        'Only after successful single-fault practice consider a linked transition/boundary defect. '
        'If repairs still fail, stay with one simple unresolved transition rather than stacking faults.',
    ],
}

BLUE['prob017'] = 'Use the public waveform contract and tests to trace PRE-EDGE clk_cnt, cyc_cnt, div_flag and the registered output at reset release, count wrap and mode-switch boundaries. All nonblocking updates take effect together; the output uses old counter/mode values, not the just-updated state. Respect four-bit clock-count wrap, seven-bit cycle-count wrap, asynchronous active-low reset and parameterized even/odd periods. The original prose contains an inconsistent frequency example: the explicit public waveform contract is authoritative. Do not redesign the architecture merely to force an ideal average ratio. Diagnose the smallest expression fault from the public failing cycle/configuration and preserve declarations, clock edges, reset and output registration. On correction use actual expected/observed output evidence; recheck both period modes, parameter sets and wraparound. Return only complete files/edit JSON; do not output your internal trace.'
RED['prob017'] = ['Begin with one local count-wrap or increment expression fault; preserve reset, counter widths and sequential structure.', 'Use a different single local counter or output-threshold expression fault; do not rewrite the divider or parameters.', 'After public repair success, vary another count/mode expression; after failure stay with one simple RHS fault.', 'Only after the success gate opens, test transfer between mode switching and parameterized output thresholds.', 'Only after sufficient public repair success and a latest pass consider two linked expression substitutions; otherwise keep one local RHS fault.']


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
    observed=sorted(observations,key=lambda obs:obs['round'],reverse=True)
    latest = observed[0].get('label') if observed else None
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
    stage=curriculum_stage(carrier_id,round_index,observations)
    focus=RED[key][round_index-1]
    if key=='prob003':
        focus=sequence_focus(round_index,stage,latest)
    elif key=='prob017' and stage['stage']=='single_local_fault':
        focus=('Generate one compatible token substitution inside a non-reset sequential RHS expression. '
               'Preserve parameters, widths, reset branches, clock edges and output registration. '
               'Prefer a different eligible public counter/threshold site; do not add guards or branches.')
    elif key=='prob023' and stage['stage']=='single_local_fault':
        focus=('Generate one localized conversion-expression fault; preserve all register timing and output phase. '
               'Do not escalate to increment or linked faults before the success gate opens.')
    return {
        'stage':stage['stage'],'hard_constraints':stage,
        'version': 'late_bit_miss_path_boundary_v1' if key=='prob003' else VERSION, 'design': key, 'round': round_index,
        'focus': focus, 'scheduled_focus_suspended':focus!=RED[key][round_index-1], 'adaptation': adaptation,
        'priority': 'Apply the feedback adaptation first; reduce complexity after a failed repair even when the scheduled focus suggests a later-stage combination.',
        'latest_online_public_label': latest,
        'diversity': (
            'Across the five rounds, use at most one pure comparison-constant substitution. '
            'Use the same numeric value as the same mutation even if underscores, leading zeros or radix spelling differ. '
            'Choose mechanisms, not cosmetic edits; correct parentheses and compilation before considering a proposal. '
            'Respect all excluded implementations and the unchanged public admission tests.'),
        'scope': 'Only public design, round schedule and prior online public observations; no exam answers, reference-arm outcomes or validation scores.',
    }


def curriculum_stage(carrier_id,round_index,observations):
    key=design_key(carrier_id)
    observed=sorted(observations,key=lambda obs:obs['round'],reverse=True)
    successes=len({obs['source_hash'] for obs in observed if obs['label']=='public_pass_single_sample_hidden_unknown'})
    latest_pass=bool(observed and observed[0]['round']==round_index-1
                     and observed[0]['label']=='public_pass_single_sample_hidden_unknown')
    if key=='prob003':
        # One demonstrated online success permits a single boundary exercise;
        # never stack faults, and never consult validation or exam outcomes.
        unlocked=round_index>=4 and successes>=1
        preferences=(['s5','sf5'] if round_index==1 else ['sf5','sf4','s5'] if round_index==2 else
            ['sf4','sf3','sf2','s4'] if round_index==3 else ['sf6','s6'] if unlocked else ['sf5','s5','sf4'])
        return {'design':key,'stage':'boundary_transfer' if unlocked else 'single_local_fault',
            'online_public_successes':successes,'latest_online_passed':latest_pass,
            'maximum_token_substitutions':2,'maximum_next_state_expressions':1,
            'preserve_register_schedule':True,'allow_group_boundary_changes':unlocked,
            'preferred_states':preferences,'local_scope':'one next-state RHS only; preserve output logic, reset, idle and default; no compound faults',
            'lesson':CURRICULUM_POLICY['prob003_curriculum']['rounds'][round_index-1]}
    unlocked=(key not in {'prob023','prob003','prob017'}) or (round_index>2 and successes>=2 and latest_pass)
    linked=(key not in {'prob023','prob003','prob017'}) or (round_index==5 and unlocked)
    return {'design':key,'stage':'linked_transfer' if linked else 'boundary_transfer' if unlocked else 'single_local_fault',
            'online_public_successes':successes,'latest_online_passed':latest_pass,
            'maximum_token_substitutions':2 if linked or key=='prob003' else 1,
            'maximum_next_state_expressions':2 if linked else 1,
            'preserve_register_schedule':True,'allow_group_boundary_changes':unlocked,
            'local_scope':('conversion expressions only' if key=='prob023' and not unlocked else
                'intermediate next-state targets only; preserve idle, output and terminal-state arms' if key=='prob003' and not unlocked else
                'one non-reset divider RHS expression; preserve register timing, widths and parameter declarations' if key=='prob017' else
                'single expression/transition; linked expressions only at the last stage')}


def curriculum_violation(public,proposal,round_index,observations):
    key=design_key(public['carrier_id'])
    if key not in {'prob023','prob003','prob017'} or proposal.get('status')!='proposal':
        return None
    from .online_mutation import tokens
    before,after=tokens(public['clean_rtl']),tokens(proposal['buggy_rtl'])
    stage=curriculum_stage(public['carrier_id'],round_index,observations)
    detail='Current stage: '+str(stage)+'. '
    if len(before)!=len(after):
        return detail+'Use only existing expression/transition token substitutions; preserve declarations and register scheduling.'
    changed=[i for i,(old,new) in enumerate(zip(before,after)) if old!=new]
    if len(changed)>stage['maximum_token_substitutions']:
        return detail+'Use one localized fault until public repair success unlocks the later stage.'
    clean=public['clean_rtl'];allowed=set()
    def allow(start,end):
        allowed.update(range(len(tokens(clean[:start])),len(tokens(clean[:end]))))
    if key=='prob023':
        # Only RHS expressions; assignments, registers and reset branches stay intact.
        pattern=r'(?:bin_out\s*\[\s*\d+\s*\]|assign\s+gray_wire)\s*=\s*([^;]+);'
        if stage['allow_group_boundary_changes']:
            pattern=r'(?:bin_out\s*\[\s*\d+\s*\]|assign\s+gray_wire|bin_add_wire)\s*(?:<=|=)\s*([^;]+);'
        for match in re.finditer(pattern,clean):allow(*match.span(1))
    elif key=='prob017':
        for site in divider_sites(public):allowed.update(range(site['token_start'],site['token_end']))
    else:
        sites=transition_sites(public)
        eligible=[site for site in sites if sequence_site_allowed(site,stage)]
        touched=[site for site in sites if any(site['token_start']<=i<site['token_end'] for i in changed)]
        if len(touched)>stage['maximum_next_state_expressions']:
            return detail+'Only one next-state RHS expression may change in the local stage. A two-target swap inside ONE expression is allowed; changing two expressions is not.'
        for site in eligible:allowed.update(range(site['token_start'],site['token_end']))
    if any(i not in allowed for i in changed):
        return detail+'Mutation is outside the allowed RHS expressions or changes a protected group boundary. Choose a distinct simpler local fault.'
    return None



def transition_sites(public):
    """Unmodified public source locations, not generated mutations or fallback questions."""
    if design_key(public['carrier_id'])!='prob003':return []
    from .online_mutation import tokens
    clean=public['clean_rtl'];terminal=set(re.findall(r'\bpstate\s*==\s*(\w+)',clean))
    arms=list(re.finditer(r'(?m)^\s*(\w+)\s*:\s*',clean));sites=[]
    for i,arm in enumerate(arms):
        end=arms[i+1].start() if i+1<len(arms) else clean.find('endcase',arm.end())
        if end<arm.end():continue
        for ordinal,match in enumerate(re.finditer(r'\bnstate\s*=\s*([^;]+);',clean[arm.end():end])):
            start=arm.end()+match.start(1);finish=arm.end()+match.end(1)
            sites.append({'site_id':f'{arm[1]}:nstate:{ordinal}','state':arm[1],
                'clean_rhs':match[1],'line':clean[:start].count('\n')+1,
                'token_start':len(tokens(clean[:start])),'token_end':len(tokens(clean[:finish])),
                'protected_boundary':arm[1] in terminal|{'idle','default'}})
    return sites


def changed_transition_sites(public,proposal):
    if not isinstance(proposal.get('buggy_rtl'),str):return []
    from .online_mutation import tokens
    before,after=tokens(public['clean_rtl']),tokens(proposal['buggy_rtl'])
    if len(before)!=len(after):return []
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    return [site['site_id'] for site in transition_sites(public)
            if any(site['token_start']<=i<site['token_end'] for i in changed)]


def transition_inventory(public,round_index,observations,rejected_edits=(),blocked_site_ids=()):
    if design_key(public['carrier_id'])!='prob003':return None
    from .blue_provider import apply_text_edits, BlueOutputViolation
    stage=curriculum_stage(public['carrier_id'],round_index,observations);counts={}
    for edits in rejected_edits:
        try:mutant=apply_text_edits(public['clean_rtl'],edits)
        except (BlueOutputViolation,TypeError,KeyError,ValueError):continue
        for site_id in changed_transition_sites(public,{'buggy_rtl':mutant}):counts[site_id]=counts.get(site_id,0)+1
    sites=[]
    for site in transition_sites(public):
        if not sequence_site_allowed(site,stage):continue
        sites.append({k:site[k] for k in ('site_id','state','line','clean_rhs')}|
                     {'lesson_priority':stage.get('preferred_states',[]).index(site['state']) if site['state'] in stage.get('preferred_states',[]) else 99,
                      'previous_candidate_count':counts.get(site['site_id'],0),
                      'blocked_this_retry':site['site_id'] in blocked_site_ids})
    sites.sort(key=lambda s:(s['blocked_this_retry'],s['previous_candidate_count']>0,s.get('lesson_priority',99),s['previous_candidate_count'],s['line']))
    return {'instruction':'These are unmodified public source locations, not proposed questions. Generate your own mutation online. '
        'Prefer an untried eligible site and submit up to four distinct candidates across sites. '
        'Do not repeat any excluded implementation. A branch swap within one eligible RHS is one fault. '
        'Every candidate still needs compile, public functional, structural and isolation qualification.',
        'stage':stage['stage'],'sites':sites}


def transfer_summary(carrier_id,patch):
    # These checks are guidance, not claims of correctness beyond the observed public pass.
    key=design_key(carrier_id)
    checks={
        'prob017':[
            'Trace pre-edge counter/mode values before altering registered output timing.',
            'Recheck both even/odd period modes, finite-width counter wraps and the public parameterized waveform contract.',
            'Preserve asynchronous reset and parameter declarations; do not generalize one repaired constant to every divider expression.'],
        'prob023':[
            'Trace old/new decode, increment and output values against public test cycles before adding a cadence enable.',
            'Preserve dependent bit evaluation; changing blocking/nonblocking assignments can change the function.',
            'Recheck reset, output phase and wraparound; a successful operator repair is not proof that all counter schedules are correct.'],
        'prob003':[
            'Use the public six-position worksheet to separate consumed-prefix depth from prefix validity; a mismatch must not restart a group.',
            'Use observed pre-state/next-state/post-state traces to locate the first divergence, then check two consecutive groups without reset.',
            'Preserve correct terminal-state transitions unless public evidence proves they are faulty.',
            'Derive transition polarity from the current public specification and inputs; do not copy a previous state target blindly.'],
    }.get(key,['Check the current public specification and timing before reusing a previously successful patch.'])
    changed=[line[:240] for line in patch.splitlines() if line.startswith(('+','-')) and not line.startswith(('+++','---'))][:6]
    return {'changed_lines':changed,'checks_on_transfer':checks,
            'scope':'Observed public success only; recheck applicability on a new task.'}


def divider_sites(public):
    if design_key(public['carrier_id'])!='prob017':return []
    from .online_mutation import tokens
    clean=public['clean_rtl'];sites=[]
    for i,match in enumerate(re.finditer(r'\b(clk_cnt|cyc_cnt|div_flag|clk_out_r)\s*<=\s*([^;]+);',clean)):
        if not re.search(r'\b(?:clk_cnt|cyc_cnt|div_flag|div_e|div_o|M_N|c89)\b',match[2]):continue
        start,end=match.span(2)
        sites.append({'site_id':f'{match[1]}:rhs:{i}','register':match[1],'clean_rhs':match[2],
            'line':clean[:start].count('\n')+1,'token_start':len(tokens(clean[:start])),
            'token_end':len(tokens(clean[:end]))})
    return sites


def divider_inventory(public,rejected_edits=(),blocked_site_ids=()):
    if design_key(public['carrier_id'])!='prob017':return None
    from .blue_provider import apply_text_edits,BlueOutputViolation
    counts={}
    for edits in rejected_edits:
        try:mutant=apply_text_edits(public['clean_rtl'],edits)
        except (BlueOutputViolation,ValueError,TypeError,KeyError):continue
        for site in changed_public_sites(public,{'buggy_rtl':mutant}):counts[site]=counts.get(site,0)+1
    sites=[{k:s[k] for k in ('site_id','register','clean_rhs','line')}|
           {'previous_candidate_count':counts.get(s['site_id'],0),'blocked_this_retry':s['site_id'] in blocked_site_ids}
           for s in divider_sites(public)]
    sites.sort(key=lambda s:(s['blocked_this_retry'],s['previous_candidate_count']>0,s.get('lesson_priority',99),s['previous_candidate_count'],s['line']))
    return {'instruction':'Unmodified public divider source sites only; generate your own online mutation. '
        'Prefer untried eligible sites; keep parameters, reset, widths and register scheduling intact. '
        'Submit up to four distinct compatible expression candidates, not a rewritten divider or added conditional.',
        'sites':sites}


def changed_public_sites(public,proposal):
    if design_key(public['carrier_id'])!='prob017':return changed_transition_sites(public,proposal)
    if not isinstance(proposal.get('buggy_rtl'),str):return []
    from .online_mutation import tokens
    before,after=tokens(public['clean_rtl']),tokens(proposal['buggy_rtl'])
    if len(before)!=len(after):return []
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    return [site['site_id'] for site in divider_sites(public) if any(site['token_start']<=i<site['token_end'] for i in changed)]


def gray_inventory(public, round_index, observations, rejected_edits=()):
    """Expose original eligible expressions, never candidate bugs or solutions to Blue."""
    if design_key(public['carrier_id']) != 'prob023':
        return None
    from .online_mutation import tokens
    from .blue_provider import apply_text_edits, BlueOutputViolation
    clean = public['clean_rtl']
    stage = curriculum_stage(public['carrier_id'], round_index, observations)
    pattern = r'(?:bin_out\s*\[\s*\d+\s*\]|assign\s+gray_wire)\s*=\s*([^;]+);'
    if stage['allow_group_boundary_changes']:
        pattern = r'(?:bin_out\s*\[\s*\d+\s*\]|assign\s+gray_wire|bin_add_wire)\s*(?:<=|=)\s*([^;]+);'
    mutants = []
    for edits in rejected_edits:
        try:
            mutant = tokens(apply_text_edits(clean, edits))
            if len(mutant) == len(tokens(clean)):
                mutants.append(mutant)
        except (BlueOutputViolation, ValueError, TypeError, KeyError):
            continue
    sites = []
    for index, match in enumerate(re.finditer(pattern, clean)):
        start, end = len(tokens(clean[:match.start(1)])), len(tokens(clean[:match.end(1)]))
        before = tokens(clean)[start:end]
        sites.append({'site_id':f'gray_rhs:{index}', 'line':clean[:match.start(1)].count('\n')+1,
            'clean_rhs':match[1], 'previous_candidate_count':sum(m[start:end] != before for m in mutants)})
    sites.sort(key=lambda x:(x['previous_candidate_count'],x['line']))
    return {'stage':stage['stage'], 'sites':sites,
        'instruction':'These are original eligible public expression sites, not generated questions. '
            'Generate your own distinct one-token operator or index substitution at an allowed site; '
            'an attempted operator does not exhaust other operators or indices at that expression. '
            'Preserve sequential assignments and register schedule. Do not introduce cadence logic. '
            'Do not copy excluded exam/validation/previous implementations. '
            'Submit distinct candidates across sites. All original qualification checks remain mandatory. '
            'An exhaustion claim is not a proof that all eligible mutations have been attempted.'}


def sequence_site_allowed(site, stage):
    # Boundary permission never grants mutations to initialization/default arms.
    return site['state'] not in {'idle','default'} and (stage['allow_group_boundary_changes'] or not site['protected_boundary'])


def sequence_focus(round_index, stage, latest):
    lessons = [
        'Begin at the last-bit decision near group completion. Prefer one late matching-path next-state expression; keep the first five positions, all outputs and both terminal boundaries correct. Avoid an early-prefix defect that fails every matching group before any boundary can be observed.',
        'Teach completion after an earlier mismatch. Prefer one late nonmatching-path progression expression; every remaining input bit must still be consumed before the failure result. Preserve the matching path and both terminal boundaries.',
        'Move one step earlier along the nonmatching path using a distinct local progression fault. Separate position within the six-bit group from whether its prefix still matches. Keep output polarity and registration intact.',
        'After a prior public repair success, introduce one terminal next-state expression fault to study the next group first bit after a nonmatching group. Keep the matching terminal and all earlier paths intact. Without prior success, stay with a distinct simple late-bit or late-miss progression fault.',
        'After a prior public repair success, test transfer at a distinct group boundary using another legal local fault and input history; keep exactly one changed next-state expression. Without prior success, seek one simpler late-group repair instead of composing failures.'
    ]
    feedback = ('The latest online patch failed. Inspect its actual blue_patch and public_evidence: if it rewrites output polarity but leaves the faulty transition, choose a simpler next-state exercise whose unchanged outputs separate these explanations. '
        if latest in {'public_functional_failure_single_sample_unconfirmed','valid_no_op_single_sample_unconfirmed'} else '')
    return (lessons[round_index-1]+' '+feedback+
        'Author a learnable, distinct functional challenge from the clean PUBLIC design. Internally trace a concrete public-test input history with consumed-bit position, pre-state, input and next-state; compare two consecutive groups without reset when applicable. '
        'Do not disclose a repair or explanatory worksheet to Blue. Do not mutate output assignments, reset, idle/default or multiple expressions. '
        'Boundary edits are legal only when hard_constraints allows them. Generate mutations online, not from a prepared question or historical seed. '
        'All excluded exam/validation implementations, compilation, public witness and structural checks still apply.')
