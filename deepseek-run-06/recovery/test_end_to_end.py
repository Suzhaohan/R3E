"""Exercise both complete arms with a scripted model and real local EDA.

This is an offline plumbing test, not model performance evidence. Both arms
complete the original five-round workflow, final evaluation and resume.
"""
from types import SimpleNamespace
import pytest
from test_m3_arena import ROOT, client
from competition.arena.evidence import read, freeze, signed
from competition.arena.baseline import build_baseline
from competition.arena.cli import _identity


def test_original_five_round_workflow_with_run_scoped_memory(tmp_path,monkeypatch):
    from competition.arena import cli
    from competition.scripts import run_arena_live
    from competition.services import arena_freeze_service as freezing
    from competition.services import arena_comparison_service as comparison
    from competition.services.arena_evaluation_service import ArenaEvaluationService
    from r3e.protocol.hashing import atomic_write_json,hash_payload
    raw=client([])
    monkeypatch.setattr(raw,'readiness',lambda:{'ready':True})
    monkeypatch.setattr(cli,'_client',lambda path:raw)
    monkeypatch.setattr(run_arena_live,'_client',lambda path:raw)
    # Formal production verification still rejects scripted model evidence.
    # Only these test-local validators explicitly allow injected receipts.
    original_evaluation=comparison.verify_evaluation
    original_arm=comparison.verify_arm
    monkeypatch.setattr(comparison,'verify_evaluation',lambda value,**kw:original_evaluation(value,live_only=False))
    monkeypatch.setattr(freezing,'verify_evaluation',lambda value,**kw:original_evaluation(value,live_only=False))
    monkeypatch.setattr(freezing,'verify_arm',lambda value:original_arm(value,live_only=False))
    manifests={name:read(ROOT/f'competition/manifests/{file}.json') for name,file in
               [('strider-subset4','demo18_strider'),('red-heldout','demo18_heldout')]}
    baseline=build_baseline(ROOT,provider_identity=_identity(raw.config),evaluation_manifests=manifests,
                            seeds=[1,2,3],image_hash='offline-integration-test')
    baseline_path=tmp_path/'baseline.json';freeze(baseline_path,baseline)
    for arm,name in [('a','static'),('b','adversarial')]:
        args=SimpleNamespace(client_config=str(ROOT.parent/'client.json'),check=False,baseline_only=False,
            arm=name,baseline=str(baseline_path),state_root=str(tmp_path/('arm-'+arm)),
            max_calls=6000,max_tokens=120000000)
        result=run_arena_live.run(ROOT,args,progress=lambda *a,**kw:None)
        assert result['round_count']==(5 if arm=='b' else 0)
    b=read(tmp_path/'arm-b/frozen_arm.json');a=read(tmp_path/'arm-a/frozen_arm.json')
    assert a['experience_snapshots']['T0']['entries']==[]
    assert a['experience_snapshots']['T1']['entries']==[]
    assert b['experience_snapshots']['R000']['entries']==[]
    assert any(v['entries'] for k,v in b['experience_snapshots'].items() if k.startswith('R'))
    assert b['experience_snapshots']['T1']==b['experience_snapshots']['R004']
    assert not (tmp_path/'arm-a/experience/archive').exists()
    result=comparison.compare_arms(a,b,live_only=False)
    assert result['mode']=='offline_contract_test'
    assert {k:v['denominator'] for k,v in result['metrics'].items()}=={'strider-subset4':12,'red-heldout':6}
    # Resume every stage without reissuing already-completed model calls.
    before=read(tmp_path/'arm-b/budgets/total.json')
    run_arena_live.run(ROOT,args,progress=lambda *a,**kw:None)
    assert read(tmp_path/'arm-b/budgets/total.json')==before
