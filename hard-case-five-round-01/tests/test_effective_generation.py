"""Replay the actual ineffective mutation and check public-only correction paths."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE = Path(__file__).resolve().parents[1]
FAILED = HERE/'real-all-20261017-000441/Prob001/collection/rounds/3/r3_s0'
spec = importlib.util.spec_from_file_location('effective_experiment', HERE/'experiment-moderate-feedback-v1.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


@pytest.fixture(scope='module', autouse=True)
def isolate_core():
    def owned(name):
        return name in ('r3e','experiments') or name.startswith(('r3e.','experiments.'))
    saved = {k:v for k,v in sys.modules.items() if owned(k)}
    paths = list(sys.path)
    for key in list(saved):
        sys.modules.pop(key)
    sys.path.insert(0, str(ex.PROMOTION_SOURCE))
    yield
    for key in list(sys.modules):
        if owned(key):
            sys.modules.pop(key)
    sys.modules.update(saved)
    sys.path[:] = paths


def setup_core():
    base = ex.runner('Prob001')
    _,loop,*_ = base.modules()
    carrier = ex.material('Prob001')['carriers'][0]
    public = loop.red907.public_material(Path(carrier['package']), ex.read(carrier['suite_freeze']))
    raw = ex.read(FAILED/'red/response.json')['result']
    proposal = loop.red.materialize(raw,public)
    return base,loop,carrier,public,proposal


def read_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def test_actual_four_failed_proposals_replay_and_feedback(tmp_path):
    _,loop,carrier,public,proposal = setup_core()
    assert proposal['status']=='proposal'
    for i in range(4):
        directory = FAILED/('red' if i==0 else f'red_retry_{i}')
        raw = ex.read(directory/'response.json')['result']
        assert loop.red.materialize(raw,public)['buggy_rtl_hash']==proposal['buggy_rtl_hash']
    actual = loop.red907.check_proposal(Path(carrier['package']),ex.read(carrier['suite_freeze']),
                                      proposal,tmp_path/'replay',seen=set())
    assert actual['reason']=='outside_public_admission_matrix'
    feedback = loop.red.admission_feedback(actual,proposal,round_index=3,attempt=0)
    assert feedback['actual_public_results']=={'W_bug':'pass','W_preserve':'pass'}
    assert feedback['expected_public_results']=={'W_bug':'fail','W_preserve':'pass'}
    assert 'reachable' in feedback['correction'] and 'dead or redundant' in feedback['correction']
    assert 'TESTBENCH PASS' in feedback['public_test_evidence']['W_bug']


def test_feedback_preservation_compile_failure_and_private_data_boundary():
    _,loop,_,_,proposal=setup_core()
    record=dict(reason='outside_public_admission_matrix',status='rejected',
        suites={'W_bug':dict(tier='fail',log='CHECK_FAIL mismatch'),
                'W_preserve':dict(tier='fail',log='CHECK_FAIL reset')},
        hidden_evaluator='PRIVATE_SENTINEL',validation_scores='PRIVATE_SENTINEL')
    feedback=loop.red.admission_feedback(record,proposal,round_index=1,attempt=0)
    assert 'preserved behavior was broken' in feedback['correction']
    assert 'PRIVATE_SENTINEL' not in json.dumps(feedback)
    record['suites']['W_bug']['tier']='build_fail'
    feedback=loop.red.admission_feedback(record,proposal,round_index=1,attempt=1)
    assert 'not qualify as functional defects' in feedback['correction']


def test_repeated_ineffective_edit_uses_cached_evidence_then_new_valid_edit(tmp_path, monkeypatch):
    base,loop,_,_,bad=setup_core()
    original=loop.red.propose
    original_check=loop.red907.check_proposal
    bad_checks=[]
    def check(*args,**kwargs):
        if args[2].get('buggy_rtl_hash')==bad['buggy_rtl_hash']:
            bad_checks.append(1)
        return original_check(*args,**kwargs)
    injected=[]
    def propose(public,observations,**kw):
        if kw['round_index']==3 and len(injected)<2:
            if injected:
                assert kw['generation_feedback'][-1]['actual_public_results']=={'W_bug':'pass','W_preserve':'pass'}
            injected.append(1)
            return bad
        if kw['round_index']==3:
            latest=kw['generation_feedback'][-1]
            assert latest['reason']=='repeated_rejected_proposal'
            assert latest['actual_public_results']=={'W_bug':'pass','W_preserve':'pass'}
            assert 'different functional mutation' in latest['correction']
        return original(public,observations,**kw)
    monkeypatch.setattr(loop.red907,'check_proposal',check)
    monkeypatch.setattr(loop.red,'propose',propose)
    out=tmp_path/'collection'
    assert base.smoke(out)['status']=='complete'
    assert len(bad_checks)==1
    row=read_rows(out/'slots.jsonl')[2]
    assert row['admission']=='admitted' and len(row['generation_attempts'])==3
    reused=ex.read(out/'rounds/3/r3_s0/admission_retry_1/admission.json')
    prior=ex.read(out/'rounds/3/r3_s0/admission/admission.json')
    assert reused['reused_admission_hash']==loop.hash_payload(prior)
    request=ex.read(out/'rounds/3/r3_s0/red_retry_2/request.json')
    user=json.loads(request['messages'][-1]['content'])
    assert user['generation_feedback'][-1]['actual_public_results']['W_bug']=='pass'
    assert 'else-if repeating an earlier if condition is unreachable' in request['messages'][0]['content']
    assert ex.read(out/'audits/source_audit.json')
    assert ex.read(out/'audits/exposure_audit.json')


def test_repeated_bad_edits_exhaust_budget_without_retesting_or_exams(tmp_path,monkeypatch):
    base,loop,_,_,bad=setup_core()
    original_check=loop.red907.check_proposal
    checked=[]
    def check(*a,**kw):
        checked.append(1)
        return original_check(*a,**kw)
    monkeypatch.setattr(loop.red907,'check_proposal',check)
    monkeypatch.setattr(loop.red,'propose',lambda *a,**kw:bad)
    out=tmp_path/'collection'
    with pytest.raises(loop.measure.MeasurementRefused,match='generation_attempts_exhausted'):
        base.smoke(out)
    attempts=read_rows(out/'generation_attempts.jsonl')
    assert len(attempts)==4 and len(checked)==1
    assert [r['reason'] for r in attempts]==['outside_public_admission_matrix']+['repeated_rejected_proposal']*3
    assert ex.read(out/'collection.json')['completed_probes']==0


def test_only_generation_implementation_changed_and_budget_unchanged():
    old=ex.read(HERE/'promotion_code_simple_v1.json')
    new=ex.read(HERE/'promotion_code_effective_v1.json')
    assert set(old)==set(new)
    assert {p for p in old if old[p]!=new[p]}=={
        'r3e/loop/red_continuous.py','experiments/loop_probes/continuous_loop.py'}
    for design in ex.DESIGNS:
        plan=ex.read(ex.PLAN_ROOT/design/'plan.json')
        before=ex.read(HERE/'plan-v3-moderate-v1'/design/'plan.json')
        for key in ('blue_config','client_config','promotion','learning','retrieval',
                    'anchors','validation_tasks','rounds','slots_per_round','max_calls'):
            assert plan[key]==before[key],key
