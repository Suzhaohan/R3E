"""Regression: one saturated design cannot prevent the remaining designs running."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('listed_experiment', HERE/'experiment-listed-v1.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


@pytest.fixture(scope='module',autouse=True)
def isolate_core():
    def owned(name):
        return name in ('r3e','experiments') or name.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)}
    paths=list(sys.path)
    for key in list(saved):sys.modules.pop(key)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for key in list(sys.modules):
        if owned(key):sys.modules.pop(key)
    sys.modules.update(saved)
    sys.path[:]=paths


def test_three_exact_questions_bound_to_requested_list():
    rows=ex.verify_questions()
    assert len(rows)==3 and tuple(r['family'] for r in rows)==ex.DESIGNS
    selection=ex.read(ex.SELECTION)
    document='09_Low_Pass_Rate_RTL_Cases.md'
    assert selection['selection_document']==document
    assert selection['evidence'][document]==ex.sha(ex.ROOT/document)
    assert selection['document_sections']=={'Prob001':2,'Prob002':2,'Prob003':1}
    third=rows[2]
    assert third['case_id']=='historical:RC_406d811b4d61a2'
    clean=(ex.ROOT/third['golden_rtl']).read_text()
    defect=(ex.ROOT/third['buggy_rtl']).read_text()
    assert clean.count('nstate=data?sf1:s1;')==2
    assert defect==clean.replace('nstate=data?sf1:s1;','nstate=idle;')


def test_prob002_validation_shift_is_a_real_observable_defect(tmp_path):
    base=ex.runner('Prob002')
    _,loop,*_=base.modules()
    carrier=ex.material('Prob002')['carriers'][0]
    package=Path(carrier['package'])
    public=loop.red907.public_material(package,ex.read(carrier['suite_freeze']))
    proposal=loop.red.materialize(dict(edits=[dict(find='{a_tem[7:0],a}',replace='{a,a_tem[7:0]}')],
                                    violated_requirement='history ordering',spec_basis='shift input into LSB'),public)
    result=loop.red907.check_proposal(package,ex.read(carrier['suite_freeze']),proposal,tmp_path/'shift',seen=set())
    assert result['status']=='admitted'
    assert result['suites']['W_bug']['tier']=='fail'
    assert result['suites']['W_preserve']['tier']=='pass'


def test_saturated_middle_design_skips_and_third_finishes(tmp_path,monkeypatch):
    _,loop,*_=ex.runner('Prob001').modules()
    original=loop.promotion_pass
    def score(trial,task_dir,carrier):
        # Synthetic baseline scores exercise batch control, not model performance.
        if 'Prob002' in Path(task_dir).parts and 'validation_baseline' in Path(trial['directory']).parts:
            return True
        return original(trial,task_dir,carrier)
    monkeypatch.setattr(loop,'promotion_pass',score)
    root=tmp_path/'batch'
    monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--run-dir',str(root)])
    ex.main()
    first=ex.read(root/'Prob001/collection/collection.json')
    second=ex.read(root/'Prob002/collection/collection.json')
    third=ex.read(root/'Prob003/collection/collection.json')
    assert first['status']=='complete' and third['status']=='complete'
    assert third['committed_rounds']==5 and third['completed_probes']==12
    assert second['status']=='skipped' and second['skip_reason']=='validation_baseline_saturated'
    assert second['calls']==4 and second['completed_slots']==second['completed_probes']==0
    assert not (root/'Prob002/launch_stop.json').exists()
    ex.write_results(root)
    report=ex.read(root/'promotion_results.json')
    assert report['comparison']['all_designs_finished']
    assert report['comparison']['skipped_designs']==['Prob002']
    assert report['comparison']['completed_designs']==2
    assert not report['comparison']['complete']  # Missing exams are not counted as success.
    assert report['designs']['Prob002']['certified_validation']['retained_passed']==4
    assert report['designs']['Prob002']['final_exam'] is None
    dashboard_spec=importlib.util.spec_from_file_location('listed_dashboard',HERE/'dashboard.py')
    dashboard=importlib.util.module_from_spec(dashboard_spec);dashboard_spec.loader.exec_module(dashboard)
    state=dashboard.snapshot(root/'Prob002')
    assert state['status']=='skipped' and '继续下一题' in state['phase']


def test_other_errors_are_not_silently_swallowed(tmp_path,monkeypatch):
    invoked=[]
    def runner(design):
        def main():
            invoked.append(design)
            if design=='Prob002':raise RuntimeError('provider unavailable')
            folder=tmp_path/'batch'/design/'collection'
            ex.save(folder/'collection.json',dict(status='complete'))
        return SimpleNamespace(main=main)
    monkeypatch.setattr(ex,'runner',runner)
    monkeypatch.setattr(sys,'argv',['experiment.py','collect','--run-dir',str(tmp_path/'batch'),'--env-file','unused-test-env'])
    with pytest.raises(RuntimeError,match='provider unavailable'):
        ex.main()
    assert invoked==['Prob001','Prob002']
