import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ex=module('handoff_first_experiment',HERE/'experiment-handoff-prob003-red-only-v1.py')
helpers=module('handoff_feedback_fixtures',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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

def test_first_question_is_exact_primary_archive_defect_and_others_are_unchanged():
    rows=ex.verify_questions();assert ex.DESIGNS==('Prob003','Prob023','Prob017')
    previous=[json.loads(x) for x in (HERE/'cases-prob017-arithmetic-v1.jsonl').read_text().splitlines()]
    assert rows[1:]==previous[1:]
    assert len(rows)==3
    row=rows[0];assert row['artifact']=='exact_original_handoff_archive'
    with tarfile.open(ex.ROOT/row['source_archive']) as tar:
        defect=tar.extractfile(row['archive_member']).read()
        package=Path(ex.material('Prob003')['carriers'][0]['package'])
        for rel in ('src/rtl/sequence.sv','spec.md','suites/W_bug/tb.sv','suites/W_preserve/tb.sv'):
            assert (package/rel).read_bytes()==tar.extractfile('prob003_handoff_20261013/materials/package/'+rel).read()
    assert defect==(ex.ROOT/row['buggy_rtl']).read_bytes()
    task=Path(ex.material('Prob003')['anchors'][0]['task_dir'])
    assert (task/'public/repo/rtl/sequence.sv').read_bytes()==defect
    for d in ('Prob023','Prob017'):
        assert (ex.MATERIAL_ROOT/d/'materials.json').read_bytes()==(HERE/'materials-prob017-arithmetic-v1'/d/'materials.json').read_bytes()
        assert (ex.VALIDATION_ROOT/d/'validation.json').read_bytes()==(HERE/'validation-prob017-arithmetic-v1'/d/'validation.json').read_bytes()

def test_handoff_clean_passes_both_checks_and_defect_fails_functionally():
    loop,m,p=helpers.core('Prob003');c=m['carriers'][0];task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    bug=(task.repo/'rtl/sequence.sv').read_text()
    for rtl,expected in ((p['clean_rtl'],'visible_pass'),(bug,'visible_fail')):
        actual=loop.rb.execute(task,{'rtl/sequence.sv':rtl})
        assert actual.tier==expected
        hidden=loop.measure._evaluate(task,{'rtl/sequence.sv':rtl},ex.read(c['evaluator_freeze']),Path(c['evaluator_root'])/'evaluator')
        assert hidden['result']==('pass' if expected=='visible_pass' else 'fail')

def test_no_human_advice_or_transition_scaffold_in_any_blue_role(tmp_path,monkeypatch):
    loop,m,p=helpers.core('Prob003');seen=[];original=loop.rb.RepoBlueRunner._call
    def checked(self,phase,system,user,seed,journal=None):
        if phase=='blue_inference':
            assert system==loop.rb.SYSTEM_REPAIR
            assert not self.cfg.prob003_transition_training
            assert not ({'public_repair_guidance','public_group_worksheet','public_fault_focus','public_previous_patch_feedback'} & set(user))
            assert set(user['required_output_schema'])=={'files','edit'}
            for entry in user.get('repair_experience',{}).get('entries',[]):
                assert entry['content']['transfer_summary']['checks_on_transfer']==[]
            seen.append(True)
        return original(self,phase,system,user,seed,journal)
    monkeypatch.setattr(loop.rb.RepoBlueRunner,'_call',checked)
    root,order=helpers.batch(tmp_path,monkeypatch)
    result=ex.read(root/'promotion_results.json')
    assert seen and result['comparison']['complete']
    assert set(result['designs'])=={'Prob003','Prob023','Prob017'} and not (root/'Prob001').exists()
    assert result['normal_max_requests']==243 and result['hard_max_requests']==486
    assert result['comparison']['promotion_passed_completed_designs']==6
    assert all(phase=='pretest' for _,phase in order[:12])
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>max(i for i,(_,p) in enumerate(order) if p=='red')
    for d in ex.DESIGNS:
        for p in (root/d/'collection/anchors').glob('b0*/delivery.json'):
            assert ex.read(p)['payload']['entries']==[]

def test_saturated_three_question_pretest_stops_before_training(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch,saturated=True)
    assert len(order)==6 and all(role=='pretest' for _,role in order)
    assert ex.read(root/'initial_exam_gate.json')['decision']=='stop_saturated'
    assert not (root/'training_barrier.json').exists()

def test_only_generic_blue_system_is_registered_for_new_first_question():
    base=ex.runner('Prob003');modules=base.modules();_,loop,*_=modules
    systems={loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000}
    assert ex.registered_systems('Prob003',loop,systems)==systems
    assert ex.verify_launch_guard('Prob003',modules)==dict(status='PASS',registered_systems=2,model_calls=0)
