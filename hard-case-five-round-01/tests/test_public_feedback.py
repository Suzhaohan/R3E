import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('feedback_experiment',HERE/'experiment-feedback-v1.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

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


def core(design='Prob023'):
    _,loop,*_=ex.runner(design).modules()
    m=ex.material(design)
    public=loop.red907.public_material(Path(m['carriers'][0]['package']),ex.read(m['carriers'][0]['suite_freeze']))
    return loop,m,public


def run_trial(tmp_path,replies,design='Prob023'):
    loop,m,public=core(design)
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.fakes import _reply
    from r3e.loop.token_count import TokenCounter
    requests=[]
    def transport(**request):
        u=json.loads(request['messages'][-1]['content']);requests.append(u)
        answer=replies[len(requests)-1](u,public) if callable(replies[len(requests)-1]) else replies[len(requests)-1]
        return _reply(answer,1)
    c=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000)
    counter=TokenCounter();out=tmp_path/'blue'
    result=loop.measure.run_blue(Path(m['anchors'][0]['task_dir']),out,client=BudgetedClient(c,max_calls=4),counter=counter,
        cfg=loop.CONFIG,seed=700,encounters=1,direct_only=True,endpoint_protocol='public_feedback')
    return result[0],requests,out,loop,m,public


def source(text,request=None):
    if request is not None and 'transitions' in request.get('required_output_schema',{}):
        from r3e.loop.fsm_diagnostics import state_tables
        constants,rows=state_tables(text)
        return dict(transitions=[dict(state=k,on_0=v['0'],on_1=v['1']) for k,v in rows.items() if k in constants],edit='offline scripted transition repair')
    return dict(files=[dict(file='rtl/sequence.sv',content=text)],edit='offline scripted repair')
def noop(u,p):return source(u['files']['rtl/sequence.sv']['content'])
def clean(u,p):return source(p['clean_rtl'])


def test_public_simulation_feedback_repairs_historical_gray_phase_error(tmp_path):
    # Reproduce the previous run's extra-enable timing error without reading a historical run.
    def phase_error(u,public):
        bad=public['clean_rtl'].replace('reg [3:0] bin_add_wire;',
            'reg [3:0] bin_add_wire;\nreg toggle;\nalways @(posedge clk or negedge rst_n) if (!rst_n) toggle <= 0; else toggle <= ~toggle;')
        bad=bad.replace("else begin\n      bin_add_wire <= bin_out + 1'b1;", "else if (toggle) begin\n      bin_add_wire <= bin_out + 1'b1;")
        return source(bad)
    result,requests,out,loop,m,public=run_trial(tmp_path,[phase_error,clean])
    assert result['outcome']=='fixed' and result['calls']==2
    assert requests[1]['submission_kind']=='public_feedback_correction'
    feedback=json.dumps(requests[1]['current_failure_evidence'])
    assert 'CHECK_FAIL gray cycle=1 got=0000 expected=0001' in feedback
    assert 'reg toggle;' in requests[1]['files']['rtl/sequence.sv']['content']
    assert requests[1]['previous_attempts'][0]['result']=='visible_fail'
    assert 'public_repair_guidance' in requests[0]
    assert set(requests[1]).isdisjoint({'evaluator','hidden','correct_solution','clean_rtl','exam_results'})
    assert loop.measure.classify(out,Path(m['anchors'][0]['task_dir']),ex.read(m['carriers'][0]['evaluator_freeze']),Path(m['carriers'][0]['evaluator_root']))['summary']['categories']=={'public_pass_hidden_pass':1}


def test_compile_feedback_can_be_corrected_within_same_trial(tmp_path):
    result,requests,*_=run_trial(tmp_path,[source('module TopModule(input clk input rst_n); endmodule'),clean])
    assert result['outcome']=='fixed' and result['calls']==2
    assert result['attempts'][0]['tier']=='compile_fail'
    assert 'syntax' in json.dumps(requests[1]['current_failure_evidence']).lower()


def test_persistent_functional_failure_stops_after_two_attempts(tmp_path):
    result,requests,out,loop,m,_=run_trial(tmp_path,[noop,noop])
    assert result['outcome']=='not_fixed' and result['calls']==2 and len(requests)==2
    classified=loop.measure.classify(out,Path(m['anchors'][0]['task_dir']),ex.read(m['carriers'][0]['evaluator_freeze']),Path(m['carriers'][0]['evaluator_root']))
    assert classified['summary']['categories']=={'no_candidate':1}  # both replies were valid unchanged RTL
    assert classified['encounters'][0]['calls']==2


def test_format_correction_and_functional_correction_have_four_call_hard_limit(tmp_path):
    invalid=dict(edits=[],edit='offline invalid format')
    result,requests,*_=run_trial(tmp_path,[invalid,noop,invalid,clean])
    assert result['outcome']=='fixed' and result['calls']==4
    assert [u['submission_kind'] for u in requests]==['repair','format_correction','public_feedback_correction','format_correction']
    assert 'public_feedback_correction' not in requests[1]
    assert 'public_feedback_correction' in requests[3]


def test_persistent_invalid_format_does_not_trigger_functional_retry(tmp_path):
    invalid=dict(edits=[],edit='offline invalid format')
    result,requests,*_=run_trial(tmp_path,[invalid,invalid])
    assert result['outcome']=='not_fixed' and result['calls']==2
    assert result['attempts'][0]['tier']=='invalid_edit'


def test_early_success_costs_one_call(tmp_path):
    result,requests,*_=run_trial(tmp_path,[clean])
    assert result['outcome']=='fixed' and result['calls']==1


def observations(successes=0,failed_latest=False,latest_round=None):
    rows=[dict(round=i+1,label='public_pass_single_sample_hidden_unknown',source_hash=str(i)) for i in range(successes)]
    if failed_latest:rows.append(dict(round=successes+1,label='public_functional_failure_single_sample_unconfirmed',source_hash='failure'))
    if latest_round is not None:
        offset=latest_round-rows[-1]['round']
        for obs in rows:obs['round']+=offset
    return rows


@pytest.mark.parametrize('design',['Prob023','Prob003'])
def test_curriculum_uses_public_success_and_resets_after_failure(design):
    loop,m,p=core(design);g=loop.targeted_prompts
    assert g.curriculum_stage(p['carrier_id'],5,[])['stage']=='single_local_fault'
    assert g.curriculum_stage(p['carrier_id'],2,observations(2))['stage']=='single_local_fault'
    assert g.curriculum_stage(p['carrier_id'],3,observations(2))['stage']=='boundary_transfer'
    assert g.curriculum_stage(p['carrier_id'],5,observations(2,latest_round=4))['stage']=='linked_transfer'
    assert g.curriculum_stage(p['carrier_id'],5,observations(2,True,latest_round=4))['stage']=='single_local_fault'
    # A prior success does not cover a later empty or unusable-format round.
    assert g.curriculum_stage(p['carrier_id'],5,observations(2))['stage']=='single_local_fault'
    # Order and duplicate observations cannot manufacture the success gate.
    repeated=observations(1,latest_round=4)*3
    assert g.curriculum_stage(p['carrier_id'],5,repeated)['stage']=='single_local_fault'


def test_gray_curriculum_protects_register_schedule_and_requires_single_fault():
    loop,m,p=core();g=loop.targeted_prompts
    def proposal(old,new):return dict(status='proposal',buggy_rtl=p['clean_rtl'].replace(old,new))
    assert g.curriculum_violation(p,proposal('gray_wire[2]^bin_out[3]','gray_wire[2]&bin_out[3]'),5,[]) is None
    assert g.curriculum_violation(p,proposal("bin_out + 1'b1","bin_out + 1'b0"),5,[])
    double=proposal('gray_wire[2]^bin_out[3]','gray_wire[2]&bin_out[3]')
    double['buggy_rtl']=double['buggy_rtl'].replace('gray_wire[1]^bin_out[2]','gray_wire[1]|bin_out[2]')
    assert g.curriculum_violation(p,double,5,[])
    assert g.curriculum_violation(p,double,5,observations(2,latest_round=4)) is None


def test_sequence_curriculum_protects_terminal_and_idle_boundaries():
    loop,m,p=core('Prob003');g=loop.targeted_prompts
    def proposal(old,new):return dict(status='proposal',buggy_rtl=p['clean_rtl'].replace(old,new))
    local=proposal('nstate=data?s2:sf2;','nstate=data?s2:sf3;')
    boundary=proposal('nstate=data?sf1:s1;','nstate=data?sf1:s2;')
    assert g.curriculum_violation(p,local,5,[]) is None
    assert g.curriculum_violation(p,boundary,5,[])
    # Both terminal arms change, which is only allowed in the linked stage.
    assert g.curriculum_violation(p,boundary,5,observations(2,latest_round=4)) is None


def test_transfer_summary_requires_actual_public_success_and_validates_schema():
    loop,m,p=core();s=loop.state
    src=dict(round=1,carrier_id=p['carrier_id'])
    archive=dict(patch='--- a/x\n+++ b/x\n- bad\n+ repaired\n')
    with pytest.raises(ValueError,match='fully public-passing'):s.episode_entry(src,'public spec',archive,dict(W_bug='visible_fail',W_preserve='visible_pass'))
    entry=s.episode_entry(src,'public spec',archive,dict(W_bug='visible_pass',W_preserve='visible_pass'))
    s.validate_entry(entry)
    summary=entry['body']['content']['transfer_summary']
    assert summary['changed_lines']==['- bad','+ repaired']
    assert any('cadence' in x for x in summary['checks_on_transfer'])
    assert loop.rb.valid_transfer_summary(summary)
    assert not loop.rb.valid_transfer_summary({**summary,'scope':'proven universal repair'})


def batch(tmp_path,monkeypatch,saturated=False,training_success_attempt=2,practice_edits=None,neutral_validation=False,all_structured_rounds=False,force_all_validation_fail=False):
    original=ex.runner;order=[]
    edits={
      'Prob001':dict(find='a_tem[6:0]',replace='a_tem[5:0]'),
      'Prob023':dict(find='gray_wire[2]^bin_out[3]',replace='gray_wire[2]&bin_out[3]'),
      'Prob003':dict(find='nstate=data?s2:sf2;',replace='nstate=data?s2:sf3;'),
      'Prob017':dict(find='div_o-1',replace='div_o+1')}
    if practice_edits:edits.update(practice_edits)
    def runner(design):
        base=original(design)
        def smoke(out):
            _,loop,*_=base.modules();m=ex.material(design)
            from r3e.loop.env import build_client
            from r3e.loop.budget import BudgetedClient
            from r3e.loop.fakes import _reply
            from r3e.loop.token_count import TokenCounter
            clean=(Path(m['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
            trial=red=trial_in_round=0
            def transport(**request):
                nonlocal trial,red,trial_in_round
                u=json.loads(request['messages'][-1]['content'])
                if 'carrier' in u:
                    red+=1;trial_in_round=0;order.append((design,'red'))
                    value={'candidates':[dict(edits=[edits[design]],violated_requirement='offline reachable public defect',spec_basis='unchanged public specification')]} if red==1 else {'abstain':'offline fixture'}
                    if 'structured_transition_actions' in u and (red==1 or all_structured_rounds):
                        choice=(next(a for a in u['structured_transition_actions']['available_actions'] if a['state']=='s5' and a['operation']=='swap_targets') if red==1 else u['structured_transition_actions']['available_actions'][0])
                        value={'candidate_actions':[dict(action_id=choice['action_id'],violated_requirement='offline reachable public defect',spec_basis='unchanged public specification')]}
                else:
                    if u['submission_kind']=='repair':
                        trial+=1;trial_in_round+=int(red>0)
                    phase='pretest' if trial<=2 else 'baseline' if trial<=6 else 'practice_or_validation' if red<5 else 'B5'
                    order.append((design,phase))
                    can_correct=bool(u.get('public_feedback_correction')) and (trial not in (7,8) or len(u['previous_attempts']) >= training_success_attempt-1)
                    content=clean if saturated is True or ((saturated=='after_correction' or trial>6) and can_correct) else u['files']['rtl/sequence.sv']['content']
                    if neutral_validation and trial>=9 and red<2:content=u['files']['rtl/sequence.sv']['content']
                    if force_all_validation_fail and red>0 and trial_in_round>2:content=u['files']['rtl/sequence.sv']['content']
                    value=source(content,u)
                return _reply(value,1)
            client=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000)
            counter=TokenCounter();plan=loop.make_plan(m['carriers'],m['anchors'],counter=counter,client_config=client.config.public_identity,
                rounds=5,slots_per_round=1,seed=700,carrier_mode='fixed',fixed_carrier_index=0,anchor_repeats=2,
                mechanism_focus=m['mechanism_focus'],red_output_tokens=16000,reserved_collision_retries=1)
            assert plan['max_calls']==ex.cap(design)
            result=loop.collect(plan,out,client=BudgetedClient(client,max_calls=plan['max_calls']),counter=counter)
            ex.save(out/'simulation_only.json',dict(fake=True,model_calls=0));return result
        base.smoke=smoke;return base
    monkeypatch.setattr(ex,'runner',runner)
    root=tmp_path/'batch';monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--run-dir',str(root)])
    ex.main();return root,order


def test_full_batch_feedback_creates_promoted_experience_with_both_global_barriers(tmp_path,monkeypatch):
    root,order=batch(tmp_path,monkeypatch)
    assert all(phase=='pretest' for _,phase in order[:12])
    assert sum(phase=='pretest' for _,phase in order)==12  # six trials, two attempts; no static re-exam
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    result=ex.read(root/'promotion_results.json')
    assert result['comparison']['complete'] and result['comparison']['static_passed_completed_designs']==0
    assert result['comparison']['promotion_passed_completed_designs']==6
    assert result['normal_max_requests']==243 and result['hard_max_requests']==486
    gate=ex.read(root/'initial_exam_gate.json')
    for design in ex.DESIGNS:
        row=result['designs'][design]
        assert row['accepted_promotions']==1 and row['retained_entries']==1
        assert row['qualified_online_practices']==1 and row['empty_practice_slots']==4
        assert row['certified_validation']['initial_passed']==0 and row['certified_validation']['retained_passed']==4
        c=root/design/'collection';initial=ex.read(c/'initial_exam.json')
        assert ex.sha(c/'initial_exam.json')==next(m['initial_exam_sha256'] for m in gate['members'] if m['design']==design)
        for name,digest in initial['evidence_hashes'].items():assert ex.sha(c/name)==digest
        commit=ex.read(c/'rounds/5/commit.json')
        assert commit['blue']['entries'][0]['body']['content']['transfer_summary']['changed_lines']
        assert (c/'audits/source_audit.json').exists()
        for role in ('online','reference'):
            encounter=ex.read(c/f'rounds/1/r1_s0/{role}/blue/encounters.jsonl')
            assert encounter['result']['calls']==2
            assert encounter['result']['attempts'][1]['submissions'][0]['kind']=='public_feedback_correction'
            assert ex.read(c/f'rounds/1/r1_s0/{role}/blue/blue_config.json')['runner']['budget_k']==2


def test_saturated_batch_stops_before_any_training_with_new_budget(tmp_path,monkeypatch):
    root,order=batch(tmp_path,monkeypatch,saturated=True)
    assert len(order)==6 and all(phase=='pretest' for _,phase in order)
    assert ex.read(root/'initial_exam_gate.json')['decision']=='stop_saturated'
    assert not (root/'training_barrier.json').exists()


def test_saturation_uses_corrected_static_endpoints_without_starting_training(tmp_path,monkeypatch):
    root,order=batch(tmp_path,monkeypatch,saturated='after_correction')
    gate=ex.read(root/'initial_exam_gate.json')
    assert gate['decision']=='stop_saturated' and gate['passed']==6
    assert len(order)==12 and all(phase=='pretest' for _,phase in order)
    assert ex.read(root/'promotion_results.json')['actual_requests']==12


def test_wrong_feedback_protocol_budget_is_refused_before_model_calls(tmp_path):
    from dataclasses import replace
    loop,m,p=core()
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.token_count import TokenCounter
    def unexpected(**request):raise AssertionError('must refuse before any request')
    client=BudgetedClient(build_client({'DEEPSEEK_MODEL':'fake-local'},transport=unexpected,maximum_output_tokens=16000),max_calls=4)
    with pytest.raises(loop.measure.MeasurementRefused,match='two direct attempts'):
        loop.measure.run_blue(Path(m['anchors'][0]['task_dir']),tmp_path/'blue',client=client,counter=TokenCounter(),
            cfg=replace(loop.CONFIG,budget_k=1),seed=1,encounters=1,direct_only=True,endpoint_protocol='public_feedback')
    assert client.total_calls==0
