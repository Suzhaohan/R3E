import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('structured_red_experiment',HERE/'experiment-working-experience-v1.py');ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

@pytest.fixture(autouse=True)
def isolate():
    def owned(k):return k in ('r3e','experiments') or k.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)};paths=list(sys.path)
    for k in saved:sys.modules.pop(k)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):sys.modules.pop(k)
    sys.modules.update(saved);sys.path[:]=paths


def core():
    _,loop,*_=ex.runner('Prob003').modules();m=ex.material('Prob003');c=m['carriers'][0]
    p=loop.red907.public_material(Path(c['package']),ex.read(c['suite_freeze']))
    from r3e.loop import transition_actions as actions
    return loop,m,p,actions


def test_all_rendered_actions_preserve_existing_token_grammar_and_lesson():
    loop,m,p,a=core()
    observations=[dict(round=2,label='public_pass_single_sample_hidden_unknown',source_hash='current-run')]
    for round_index,obs in [(1,[]),(2,[]),(3,[]),(4,observations),(5,observations)]:
        inv=a.inventory(p,round_index,obs)
        assert inv['available_actions']
        for choice in inv['available_actions']:
            raw={'candidate_actions':[dict(action_id=choice['action_id'],violated_requirement='offline public-contract check',spec_basis='public spec')]}
            decoded=a.decode(raw,p,inv);proposal=loop.red.materialize_batch(decoded,p)['candidates'][0]
            assert proposal['status']=='proposal'
            assert loop.red.online_mutation.violation(p,proposal) is None
            assert loop.targeted_prompts.curriculum_violation(p,proposal,round_index,obs) is None
            assert len(loop.red.online_mutation.tokens(p['clean_rtl']))==len(loop.red.online_mutation.tokens(proposal['buggy_rtl']))


def test_free_expression_insertion_and_unlisted_or_repeated_choices_are_refused():
    loop,m,p,a=core();inv=a.inventory(p,2,[])
    with pytest.raises(ValueError,match='candidate_actions'):
        a.decode({'candidates':[dict(edits=[dict(find='nstate=sf6;',replace='nstate=data?sf6:s6;')],violated_requirement='x',spec_basis='x')]},p,inv)
    choice=dict(action_id='invented',violated_requirement='x',spec_basis='x')
    with pytest.raises(ValueError,match='unavailable'):a.decode({'candidate_actions':[choice]},p,inv)
    choice['action_id']=inv['available_actions'][0]['action_id']
    decoded=a.decode({'candidate_actions':[choice]},p,inv)
    remaining=a.inventory(p,2,[],[decoded['candidates'][0]['edits']])
    assert choice['action_id'] not in {x['action_id'] for x in remaining['available_actions']}
    assert len(remaining['available_actions'])==len(inv['available_actions'])-1
    with pytest.raises(ValueError,match='unavailable'):a.decode({'candidate_actions':[choice]},p,remaining)
    with pytest.raises(ValueError,match='duplicated'):a.decode({'candidate_actions':[choice,choice]},p,inv)


def test_single_failed_action_does_not_block_a_whole_site():
    loop,m,p,a=core();inv=a.inventory(p,2,[]);action=inv['available_actions'][0]
    raw={'candidate_actions':[dict(action_id=action['action_id'],violated_requirement='x',spec_basis='x')]}
    proposal=loop.red.materialize_batch(a.decode(raw,p,inv),p)['candidates'][0]
    admission={'status':'rejected','reason':'no_observed_functional_fault','suites':{'W_bug':{'tier':'pass'},'W_preserve':{'tier':'pass'}}}
    feedback=loop.red.admission_feedback(admission,proposal,round_index=2,attempt=0)
    result=loop.red_retry.annotate(feedback,proposal,[],public=p)
    assert result['retry_control']['blocked_site_ids']==[]
    assert 'candidate_actions' in result['retry_control']['instruction']
    remaining=a.inventory(p,2,[],[proposal['mutation_edits']])
    assert any(x['site_id']==action['site_id'] for x in remaining['available_actions'])


def test_exhaustive_real_eda_proof_and_startup_guard(tmp_path,monkeypatch):
    ex.verify_structured_red_space()
    proof=ex.read(HERE/'structured-red-space-validation.json')
    assert proof['compile_failures']==0 and proof['model_calls']==0
    assert proof['stages']['miss_progression']['qualified_distinct_implementations']>=4
    assert proof['stages']['boundary']['qualified_distinct_implementations']>=2
    proof['stages']['miss_progression']['qualified_distinct_implementations']=0
    (tmp_path/'structured-red-space-validation.json').write_text(json.dumps(proof))
    monkeypatch.setattr(ex,'HERE',tmp_path)
    with pytest.raises(ValueError,match='insufficient distinct'):ex.verify_structured_red_space()


def test_actual_http_guard_registers_structured_red_only_for_prob003():
    loop,m,p,a=core()
    allowed={loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000}
    systems=ex.registered_systems('Prob003',loop,allowed)
    assert loop.red.SYSTEM_TRANSITION in systems and loop.red.SYSTEM not in systems
    assert ex.registered_systems('Prob023',loop,allowed)==allowed
    assert ex.verify_launch_guard('Prob003',ex.runner('Prob003').modules())['status']=='PASS'


def test_five_round_runtime_has_five_qualified_distinct_practices_and_reaches_boundary(tmp_path,monkeypatch):
    helper_spec=importlib.util.spec_from_file_location('structured_continuity_fixtures',HERE/'tests/test_public_feedback.py')
    helpers=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helpers);helpers.ex=ex
    root,order=helpers.batch(tmp_path,monkeypatch,all_structured_rounds=True)
    c=root/'Prob003/collection';summary=ex.read(root/'promotion_results.json')['designs']['Prob003']
    assert summary['qualified_online_practices']==5 and summary['empty_practice_slots']==0
    assert summary['training_experience_entries']==5 and summary['retained_entries']>=1
    rows=[json.loads(l) for l in (c/'slots.jsonl').read_text().splitlines()]
    assert all(x['admission']=='admitted' for x in rows)
    identities=[]
    for x in rows:
        proposal=ex.read(Path(x['admission_directory'])/'proposal.json')
        identities.append(proposal['buggy_rtl_hash'])
        if x['round']>=4:
            assert x['curriculum']['stage']=='boundary_transfer'
            assert x['generation_attempts'][-1]['transition_site_ids'][0].split(':')[0] in {'s6','sf6'}
        request=ex.read(c/f"rounds/{x['round']}/r{x['round']}_s0/red/request.json")
        u=json.loads(request['messages'][-1]['content'])
        assert request['messages'][0]['content'].startswith('Author a learnable')
        assert 'json' in request['messages'][0]['content'].lower()
        assert u['structured_transition_actions']['available_actions']
        assert 'model_calls' not in u['structured_transition_actions']  # offline qualification data is not fed to Red
    assert len(set(identities))==5
    assert (root/'training_barrier.json').exists()
