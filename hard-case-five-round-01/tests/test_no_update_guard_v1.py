"""No score selection, explicit cached accounting, and tamper-resistant provenance."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('no_update_guard_experiment',HERE/'experiment-no-update-guard-v1.py')
helpers=module('no_update_guard_helpers',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def test_exact_policy_reuse_preserves_failure_and_real_execution_identity():
    loop,_,_=helpers.core();b0=loop.state.snapshot(0,{'solver':'fixed'});b5=b0
    for n in range(1,6):b5=loop.state.snapshot(n,{'solver':'fixed'},[],b5)
    initial={'frozen_b0_snapshot_hash':loop.hash_payload(b0),'probe_rows':[
        {'snapshot':0,'anchor_index':0,'repeat':0,'seed':100,'online_seed':1000,'status':'not_fixed',
         'task_hash':'task','snapshot_hash':loop.hash_payload(b0),'directory':'real-b0','delivery_hash':'actual-delivery'}]}
    probe={'snapshot':5,'anchor_index':0,'repeat':0,'seed':100}
    result=loop.reuse_unchanged_exam(b0,b5,initial,probe,'task')
    assert result['status']=='not_fixed'  # failing baseline is reused too; never choose a good score
    assert result['directory']=='real-b0' and result['delivery_hash']=='actual-delivery'
    assert result['snapshot_hash']==loop.hash_payload(b0)
    assert result['reuse_evidence']['source_execution_seed']==100
    assert result['online_seed']==1000 and result['new_model_calls']==0
    assert result['reuse_evidence']['not_an_independent_measurement']
    changed={**b5,'state_hash':'changed'}
    assert loop.reuse_unchanged_exam(b0,changed,initial,probe,'task') is None
    assert loop.reuse_unchanged_exam(b0,b5,initial,{**probe,'seed':999},'task') is None
    with pytest.raises(ValueError,match='task, snapshot or measurement'):
        loop.reuse_unchanged_exam(b0,b5,initial,probe,'other-task')
    with pytest.raises(ValueError,match='exactly one'):
        loop.reuse_unchanged_exam(b0,b5,initial,{**probe,'repeat':1},'task')


def scripted_patch(text,request=None):
    current=request['files']['rtl/sequence.sv']['content']
    if text==current:text+='\nINVALID_PUBLIC_FIXTURE_TOKEN\n'
    return {'edits':[{'file':'rtl/sequence.sv','find':current,'replace':text}],
            'edit':'Offline fixture with an actual patch and actual public feedback.'}

@pytest.mark.parametrize('promote',[False,True])
def test_full_pipeline_reuses_only_unchanged_and_audits_provenance(tmp_path,monkeypatch,promote):
    monkeypatch.setattr(helpers,'source',scripted_patch)
    root,_=helpers.batch(tmp_path,monkeypatch,all_structured_rounds=True,
        force_all_validation_fail=not promote,neutral_validation=promote)
    report=ex.read(root/'promotion_results.json')
    assert report['comparison']['complete']
    for design in ex.DESIGNS:
        c=root/design/'collection';measurement=ex.read(c/'final_exam_measurement.json')
        b0=ex.read(c/'rounds/0/commit.json')['blue'];b5=ex.read(c/'rounds/5/commit.json')['blue']
        probes=[json.loads(l) for l in (c/'probes.jsonl').read_text().splitlines()]
        final=[r for r in probes if r['snapshot']==5]
        if b0['state_hash']==b5['state_hash']:
            assert measurement['reused_samples']==2 and measurement['new_samples']==0
            assert all(r['new_model_calls']==0 for r in final)
            assert not list((c/'anchors').glob('b5*'))
            assert report['designs'][design]['final_exam']['B_0']==report['designs'][design]['final_exam']['B_5']
        else:
            assert measurement['new_samples']==2 and measurement['reused_samples']==0
            assert all(r['measurement_origin']=='new_adaptive_exam' for r in final)
            assert len(list((c/'anchors').glob('b5*')))==2
        assert (c/'audits/source_audit.json').exists() and (c/'audits/exposure_audit.json').exists()
    if promote:
        assert any(report['designs'][d]['exam_measurement']['policy_changed'] for d in ex.DESIGNS)
    else:
        assert report['comparison']['reused_unchanged_policy_samples']==6
        assert report['comparison']['new_adaptive_measurements']==0
        # Tampering a sealed B0 request must invalidate cached reporting.
        from experiments.loop_probes.continuous_audit import verify_exam_reuse
        c=root/'Prob003/collection';p=next((c/'anchors').glob('b0*/blue/submissions/request_*.json'))
        p.write_text(p.read_text()+' ')
        with pytest.raises(Exception,match='sealed initial exam evidence changed'):
            verify_exam_reuse(c,ex.read(c/'plan.json'))


def test_latest_historical_results_are_only_an_offline_counterfactual():
    loop,_,_=helpers.core();run=HERE/'real-all-20261020-222636'
    original=ex.sha(run/'promotion_results.json')
    for design in ex.DESIGNS:
        c=run/design/'collection';initial=ex.read(c/'initial_exam.json');plan=ex.read(c/'plan.json')
        b0=ex.read(c/'rounds/0/commit.json')['blue'];b5=ex.read(c/'rounds/5/commit.json')['blue']
        assert b0['state_hash']==b5['state_hash']
        for probe in plan['anchor_probes']:
            if probe['snapshot']!=5:continue
            task=loop.rb.RepoTask.load(Path(plan['anchors'][probe['anchor_index']]['task_dir']))
            paired={**probe,'seed':next(r['seed'] for r in initial['probe_rows'] if r['anchor_index']==probe['anchor_index'] and r['repeat']==probe['repeat'])}
            row=loop.reuse_unchanged_exam(b0,b5,initial,paired,loop.rb.public_task_hash(task))
            assert row['reuse_evidence']['not_an_independent_measurement']
    assert ex.sha(run/'promotion_results.json')==original
    raw=ex.read(run/'promotion_results.json')['comparison']
    assert raw['static_passed_completed_designs']==3 and raw['promotion_passed_completed_designs']==2


def test_exam_seeds_are_paired_without_merging_repeat_samples():
    loop,_,_=helpers.core()
    _,probes=loop.schedule(5,1,1,1,700,anchor_repeats=2)
    first={p['repeat']:p['seed'] for p in probes if p['snapshot']==0}
    final={p['repeat']:p['seed'] for p in probes if p['snapshot']==5}
    assert first==final and len(set(first.values()))==2
