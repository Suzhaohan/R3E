import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('moderate_experiment', HERE/'experiment-moderate-v1.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


def test_medium_selection_has_mixed_history_and_preserves_original_exam_bytes():
    rows = ex.verify_questions()
    assert [r['family'] for r in rows] == ['Prob001','Prob002','Prob003']
    evidence = ex.read(ex.SELECTION)
    for record in evidence['rows']:
        assert record['current_v3_pass_rate'] is None
        assert all(0 < s['passed'] < s['observations'] for s in record['historical_successes'])
        assert record['practice_admitted']==5
        evaluator = ex.read(ex.MATERIAL_ROOT/record['family']/'evaluator_qualification.json')
        assert evaluator['reference']['result']=='pass'
        assert evaluator['defect']['result']=='fail'


def test_validation_is_composite_and_all_materials_are_disjoint():
    # Load the guarded source in a subprocess to avoid historical version imports.
    import subprocess
    import sys
    script = '''
import sys,json
from pathlib import Path
h=Path(sys.argv[1]);sys.path.insert(0,str(h/'source-promotion-simple-v1'))
from r3e.loop.blue_provider import apply_text_edits
from experiments.loop_probes.continuous_loop import mutant_identity
from experiments.loop_probes.red907 import public_material
for design in ('Prob001','Prob002','Prob003'):
 root=h/'materials-moderate-v1'/design; vp=h/'validation-moderate-v1'/design
 read=lambda p:json.loads(p.read_text())
 m=read(root/'materials.json');pkg=root/'package';public=public_material(pkg,read(root/'suite_freeze.json'))
 clean=(pkg/'src/rtl/sequence.sv').read_text()
 values=[apply_text_edits(clean,m['mechanism_focus']['seed_edits']),
         (Path(m['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv').read_text()]
 for i in range(2):
  variant=(vp/'package/variants'/f'validation_{i}'/'rtl/sequence.sv').read_text()
  assert variant!=clean
  values.append(variant)
 for i,group in enumerate(read(vp/'training_fixtures.json')):
  values.append(apply_text_edits(clean,group))
  assert read(root/'practice_checks'/str(i)/'admission.json')['status']=='admitted'
 ids=[mutant_identity(public,v) for v in values]
 assert len(ids)==len(set(ids))==9
 assert read(root/'qualification.json')['qualified']
 assert read(vp/'qualification.json')['qualified']
'''
    subprocess.run([sys.executable,'-c',script,str(HERE)],check=True,capture_output=True,text=True)


def test_medium_preserves_guarded_code_model_and_request_caps():
    for design in ex.DESIGNS:
        plan = ex.read(ex.PLAN_ROOT/design/'plan.json')
        old = ex.read(HERE/'plan-v3-simple-v1/Prob001/plan.json')
        for key in ('code','blue_config','client_config','promotion','learning','retrieval',
                    'rounds','slots_per_round','anchor_repeats','reserved_collision_retries','max_calls'):
            assert plan[key]==old[key],key
    suite=ex.read(ex.PLAN_ROOT/'suite.json')
    assert suite['final_questions']==3
    assert suite['normal_max_calls']==153 and suite['hard_max_calls']==336
