from copy import deepcopy
from pathlib import Path
import pytest
import yaml

from competition.arena.evidence import read, signed, freeze
from competition.arena_config import validate_arena_config
from competition.services.experience_memory import bank, snapshot, archive, ExperienceMemory
from competition.services.experience_guard import guard, verify_guard, qualification, QUALIFICATION
from r3e.protocol.hashing import hash_payload
from test_m3_arena import ROOT, setup_arm, client


def test_new_runs_and_static_arm_start_empty_and_never_import_other_runs(tmp_path):
    _,_,state=setup_arm(tmp_path)
    unrelated=tmp_path/'old-run/experience'
    unrelated.mkdir(parents=True)
    freeze(unrelated/'R000.json',signed({"schema_version": "old-bank", "entries": [{"receipt_hash": "old"}]}))
    value=snapshot(ROOT,state,'R000',evolving=True)
    assert value==bank([])
    assert snapshot(ROOT,state,'R000',evolving=True)==value
    _,_,static=setup_arm(tmp_path,'static')
    assert snapshot(ROOT,static,'T0')==bank([])
    assert snapshot(ROOT,static,'T1')==bank([])
    assert snapshot(ROOT,static,'T1')['enabled'] is False
    with pytest.raises(ValueError,match='A cannot'):
        snapshot(ROOT,static,'R000',evolving=True)
    assert archive(ROOT,static)==bank([])
    assert not (static/'experience/archive').exists()


def test_a_configuration_cannot_enable_memory():
    raw=yaml.safe_load((ROOT/'competition/configs/arena/static.yaml').read_text())
    raw['memory']['enabled']=True
    with pytest.raises(ValueError,match='Only B'):
        validate_arena_config(raw)


def test_legacy_notes_are_not_activated_as_v2_cases():
    with pytest.raises(KeyError, match="episode"):
        bank([{'receipt_hash': 'local', 'family': 'mux', 'notes': []}])
    with pytest.raises(ValueError, match="legacy"):
        ExperienceMemory(signed({'schema_version': 'r3e-experience-bank-v1', 'entries': []}))


def test_no_changed_retrieval_makes_no_model_calls(tmp_path):
    _,_,state=setup_arm(tmp_path)
    from competition.arena.baseline import load_runtime
    runtime,_,_=load_runtime(state)
    calls=[]
    old=bank([])
    rows=read(ROOT/'competition/manifests/demo18_regression.json')['rows']
    assert not guard(ROOT,state,'R001',client(calls),runtime.active_policy(),rows,[1],old,old)
    assert calls==[]
    report=verify_guard(read(state/'experience/guards/R001/report.json'))
    assert report['reason']=='no_coverage'


def test_memory_guard_rejects_regression_and_unavailable_evidence():
    before=signed({'case_id':'x','seed':1,'policy_hash':'p','case_asset_hash':'x',
        'provider_fingerprint':{},'budget_hash':'b','verifier_hash':'v',
        'experience_memory_hash':'old','oracle_ok':True,'status':'evaluated'},'receipt_hash')
    for status in ['evaluated','baseline_not_functional_mismatch']:
        after=signed({**{k:v for k,v in before.items() if k!='receipt_hash'},
            'experience_memory_hash':'new','oracle_ok':False,'status':status},'receipt_hash')
        pairs=[{'before':before,'after':after,'memory_delivered':True}]
        report=signed({'qualification':QUALIFICATION, 'statistics':qualification(pairs), 'binding':{'case_ids':['x'],'seeds':[1],'policy_hash':'p',
            'parent_memory_hash':'old','proposed_memory_hash':'new'},
            'pairs':pairs,'accepted':False,'complete':True})
        assert not verify_guard(report)['accepted']
        forged=signed({**{k:v for k,v in report.items() if k!='result_hash'},'accepted':True})
        with pytest.raises(ValueError):verify_guard(forged)


def test_only_two_guard_cases_added_and_original_flow_ui_preserved():
    base=read(ROOT/'competition/manifests/demo18_regression.json')
    current=read(ROOT/'competition/manifests/guard_regression.json')
    old={r['case_id'] for r in base['rows']}
    new={r['case_id'] for r in current['rows']}
    assert len(new)==4 and old<new and len(new-old)==2
    from competition.scripts.run_arena_live import ROUND_IDS
    assert len(ROUND_IDS)==5
    assert read(ROOT/'competition/configs/arena/policy_search_space_v1.json')['max_children_per_round']==5
    original=ROOT.parent.parent/'deepseek-run-03/source'
    for name in ['index.html','styles.css']:
        p=original/'competition/app/frontend'/name
        if p.exists():assert (ROOT/'competition/app/frontend'/name).read_bytes()==p.read_bytes()
    for name in ['demo18_red_sources','demo18_supplied_assets','demo18_heldout','demo18_strider']:
        assert read(ROOT/f'competition/manifests/{name}.json')==read(original/f'competition/manifests/{name}.json')
