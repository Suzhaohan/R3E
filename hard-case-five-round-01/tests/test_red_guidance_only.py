import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('red_guidance_only_experiment',HERE/'experiment-red-guidance-only-v1.py')
helpers=module('prob017_feedback_fixtures',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def core():return helpers.core('Prob017')

def test_selected_original_case_and_existing_two_questions_are_unchanged():
    assert ex.DESIGNS==('Prob001','Prob023','Prob017')
    rows=ex.verify_questions();row=rows[2]
    assert row['case_id']=='chipbench:arithmetic:Prob017_arbitrary_fractional_frequency_division'
    assert row['artifact']=='dataset_original'
    for d in ex.DESIGNS[:2]:
        assert ex.material(d)==ex.read(HERE/'materials-listed-v2'/d/'materials.json')
        assert ex.read(ex.VALIDATION_ROOT/d/'validation.json')==ex.read(HERE/'validation-listed-v2'/d/'validation.json')
    assert (Path(ex.material('Prob017')['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv').read_bytes()==(ex.ROOT/row['buggy_rtl']).read_bytes()


def test_original_spec_is_retained_and_inconsistent_example_is_publicly_clarified():
    loop,m,public=core();package=Path(m['carriers'][0]['package']);original=ex.read(ex.SELECTION)['rows'][2]
    spec=(package/'spec.md').read_text()
    assert '53 output cycles' in spec and 'not an acceptance criterion' in spec
    assert 'PRE-EDGE' in spec and 'modulo 16' in spec and 'modulo 128' in spec
    assert (package.parent/'source_spec_original.txt').read_text() in spec
    assert original['current_v3_pass_rate']==dict(static_passed=1,adaptive_passed=2,samples=2,scope='prior independent pilot; not current 01 protocol')


def test_real_public_and_independent_checks_accept_clean_and_reject_original_defect():
    loop,m,public=core();c=m['carriers'][0];task=Path(m['anchors'][0]['task_dir']);t=loop.rb.RepoTask.load(task)
    clean=public['clean_rtl'];bug=(task/'public/repo/rtl/sequence.sv').read_text()
    assert loop.rb.execute(t,{'rtl/sequence.sv':clean}).tier=='visible_pass'
    assert loop.rb.execute(t,{'rtl/sequence.sv':bug}).tier=='visible_fail'
    ef=ex.read(c['evaluator_freeze']);root=Path(c['evaluator_root'])
    assert loop.measure._evaluate(t,{'rtl/sequence.sv':clean},ef,root/'evaluator')['result']=='pass'
    assert loop.measure._evaluate(t,{'rtl/sequence.sv':bug},ef,root/'evaluator')['result']=='fail'
    assert ex.read(root/'structure.json')['status']=='ok'


def test_async_reset_shortcut_fails_preservation():
    loop,m,public=core();task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    bad=public['clean_rtl'].replace('posedge clk_in or negedge rst','posedge clk_in')
    result=loop.rb.execute(task,{'rtl/sequence.sv':bad})
    assert result.evidence['suites']['W_bug']['result']=='visible_pass'
    assert result.evidence['suites']['W_preserve']['result']=='visible_fail'


def test_two_distinct_validation_questions_are_not_exam_and_have_no_historical_seed():
    loop,m,public=core();vf=ex.read(ex.VALIDATION_ROOT/'Prob017/validation.json')
    rows=[loop.mutant_identity(public,(Path(p)/'public/repo/rtl/sequence.sv').read_text()) for p in vf['tasks']]
    exam=loop.mutant_identity(public,(Path(m['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv').read_text())
    assert m['mechanism_focus'] is None
    assert len(set(rows+[exam]))==3
    from r3e.loop.token_count import TokenCounter
    for p in vf['tasks']:
        task=loop.rb.RepoTask.load(Path(p))
        assert loop.rb.setup(task,TokenCounter(),loop.CONFIG).baseline.tier=='visible_fail'


def test_divider_stage_and_inventory_protect_reset_parameters_and_clocking():
    loop,m,public=core();g=loop.targeted_prompts
    def p(a,b):return loop.red.materialize_batch(dict(candidates=[dict(edits=[dict(find=a,replace=b)],violated_requirement='offline public witness',spec_basis='public waveform contract')]),public)['candidates'][0]
    local=p('div_o-1','div_o+1')
    assert local['status']=='proposal' and g.curriculum_violation(public,local,1,[]) is None
    reset=p('clk_cnt <= 0;','clk_cnt <= 1;')
    assert g.curriculum_violation(public,reset,1,[])
    declaration=p("8'd87","8'd86")
    assert declaration['status']=='rejected' and declaration['reason']=='mutation_grammar_violation'
    inv=g.divider_inventory(public,[[dict(find='div_o-1',replace='div_o+1')]])
    assert inv['sites'] and all('<= 0' not in x['clean_rhs'] for x in inv['sites'])
    assert any(x['previous_candidate_count'] for x in inv['sites'])
    assert g.red_guidance(public['carrier_id'],5,[])['stage']=='single_local_fault'
    assert 'pre-edge' in g.blue_guidance('Prob017').lower()


def test_no_prepared_training_pool_is_loaded_or_written():
    loop,m,public=core();root=Path(m['carriers'][0]['package']).parent
    assert not (root/'practice_fixtures.json').exists()
    assert not (ex.VALIDATION_ROOT/'Prob017/training_fixtures.json').exists()
    proof=ex.read(root/'offline_qualification_summary.json')
    assert proof['qualification_only'] and not proof['training_uses_these_candidates']


def test_new_three_design_batch_promotes_experience_and_reuses_sealed_pretest(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch)
    result=ex.read(root/'promotion_results.json');assert set(result['designs'])==set(ex.DESIGNS)
    assert not (root/'Prob003').exists()
    assert result['comparison']['complete'] and result['comparison']['promotion_passed_completed_designs']==6
    assert result['designs']['Prob017']['retained_entries']==1
    assert result['designs']['Prob017']['certified_validation']['retained_passed']==4
    assert result['normal_max_requests']==243 and result['hard_max_requests']==486
    assert all(role=='pretest' for _,role in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    gate=ex.read(root/'initial_exam_gate.json')
    for design in ex.DESIGNS:
        path=root/design/'collection/initial_exam.json'
        assert ex.sha(path)==next(m['initial_exam_sha256'] for m in gate['members'] if m['design']==design)
    entry=ex.read(root/'Prob017/collection/rounds/5/commit.json')['blue']['entries'][0]
    assert entry['body']['content']['transfer_summary']['checks_on_transfer']==[]
    assert entry['body']['content']['transfer_summary']['changed_lines']


def test_full_static_pass_stops_before_training_with_new_design(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch,saturated=True)
    assert len(order)==6 and all(role=='pretest' for _,role in order)
    assert ex.read(root/'initial_exam_gate.json')['decision']=='stop_saturated'
    assert not (root/'training_barrier.json').exists()


def test_selected_exam_matches_the_improved_pilot_original_without_importing_experience():
    row=ex.verify_questions()[2]
    pilot=ex.ROOT/'failed-five-round-20261019/work/chipbench__arithmetic__Prob017_arbitrary_fractional_frequency_division'
    exam=Path(ex.material('Prob017')['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv'
    assert exam.read_bytes()==(pilot/'public/buggy.sv').read_bytes()
    plan=ex.read(ex.PLAN_ROOT/'Prob017/plan.json')
    assert plan['blue_config']['prob003_transition_training'] is False
    assert plan['initial_exam_policy']['expose_exam_outcomes_to_training'] is False
    assert ex.material('Prob017')['mechanism_focus'] is None
    assert len(plan['anchors'])==1 and plan['anchor_repeats']==2



def test_red_author_guidance_and_curriculum_are_unchanged():
    old=HERE/'source-promotion-prob017-arithmetic-v1'
    for name in ('r3e/loop/targeted_prompts.py','r3e/loop/red_continuous.py','r3e/loop/red_retry.py'):
        assert (old/name).read_bytes()==(ex.PROMOTION_SOURCE/name).read_bytes()
    loop,m,public=core()
    guidance=loop.targeted_prompts.red_guidance(public['carrier_id'],1,[])
    assert guidance['focus'] and guidance['stage']=='single_local_fault'


def test_all_blue_roles_exclude_authored_advice_and_only_deliver_actual_episodes(tmp_path,monkeypatch):
    loop,m,public=core()
    seen=[]
    original=loop.rb.RepoBlueRunner._call
    def checked(self,phase,system,user,seed,journal=None):
        if phase=='blue_inference':
            assert not ({'public_repair_guidance','public_group_worksheet','public_fault_focus','public_previous_patch_feedback'} & set(user))
            assert 'visible_test_sources' in user and 'current_failure_evidence' in user
            entries=user.get('repair_experience',{}).get('entries',[])
            for entry in entries:
                content=entry['content']
                assert content['transfer_summary']['checks_on_transfer']==[]
                assert content['applied_patch'] and set(content['public_rows'].values())=={'visible_pass'}
            seen.append(bool(entries))
        return original(self,phase,system,user,seed,journal)
    monkeypatch.setattr(loop.rb.RepoBlueRunner,'_call',checked)
    root,order=helpers.batch(tmp_path,monkeypatch)
    assert any(seen) and not all(seen)
    result=ex.read(root/'promotion_results.json')
    assert result['comparison']['complete']
    for design in ex.DESIGNS:
        c=root/design/'collection'
        for p in (c/'anchors').glob('b0*/delivery.json'):
            assert ex.read(p)['payload']['entries']==[]
