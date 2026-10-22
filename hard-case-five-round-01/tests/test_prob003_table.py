"""Offline interface and full-batch checks. Scripted replies do not prove model gains."""
import importlib.util,json,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ex=module('table_experiment',HERE/'experiment-prob003-table-guard-v1.py')
helpers=module('table_fixtures',HERE/'tests/test_public_feedback.py');helpers.ex=ex
old_source=helpers.source

def source(content):
    if 'pstate,nstate' not in content:return old_source(content)
    from r3e.loop.fsm_diagnostics import state_tables
    constants,rows=state_tables(content)
    return dict(transitions=[dict(state=k,on_0=v['0'],on_1=v['1']) for k,v in rows.items() if k in constants],edit='offline model-supplied transition fixture')

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

def training_trial(tmp_path,replies):
    from dataclasses import replace
    loop,_,_=helpers.core('Prob003');original=loop.CONFIG
    loop.CONFIG=replace(original,prob003_transition_training=True)
    try:return helpers.run_trial(tmp_path,replies,design='Prob003')
    finally:loop.CONFIG=original


def test_model_rows_materialize_actual_repairs_and_pass_both_real_suites():
    loop,m,p=core()
    from r3e.loop import transition_repair as tr
    task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']));files={'rtl/sequence.sv':(task.repo/'rtl/sequence.sv').read_text()};allowed=set(files)
    ctx=tr.context(task.task['task_id'],task.spec,files,allowed)
    assert ctx and ctx['maximum_changed_rows']==2
    reply=source(p['clean_rtl']);new,why=tr.apply(files,allowed,ctx,reply)
    assert why is None and loop.rb.execute(task,new).tier=='visible_pass'
    c=m['carriers'][0]
    assert loop.measure._evaluate(task,new,ex.read(c['evaluator_freeze']),Path(c['evaluator_root'])/'evaluator')['result']=='pass'
    # Only the two submitted terminal rows change, not the reset/output/other states.
    from r3e.loop.fsm_diagnostics import state_tables
    _,before=state_tables(files['rtl/sequence.sv']);_,after=state_tables(new['rtl/sequence.sv'])
    assert {k for k in before if before[k]!=after[k]}=={'s6','sf6'}
    assert 'always @(posedge clk or negedge rst_n)' in new['rtl/sequence.sv']


def test_current_table_and_claimed_repair_without_changes_are_rejected():
    loop,m,p=core()
    from r3e.loop import transition_repair as tr
    task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']));files={'rtl/sequence.sv':(task.repo/'rtl/sequence.sv').read_text()};ctx=tr.context(task.task['task_id'],task.spec,files,set(files))
    result=source(files['rtl/sequence.sv']);result['edit']='I fixed the bug'
    new,why=tr.apply(files,set(files),ctx,result)
    assert new is None and why.startswith('no_transition_change:')
    assert tr.validate(old_source(p['clean_rtl']))


def test_destinations_and_row_budget_cannot_inject_code_or_rewrite_reset():
    loop,m,p=core()
    from r3e.loop import transition_repair as tr
    files={'rtl/sequence.sv':p['clean_rtl']};ctx=tr.context('Prob003','011100',files,set(files))
    assert tr.validate(dict(transitions=[dict(state='s1',on_0='s2; endmodule',on_1='s2')],edit='bad'))
    new,why=tr.apply(files,set(files),ctx,dict(transitions=[dict(state='s1',on_0='missing',on_1='s2')],edit='bad'))
    assert new is None and 'declared' in why
    reply=dict(transitions=[dict(state=k,on_0='idle',on_1='idle') for k in ('s1','s2','s3')],edit='too broad')
    new,why=tr.apply(files,set(files),ctx,reply)
    assert new is None and 'one or two' in why


def test_only_model_selected_rows_are_applied_no_automatic_solution_completion():
    loop,m,p=core()
    from r3e.loop import transition_repair as tr
    task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']));files={'rtl/sequence.sv':(task.repo/'rtl/sequence.sv').read_text()};ctx=tr.context(task.task['task_id'],task.spec,files,set(files))
    partial=dict(transitions=[dict(state='s6',on_0='s1',on_1='sf1')],edit='repair one terminal only')
    new,why=tr.apply(files,set(files),ctx,partial)
    assert why is None and loop.rb.execute(task,new).tier=='visible_fail'
    from r3e.loop.fsm_diagnostics import state_tables
    _,rows=state_tables(new['rtl/sequence.sv']);assert rows['sf6']=={'0':'idle','1':'idle'}


def test_all_fixed_validation_tasks_can_be_repaired_through_same_interface():
    loop,m,p=core()
    from r3e.loop import transition_repair as tr
    for path in loop.PROMOTION_VALIDATION:
        task=loop.rb.RepoTask.load(Path(path));files={'rtl/sequence.sv':(task.repo/'rtl/sequence.sv').read_text()};ctx=tr.context(task.task['task_id'],task.spec,files,set(files))
        fixed,why=tr.apply(files,set(files),ctx,source(p['clean_rtl']))
        assert why is None and loop.rb.execute(task,fixed).tier=='visible_pass'


def test_two_attempt_interface_rejects_noop_then_accepts_real_model_rows(tmp_path):
    row,requests,out,*_=training_trial(tmp_path,[lambda u,p:source(u['files']['rtl/sequence.sv']['content']),lambda u,p:source(p['clean_rtl'])])
    assert row['outcome']=='fixed' and len(requests)==2
    assert row['attempts'][0]['tier']=='visible_fail'
    assert row['attempts'][0]['transition_submission_feedback'].startswith('no_transition_change:')
    assert requests[1]['previous_attempts'][0]['reason'].startswith('no_transition_change:')
    assert all(u['required_output_schema'].get('transitions') for u in requests)
    assert all(u['output_constraints']['no_complete_source_files'] for u in requests)
    assert requests[1]['public_feedback_correction']['remaining_functional_corrections']==0


def test_invalid_format_correction_does_not_add_functional_feedback(tmp_path):
    row,requests,*_=training_trial(tmp_path,[{'bad':'format'},lambda u,p:source(p['clean_rtl'])])
    assert row['outcome']=='fixed' and len(requests)==2
    assert requests[1]['submission_kind']=='format_correction'
    assert requests[0]['current_failure_evidence']==requests[1]['current_failure_evidence']
    assert 'transitions and edit' in requests[1]['format_correction']['instruction']


@pytest.mark.parametrize('design',['Prob001','Prob023'])
def test_other_designs_keep_full_file_interface(tmp_path,design):
    row,requests,*_=helpers.run_trial(tmp_path,[lambda u,p:old_source(u['files']['rtl/sequence.sv']['content']),lambda u,p:old_source(p['clean_rtl'])],design=design)
    assert row['outcome']=='fixed' and len(requests)==2
    assert all('current_transition_table' not in u and 'files' in u['required_output_schema'] for u in requests)


def test_scripted_five_round_batch_promotes_real_current_batch_sources(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch)
    result=ex.read(root/'promotion_results.json');third=result['designs']['Prob003']
    assert third['retained_entries']==1 and third['final_exam']=={'B_0':0,'B_5':2}
    assert third['certified_validation']['retained_passed']==4
    assert ex.read(root/'Prob003/collection/rounds/0/commit.json')['blue']['entries']==[]
    assert all(phase=='pretest' for _,phase in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    assert result['normal_max_requests']==243 and result['hard_max_requests']==486
    third=root/'Prob003/collection'
    for pattern in ('anchors/**/request_*.json','validation_baseline/**/request_*.json','promotion/**/request_*.json'):
        paths=list(third.glob(pattern));assert paths
        for path in paths:
            u=json.loads(ex.read(path)['messages'][-1]['content'])
            assert 'files' in u['required_output_schema'] and 'current_transition_table' not in u
    for role in ('online','reference'):
        paths=list(third.glob('rounds/*/*/'+role+'/blue/submissions/request_*.json'));assert paths
        for path in paths:
            u=json.loads(ex.read(path)['messages'][-1]['content'])
            assert 'transitions' in u['required_output_schema']
