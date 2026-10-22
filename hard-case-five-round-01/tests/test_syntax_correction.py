import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('syntax_experiment',HERE/'experiment-syntax-v1.py')
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


FAILED=HERE/'real-all-20261017-082127/Prob001/collection/rounds/4/r4_s0'


def setup_core():
    base=ex.runner('Prob001');_,loop,*_=base.modules()
    carrier=ex.material('Prob001')['carriers'][0]
    public=loop.red907.public_material(Path(carrier['package']),ex.read(carrier['suite_freeze']))
    return base,loop,carrier,public


@pytest.mark.parametrize('attempt',[1,2])
def test_actual_syntax_failures_are_locally_corrected_and_compiled(tmp_path,attempt):
    _,loop,carrier,public=setup_core()
    raw=ex.read(FAILED/f'red_retry_{attempt}/response.json')['result']
    original=json.loads(json.dumps(raw))
    proposal=loop.red.materialize(raw,public)
    assert raw==original
    assert proposal['syntax_corrections']
    assert proposal['original_mutation_edits']==raw['edits']
    assert proposal['mutation_edits']!=raw['edits']
    record=loop.red907.check_proposal(Path(carrier['package']),ex.read(carrier['suite_freeze']),
                                     proposal,tmp_path/'replay',seen=set())
    assert set(record['suites'])=={'W_bug','W_preserve'}
    assert all(cell['tier'] in ('pass','fail') for cell in record['suites'].values())
    # Compiling is never mistaken for functional admission.
    if all(cell['tier']=='pass' for cell in record['suites'].values()):
        assert record['status']=='rejected'


@pytest.mark.parametrize('expression',[
    'if ((A) && (B))','if (A)','if (A) & (B) begin',
    'if (A) & (B // comment)','if (A) & (B))','if (A) + (B)',
    'if (A) & (`MACRO)','if (A) & ("text")'])
def test_normalizer_leaves_unsupported_or_valid_code_unchanged(expression):
    setup_core()
    from r3e.loop.red_syntax import normalize_condition_edits
    edits=[{'find':'original','replace':expression}]
    fixed,audit=normalize_condition_edits(edits)
    assert fixed==edits and audit==[]


def test_normalizer_keeps_operator_operand_order_and_multiline_source():
    setup_core()
    from r3e.loop.red_syntax import normalize_condition_edits
    edits=[{'find':'old','replace':'  else if (a[0]) && (b | c) ^ (d)\nnext_line\n'}]
    fixed,audit=normalize_condition_edits(edits)
    assert fixed[0]['replace']=='  else if ((a[0]) && (b | c) ^ (d))\nnext_line\n'
    assert audit[0]['replacement_line']==1


def test_compile_feedback_reaches_retry_and_valid_mutation_runs(tmp_path,monkeypatch):
    base,loop,_,public=setup_core()
    original=loop.red.propose
    injected=[]
    # Unsupported broken assignment deliberately needs model correction;
    # the conservative local parenthesis helper must not guess its meaning.
    bad=loop.red.materialize({'edits':[{'find':"a_tem <= {a_tem[6:0],a};",
        'replace':"a_tem <= {a_tem[6:0],a;"}],
        'violated_requirement':'history fault','spec_basis':'public shift register requirement'},public)
    assert not bad['syntax_corrections']
    def propose(public,observations,**kwargs):
        if kwargs['round_index']==2 and not injected:
            injected.append(1)
            return bad
        return original(public,observations,**kwargs)
    monkeypatch.setattr(loop.red,'propose',propose)
    out=tmp_path/'collection'
    assert base.smoke(out)['status']=='complete'
    request=ex.read(out/'rounds/2/r2_s0/red_retry_1/request.json')
    user=json.loads(request['messages'][-1]['content'])
    correction=user['compilation_correction']
    assert correction['failed_edits']==bad['mutation_edits']
    assert correction['candidate_source']==bad['buggy_rtl']
    assert correction['diagnostics']
    assert any('a_tem <=' in row['text'] for d in correction['diagnostics'] for row in d['source_context'])
    assert 'syntax error' in str(correction['compiler_logs'])
    assert 'PRIORITY' in correction['instruction'] and 'carrier.clean_rtl' in correction['instruction']
    assert 'rather than changing a constant' in correction['instruction']
    assert 'validation_scores' not in correction and 'reference_outcome' not in correction
    first=ex.read(out/'rounds/2/r2_s0/admission/admission.json')
    assert first['status']=='rejected'
    second=ex.read(out/'rounds/2/r2_s0/admission_retry_1/admission.json')
    assert second['status']=='admitted'
    assert ex.read(out/'audits/source_audit.json')
    assert ex.read(out/'audits/exposure_audit.json')


def test_new_manifest_and_unchanged_budget_materials_blue_guidance():
    setup_core()
    old=ex.read(HERE/'promotion_code_focused_v1.json')
    new=ex.read(HERE/'promotion_code_syntax_v1.json')
    assert set(new)-set(old)=={'r3e/loop/red_syntax.py'}
    assert {p for p in old if old[p]!=new[p]}=={
        'r3e/loop/red_continuous.py','experiments/loop_probes/continuous_loop.py'}
    for design in ex.DESIGNS:
        before=ex.read(HERE/'plan-v3-0324-focused-v1'/design/'plan.json')
        current=ex.read(ex.PLAN_ROOT/design/'plan.json')
        for key in ('client_config','blue_config','max_calls','rounds','slots_per_round',
                    'anchors','validation_tasks','carriers','promotion','learning','retrieval'):
            assert current[key]==before[key],key
        assert ex.sha(ex.PLAN_ROOT/design/'code_snapshot/r3e/loop/red_syntax.py')==new['r3e/loop/red_syntax.py']
