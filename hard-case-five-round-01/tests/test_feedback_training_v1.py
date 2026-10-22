import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('feedback_training_experiment',HERE/'experiment-working-experience-v1.py')
helpers=module('feedback_training_helpers',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def test_fourth_training_repair_teaches_but_exams_keep_two_attempts(tmp_path,monkeypatch):
    loop,_,_=helpers.core();seen=[];original=loop.rb.RepoBlueRunner._call
    def checked(self,phase,system,user,seed,journal=None):
        if phase=='blue_inference':
            assert system==loop.rb.SYSTEM_REPAIR
            assert not ({'public_repair_guidance','public_group_worksheet','public_fault_focus'} & set(user))
            assert not self.cfg.prob003_transition_training
            if user.get('public_feedback_correction'):
                diag=user['public_patch_diagnostics']
                assert diag['source']=='current_public_task_and_actual_submissions_only'
                assert 'clean_rtl' not in diag
            seen.append(self.cfg.budget_k)
        return original(self,phase,system,user,seed,journal)
    monkeypatch.setattr(loop.rb.RepoBlueRunner,'_call',checked)
    root,order=helpers.batch(tmp_path,monkeypatch,training_success_attempt=4,practice_edits={'Prob003':dict(find='nstate=data?sf6:s6;',replace='nstate=data?s6:sf6;')})
    summary=ex.read(root/'promotion_results.json')
    assert summary['comparison']['complete']
    assert summary['normal_max_requests']==303 and summary['hard_max_requests']==606
    assert set(seen)=={2,4}
    for design in ex.DESIGNS:
        c=root/design/'collection'
        row=summary['designs'][design]
        assert row['retained_entries']==1 and row['accepted_promotions']==1
        assert row['initial_static_exam']['passed']==0 and row['final_exam']['B_5']==2
        for role in ('online','reference'):
            b=c/f'rounds/1/r1_s0/{role}/blue'
            encounter=ex.read(b/'encounters.jsonl')['result']
            assert encounter['calls']==4
            assert [a['tier'] for a in encounter['attempts']]==['visible_fail']*3+['visible_pass']
            config=ex.read(b/'blue_config.json')
            assert config['endpoint_protocol']=='training_public_feedback' and config['runner']['budget_k']==4
        for path in (c/'anchors').glob('*/blue/blue_config.json'):
            assert ex.read(path)['runner']['budget_k']==2
        # First abstention is corrected once; a second still-abstaining answer is an honest empty slot.
        rows=[json.loads(s) for s in (c/'empty_practice.jsonl').read_text().splitlines()]
        assert all(r['online_requests']==2 and r['replacement_used'] is False for r in rows)
        retry=ex.read(c/'rounds/2/r2_s0/red_retry_1/request.json')['messages'][-1]['content']
        assert 'abstention is not evidence' in retry
    assert (root/'training_barrier.json').exists()


def test_original_bug_patch_feedback_exposes_added_cadence_and_passing_suite_regression():
    helpers.core()
    from r3e.loop.repair_diagnostics import correction_context
    original={'rtl/x.sv':'module x;\nreg a;\nendmodule\n'}
    current={'rtl/x.sv':'module x;\nreg a;\nreg toggle;\nendmodule\n'}
    d=correction_context(original,current,{'rtl/x.sv'},
        {'suites':{'W_bug':{'result':'visible_fail'},'W_preserve':{'result':'visible_pass'}}},
        {'suites':{'W_bug':{'result':'visible_fail'},'W_preserve':{'result':'visible_fail'}}},
        [{'evidence':'same public failure'},{'evidence':'same public failure'}],10000)
    assert d['original_buggy_files']==original
    assert '+reg toggle;' in d['patches_from_original_bug']['rtl/x.sv']['diff']
    assert d['regressed_public_suites']==['W_preserve'] and d['repeated_public_failure']
    assert not d['unchanged_from_original_bug']


def test_gray_inventory_contains_original_sites_and_tracks_used_expressions():
    loop,m,p=helpers.core('Prob023');g=loop.targeted_prompts
    edit=[{'find':'gray_wire[2]^bin_out[3]','replace':'gray_wire[2]&bin_out[3]'}]
    inventory=g.gray_inventory(p,5,[],[edit])
    assert len(inventory['sites'])>=4
    assert any(s['previous_candidate_count']==0 for s in inventory['sites'])
    assert sum(s['previous_candidate_count'] for s in inventory['sites'])==1
    assert all(s['clean_rhs'] in p['clean_rtl'] for s in inventory['sites'])
    assert inventory['stage']=='single_local_fault'
    assert 'not a proof' in inventory['instruction']


def test_exam_protocol_rejects_training_budget_before_any_call(tmp_path):
    loop,m,p=helpers.core()
    class NeverCalled:
        total_calls=0
    with pytest.raises(loop.measure.MeasurementRefused,match='two direct attempts'):
        loop.measure.run_blue(Path(m['anchors'][0]['task_dir']),tmp_path/'refused',
            client=NeverCalled(),counter=None,cfg=loop.TRAINING_CONFIG,seed=1,
            encounters=1,direct_only=True,endpoint_protocol='public_feedback')
    assert not (tmp_path/'refused').exists()

@pytest.mark.parametrize('replies,expected,calls',[
    (['noop']*4,'not_fixed',4),
    (['clean'],'fixed',1),
    (['compile','noop','clean'],'fixed',3),
])
def test_training_feedback_is_bounded_and_can_recover_compile_failure(tmp_path,replies,expected,calls):
    loop,m,p=helpers.core('Prob023')
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.fakes import _reply
    from r3e.loop.token_count import TokenCounter
    requests=[]
    def transport(**request):
        u=json.loads(request['messages'][-1]['content']);requests.append(u)
        kind=replies[len(requests)-1]
        text=p['clean_rtl'] if kind=='clean' else 'module TopModule(input clk input rst_n); endmodule' if kind=='compile' else u['files']['rtl/sequence.sv']['content']
        # After a compile failure, restore the ORIGINAL defect, not the clean answer.
        if kind=='noop' and 'original_buggy_files' in u.get('public_patch_diagnostics',{}):
            text=u['public_patch_diagnostics']['original_buggy_files'].get('rtl/sequence.sv',text)
        return _reply(helpers.source(text),1)
    client=BudgetedClient(build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000),max_calls=8)
    results=loop.measure.run_blue(Path(m['anchors'][0]['task_dir']),tmp_path/'training',client=client,
        counter=TokenCounter(),cfg=loop.TRAINING_CONFIG,seed=700,encounters=1,direct_only=True,
        endpoint_protocol='training_public_feedback')
    assert results[0]['outcome']==expected and results[0]['calls']==calls
    assert len(requests)==calls
    if replies[0]=='compile':
        assert requests[1]['current_failure_evidence']['result']=='compile_fail'
        assert requests[1]['public_patch_diagnostics']['original_buggy_files']['rtl/sequence.sv'] != p['clean_rtl']
