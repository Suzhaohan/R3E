import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('retry_experiment',HERE/'experiment-retry-v1.py')
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


FAILED=HERE/'real-all-20261017-215846/Prob001/collection/rounds/4/r4_s0'


def setup_core():
    _,loop,*_=ex.runner('Prob001').modules()
    carrier=ex.material('Prob001')['carriers'][0]
    public=loop.red907.public_material(Path(carrier['package']),ex.read(carrier['suite_freeze']))
    return loop,carrier,public


@pytest.mark.parametrize('suffix',['','_retry_2','_retry_3'])
def test_real_redundant_guards_get_specific_implication_diagnosis(suffix):
    loop,_,public=setup_core()
    from r3e.loop import red_retry
    raw=ex.read(FAILED/('red'+suffix)/'response.json')['result']
    proposal=loop.red.materialize(raw,public)
    admission=ex.read(FAILED/('admission'+suffix)/'admission.json')
    feedback=red_retry.annotate(loop.red.admission_feedback(admission,proposal,round_index=4,attempt=0),proposal,[])
    control=feedback['retry_control']
    assert control['failed_mechanisms']==['added_condition_guard']
    assert control['blocked_mechanisms']==['added_condition_guard']
    assert 'already guarantees' in control['specific_diagnosis'][0]
    assert 'slice value' in control['specific_diagnosis'][0]
    assert 'hidden' not in control and 'validation_scores' not in control


def test_numeric_identity_ignores_equivalent_spelling_but_keeps_width_and_unknowns():
    loop,_,public=setup_core()
    clean=public['clean_rtl'];literal="8'b0111_0001"
    assert loop.mutant_identity(public,clean)==loop.mutant_identity(public,clean.replace(literal,"8'h71"))
    assert loop.mutant_identity(public,clean)!=loop.mutant_identity(public,clean.replace(literal,"9'h071"))
    assert loop.mutant_identity(public,clean)!=loop.mutant_identity(public,clean.replace(literal,"8'b0111_x001"))
    from r3e.loop import red_retry
    false_guard=loop.red.materialize(dict(edits=[dict(find='else if ('+ 'a_tem == '+literal+')',
        replace='else if ((a_tem == '+literal+") && (a_tem[7] == 1'b1))")],violated_requirement='public',spec_basis='public'),public)
    assert red_retry.redundant_guard_details(false_guard)==[]


def scenario(tmp_path, raw_replies):
    loop,carrier,public=setup_core()
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    clean=public['clean_rtl'];red_count=blue_count=0
    def transport(**request):
        nonlocal red_count,blue_count
        u=json.loads(request['messages'][-1]['content'])
        if 'carrier' in u:
            red_count+=1
            result=raw_replies[red_count-1] if red_count<=len(raw_replies) else {'abstain':'offline fixture'}
        else:
            blue_count+=1
            content=u['files']['rtl/sequence.sv']['content'] if blue_count<=4 else clean
            result=dict(files=[dict(file='rtl/sequence.sv',content=content)],edit='offline scripted repair')
        return _reply(result,1)
    client=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000)
    from r3e.loop.token_count import TokenCounter
    counter=TokenCounter();m=ex.material('Prob001')
    plan=loop.make_plan(m['carriers'],m['anchors'],counter=counter,client_config=client.config.public_identity,
        rounds=5,slots_per_round=1,seed=700,carrier_mode='fixed',fixed_carrier_index=0,anchor_repeats=2,
        mechanism_focus=m['mechanism_focus'],red_output_tokens=16000,reserved_collision_retries=1)
    out=tmp_path/'collection';loop.EXAM_QUEUE=[]
    try:
        result=loop.collect(plan,out,client=BudgetedClient(client,max_calls=plan['max_calls']),counter=counter)
        assert result['status']=='trained' and result['committed_rounds']==5 and result['completed_probes']==0
        for job in loop.EXAM_QUEUE:job()
    finally:
        loop.EXAM_QUEUE=None
    return out


@pytest.mark.parametrize('second',['blocked_guard','valid_different_mechanism','different_but_invalid','syntax_fixed'])
def test_real_retry_requests_obey_switch_and_second_failure_immediately_uses_fallback(tmp_path,second):
    loop,_,public=setup_core()
    first=ex.read(FAILED/'red/response.json')['result']
    if second=='blocked_guard':
        follow=ex.read(FAILED/'red_retry_1/response.json')['result']
    elif second=='valid_different_mechanism':
        follow=dict(edits=[dict(find="else if (a_tem == 8'b0111_0001)",replace="else if (a_tem[7:1] == 7'b0111000)")],
                    violated_requirement='partial comparison accepts wrong LSB',spec_basis='full eight-bit match')
    elif second=='different_but_invalid':
        follow=dict(edits=[dict(find="match <= 1'b0;",replace="match <= (1'b0 | 1'b0);")],
                    violated_requirement='ineffective fixture',spec_basis='public')
        # find must be unique for this negative functional example.
        follow['edits']=[dict(find=public['clean_rtl'],replace=public['clean_rtl'].replace("1'b0","(1'b0 | 1'b0)",1))]
    else:
        first=dict(edits=[dict(find="else if (a_tem == 8'b0111_0001)",replace="else if (a_tem == 8'b01010101")],
                   violated_requirement='comparison fixture',spec_basis='public pattern')
        follow=dict(edits=[dict(find="else if (a_tem == 8'b0111_0001)",replace="else if (a_tem == 8'b01010101)")],
                    violated_requirement='comparison fixture',spec_basis='public pattern')
    out=scenario(tmp_path,[first,follow]);rows=[json.loads(s) for s in (out/'slots.jsonl').read_text().splitlines()]
    row=rows[0];assert len(row['generation_attempts'])==2
    request=ex.read(out/'rounds/1/r1_s0/red_retry_1/request.json');u=json.loads(request['messages'][-1]['content'])
    assert u['retry_control']['round']==1
    assert 'original round focus is suspended' in u['round_curriculum']['focus']
    assert 'one corrective request' in request['messages'][0]['content']
    if second=='syntax_fixed':
        assert u['compilation_correction']['diagnostics']
        assert u['retry_control']['failure_kind']=='compilation_error'
        assert row['generation_source']=='online_red'
    else:
        assert u['retry_control']['blocked_mechanisms']==['added_condition_guard']
        assert 'already guarantees' in str(u['retry_control']['specific_diagnosis'])
        assert row['generation_source']==('online_red' if second=='valid_different_mechanism' else 'prequalified_human_seeded_fallback')
    if second=='blocked_guard':
        rejected=ex.read(out/'rounds/1/r1_s0/admission_retry_1/admission.json')
        assert rejected['reason']=='blocked_failed_mechanism'
        assert 'suites' not in rejected  # rejected before more EDA/Blue work
    if second in {'blocked_guard','different_but_invalid'}:
        fallback=ex.read(out/'rounds/1/r1_s0/admission_fallback/admission.json')
        assert fallback['status']=='admitted'
    assert not (out/'rounds/1/r1_s0/red_retry_2').exists()
    assert ex.read(out/'collection.json')['status']=='complete'
    assert ex.read(out/'collection.json')['completed_probes']==4


def test_three_designs_finish_with_two_bad_requests_per_slot_then_frozen_exams(tmp_path,monkeypatch):
    _,loop,*_=ex.runner('Prob001').modules();original=loop.red.propose
    def bad(public,observations,**kwargs):
        original(public,observations,**kwargs)
        clean=public['clean_rtl']
        return loop.red.materialize(dict(edits=[dict(find=clean,replace=clean.replace("1'b0","(1'b0 | 1'b0)",1))],
             violated_requirement='offline equivalent mutation',spec_basis='public spec'),public)
    monkeypatch.setattr(loop.red,'propose',bad)
    root=tmp_path/'batch';monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--run-dir',str(root)])
    ex.main()
    result=ex.read(root/'promotion_results.json')
    assert result['comparison']['complete'] and result['prequalified_fallback_count']==15
    assert result['hard_max_requests']==258 and result['actual_requests']<=258
    barrier=ex.read(root/'training_barrier.json');assert len(barrier['members'])==3
    for design in ex.DESIGNS:
        c=root/design/'collection';summary=ex.read(c/'collection.json');plan=ex.read(c/'plan.json')
        assert summary['committed_rounds']==5 and summary['completed_probes']==4
        rows=[json.loads(s) for s in (c/'slots.jsonl').read_text().splitlines()]
        assert all(len(r['generation_attempts'])==2 for r in rows)
        assert all(r['generation_source']=='prequalified_human_seeded_fallback' for r in rows)
        assert all(r['generation_attempts'][1]['reason']=='blocked_failed_mechanism' for r in rows)
        assert plan['max_calls']==86 and plan['generation_policy']['max_online_attempts']==2
        assert {p['snapshot'] for p in plan['anchor_probes']}=={0,5}
        assert ex.read(c/'audits/source_audit.json') and ex.read(c/'audits/exposure_audit.json')
        for request in c.glob('anchors/**/blue/submissions/request_*.json'):
            assert request.stat().st_mtime_ns>=(root/'training_barrier.json').stat().st_mtime_ns
        for entry in ex.read(c/'rounds/5/commit.json')['blue']['entries']:
            assert design.lower() in entry['body']['source']['carrier_id'].lower()
