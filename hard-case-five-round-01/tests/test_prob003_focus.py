import importlib.util,json,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('focus_experiment',HERE/'experiment-prob003-focus-v1.py')
helpers=module('focus_fixtures',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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
def diagnostic():
    from r3e.loop import fsm_diagnostics
    return fsm_diagnostics


def test_no_material_budget_learning_or_other_design_prompt_change():
    _,loop,*_=ex.runner('Prob003').modules()
    old=module('old_focus_prompts',HERE/'source-promotion-fsmtrace-v1/r3e/loop/targeted_prompts.py')
    for key in ('prob001','prob023'):
        assert loop.targeted_prompts.BLUE[key]==old.BLUE[key]
        assert loop.targeted_prompts.RED[key]==old.RED[key]
        for n in range(1,6):
            for obs in ([],[dict(round=1,label='public_pass_single_sample_hidden_unknown',source_hash='one')]):
                assert loop.targeted_prompts.red_guidance(key,n,obs)==old.red_guidance(key,n,obs)
    assert loop.targeted_prompts.CURRICULUM_POLICY==old.CURRICULUM_POLICY
    for design in ex.DESIGNS:
        assert ex.material(design)==ex.read(HERE/'materials-listed-v2'/design/'materials.json')
        assert ex.cap(design)==162
    for name in ('r3e/loop/continuous_state.py','experiments/loop_probes/red907_measure.py'):
        assert (ex.PROMOTION_SOURCE/name).read_bytes()==(HERE/'source-promotion-fsmtrace-v1'/name).read_bytes()


def test_fault_focus_links_boundary_alias_to_actual_public_output_failure():
    loop,m,p=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    r=loop.rb.execute(task,{})
    loc=r.evidence['suites']['W_bug']['public_state_trace']['localization']
    assert r.tier=='visible_fail' and loc['first_output_mismatch']['cycle']==12
    conflict=loc['earliest_observed_state_context_conflict']
    assert conflict['cycle']==7 and conflict['state_name']=='idle'
    assert conflict['earlier_context']['position']==0 and conflict['current_context']['position']==1
    edge=next(x for x in loc['focus_window'] if x['cycle']==7)
    assert edge['input_bit']==0 and edge['current_branch']['selected']=='idle'
    assert edge['current_branch']['agrees_with_simulator']
    assert all(f.startswith('public/') for f in task.read_files)


def test_first_group_failure_keeps_all_six_edges_and_never_guesses_correct_state():
    loop,m,p=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    bad=p['clean_rtl'].replace('nstate=data?s3:sf3;','nstate=data?sf3:s3;')
    r=loop.rb.execute(task,{'rtl/sequence.sv':bad})
    loc=r.evidence['suites']['W_bug']['public_state_trace']['localization']
    assert loc['first_output_mismatch']['cycle']==6
    assert [x['cycle'] for x in loc['focus_window']]==list(range(1,7))
    assert 'first group already fails' in loc['repair_focus']
    assert 'expected_state' not in json.dumps(loc)


def test_truth_table_uses_actual_ternary_polarity_not_reply_description():
    _,_,public=core();d=diagnostic();old=public['clean_rtl'];new=old.replace('nstate=data?sf1:s1;','nstate=data?s1:sf1;')
    r=d.attempt_delta('Prob003','target 011100',{'rtl/x.sv':old},{'rtl/x.sv':new},{},{})
    branches=r['changes'][0]['branch_truth_table_changes']
    assert branches and all(b['swapped_binary_targets'] for b in branches)
    assert all(b['before']=={'0':'s1','1':'sf1'} and b['after']=={'0':'sf1','1':'s1'} for b in branches)
    constants,_=d.state_tables(old)
    assert constants['idle']==0 and 'not_match' not in constants


def test_noop_and_sensitivity_only_feedback_remain_different():
    _,_,public=core();d=diagnostic();old=public['clean_rtl'];ev={'suites':{'W_bug':{'result':'visible_fail','log':'CHECK_FAIL cycle=12'}}}
    r=d.attempt_delta('Prob003','011100',{'x':old},{'x':old+'\n // formatting'},ev,ev)
    assert r['no_syntax_token_change'] and r['public_failure_unchanged']
    new=old.replace('always @(pstate or data or rst_n)','always @(pstate or rst_n)')
    assert new!=old
    r=d.attempt_delta('Prob003','011100',{'x':old},{'x':new},ev,ev)
    assert not r['no_syntax_token_change'] and r['changes'][0]['only_sensitivity_lists_changed']
    assert r['public_failure_unchanged']
    changed={'suites':{'W_bug':{'result':'visible_fail','log':'CHECK_FAIL cycle=18'}}}
    assert not d.attempt_delta('Prob003','011100',{'x':old},{'x':new},ev,changed)['public_failure_unchanged']


def test_two_attempt_delivery_contains_only_current_sample_delta(tmp_path):
    row,requests,*_=helpers.run_trial(tmp_path,[lambda u,p:helpers.source(u['files']['rtl/sequence.sv']['content']+'\n'),lambda u,p:helpers.source(p['clean_rtl'])],design='Prob003')
    assert row['outcome']=='fixed' and len(requests)==2
    assert 'public_previous_patch_feedback' not in requests[0]
    delta=requests[1]['public_previous_patch_feedback']
    assert delta['no_syntax_token_change'] and delta['public_failure_unchanged']
    assert requests[1]['public_fault_focus']['suites']['W_bug']['first_output_mismatch']['cycle']==12
    assert requests[1]['public_feedback_correction']['remaining_functional_corrections']==0


@pytest.mark.parametrize('design',['Prob001','Prob023'])
def test_other_design_repair_payload_gets_no_prob003_fields(tmp_path,design):
    row,requests,*_=helpers.run_trial(tmp_path,[lambda u,p:helpers.source(u['files']['rtl/sequence.sv']['content']),lambda u,p:helpers.source(p['clean_rtl'])],design=design)
    assert len(requests)==2 and row['outcome']=='fixed'
    for u in requests:
        assert not {'public_group_worksheet','public_fault_focus','public_previous_patch_feedback'} & u.keys()
    assert diagnostic().attempt_delta(design,'011100',{}, {}, {}, {}) is None


def test_red_initial_rounds_differ_and_failure_cannot_unlock_boundary():
    loop,_,public=core();g=loop.targeted_prompts
    one=g.red_guidance(public['carrier_id'],1,[]);two=g.red_guidance(public['carrier_id'],2,[])
    assert one['focus']!=two['focus'] and 'polarity' in one['focus'] and 'progression' in two['focus']
    failed=[dict(round=4,label='public_functional_failure_single_sample_unconfirmed',source_hash='f')]
    assert g.red_guidance(public['carrier_id'],5,failed)['stage']=='single_local_fault'
    success=[dict(round=i,label='public_pass_single_sample_hidden_unknown',source_hash=str(i)) for i in (1,2)]
    assert g.red_guidance(public['carrier_id'],3,success)['stage']=='boundary_transfer'
    assert g.red_guidance(public['carrier_id'],5,success+[{**success[-1],'round':4,'source_hash':'4'}])['stage']=='linked_transfer'


def test_fresh_b0_and_within_batch_promotion_and_barriers(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch)
    result=ex.read(root/'promotion_results.json')
    assert result['designs']['Prob003']['retained_entries']==1
    assert result['designs']['Prob003']['certified_validation']==dict(initial_passed=0,retained_passed=4,samples=4,incumbent_scores_cached=True)
    assert result['comparison']['complete']
    assert all(phase=='pretest' for _,phase in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    # The initial B0 snapshot is empty even though the completed batch has an entry.
    commits=list((root/'Prob003/collection/rounds/0').glob('commit.json'))
    assert len(commits)==1 and ex.read(commits[0])['blue']['entries']==[]
    gate=ex.read(root/'initial_exam_gate.json')
    for row in gate['members']:assert ex.sha(root/row['design']/'collection/initial_exam.json')==row['initial_exam_sha256']
    assert result['hard_max_requests']==486 and result['normal_max_requests']==243


def test_compile_failure_retains_public_diagnostics_and_bounded_correction(tmp_path):
    row,requests,*_=helpers.run_trial(tmp_path,[helpers.source('module broken('),lambda u,p:helpers.source(p['clean_rtl'])],design='Prob003')
    assert row['outcome']=='fixed' and len(requests)==2
    assert requests[1]['current_failure_evidence']['result']=='compile_fail'
    assert requests[1]['public_previous_patch_feedback']['no_syntax_token_change'] is False


def test_unsupported_fsm_architecture_preserves_original_failure():
    loop,m,p=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    source=(task.repo/'rtl/sequence.sv').read_text().replace('pstate','current_state')
    result=loop.rb.execute(task,{'rtl/sequence.sv':source})
    assert result.tier=='visible_fail'
    assert result.evidence['suites']['W_bug']['public_state_trace']['status']=='unavailable'
    assert diagnostic().failure_focus(task.task['task_id'],task.spec,{'result':result.tier,**result.evidence}) is None


def test_next_sample_starts_without_previous_sample_patch_feedback(tmp_path):
    for index in range(2):
        row,requests,*_=helpers.run_trial(tmp_path/str(index),[lambda u,p:helpers.source(u['files']['rtl/sequence.sv']['content']),lambda u,p:helpers.source(p['clean_rtl'])],design='Prob003')
        assert row['outcome']=='fixed'
        assert 'public_previous_patch_feedback' not in requests[0]
        assert requests[1]['public_previous_patch_feedback']['no_syntax_token_change']
