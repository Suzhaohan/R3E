"""Exercise both complete arms with a scripted model and real local EDA.

This is an offline plumbing test, not model performance evidence. The slow
suite deliberately injects an unavailable simulation to test safe fallback.
"""
from types import SimpleNamespace
import pytest
from test_m3_arena import ROOT, client
from competition.arena.evidence import read, freeze, signed
from competition.arena.baseline import build_baseline
from competition.arena.cli import _identity


def test_two_arms_finish_and_compare_after_final_guard_fallback(tmp_path,monkeypatch):
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
    original_evaluate=ArenaEvaluationService.evaluate_case_with_policy
    def evaluate(self,policy,row,seed,**kwargs):
        if not any(x in row['design'].lower() for x in ('reed','sdram','sha3')):
            return original_evaluate(self,policy,row,seed,**kwargs)
        import uuid
        case=self._case(row);provider=kwargs.get('provider') or self.provider
        work=self.output/('unavailable-'+uuid.uuid4().hex);work.mkdir(parents=True)
        result=signed({'policy_hash':policy.policy_hash,'seed':seed,'case_id':case['case_id'],
            'design':row['design'],'model_id':provider.toolchain_fingerprint['model_id'],
            'budget_hash':hash_payload(policy.budgets),'verifier_hash':provider.toolchain_fingerprint['verifier_hash'],
            'provider_fingerprint':provider.toolchain_fingerprint,'source_kind':'injected_test',
            'case_asset_hash':hash_payload({'assets':case['manifest_file_hashes'],'buggy':case['buggy_rtl_hash']}),
            'artifact_id':work.name,'experience_memory_hash':provider.memory_hash,
            'oracle_ok':False,'cost':0.0,'status':'baseline_not_functional_mismatch',
            'resource_usage':{'provider_calls':0,'input_tokens':0,'output_tokens':0},'portfolio_execution_hash':''},'receipt_hash')
        atomic_write_json(work/'receipt.json',result);return result
    monkeypatch.setattr(ArenaEvaluationService,'evaluate_case_with_policy',evaluate)
    manifests={name:read(ROOT/f'competition/manifests/{file}.json') for name,file in
               [('strider-subset4','demo32_strider'),('red-heldout','demo32_heldout')]}
    baseline=build_baseline(ROOT,provider_identity=_identity(raw.config),evaluation_manifests=manifests,
                            seeds=[1,2,3],image_hash='offline-integration-test')
    baseline_path=tmp_path/'baseline.json';freeze(baseline_path,baseline)
    for arm,name in [('a','static'),('b','adversarial')]:
        args=SimpleNamespace(client_config=str(ROOT.parent/'client.json'),check=False,baseline_only=False,
            arm=name,baseline=str(baseline_path),state_root=str(tmp_path/('arm-'+arm)),
            max_calls=6000,max_tokens=120000000)
        result=run_arena_live.run(ROOT,args,progress=lambda *a,**kw:None)
        assert result['round_count']==(2 if arm=='b' else 0)
    b=read(tmp_path/'arm-b/frozen_arm.json');a=read(tmp_path/'arm-a/frozen_arm.json')
    assert not b['final_selection']['accepted']
    assert b['final_selection']['unavailable']>0 or b['final_selection']['losses']>0
    assert b['final_policy_hash']==baseline['initial_policy_hash']
    assert b['experience_snapshots']['T1']==a['experience_snapshots']['T1']
    result=comparison.compare_arms(a,b,live_only=False)
    assert result['mode']=='offline_contract_test'
    assert {k:v['denominator'] for k,v in result['metrics'].items()}=={'strider-subset4':12,'red-heldout':6}
    assert (tmp_path/'arm-b/demo_final.json').exists()
    # Resume every stage without reissuing already-completed model calls.
    before=read(tmp_path/'arm-b/budgets/total.json')
    run_arena_live.run(ROOT,args,progress=lambda *a,**kw:None)
    assert read(tmp_path/'arm-b/budgets/total.json')==before
