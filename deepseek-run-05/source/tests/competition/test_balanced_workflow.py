"""Balanced workflow contracts: real parsing, gates, persistence and orchestration."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from competition.adapters.policy_provider import expand_local_edits
from competition.arena.evidence import read, signed, freeze
from competition.services.balanced_final import verify_selection
from competition.services.experience_memory import bank, snapshot
from competition.services.balanced_screening import precheck
from competition.services.repair_service import RepairService
from r3e.arena.manifests import make_manifest
from test_m3_arena import ROOT


def test_local_edits_match_original_exactly_and_preserve_other_lines():
    source='module f;\nassign x=a|b;\nassign y=c;\nendmodule\n'
    result=expand_local_edits({'edits':[{'search':'assign x=a|b;','replace':'assign x=a^b;'}],'edit':'fix XOR'},source)
    assert result['replacement_rtl']==source.replace('a|b','a^b')


@pytest.mark.parametrize('source,edits',[
    ('abc abc',[{'search':'abc','replace':'x'}]),
    ('abc',[{'search':'missing','replace':'x'}]),
    ('abc',[{'search':'ab','replace':'x'},{'search':'bc','replace':'y'}]),
    ('abc',[{'search':'','replace':'x'}]),
    ('abc',[]),
])
def test_invalid_local_edits_never_apply(source,edits):
    with pytest.raises(ValueError):expand_local_edits({'edits':edits,'edit':'test'},source)


def selection_fixture(*,fail=False):
    policy=RepairService(ROOT,ROOT/'runtime/test-balanced')._policy()
    old=bank([]);new=bank([{'receipt_hash':'e','family':'f','category':'other','notes':[],'oracle_ok':True}])
    manifest=make_manifest([{'case_id':'a','design':'a'},{'case_id':'b','design':'b'}],split='non_target')
    pairs=[]
    for row in manifest['rows']:
        for seed in (1,2,3):
            def receipt(memory,ok):
                return signed({'case_id':row['case_id'],'seed':seed,'policy_hash':policy.policy_hash,
                    'case_asset_hash':row['case_id'],'provider_fingerprint':{},'budget_hash':'b','verifier_hash':'v',
                    'experience_memory_hash':memory['result_hash'],'oracle_ok':ok,'status':'evaluated'},'receipt_hash')
            pairs.append({'before':receipt(old,True),'after':receipt(new,not fail)})
            if fail:break
        if fail:break
    return signed({'manifest':manifest,'initial_policy':policy.to_dict(),'candidate_policy':policy.to_dict(),
        'initial_memory':old,'candidate_memory':new,'seeds':[1,2,3],'pairs':pairs,
        'complete':not fail,'accepted':not fail,'losses':int(fail),'unavailable':0,'selected_policy':policy.to_dict(),
        'selected_memory':old if fail else new})


def test_final_gate_accepts_only_full_coverage_and_reverts_memory_on_failure():
    assert verify_selection(selection_fixture())['accepted']
    rejected=verify_selection(selection_fixture(fail=True))
    assert not rejected['accepted'] and rejected['selected_memory']==bank([])
    for field,value in [('accepted',True),('selected_memory',rejected['candidate_memory'])]:
        altered={**rejected,field:value};altered.pop('result_hash')
        with pytest.raises(ValueError):verify_selection(signed(altered))


def test_incomplete_or_duplicate_final_checks_cannot_be_called_complete():
    original=selection_fixture()
    for pairs in (original['pairs'][:-1],original['pairs']+[original['pairs'][0]]):
        altered={**original,'pairs':pairs};altered.pop('result_hash')
        with pytest.raises(ValueError):verify_selection(signed(altered))


def test_unavailable_simulation_is_not_a_pass():
    original=selection_fixture()
    for arm in ('before','after'):
        r=original['pairs'][0][arm]
        r={**r,'status':'baseline_not_functional_mismatch','oracle_ok':False};r.pop('receipt_hash')
        original['pairs'][0][arm]=signed(r,'receipt_hash')
    original.pop('result_hash')
    with pytest.raises(ValueError):verify_selection(signed(original))
    original.update(accepted=False,unavailable=1,selected_memory=bank([]))
    assert not verify_selection(signed(original))['accepted']


def test_invalid_model_json_is_a_failed_candidate_not_an_experiment_crash(tmp_path):
    from test_m3_arena import client
    from competition.adapters.policy_provider import PolicyCandidateProvider
    from competition.services.arena_evaluation_service import ArenaEvaluationService
    from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
    raw=client([])
    raw._transport=lambda **kw:{'content':'bad JSON','finish_reason':'stop','input_tokens':10,
                               'output_tokens':2,'provider_request_id':'test-invalid'}
    provider=PolicyCandidateProvider(raw,verifier_id=PublicManifestOracleVerifier.verifier_id,
                                     verifier_version=PublicManifestOracleVerifier.verifier_version)
    service=ArenaEvaluationService(ROOT,tmp_path,provider=provider)
    row=next(r for r in read(ROOT/'competition/manifests/demo32_supplied_assets.json')['rows']
             if r['case_id']=='assignment4v:fa_behavioral_1')
    result=service.evaluate_case_with_policy(service.repair._policy(),row,1)
    assert result['oracle_ok'] is False and result['status']=='evaluated'
    assert result['resource_usage']['provider_calls']==3


def test_second_round_uses_same_memory_without_rechecking_or_discarding_proposals(tmp_path):
    first=snapshot(ROOT,tmp_path,'R000',evolving=True,approve=lambda before,after:True)
    second=snapshot(ROOT,tmp_path,'R001',evolving=True,approve=lambda *a:pytest.fail('memory must stay frozen'))
    assert first==second
    assert (tmp_path/'experience/proposals/R000.json').exists()


def test_early_rejection_avoids_all_regression_work_for_no_target_gain():
    parent=SimpleNamespace(policy_id='parent');child=SimpleNamespace(policy_id='child')
    target={'rows':[{'case_id':'t','design':'t'}]};reg={'rows':[{'case_id':'slow','design':'slow'}]}
    calls=[]
    def replay(policy,row,seed):
        calls.append(row['case_id']);return {'oracle_ok':False,'design':row['design']}
    result=precheck(parent,child,target,reg,[1,2,3],replay)
    assert not result['eligible'] and result['reason']=='insufficient_target_gain'
    assert 'slow' not in calls


def test_fast_suite_keeps_old_regressions_and_all_types_are_in_final_suite():
    full=read(ROOT/'competition/manifests/demo32_regression.json')
    fast=read(ROOT/'competition/manifests/balanced_fast_regression.json')
    assert full['row_count']==16 and fast['row_count']==10
    assert len({r['design'] for r in fast['rows']})==5
    ids={r['case_id'] for r in fast['rows']}
    assert {'strider:fsm_full_4','strider:mux_4_1_3'}<=ids
    assert ids<={r['case_id'] for r in full['rows']}


def test_dashboard_shows_historical_evidence_without_claiming_current_completion():
    import balanced
    data=balanced.snapshot(ROOT.parent)
    assert data['historical'] and data['pipeline']['status']!='complete'
    row=next(r for r in data['historical'] if r['case_id']=='assignment4v:JG3_10')
    assert (row['static_successes'],row['memory_successes'])==(0,3)
    assert not data['metrics']


def test_one_command_orders_all_stages_and_preserves_interrupted_stage(tmp_path,monkeypatch):
    import balanced,run_resilient
    import competition.arena.cli as cli
    import competition.services.experience_library as library
    monkeypatch.setattr(balanced,'RUN',tmp_path)
    monkeypatch.setattr(balanced,'ensure_web',lambda port:None)
    monkeypatch.setattr(run_resilient,'preflight',lambda *a:{'ready':True})
    monkeypatch.setattr(library,'archive',lambda *a:None)
    events=[]
    monkeypatch.setattr(cli,'main',lambda argv,root:events.append('init-arm'))
    monkeypatch.setattr(balanced,'demonstration',lambda arm,phase,**kw:events.append('preview-'+arm))
    def launch(argv):
        events.append(argv[0]);return 0
    monkeypatch.setattr(run_resilient,'main',launch)
    args=SimpleNamespace(port=8085,max_calls=6000,max_tokens=120000000)
    assert balanced.run_pipeline(args)==0
    assert events==['init','init-arm','init-arm','preview-a','preview-b','a0','b','a','compare']
    assert read(tmp_path/'pipeline.json')['status']=='complete'
    monkeypatch.setattr(run_resilient,'main',lambda argv:1 if argv[0]=='b' else 0)
    assert balanced.run_pipeline(args)==1
    state=read(tmp_path/'pipeline.json')
    assert state['status']=='blocked' and state['stage']=='b'
