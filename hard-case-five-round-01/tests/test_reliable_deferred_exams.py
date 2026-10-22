import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reliable_experiment',HERE/'experiment-reliable-v1.py')
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


def run_cli(monkeypatch,tmp_path,design='all'):
    monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--design',design,'--run-dir',str(tmp_path/'batch')])
    ex.main()
    return tmp_path/'batch'


def test_all_red_proposals_ineffective_still_finish_three_five_rounds_then_exams(tmp_path,monkeypatch):
    _,loop,*_=ex.runner('Prob001').modules()
    original=loop.red.propose
    def ineffective(public,observations,**kwargs):
        original(public,observations,**kwargs)  # Real request/response ledger, scripted transport only.
        clean=public['clean_rtl']
        # A token-changing but equivalent expression reaches real compilation/public tests.
        return loop.red.materialize(dict(edits=[dict(find=clean,replace=clean.replace("1'b0","(1'b0 | 1'b0)",1))],
              violated_requirement='offline ineffective proposal',spec_basis='public spec'),public)
    monkeypatch.setattr(loop.red,'propose',ineffective)
    root=run_cli(monkeypatch,tmp_path)
    barrier=ex.read(root/'training_barrier.json')
    assert barrier['status']=='all_training_complete' and len(barrier['members'])==3
    assert barrier['experience_policy']=='independent_per_design'
    results=ex.read(root/'promotion_results.json')
    assert results['comparison']['complete'] and results['comparison']['scheduled_trials_per_group']==6
    assert results['prequalified_fallback_count']==15
    assert results['actual_requests']<=288
    for design in ex.DESIGNS:
        c=root/design/'collection';summary=ex.read(c/'collection.json');plan=ex.read(c/'plan.json')
        assert summary['status']=='complete' and summary['committed_rounds']==5
        assert summary['completed_probes']==4
        assert {p['snapshot'] for p in plan['anchor_probes']}=={0,5}
        assert len(ex.read(c/'report.json')['reserved_variants_by_snapshot'])==2
        slots=[json.loads(s) for s in (c/'slots.jsonl').read_text().splitlines()]
        assert len(slots)==5
        assert all(r['generation_source']=='prequalified_human_seeded_fallback' for r in slots)
        assert all(len(r['generation_attempts'])==4 for r in slots)
        assert slots[0]['generation_attempts'][0]['reason']=='outside_public_admission_matrix'
        rejected=ex.read(c/'rounds/1/r1_s0/admission/admission.json')
        assert {k:v['tier'] for k,v in rejected['suites'].items()}=={'W_bug':'pass','W_preserve':'pass'}
        assert all(r['trials'].keys()=={'online','reference'} for r in slots)
        fallbacks=[json.loads(s) for s in (c/'fallbacks.jsonl').read_text().splitlines()]
        assert len({r['identity'] for r in fallbacks})==5
        excluded={a['mutant_identity'] for a in plan['anchors']}
        public=loop.red907.public_material(Path(plan['carriers'][0]['package']),ex.read(plan['carriers'][0]['suite_freeze']))
        for t in plan['validation_tasks']:
            task=loop.rb.RepoTask.load(Path(t))
            excluded.add(loop.mutant_identity(public,(task.repo/public['editable_file']).read_text()))
        assert not excluded & {r['identity'] for r in fallbacks}
        assert ex.read(c/'audits/source_audit.json') and ex.read(c/'audits/exposure_audit.json')
        b5=ex.read(c/'rounds/5/commit.json')
        assert b5['blue']['state_hash']==next(x['final_state_hash'] for x in barrier['members'] if x['design']==design)
        for req in c.glob('anchors/**/blue/submissions/request_*.json'):
            # Every actual final exam request is after every design's B5 commit and the barrier.
            assert req.stat().st_mtime_ns>= (root/'training_barrier.json').stat().st_mtime_ns
            for other in ex.DESIGNS:
                assert req.stat().st_mtime_ns >= (root/other/'collection/rounds/5/commit.json').stat().st_mtime_ns
        for delivery in c.glob('anchors/*/delivery.json'):
            d=ex.read(delivery)
            if d['snapshot_id']=='B_0':assert not d['selected_entry_hashes']
        for entry in b5['blue']['entries']:
            assert design.lower() in entry['body']['source']['carrier_id'].lower()


@pytest.mark.parametrize('mode',['saturated','no_learnable_repairs'])
def test_saturation_or_no_experience_cannot_cancel_five_rounds_and_exam(tmp_path,monkeypatch,mode):
    _,loop,*_=ex.runner('Prob001').modules()
    if mode=='saturated':
        monkeypatch.setattr(loop,'promotion_pass',lambda *a,**kw:True)
    else:
        monkeypatch.setattr(loop,'online_evidence',lambda *a,**kw:(None,None,{'reason':'offline no learnable repair fixture'}))
    root=run_cli(monkeypatch,tmp_path,'Prob001');c=root/'collection'
    summary=ex.read(c/'collection.json')
    assert summary['status']=='complete' and summary['committed_rounds']==5
    assert summary['completed_probes']==4
    assert not (c/'stop_reason.json').exists()
    if mode=='saturated':assert all(ex.read(c/'validation_baseline.json')['scores'].values())
    else:assert summary['retained_experience_entries']==0


def test_frozen_pool_budget_and_original_exam_selection_preserved():
    ex.verify_questions()
    for design in ex.DESIGNS:
        plan=ex.read(ex.PLAN_ROOT/design/'plan.json')
        assert plan['max_calls']==96 and len(plan['fallback_pools'][0])==5
        assert len(plan['anchors'])==1 and len(plan['slots'])==5
        assert plan['validation_tasks']==ex.read(ex.VALIDATION_ROOT/design/'validation.json')['tasks']
        assert plan['anchors'][0]['task_dir']==ex.material(design)['anchors'][0]['task_dir']
        assert {p['snapshot'] for p in plan['anchor_probes']}=={0,5}
        assert plan['client_config']['model_id']=='deepseek/deepseek-chat-v3-0324'
