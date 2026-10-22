import importlib.util
import json
from pathlib import Path
import re
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
ex=module('transition_experiment',HERE/'experiment-transition-v1.py')
helpers=module('transition_feedback_fixtures',HERE/'tests/test_public_feedback.py')
helpers.ex=ex

@pytest.fixture(autouse=True)
def isolate_core():
    def owned(k):return k in ('r3e','experiments') or k.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)};paths=list(sys.path)
    for k in saved:sys.modules.pop(k)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):sys.modules.pop(k)
    sys.modules.update(saved);sys.path[:]=paths


def core():return helpers.core('Prob003')
def raw(edit):return dict(edits=[edit],violated_requirement='offline reachable public transition defect',spec_basis='unchanged public specification')
def arm(public,state,rhs):
    match=re.search(r'\b'+state+r':\s*nstate\s*=\s*([^;]+);',public['clean_rtl'])
    return dict(find=match[0],replace=match[0].replace(match[1],rhs))
def proposal(loop,public,edit):return loop.red.materialize_batch(dict(candidates=[raw(edit)]),public)['candidates'][0]


def test_one_branch_swap_is_local_fault_and_passes_real_public_qualification(tmp_path):
    loop,m,public=core();p=proposal(loop,public,arm(public,'s3','data?sf4:s4'))
    assert p['status']=='proposal'
    assert loop.targeted_prompts.curriculum_violation(public,p,5,[]) is None
    result=loop.red907.check_proposal(Path(m['carriers'][0]['package']),ex.read(m['carriers'][0]['suite_freeze']),p,tmp_path/'admission',seen=set())
    assert result['status']=='admitted'
    assert result['suites']['W_bug']['tier']=='fail' and result['suites']['W_preserve']['tier']=='pass'
    # A qualifying candidate must still remain distinct from held-out tasks.
    identity=loop.mutant_identity(public,p['buggy_rtl'])
    dirs=[x['task_dir'] for x in m['anchors']]+loop.PROMOTION_VALIDATION
    assert all(identity!=loop.mutant_identity(public,(Path(d)/'public/repo/rtl/sequence.sv').read_text()) for d in dirs)


def test_two_different_transitions_are_still_forbidden_before_success_gate():
    loop,m,public=core()
    p=loop.red.materialize_batch(dict(candidates=[dict(raw(arm(public,'s1','data?s2:sf3')),edits=[arm(public,'s1','data?s2:sf3'),arm(public,'s2','data?s3:sf4')])]),public)['candidates'][0]
    assert p['status']=='proposal'
    assert 'Only one next-state RHS' in loop.targeted_prompts.curriculum_violation(public,p,5,[])


@pytest.mark.parametrize('state',['idle','s6','sf6','default'])
def test_local_stage_keeps_group_boundaries_protected(state):
    loop,m,public=core()
    if state=='idle':
        old='nstate=s1;';edit=dict(find=old,replace='nstate=s2;')
    else:edit=arm(public,state,'s2') if state=='default' else arm(public,state,'data?sf1:s2')
    p=proposal(loop,public,edit)
    assert p['status']=='proposal'
    assert loop.targeted_prompts.curriculum_violation(public,p,5,[])


def test_round_focus_and_clean_site_inventory_agree_with_actual_stage():
    loop,m,public=core();g=loop.targeted_prompts
    guidance=g.red_guidance(public['carrier_id'],4,[])
    assert guidance['stage']=='single_local_fault' and guidance['scheduled_focus_suspended']
    assert 'ONE eligible intermediate' in guidance['focus']
    attempted=arm(public,'s3','data?sf4:s4')
    inventory=g.transition_inventory(public,4,[],[[attempted]],['s2:nstate:0'])
    assert all(s['state'] not in {'idle','s6','sf6','default'} for s in inventory['sites'])
    assert next(s for s in inventory['sites'] if s['state']=='s3')['previous_candidate_count']==1
    assert inventory['sites'][0]['previous_candidate_count']==0
    assert next(s for s in inventory['sites'] if s['state']=='s2')['blocked_this_retry']
    assert all(s['clean_rhs'] in public['clean_rtl'] for s in inventory['sites'])
    assert all(set(s)=={'site_id','state','line','clean_rhs','previous_candidate_count','blocked_this_retry'} for s in inventory['sites'])


def test_nonfunctional_site_does_not_ban_all_other_transitions():
    loop,m,public=core();p=proposal(loop,public,arm(public,'s3','data?sf4:s4'))
    admission=dict(reason='functional_not_qualified',suites={'W_bug':dict(tier='pass'),'W_preserve':dict(tier='pass')})
    feedback=loop.red.admission_feedback(admission,p,round_index=4,attempt=0)
    control=loop.red_retry.annotate(feedback,p,[],public=public)['retry_control']
    assert control['blocked_site_ids']==['s3:nstate:0']
    assert 'state_transition' not in control['blocked_mechanisms']
    assert 'another eligible' in control['instruction']


def test_corrective_request_rejects_duplicate_and_accepts_online_alternative(tmp_path):
    loop,m,public=core()
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.fakes import _reply
    from r3e.loop.token_count import TokenCounter
    boundary=arm(public,'s6','data?sf1:s2');local=arm(public,'s3','data?sf4:s4')
    red_count=trial=0;red_requests=[]
    def transport(**request):
        nonlocal red_count,trial
        u=json.loads(request['messages'][-1]['content'])
        if 'carrier' in u:
            red_count+=1;red_requests.append(u)
            if red_count==1:value=dict(candidates=[raw(boundary)])
            elif red_count==2:
                # Same implementation with different whitespace must not be requalified.
                repeat={**boundary,'replace':boundary['replace'].replace('nstate=','nstate = ')}
                value=dict(candidates=[raw(repeat),raw(local)])
            elif red_count==3:
                value=dict(candidates=[raw(boundary),raw(arm(public,'s1','data?s2:sf3'))])
            else:value={'abstain':'offline fixture only'}
        else:
            if u['submission_kind']=='repair':trial+=1
            content=u['files']['rtl/sequence.sv']['content'] if trial<=6 else public['clean_rtl']
            value=helpers.source(content)
        return _reply(value,1)
    client=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000);counter=TokenCounter()
    plan=loop.make_plan(m['carriers'],m['anchors'],counter=counter,client_config=client.config.public_identity,
        rounds=5,slots_per_round=1,seed=700,carrier_mode='fixed',fixed_carrier_index=0,anchor_repeats=2,
        mechanism_focus=m['mechanism_focus'],red_output_tokens=16000,reserved_collision_retries=1)
    out=tmp_path/'collection';loop.TRAIN_QUEUE=[];loop.EXAM_QUEUE=[];loop.PRETEST_DECISION=None
    try:
        loop.collect(plan,out,client=BudgetedClient(client,max_calls=plan['max_calls']),counter=counter)
        loop.PRETEST_DECISION='continue';loop.TRAIN_QUEUE[0]();loop.EXAM_QUEUE[0]()
    finally:loop.TRAIN_QUEUE=loop.EXAM_QUEUE=loop.PRETEST_DECISION=None
    rows=[json.loads(l) for l in (out/'slots.jsonl').read_text().splitlines()]
    assert rows[0]['admission']=='admitted' and rows[0]['online_generation_requests']==2
    attempts=rows[0]['generation_attempts']
    assert [a['reason'] for a in attempts]==['curriculum_stage_violation','repeated_rejected_proposal','public_matrix_and_structure_pass']
    assert attempts[0]['proposal_identity']==attempts[1]['proposal_identity']
    assert attempts[2]['transition_site_ids']==['s3:nstate:0']
    assert rows[1]['admission']=='admitted'
    assert rows[1]['generation_attempts'][0]['reason']=='repeated_rejected_proposal'
    assert rows[1]['generation_attempts'][0]['proposal_identity']==attempts[0]['proposal_identity']
    retry=red_requests[1]
    assert retry['round_curriculum']['stage']=='single_local_fault'
    assert retry['eligible_transition_sites']['sites']
    assert retry['excluded_previous_proposals']['edits']
    assert all('boundary or compound' not in x['clean_rhs'] for x in retry['eligible_transition_sites']['sites'])
    assert ex.read(out/'collection.json')['accepted_promotions']==1


def test_three_design_batch_keeps_feedback_promotion_and_both_exam_barriers(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch)
    results=ex.read(root/'promotion_results.json')
    assert results['comparison']['complete'] and results['comparison']['promotion_passed_completed_designs']==6
    assert results['hard_max_requests']==486
    assert all(results['designs'][d]['retained_entries']==1 for d in ex.DESIGNS)
    assert all(phase=='pretest' for _,phase in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
