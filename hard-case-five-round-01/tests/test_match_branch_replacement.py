import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('match_branch_experiment',HERE/'experiment-match-branch-v1.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

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


def test_exact_archive_match_variant_and_other_questions_unchanged():
    rows=ex.verify_questions()
    prior=[json.loads(l) for l in (HERE/'cases-handoff-prob003-red-only-v1.jsonl').read_text().splitlines()]
    assert ex.DESIGNS==('Prob003','Prob023','Prob017') and len(rows)==3
    assert rows[1:]==prior[1:]
    row=rows[0];assert row['case_id']=='handoff:Prob003:eval_match_branch'
    with tarfile.open(ex.ROOT/row['source_archive']) as archive:
        original=archive.extractfile(row['archive_member']).read()
        assert original==(ex.ROOT/row['buggy_rtl']).read_bytes()
        package=Path(ex.material('Prob003')['carriers'][0]['package'])
        for rel in ['src/rtl/sequence.sv','spec.md','suites/W_bug/tb.sv','suites/W_preserve/tb.sv']:
            assert (package/rel).read_bytes()==archive.extractfile('prob003_handoff_20261013/materials/package/'+rel).read()
    task=Path(ex.material('Prob003')['anchors'][0]['task_dir'])
    assert (task/'public/repo/rtl/sequence.sv').read_bytes()==original
    assert ex.read(task/'public/task.json')['task_id'].endswith('__eval_match_branch')
    assert ex.read(ex.SELECTION)['rows'][0]['historical_successes']==[]
    for d in ['Prob023','Prob017']:
        assert ex.material(d)==ex.read(HERE/'materials-handoff-prob003-red-only-v1'/d/'materials.json')
    assert ex.VALIDATION_ROOT==HERE/'validation-handoff-prob003-red-only-v1'


def test_new_exam_is_functional_failure_and_original_clean_passes():
    _,loop,*_=ex.runner('Prob003').modules()
    material=ex.material('Prob003');c=material['carriers'][0]
    task=loop.rb.RepoTask.load(Path(material['anchors'][0]['task_dir']))
    bug=(task.repo/'rtl/sequence.sv').read_text()
    clean=(Path(c['package'])/'src/rtl/sequence.sv').read_text()
    assert bug==clean.replace('        s6:\n            nstate=data?sf1:s1;', '        s6:\n            nstate=data?s1:sf1;')
    for rtl,public_expected,independent_expected in [(clean,'visible_pass','pass'),(bug,'visible_fail','fail')]:
        result=loop.rb.execute(task,{'rtl/sequence.sv':rtl})
        assert result.tier==public_expected
        assert result.evidence['suites']['W_preserve']['result']=='visible_pass'
        evaluator=loop.measure._evaluate(task,{'rtl/sequence.sv':rtl},ex.read(c['evaluator_freeze']),Path(c['evaluator_root'])/'evaluator')
        assert evaluator['result']==independent_expected


def test_exam_is_distinct_from_validation_and_seed_and_frozen_exclusion_tracks_it():
    _,loop,*_=ex.runner('Prob003').modules()
    material=ex.material('Prob003');c=material['carriers'][0]
    public=loop.red907.public_material(Path(c['package']),ex.read(c['suite_freeze']))
    task=loop.rb.RepoTask.load(Path(material['anchors'][0]['task_dir']))
    exam=(task.repo/'rtl/sequence.sv').read_text()
    identity=loop.mutant_identity(public,exam)
    for path in ex.read(ex.VALIDATION_ROOT/'Prob003/validation.json')['tasks']:
        validation=loop.rb.RepoTask.load(Path(path))
        assert identity!=loop.mutant_identity(public,(validation.repo/'rtl/sequence.sv').read_text())
    from r3e.loop.blue_provider import apply_text_edits
    assert identity!=loop.mutant_identity(public,apply_text_edits(public['clean_rtl'],material['mechanism_focus']['seed_edits']))
    plan=ex.read(ex.PLAN_ROOT/'Prob003/plan.json')
    assert plan['anchors'][0]['mutant_identity']==identity
    assert plan['training_repair_policy']['online_attempts']==4
    assert plan['blue_config']['budget_k']==2 and plan['max_calls']==202
