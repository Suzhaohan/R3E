import importlib.util
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gray_replacement_experiment',HERE/'experiment-v3-0324-listed-v2.py')
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


def test_second_question_is_exact_listed_gray_defect_and_three_questions_remain():
    selected=ex.verify_questions()
    assert tuple(r['family'] for r in selected)==('Prob001','Prob023','Prob003')
    row=selected[1]
    assert row['case_id']=='chipbench:arithmetic:Prob023_gray_code_counter'
    original=ex.ROOT/'datasets/low_pass_rate_rtl_cases/chipbench/arithmetic/Prob023_gray_code_counter'
    assert (ex.ROOT/row['buggy_rtl']).read_bytes()==(original/'buggy.sv').read_bytes()
    assert ex.read(ex.SELECTION)['document_sections']=={'Prob001':2,'Prob023':2,'Prob003':1}
    assert ex.read(ex.PLAN_ROOT/'suite.json')['final_questions']==3


def test_other_two_questions_prompts_and_validation_are_preserved():
    for design in ('Prob001','Prob003'):
        before=HERE/'materials-listed-v1'/design
        after=ex.MATERIAL_ROOT/design
        for name in ('package/src/rtl/sequence.sv','reserved/exam_defect/public/repo/rtl/sequence.sv','package/spec.md'):
            assert (before/name).read_bytes()==(after/name).read_bytes()
        assert ex.read(before/'materials.json')['mechanism_focus']==ex.read(after/'materials.json')['mechanism_focus']
        for i in range(2):
            name=f'task_{i}/public/repo/rtl/sequence.sv'
            assert (HERE/'validation-listed-v1'/design/name).read_bytes()==(ex.VALIDATION_ROOT/design/name).read_bytes()
        old=ex.read(HERE/'plan-v3-0324-listed-v1'/design/'plan.json')
        new=ex.read(ex.PLAN_ROOT/design/'plan.json')
        for key in ('client_config','blue_config','code','promotion','learning','retrieval','max_calls'):
            assert new[key]==old[key]


def test_gray_reference_exam_and_five_distinct_practice_mutants_are_qualified():
    root=ex.MATERIAL_ROOT/'Prob023'
    assert ex.read(root/'qualification.json')['qualified']
    evaluator=ex.read(root/'evaluator_qualification.json')
    assert evaluator['reference']['result']=='pass' and evaluator['defect']['result']=='fail'
    assert ex.read(ex.VALIDATION_ROOT/'Prob023/qualification.json')['qualified']
    for i in range(5):
        q=ex.read(root/'practice_checks'/str(i)/'admission.json')
        assert q['status']=='admitted'
        assert q['suites']['W_bug']['tier']=='fail' and q['suites']['W_preserve']['tier']=='pass'


def test_gray_complete_offline_flow_and_source_audits(tmp_path):
    base=ex.runner('Prob023')
    out=tmp_path/'collection'
    result=base.smoke(out)
    assert result['status']=='complete' and result['committed_rounds']==5
    assert result['completed_slots']==5 and result['completed_probes']==12
    assert result['model_calls']==0 and result['stand_in_only']
    assert ex.read(out/'audits/source_audit.json')
    assert ex.read(out/'audits/exposure_audit.json')
