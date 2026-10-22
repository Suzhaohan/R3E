import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('evidence_retention_experiment',HERE/'experiment-evidence-retention-v1.py')
helpers=module('evidence_retention_helpers',HERE/'tests/test_public_feedback.py');helpers.ex=ex

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


def test_retention_keeps_ties_and_rejects_any_previously_passing_loss():
    loop,m,p=helpers.core()
    d=loop.promotion_decision({'a':False,'b':False},{'a':False,'b':False},set())
    assert d['accepted'] and not d['measured_gain']
    assert d['reason']=='retained_no_regression_no_measured_gain'
    assert loop.promotion_decision({'a':True},{'a':True},{'a'})['accepted']
    d=loop.promotion_decision({'a':True,'b':False,'c':False},{'a':False,'b':True,'c':True},{'a'})
    assert not d['accepted'] and d['reason']=='regression' and d['losses']==['a']
    d=loop.promotion_decision({'a':False},{'a':True},set())
    assert d['accepted'] and d['measured_gain'] and d['reason']=='strict_gain_no_regression'


def test_zero_validation_tie_retains_and_delivers_current_run_success_without_claiming_gain(tmp_path,monkeypatch):
    root,order=helpers.batch(tmp_path,monkeypatch,training_success_attempt=4,neutral_validation=True,
        practice_edits={'Prob003':dict(find='nstate=data?sf6:s6;',replace='nstate=data?s6:sf6;')})
    summary=ex.read(root/'promotion_results.json')
    assert summary['comparison']['complete']
    assert summary['normal_max_requests']==303 and summary['hard_max_requests']==606
    assert (root/'training_barrier.json').exists()
    for design in ex.DESIGNS:
        row=summary['designs'][design];c=root/design/'collection'
        assert row['retained_entries']==1 and row['accepted_promotions']==1
        assert row['strict_gain_promotions']==0 and row['retentions_without_measured_gain']==1
        assert row['certified_validation']['initial_passed']==row['certified_validation']['retained_passed']==0
        gates=[json.loads(l) for l in (c/'promotions.jsonl').read_text().splitlines()]
        assert gates[0]['reason']=='retained_no_regression_no_measured_gain'
        entry=ex.read(c/'rounds/5/commit.json')['blue']['entries'][0]
        assert entry['body']['source']['run_id']==c.name
        content=entry['body']['content']
        assert content['transfer_summary']['checks_on_transfer']==[]
        assert content['repair_evidence']['public_before']['W_bug']['result']=='visible_fail'
        assert content['repair_evidence']['public_after']['W_bug']['result']=='visible_pass'
        assert content['repair_evidence']['changed_ranges']
        assert 'original_buggy/' in content['applied_patch']
        for d in (c/'anchors').glob('b0*/delivery.json'):
            assert ex.read(d)['payload']['entries']==[]
        b5=list((c/'anchors').glob('b5*/delivery.json'))
        assert b5 and all(len(ex.read(d)['payload']['entries'])==1 for d in b5)
        red2=ex.read(c/'rounds/2/r2_s0/red/request.json')
        request=json.loads(red2['messages'][-1]['content'])
        assert request['target_blue']['eligible_entry_count']==1
        assert (c/'audits/source_audit.json').exists()


def test_compact_evidence_omits_format_noise_but_keeps_actual_state_context():
    helpers.core()
    from r3e.loop.episode_evidence import extract,valid
    before='module x;\n// old formatting\n always @* begin\n s5:\n nstate=data?s6:sf6;\n end\nendmodule\n'
    after='\nmodule x;\n// another comment\nalways @* begin\n s5:\n nstate = data ? sf6 : s6;\nend\nendmodule\n'
    def public(result,marker):return {'suites':{'W_bug':{'result':result,'log':marker},'W_preserve':{'result':'visible_pass','log':'TESTBENCH PASS reset'}}}
    archive={'files':{'rtl/x.sv':after},'patch':'original full raw diff kept only in authenticated archive'}
    patch,changed,evidence=extract({'rtl/x.sv':before},archive,public('visible_fail','CHECK_FAIL cycle=6 got=0 expected=1'),public('visible_pass','TESTBENCH PASS W_bug'))
    assert valid(evidence) and len(evidence['changed_ranges'])==1
    assert 's5:' in patch and 'data?s6:sf6' in patch and 'data ? sf6 : s6' in patch
    assert 'module x' not in patch and 'old formatting' not in patch and 'another comment' not in patch
    assert evidence['public_before']['W_bug']['markers']==['CHECK_FAIL cycle=6 got=0 expected=1']
    assert changed and all(len(x)<=240 for x in changed)


def test_sequence_curriculum_enforces_continuity_and_cannot_fall_back_from_boundary():
    loop,m,p=helpers.core('Prob003');g=loop.targeted_prompts
    first={'round':1,'label':'public_pass_single_sample_hidden_unknown','source_hash':'late-bit'}
    miss={'round':2,'label':'public_pass_single_sample_hidden_unknown','source_hash':'miss-path'}
    fail={'round':3,'label':'public_functional_failure_single_sample_unconfirmed','source_hash':'failed-miss'}
    assert g.curriculum_stage(p['carrier_id'],1,[])['allowed_states']==['s5']
    assert g.curriculum_stage(p['carrier_id'],4,[first,fail])['allowed_states']==['sf5','sf4']
    assert not g.curriculum_stage(p['carrier_id'],4,[first,fail])['allow_group_boundary_changes']
    for n in [4,5]:
        stage=g.curriculum_stage(p['carrier_id'],n,[first,miss,fail])
        assert stage['allowed_states']==['sf6','s6'] and stage['allow_group_boundary_changes']
        inventory=g.transition_inventory(p,n,[first,miss,fail])
        assert {s['state'] for s in inventory['sites']}=={'sf6','s6'}
        intermediate={'status':'proposal','buggy_rtl':p['clean_rtl'].replace('nstate=sf6;','nstate=s6;')}
        assert g.curriculum_violation(p,intermediate,n,[first,miss,fail])
        boundary={'status':'proposal','buggy_rtl':p['clean_rtl'].replace('        s6:\n            nstate=data?sf1:s1;','        s6:\n            nstate=data?s1:sf1;')}
        assert g.curriculum_violation(p,boundary,n,[first,miss,fail]) is None
        assert g.curriculum_violation(p,boundary,3,[first,miss])


def test_no_successful_episode_can_be_created_from_failed_public_rows():
    loop,m,p=helpers.core()
    with pytest.raises(ValueError,match='fully public-passing'):
        loop.state.episode_entry({},'',{},dict(W_bug='visible_fail',W_preserve='visible_pass'),
            original_files={},baseline_evidence={},replay_evidence={})
