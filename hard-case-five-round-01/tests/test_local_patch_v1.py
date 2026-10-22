"""Submission correctness, bounded feedback, and the common Blue interface."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('local_patch_experiment',HERE/'experiment-local-patch-v2.py')
helpers=module('local_patch_helpers',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def patch(old,new):
    return {'edits':[{'file':'rtl/sequence.sv','find':old,'replace':new}],
            'edit':'The public failure requires changing the current assignment.'}

def clean(u,p):return patch(u['files']['rtl/sequence.sv']['content'],p['clean_rtl'])
def noop(u,p):return helpers.source(u['files']['rtl/sequence.sv']['content'])


def test_patch_scope_unique_atomic_and_current_source_noop():
    loop,_,_=helpers.core();prepare=loop.rb.prepare_submission
    src={'rtl/sequence.sv':'module m; wire a; endmodule'};allowed=set(src)
    good=patch('wire a','wire b')
    new,why=prepare(good,src,allowed)
    assert why is None and 'wire b' in new['rtl/sequence.sv']
    assert prepare(good,new,allowed)[0] is None  # stale find
    assert prepare(patch('wire a','wire a'),src,allowed)[0] is None
    assert prepare(helpers.source(src['rtl/sequence.sv']+' // claimed repair'),src,allowed)[0] is None
    assert prepare(patch('wire a','wire  a'),src,allowed)[0] is None
    bad=patch('wire a','wire b');bad['edits'].append({'file':'tb/test.sv','find':'a','replace':'b'})
    assert prepare(bad,src,allowed)[0] is None and src['rtl/sequence.sv'].find('wire a')>=0
    repeat={'rtl/sequence.sv':'module m; wire a; wire a; endmodule'}
    assert prepare(good,repeat,allowed)[0] is None  # ambiguous text
    directive=patch('wire a','`define FLAG 1\nwire a')
    assert prepare(directive,src,allowed)[0] is not None


def test_unchanged_claim_gets_bounded_correction_then_real_patch(tmp_path):
    result,requests,out,loop,_,_=helpers.run_trial(tmp_path,[noop,clean])
    assert result['outcome']=='fixed' and result['calls']==2
    assert [u['submission_kind'] for u in requests]==['repair','format_correction']
    assert 'unchanged_source' in requests[1]['format_correction']['error']
    assert 'public_feedback_correction' not in requests[1]
    assert requests[0]['current_failure_evidence']==requests[1]['current_failure_evidence']
    assert result['attempts'][0]['changed_files']==['rtl/sequence.sv']
    assert result['attempts'][0]['submissions'][0]['format_valid'] is False
    assert 'edits' in requests[0]['required_output_schema']
    assert 'complete replacement' not in loop.rb.SYSTEM_REPAIR


def test_repeated_unchanged_claim_stops_without_testing_or_extra_calls(tmp_path):
    result,requests,*_=helpers.run_trial(tmp_path,[noop,noop])
    assert result['outcome']=='not_fixed' and result['calls']==2
    assert len(result['attempts'])==1 and result['attempts'][0]['tier']=='invalid_edit'
    assert result['final_candidate_hash'] is None


def test_compile_failure_still_returns_real_feedback_and_repair(tmp_path):
    def syntax(u,p):return patch(u['files']['rtl/sequence.sv']['content'],'module TopModule(input clk input rst_n); endmodule')
    result,requests,*_=helpers.run_trial(tmp_path,[syntax,clean])
    assert result['outcome']=='fixed' and result['calls']==2
    assert result['attempts'][0]['tier']=='compile_fail'
    assert requests[1]['submission_kind']=='public_feedback_correction'
    assert 'syntax' in json.dumps(requests[1]['current_failure_evidence']).lower()


def test_unchanged_is_checked_against_previous_candidate_not_original(tmp_path):
    def wrong(u,p):
        text=p['clean_rtl'].replace("bin_out + 1'b1","bin_out + 1'b0")
        return patch(u['files']['rtl/sequence.sv']['content'],text)
    result,requests,*_=helpers.run_trial(tmp_path,[wrong,noop,clean])
    assert result['outcome']=='fixed' and result['calls']==3
    assert result['attempts'][0]['tier']=='visible_fail'
    assert requests[2]['submission_kind']=='format_correction'
    assert 'unchanged_source' in requests[2]['format_correction']['error']
    assert requests[1]['files']==requests[2]['files']

@pytest.mark.parametrize('learning_passes',[True,False])
def test_bounded_probe_reports_failure_or_both_arms(tmp_path,monkeypatch,learning_passes):
    probe=module('local_patch_probe_'+str(learning_passes),HERE/'transfer_probe.py');probe.ex=ex
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
            text=u['files']['rtl/sequence.sv']['content']
            value=patch(text,p['clean_rtl']) if learning_passes else helpers.source(text)
        return _reply(value,len(requests))
    monkeypatch.setattr(env,'ThinkingTransport',lambda *args,**kwargs:transport)
    key=tmp_path/'fake-key';key.write_text('fake-not-a-real-key')
    out=tmp_path/'probe';probe.execute(out,key)
    row=ex.read(out/'result.json')
    assert row['actual_calls']<=probe.MAX_CALLS
    if learning_passes:
        assert row['status']=='complete'
        assert row['static']['passed'] and row['adaptive']['passed']
        assert row['adaptive_minus_static']==0
        a,b=[u for u in requests if 'required_output_schema' in u][-2:]
        assert {k:v for k,v in a.items() if k!='repair_experience'}=={k:v for k,v in b.items() if k!='repair_experience'}
    else:
        assert row['status']=='stopped_no_successful_learning_episode'
        assert row['actual_calls']==2
        assert 'static' not in row and 'adaptive' not in row


def test_current_pipeline_preserves_training_bank_and_exam_barriers(tmp_path,monkeypatch):
    # Fake transport tests workflow only, with real EDA checks and actual patches.
    # Wrong fixture candidates must change source: a no-op is no longer a trial.
    def scripted_source(text,request=None):
        assert request is not None
        current=request['files']['rtl/sequence.sv']['content']
        if text==current:text+='\nINVALID_PUBLIC_FIXTURE_TOKEN\n'
        return patch(current,text)
    monkeypatch.setattr(helpers,'source',scripted_source)
    root,order=helpers.batch(tmp_path,monkeypatch,all_structured_rounds=True,force_all_validation_fail=True)
    row=ex.read(root/'promotion_results.json')['designs']['Prob003']
    assert row['training_experience_entries']==5
    assert row['retained_entries']==0 and row['accepted_promotions']==0
    for n in range(1,6):
        commit=ex.read(root/f'Prob003/collection/rounds/{n}/commit.json')
        assert len(commit['practice_blue']['entries'])==n and not commit['blue']['entries']
    assert (root/'training_barrier.json').exists()
    barrier=(root/'training_barrier.json').stat().st_mtime_ns
    for design in ex.DESIGNS:
        c=root/design/'collection'
        assert (c/'rounds/5/commit.json').stat().st_mtime_ns<=barrier
        assert all(p.stat().st_mtime_ns>=barrier for p in c.glob('anchors/b5*/blue/submissions/request_*.json'))


def test_previously_failed_candidate_gets_correction_instead_of_repeated_build(tmp_path,monkeypatch):
    loop,m,p=helpers.core()
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.fakes import _reply
    from r3e.loop.token_count import TokenCounter
    requests=[]
    a=p['clean_rtl'].replace("bin_out + 1'b1","bin_out + 1'b0")
    b=p['clean_rtl'].replace("bin_out + 1'b1","bin_out + 1'b1 + 1'b1")
    targets=[a,b,a,p['clean_rtl']]
    def transport(**request):
        u=json.loads(request['messages'][-1]['content']);requests.append(u)
        return _reply(patch(u['files']['rtl/sequence.sv']['content'],targets[len(requests)-1]),1)
    client=BudgetedClient(build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000),max_calls=8)
    counter=TokenCounter();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    cfg=loop.TRAINING_CONFIG;setup=loop.rb.setup(task,counter,cfg)
    original=loop.rb.execute;builds=[]
    def execute(*args,**kwargs):builds.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(loop.rb,'execute',execute)
    result=loop.rb.RepoBlueRunner(client=client,counter=counter,cfg=cfg,archive=tmp_path/'archive').run(task,setup,seed=700)
    assert result['outcome']=='fixed' and result['calls']==4
    assert len(builds)==3  # A failed, B failed, clean passed; repeated A never rebuilt.
    assert requests[3]['submission_kind']=='format_correction'
    assert 'known_public_failure' in requests[3]['format_correction']['error']
    assert requests[2]['current_failure_evidence']==requests[3]['current_failure_evidence']
