"""Run separately from historical tests, which import a different frozen source tree."""
import importlib.util
import json
import sys
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('simple_experiment', HERE/'experiment-simple-v1.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


@pytest.fixture(scope='module', autouse=True)
def isolate_versioned_core():
    # Historical regression tests load their own frozen r3e/experiments packages.
    def owned(name):
        return name in ('r3e','experiments') or name.startswith(('r3e.','experiments.'))
    saved = {k:v for k,v in sys.modules.items() if owned(k)}
    old_path = list(sys.path)
    for k in list(saved):
        sys.modules.pop(k)
    sys.path.insert(0, str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):
            sys.modules.pop(k)
    sys.modules.update(saved)
    sys.path[:] = old_path


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def test_selected_originals_qualified_and_practice_excluded_from_validation():
    assert {r['family'] for r in ex.verify_questions()} == {'Mux','Counter','Prob001'}
    for design in ex.DESIGNS:
        base = ex.runner(design)
        _, loop, *_ = base.modules()
        m = ex.material(design)
        public = loop.red907.public_material(Path(m['carriers'][0]['package']), ex.read(m['carriers'][0]['suite_freeze']))
        forbidden = {loop.mutant_identity(public, (Path(a['task_dir'])/'public/repo/rtl/sequence.sv').read_text()) for a in m['anchors']}
        for task in loop.PROMOTION_VALIDATION:
            forbidden.add(loop.mutant_identity(public, (Path(task)/'public/repo/rtl/sequence.sv').read_text()))
        forbidden.add(loop.mutant_identity(public, loop.red.materialize(dict(edits=m['mechanism_focus']['seed_edits'],
            violated_requirement='seed', spec_basis='spec'), public)['buggy_rtl']))
        for i, group in enumerate(ex.read(ex.VALIDATION_ROOT/design/'training_fixtures.json')):
            proposal = loop.red.materialize(dict(edits=group, violated_requirement='practice', spec_basis='spec'), public)
            assert loop.mutant_identity(public, proposal['buggy_rtl']) not in forbidden
            assert ex.read(ex.MATERIAL_ROOT/design/'practice_checks'/str(i)/'admission.json')['status'] == 'admitted'


def test_invalid_patch_then_retry_and_duplicate_then_retry_are_auditable(tmp_path, monkeypatch):
    base = ex.runner('Mux')
    _, loop, *_ = base.modules()
    original = loop.red.propose
    previous = []
    injected = set()
    def propose(public, observations, **kw):
        r = kw['round_index']
        if r == 1 and 'invalid' not in injected:
            injected.add('invalid')
            # Same failure mode as the stopped Arbiter: the token is non-unique.
            result = loop.red.materialize(dict(edits=[dict(find='out <=', replace='out =')],
                violated_requirement='bad locator',spec_basis='spec'),public)
            assert result['status'] == 'rejected' and 'found 4 times' in result['reason']
            return result
        if r == 2 and 'duplicate' not in injected:
            injected.add('duplicate')
            return previous[0]
        if r == 1:
            assert any('found 4 times' in x['reason'] for x in kw['generation_feedback'])
        if r == 2:
            assert any(x['reason']=='duplicate_within_arm' for x in kw['generation_feedback'])
            assert kw['rejected_edits']
        result = original(public, observations, **kw)
        if r == 1 and result.get('status') == 'proposal':
            previous[:] = [result]
        return result
    monkeypatch.setattr(loop.red,'propose',propose)
    result = base.smoke(tmp_path/'collection')
    assert result['status'] == 'complete'
    slots = rows(tmp_path/'collection/slots.jsonl')
    assert all(s['admission']=='admitted' for s in slots)
    assert len(slots[0]['generation_attempts']) == 3  # invalid, reserved exam, valid
    assert len(slots[1]['generation_attempts']) == 2
    assert ex.read(tmp_path/'collection/audits/source_audit.json')
    assert ex.read(tmp_path/'collection/audits/exposure_audit.json')


def test_repeated_invalid_generation_stops_before_exams(tmp_path, monkeypatch):
    base = ex.runner('Mux')
    _,loop,*_ = base.modules()
    monkeypatch.setattr(loop.red,'propose', lambda *a,**kw: dict(status='rejected',reason='ambiguous find'))
    with pytest.raises(loop.measure.MeasurementRefused, match='generation_attempts_exhausted'):
        base.smoke(tmp_path/'collection')
    summary = ex.read(tmp_path/'collection/collection.json')
    assert summary['status']=='aborted' and summary['completed_probes']==0
    assert summary['committed_rounds']==0
    assert len(rows(tmp_path/'collection/generation_attempts.jsonl'))==4
    assert ex.read(tmp_path/'collection/stop_reason.json')['last_reason']=='ambiguous find'


def test_full_baseline_stops_after_baseline_before_training(tmp_path, monkeypatch):
    base = ex.runner('Mux')
    _,loop,*_ = base.modules()
    monkeypatch.setattr(loop,'promotion_pass',lambda *a: True)
    monkeypatch.setattr(loop.red,'propose',lambda *a,**kw: pytest.fail('must not generate'))
    with pytest.raises(loop.measure.MeasurementRefused,match='validation_baseline_saturated'):
        base.smoke(tmp_path/'collection')
    assert ex.read(tmp_path/'collection/collection.json')['calls']==4
    assert not rows(tmp_path/'collection/probes.jsonl')


def test_no_effective_practice_stops_after_two_rounds(tmp_path, monkeypatch):
    base = ex.runner('Mux')
    _,loop,*_ = base.modules()
    original = loop.online_evidence
    def evidence(*a,**kw):
        obs,entry,decision = original(*a,**kw)
        return obs,None,dict(reason='test functional failure yields no entry')
    monkeypatch.setattr(loop,'online_evidence',evidence)
    with pytest.raises(loop.measure.MeasurementRefused,match='no_effective_practice_two_rounds'):
        base.smoke(tmp_path/'collection')
    assert len(rows(tmp_path/'collection/slots.jsonl'))==2
    assert not rows(tmp_path/'collection/probes.jsonl')
