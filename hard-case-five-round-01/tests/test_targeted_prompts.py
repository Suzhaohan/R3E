import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('targeted_experiment',HERE/'experiment-focused-v1.py')
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


def test_red_schedule_diversity_and_real_failure_adaptation():
    ex.runner('Prob003').modules()
    from r3e.loop.targeted_prompts import red_guidance
    source=HERE/'real-all-20261017-073813/Prob003/collection/rounds/1/commit.json'
    failed=ex.read(source)['red']['observations'][::-1]
    assert failed[0]['label']=='public_functional_failure_single_sample_unconfirmed'
    adapted=red_guidance('chipbench_prob003_group_boundary_v1',2,failed)
    assert 'exactly one simpler' in adapted['adaptation']
    assert 'reduce complexity' in adapted['priority']
    assert 'idle;' not in json.dumps(adapted)  # No concrete exam patch is supplied.
    for family in ('Prob001','Prob003'):
        stages=[red_guidance('chipbench_'+family,round_index,[]) for round_index in range(1,6)]
        assert len({x['focus'] for x in stages})==5
        assert all('at most one pure comparison-constant substitution' in x['diversity'] for x in stages)
        assert all('underscores' in x['diversity'] for x in stages)
    assert red_guidance('chipbench_Prob023_gray_counter',1,[]) is None


@pytest.mark.parametrize('design',['Prob001','Prob003'])
def test_new_guidance_reaches_every_blue_role_and_each_red_round(tmp_path,design):
    ex.runner(design).modules()
    from r3e.loop.targeted_prompts import blue_guidance
    base=ex.runner(design);out=tmp_path/'collection'
    result=base.smoke(out)
    assert result['status']=='complete' and result['completed_probes']==12
    role_instructions={}
    for f in out.glob('**/blue/submissions/request_*.json'):
        request=ex.read(f)
        user=json.loads(request['messages'][-1]['content'])
        if user.get('task')!='repair':continue
        parts=f.relative_to(out).parts
        if parts[0]=='validation_baseline':role='baseline'
        elif parts[0]=='anchors':role='exam'
        elif parts[0]=='promotion':role='candidate'
        elif 'reference' in parts:role='reference'
        else:role='online'
        role_instructions.setdefault(role,set()).add(user['public_repair_guidance'])
    assert set(role_instructions)=={'baseline','online','reference','candidate','exam'}
    expected=blue_guidance('chipbench_'+design)
    assert all(texts=={expected} for texts in role_instructions.values())
    for f in out.glob('rounds/*/r*/red*/request.json'):
        request=ex.read(f);user=json.loads(request['messages'][-1]['content'])
        assert user['round_curriculum']['round']==request['round']
        assert user['round_curriculum']['design']==design.lower()
        assert 'validation_scores' not in user and 'reference_outcome' not in user
    assert ex.read(out/'audits/source_audit.json')
    assert ex.read(out/'audits/exposure_audit.json')


def test_guidance_is_task_specific_public_and_keeps_gray_prompt_unchanged():
    ex.runner('Prob001').modules()
    from r3e.loop.targeted_prompts import blue_guidance
    one=blue_guidance('chipbench_Prob001_fixed_hard_questions__exam_defect')
    three=blue_guidance('chipbench_prob003_group_boundary_v1__defect')
    assert 'Fixing an obvious comparison constant alone' in one
    assert 'each sampled bit must be consumed exactly once' in three
    assert 'extra idle clock' in three
    assert blue_guidance('chipbench_Prob023_gray_counter__exam_defect')==''
    assert blue_guidance('unrelated_public_design')==''
    for text in (one,three):
        assert "8'b01110001" not in text and 'nstate=' not in text
        assert 'Return only the required files/edit JSON' in text


def test_prompt_code_is_frozen_and_other_experiment_controls_preserved():
    old_manifest=ex.read(HERE/'promotion_code_v3_0324_v1.json')
    new_manifest=ex.read(HERE/'promotion_code_focused_v1.json')
    assert set(new_manifest)-set(old_manifest)=={'r3e/loop/targeted_prompts.py'}
    assert {p for p in old_manifest if old_manifest[p]!=new_manifest[p]}=={
        'r3e/loop/repo_blue.py','r3e/loop/red_continuous.py','experiments/loop_probes/continuous_loop.py'}
    for design in ex.DESIGNS:
        current=ex.read(ex.PLAN_ROOT/design/'plan.json')
        before=ex.read(HERE/'plan-v3-0324-listed-v2'/design/'plan.json')
        for key in ('client_config','blue_config','carriers','anchors','validation_tasks','mechanism_focus',
                    'promotion','learning','retrieval','max_calls','rounds','slots_per_round'):
            assert current[key]==before[key],key
        asset=ex.PLAN_ROOT/design/'code_snapshot/r3e/loop/targeted_prompts.py'
        assert ex.sha(asset)==new_manifest['r3e/loop/targeted_prompts.py']
