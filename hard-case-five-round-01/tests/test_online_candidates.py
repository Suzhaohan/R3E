import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('online_experiment',HERE/'experiment-online-v1.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)


@pytest.fixture(scope='module',autouse=True)
def isolate_core():
    def owned(name):
        return name in ('r3e','experiments') or name.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)};paths=list(sys.path)
    for key in list(saved):sys.modules.pop(key)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for key in list(sys.modules):
        if owned(key):sys.modules.pop(key)
    sys.modules.update(saved);sys.path[:]=paths


def setup_core(design='Prob001'):
    _,loop,*_=ex.runner(design).modules();m=ex.material(design);carrier=m['carriers'][0]
    public=loop.red907.public_material(Path(carrier['package']),ex.read(carrier['suite_freeze']))
    return loop,m,public


def raw(edits):
    return dict(edits=edits,violated_requirement='offline scripted public mutation witness',spec_basis='unchanged public specification')


def run_core(tmp_path,replies,design='Prob001'):
    loop,m,public=setup_core(design)
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    from r3e.loop.token_count import TokenCounter
    red_count=blue_count=0
    def transport(**request):
        nonlocal red_count,blue_count
        u=json.loads(request['messages'][-1]['content'])
        if 'carrier' in u:
            red_count+=1;value=replies[red_count-1] if red_count<=len(replies) else {'abstain':'offline fixture'}
        else:
            blue_count+=1
            content=u['files']['rtl/sequence.sv']['content'] if blue_count<=4 else public['clean_rtl']
            value=dict(files=[dict(file='rtl/sequence.sv',content=content)],edit='offline full-file fixture')
        return _reply(value,1)
    client=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000)
    counter=TokenCounter();p=loop.make_plan(m['carriers'],m['anchors'],counter=counter,client_config=client.config.public_identity,
        rounds=5,slots_per_round=1,seed=700,carrier_mode='fixed',fixed_carrier_index=0,anchor_repeats=2,
        mechanism_focus=m['mechanism_focus'],red_output_tokens=16000,reserved_collision_retries=1)
    out=tmp_path/'collection';loop.EXAM_QUEUE=[]
    try:
        result=loop.collect(p,out,client=BudgetedClient(client,max_calls=p['max_calls']),counter=counter)
        assert result['status']=='trained' and result['committed_rounds']==5 and result['completed_probes']==0
        for job in loop.EXAM_QUEUE:job()
    finally:loop.EXAM_QUEUE=None
    return out


def test_batch_selects_first_qualified_online_candidate_and_records_rejected_reasons(tmp_path):
    loop,_,public=setup_core()
    compare="else if (a_tem == 8'b0111_0001)"
    no_fault=raw([dict(find=compare,replace=compare.replace('==','==='))])
    bad_guard=raw([dict(find=compare,replace=compare+" && (a_tem[7] == 1'b0)")])
    exam_collision=raw([dict(find='{a_tem[6:0],a}',replace='{a,a_tem[6:0]}')])
    valid=raw([dict(find='a_tem[6:0]',replace='a_tem[5:0]')])
    out=run_core(tmp_path,[dict(candidates=[no_fault,bad_guard,exam_collision,valid])])
    rows=[json.loads(s) for s in (out/'slots.jsonl').read_text().splitlines()]
    first=rows[0];assert first['admission']=='admitted' and first['online_generation_requests']==1
    assert first['generation_source']=='online_red' and len(first['generation_attempts'])==4
    assert first['generation_attempts'][0]['reason']=='outside_public_admission_matrix'
    assert first['generation_attempts'][1]['reason']=='mutation_grammar_violation'
    assert first['generation_attempts'][2]['reason']=='reserved_task_collision'
    assert first['generation_attempts'][3]['admission']=='admitted'
    assert first['admission_directory'].endswith('admission_a0_c3')
    request=ex.read(out/'rounds/1/r1_s0/red/request.json');u=json.loads(request['messages'][-1]['content'])
    assert u['mutation_constraints']['no_human_prepared_replacement']
    assert ex.read(out/'collection.json')['qualified_practice_slots']==1
    assert ex.read(out/'collection.json')['empty_practice_slots']==4
    assert not (out/'fallbacks.jsonl').exists()


def test_two_unqualified_online_batches_record_empty_round_without_replacement_and_still_exam(tmp_path):
    loop,_,public=setup_core()
    compare="else if (a_tem == 8'b0111_0001)"
    bad=raw([dict(find=compare,replace=compare+" && (a_tem[7] == 1'b0)")])
    bad_schema=raw(['not a valid edit'])
    out=run_core(tmp_path,[dict(candidates=[bad,bad_schema,None]),dict(candidates=[bad])])
    rows=[json.loads(s) for s in (out/'slots.jsonl').read_text().splitlines()]
    first=rows[0];assert first['online_generation_requests']==2 and first['trials']=={}
    assert first['generation_source']=='no_qualified_online_challenge'
    assert len(first['generation_attempts'])==4
    req=ex.read(out/'rounds/1/r1_s0/red_retry_1/request.json');u=json.loads(req['messages'][-1]['content'])
    assert any('Syntax-token insertion/deletion is forbidden' in str(f) for f in u['generation_feedback'])
    summary=ex.read(out/'collection.json')
    assert summary['status']=='complete' and summary['committed_rounds']==5 and summary['completed_probes']==4
    assert summary['qualified_practice_slots']==0 and summary['empty_practice_slots']==5
    assert summary['human_prepared_replacements']==0
    assert not (out/'rounds/1/r1_s0/red_retry_2').exists()
    assert not list(out.glob('**/admission_fallback'))
    assert not (out/'fallbacks.jsonl').exists()
    assert all(not ex.read(out/f'rounds/{r}/commit.json')['blue']['entries'] for r in range(6))


@pytest.mark.parametrize('design',['Prob001','Prob023','Prob003'])
def test_online_candidates_produce_five_distinct_qualified_practices_without_prepared_pool(tmp_path,design):
    loop,_,public=setup_core(design)
    # These are provider responses ONLY in this offline test. The production
    # generator cannot read this test or any practice fixture/pool.
    if design=='Prob001':
        edits=[[dict(find="8'b0111_0001",replace=f"8'b{value:08b}")] for value in (0x10,0x20,0x30,0x40,0x50)]
    elif design=='Prob023':
        edits=[[dict(find='gray_wire[2]^bin_out[3]',replace='gray_wire[2]|bin_out[3]')],
               [dict(find='gray_wire[1]^bin_out[2]',replace='gray_wire[1]&bin_out[2]')],
               [dict(find='gray_wire[0]^bin_out[1]',replace='gray_wire[0]|bin_out[1]')],
               [dict(find='gray_wire[2]^bin_out[3]',replace='gray_wire[2]&bin_out[3]')],
               [dict(find='(bin_add_wire >> 1)',replace='(bin_add_wire >> 0)')]]
    else:
        pairs=[('s2','sf2'),('s3','sf3'),('s4','sf4'),('sf5','s5'),('sf6','s6')]
        edits=[[dict(find=f'nstate=data?{a}:{b};',replace=f'nstate=data?{b}:{a};')] for a,b in pairs]
    out=run_core(tmp_path,[dict(candidates=[raw(group)]) for group in edits],design)
    summary=ex.read(out/'collection.json')
    assert summary['status']=='complete' and summary['qualified_practice_slots']==5
    assert summary['empty_practice_slots']==0 and summary['human_prepared_replacements']==0
    slots=[json.loads(s) for s in (out/'slots.jsonl').read_text().splitlines()]
    assert all(s['generation_source']=='online_red' for s in slots)
    identities=[]
    for s in slots:
        ad=Path(s['admission_directory']);proposal=ex.read(ad/'proposal.json');gate=ex.read(ad/'admission.json')
        assert {k:v['tier'] for k,v in gate['suites'].items()}=={'W_bug':'fail','W_preserve':'pass'}
        identities.append(loop.mutant_identity(public,proposal['buggy_rtl']))
    assert len(set(identities))==5
    from experiments.loop_probes.continuous_audit import source_audit,exposure_audit
    assert source_audit(out) and exposure_audit(out)


@pytest.mark.parametrize('raw_value',[{'candidates':[]},{'candidates':[{}]*5},{'candidates':'wrong'},None])
def test_malformed_batches_are_rejected_without_crashing(raw_value):
    loop,_,public=setup_core()
    assert loop.red.materialize_batch(raw_value,public)['status']=='rejected'


def test_frozen_production_plans_do_not_contain_any_prepared_practice_or_substitution():
    ex.verify_questions()
    manifest=ex.read(HERE/'promotion_code_online_v1.json')
    assert not any('reliable_practice' in p for p in manifest)
    assert 'r3e/loop/online_mutation.py' in manifest
    for design in ex.DESIGNS:
        p=ex.read(ex.PLAN_ROOT/design/'plan.json')
        assert 'fallback_pools' not in p and p['mutation_constraints']['no_human_prepared_replacement']
        assert p['mutation_constraints']['maximum_candidates_per_request']==4
        assert p['max_calls']==86 and p['generation_policy']['second_invalid_proposal']=='record_empty_practice_no_replacement'
        assert {r['snapshot'] for r in p['anchor_probes']}=={0,5}


def test_batch_barrier_and_empty_rounds_are_truthful_for_all_three_designs(tmp_path,monkeypatch):
    root=tmp_path/'batch';monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--run-dir',str(root)])
    ex.main();r=ex.read(root/'promotion_results.json')
    assert r['comparison']['complete'] and r['empty_practice_slots']==15
    assert r['qualified_online_practices']==0 and r['human_prepared_replacements']==0
    assert len(ex.read(root/'training_barrier.json')['members'])==3
    for d in ex.DESIGNS:
        c=root/d/'collection'
        for req in c.glob('anchors/**/blue/submissions/request_*.json'):
            assert req.stat().st_mtime_ns>=(root/'training_barrier.json').stat().st_mtime_ns
        assert ex.read(c/'audits/source_audit.json') and ex.read(c/'audits/exposure_audit.json')


def test_internal_declaration_change_is_not_an_online_expression_mutation():
    loop,_,public=setup_core()
    candidate=raw([dict(find='reg [7:0] a_tem;',replace='reg [6:0] a_tem;')])
    result=loop.red.materialize_batch(dict(candidates=[candidate]),public)
    assert result['candidates'][0]['status']=='rejected'
    assert result['candidates'][0]['reason']=='mutation_grammar_violation'
    assert 'Declaration' in result['candidates'][0]['grammar_error']
