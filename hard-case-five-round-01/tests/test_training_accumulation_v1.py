import importlib.util
import json
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('training_accumulation_experiment',HERE/'experiment-working-experience-v1.py')
helpers=module('training_accumulation_helpers',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def test_zero_score_ties_never_enter_exam_but_learning_continues_across_five_rounds(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch,all_structured_rounds=True,force_all_validation_fail=True)
    row=ex.read(root/'promotion_results.json')['designs']['Prob003'];c=root/'Prob003/collection'
    assert row['training_experience_entries']==5
    assert row['retained_entries']==0 and row['accepted_promotions']==0
    assert row['certified_validation']['initial_passed']==row['certified_validation']['retained_passed']==0
    for n in range(1,6):
        commit=ex.read(c/f'rounds/{n}/commit.json')
        assert len(commit['practice_blue']['entries'])==n and commit['blue']['entries']==[]
        gates=[json.loads(l) for l in (c/'promotions.jsonl').read_text().splitlines()]
        assert gates[n-1]['reason']=='no_strict_gain_training_only'
        assert not gates[n-1]['measured_gain']
        if n>1:
            delivery=ex.read(c/f'rounds/{n}/r{n}_s0/online/delivery.json')
            assert len(delivery['payload']['entries'])>0
    for d in (c/'anchors').glob('b5*/delivery.json'):
        assert ex.read(d)['payload']['entries']==[]
    assert (c/'audits/exposure_audit.json').exists()
    assert (root/'training_barrier.json').exists()


def test_accumulated_earlier_successes_can_qualify_later_after_real_validation_gain(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch,all_structured_rounds=True,neutral_validation=True)
    c=root/'Prob003/collection'
    first=ex.read(c/'rounds/1/commit.json');second=ex.read(c/'rounds/2/commit.json')
    assert first['blue']['entries']==[] and len(first['practice_blue']['entries'])==1
    assert len(second['blue']['entries'])==2
    assert {e['body']['created_round'] for e in second['blue']['entries']}=={1,2}
    row=ex.read(root/'promotion_results.json')['designs']['Prob003']
    assert row['strict_gain_promotions']==1 and row['retentions_without_measured_gain']==0
    assert row['training_experience_entries']==5


def test_exam_gate_rejects_zero_tie_and_any_regression():
    loop,m,p=helpers.core()
    zero=loop.promotion_decision({'a':False},{'a':False},set())
    assert not zero['accepted'] and zero['reason']=='no_strict_gain_training_only'
    assert not loop.promotion_decision({'a':True,'b':False},{'a':False,'b':True},{'a'})['accepted']
    assert loop.promotion_decision({'a':False},{'a':True},set())['accepted']

@pytest.mark.parametrize('learning_passes',[True,False])
def test_probe_stops_early_or_reports_both_arms_without_cherry_picking(tmp_path,monkeypatch,learning_passes):
    probe=module('fresh_probe_test_'+str(learning_passes),HERE/'transfer_probe.py');probe.ex=ex
    loop,m,p=helpers.core('Prob003')
    from r3e.loop import env
    from r3e.loop.fakes import _reply
    requests=[]
    def transport(**request):
        u=json.loads(request['messages'][-1]['content']);requests.append(u)
        if 'carrier' in u:
            a=u['structured_transition_actions']['available_actions'][0]
            value={'candidate_actions':[dict(action_id=a['action_id'],violated_requirement='offline public test',spec_basis='public specification')]}
        else:
            text=p['clean_rtl'] if learning_passes else u['files']['rtl/sequence.sv']['content']
            value=helpers.source(text)
        return _reply(value,len(requests))
    monkeypatch.setattr(env,'ThinkingTransport',lambda *args,**kwargs:transport)
    key=tmp_path/'fake-key';key.write_text('offline-fixture-key')
    root=tmp_path/'probe';probe.execute(root,key)
    result=ex.read(root/'result.json')
    assert result['hard_max_calls']==14 and result['previous_run_memory_imported'] is False
    if learning_passes:
        assert result['status']=='complete' and result['actual_calls']==5
        assert result['static']['passed'] and result['adaptive']['passed']
        assert result['adaptive_minus_static']==0
        static=ex.read(root/'static/blue/submissions/request_0001.json')['messages']
        adaptive=ex.read(root/'adaptive/blue/submissions/request_0001.json')['messages']
        su=json.loads(static[-1]['content']);au=json.loads(adaptive[-1]['content'])
        assert 'repair_experience' not in su and len(au.pop('repair_experience')['entries'])==1
        assert su==au and static[0]==adaptive[0]
    else:
        assert result['status']=='stopped_no_successful_learning_episode'
        assert result['actual_calls']==5 and sum('carrier' in u for u in requests)==1
