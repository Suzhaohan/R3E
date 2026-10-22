"""Real local simulators plus scripted replies; no paid inference or model-gain claims."""
import importlib.util
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ex=module('trace_experiment',HERE/'experiment-fsmtrace-v1.py')
helpers=module('trace_fixtures',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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

def test_current_plan_keeps_exam_validation_and_budget():
    assert ex.DESIGNS==('Prob001','Prob023','Prob003')
    old=module('trace_previous_entry',HERE/'experiment-transition-v1.py')
    for d in ex.DESIGNS:
        assert ex.material(d)==old.material(d)
        assert ex.read(ex.VALIDATION_ROOT/d/'validation.json')==old.read(old.VALIDATION_ROOT/d/'validation.json')
        assert ex.cap(d)==162
    assert ex.verify_questions()[2]['case_id']=='historical:RC_406d811b4d61a2'


def test_worksheet_derives_only_public_target_and_ignores_other_designs():
    from r3e.loop.fsm_diagnostics import worksheet
    for target in ('011100','100101'):
        w=worksheet('Prob003 public task','The six-bit target is '+target)
        assert w['target']==target and w['positions'][4]['matching_prefix']==target[:5]
        assert len(w['positions'])==6
    assert worksheet('Prob023','011100') is None
    assert worksheet('Prob003','no binary target') is None
    assert worksheet('Prob003','ambiguous 011100 and 100101') is None


def test_actual_failing_trace_locates_consumed_boundary_bit_without_changing_verdict():
    loop,m,public=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    result=loop.rb.execute(task,{})
    assert result.tier=='visible_fail'
    bug=result.evidence['suites']['W_bug'];trace=bug['public_state_trace']
    assert bug['log']=='CHECK_FAIL W_bug cycle=12 group=000000 bit=0 match=0 not_match=0'
    assert trace['status']=='observed' and trace['failure_reproduced'] and trace['scoring_unchanged']
    assert any('cycle=7 position=1' in row and 'pre_state=6 pre_next=0 post_state=0' in row for row in trace['records'])
    assert 'actual=00 expected=01' in trace['records'][-1]
    assert result.evidence['suites']['W_preserve']['result']=='visible_pass'
    assert all(p.startswith('public/') for p in task.read_files)


def test_clean_reference_still_passes_without_failure_probe():
    loop,m,public=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    result=loop.rb.execute(task,{'rtl/sequence.sv':public['clean_rtl']})
    assert result.tier=='visible_pass'
    assert all('public_state_trace' not in row for row in result.evidence['suites'].values())


def test_changed_architecture_keeps_original_failure_when_probe_unavailable():
    loop,m,public=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    rtl=(task.repo/'rtl/sequence.sv').read_text().replace('pstate','current_state')
    result=loop.rb.execute(task,{'rtl/sequence.sv':rtl})
    assert result.tier=='visible_fail'
    assert result.evidence['suites']['W_bug']['public_state_trace']['status']=='unavailable'


def test_historical_bad_reply_still_fails_with_actionable_trace():
    loop,m,public=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    path=HERE/'real-all-20261018-080908/Prob003/collection/rounds/1/r1_s0/online/blue/submissions/response_0001.json'
    files={f['file']:f['content'] for f in ex.read(path)['result']['files']}
    result=loop.rb.execute(task,files)
    assert result.tier=='visible_fail'
    assert 'cycle=12' in result.evidence['suites']['W_bug']['log']
    rows=result.evidence['suites']['W_bug']['public_state_trace']['records']
    assert any('pre_state=1 pre_next=1' in row for row in rows)


def test_feedback_delivers_real_trace_and_worksheet_in_same_two_attempt_budget(tmp_path):
    row,requests,out,loop,m,public=helpers.run_trial(tmp_path,[lambda u,p:helpers.source(u['files']['rtl/sequence.sv']['content']),lambda u,p:helpers.source(p['clean_rtl'])],design='Prob003')
    assert row['outcome']=='fixed' and len(requests)==2
    assert all(u['public_group_worksheet']['target']=='011100' for u in requests)
    trace=requests[1]['current_failure_evidence']['suites']['W_bug']['public_state_trace']
    assert trace['status']=='observed' and trace['records']
    assert requests[1]['public_feedback_correction']['remaining_functional_corrections']==0
    serialized=json.dumps(requests)
    assert 'public_group_trace_v1' in serialized and 'public_evaluator' not in serialized


def test_compilation_diagnostics_remain_available_with_one_correction(tmp_path):
    row,requests,*_=helpers.run_trial(tmp_path,[helpers.source('module broken('),lambda u,p:helpers.source(p['clean_rtl'])],design='Prob003')
    assert row['outcome']=='fixed' and len(requests)==2
    assert requests[1]['current_failure_evidence']['result']=='compile_fail'
    assert all('public_state_trace' not in r for r in requests[1]['current_failure_evidence']['suites'].values())


def test_public_success_can_promote_and_both_exam_barriers_remain_intact(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch)
    result=ex.read(root/'promotion_results.json')
    assert all(p=='pretest' for _,p in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    p=result['designs']['Prob003']
    assert p['retained_entries']==1 and p['certified_validation']['retained_passed']==4
    assert p['final_exam']=={'B_0':0,'B_5':2}
    gate=ex.read(root/'initial_exam_gate.json')
    for row in gate['members']:
        assert ex.sha(root/row['design']/'collection/initial_exam.json')==row['initial_exam_sha256']
    assert result['hard_max_requests']==486 and result['normal_max_requests']==243
