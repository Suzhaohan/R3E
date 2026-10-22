import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pilot', HERE/'pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_design_and_holdout_isolation():
    carriers, cases, assets = pilot.corpus()
    assert {r: len(v) for r, v in cases.items()} == dict(learning=5, qualification=5, holdout=3, guard=3, prob003_eval=2)
    assert any('Prob001' in ch.challenge_id for ch in cases['learning'])
    assert {ch.challenge_id for ch in cases['learning']} == {ch.challenge_id for ch in cases['qualification']}
    assert all(any(p in ch.challenge_id for p in ('Prob002','Prob017','Prob023')) for ch in cases['holdout'])
    assert not {ch.challenge_id for ch in cases['learning']} & {ch.challenge_id for ch in cases['holdout']}
    assert {ch.challenge_id for ch in cases['prob003_eval']} == pilot.EVAL_IDS
    seed = next(ch for ch in cases['learning'] if ch.challenge_id == pilot.SEED_ID)
    assert all(ch.carrier.clean_rtl == seed.carrier.clean_rtl for ch in cases['prob003_eval'])
    assert assets


def test_red_only_gets_learning_carriers():
    _, cases, _ = pilot.corpus()
    selected = []
    def propose(carrier, **kwargs):
        selected.append(carrier.cluster_id)
        return pilot.RedProposal({}, None)
    red = pilot.SeededRed(SimpleNamespace(propose=propose), cases['learning'])
    original = []
    for r in range(5):
        original = []
        for _ in range(pilot.SETTINGS['proposals_per_round']):
            proposal = red.propose(None, state=None, seed=7, round_index=r)
            if proposal.challenge:
                original.append(proposal.challenge.challenge_id)
        assert set(original) == {c.challenge_id for c in cases['learning']}
    assert len(selected) == 10
    assert set(selected) <= {c.carrier.cluster_id for c in cases['learning']}


def test_evaluation_cannot_run_early(tmp_path):
    state = pilot.RunState(tmp_path)
    with pytest.raises(ValueError, match='five completed rounds'):
        pilot.evaluate(state, None, [])
    assert not (tmp_path/'comparison.json').exists()


@pytest.mark.parametrize('guard_passed, expected', [(False,'rejected'),(True,'active')])
def test_guard_runs_before_activation(monkeypatch, guard_passed, expected):
    import r3e.loop.qualification as q
    transitions = []
    store = SimpleNamespace(transition=lambda *a, **kw: transitions.append(a[2]))
    state = SimpleNamespace(active_items=lambda: [], inference=lambda: None,
                            matcher=None, store=store, append=lambda *a: None)
    candidate = SimpleNamespace(item_id='candidate', version=1, item_hash='h')
    challenge = SimpleNamespace(challenge_id='qual')
    monkeypatch.setattr(q, 'affected_cases', lambda *a, **kw: [challenge])
    monkeypatch.setattr(q, 'first_attempt', lambda x: {'verdict_tier':'visible_fail'})
    def run(ch, **kw):
        with_item = bool(kw['pool'])
        return SimpleNamespace(inconclusive=False, solved_within_budget=with_item,
                               repair_attempts=[{},{}],
                               record=lambda: {'shown_items':['candidate@v1'] if with_item else []})
    def guard(*args):
        assert not transitions, 'guard must run before active state is written'
        return {'passed':guard_passed}
    report = q.qualify_candidate(candidate, runner=SimpleNamespace(run=run), state=state,
        qset=None, config=q.QualificationConfig(), round_index=0, promotion_guard=guard)
    assert report['decision'] == expected
    assert ('active' in transitions) == guard_passed


def test_inconclusive_qualification_never_activates(monkeypatch):
    import r3e.loop.qualification as q
    transitions = []
    candidate = SimpleNamespace(item_id='candidate', version=1, item_hash='h')
    state = SimpleNamespace(active_items=lambda: [], inference=lambda: None, matcher=None,
        store=SimpleNamespace(transition=lambda *a, **kw: transitions.append(a[2])), append=lambda *a: None)
    monkeypatch.setattr(q, 'affected_cases', lambda *a, **kw: [SimpleNamespace(challenge_id='qual')])
    monkeypatch.setattr(q, 'first_attempt', lambda x: {'verdict_tier':'visible_fail'})
    def run(ch, **kw):
        with_item = bool(kw['pool'])
        return SimpleNamespace(inconclusive=kw['seed']==3034, solved_within_budget=with_item,
            repair_attempts=[{},{}], record=lambda:{'shown_items':['candidate@v1'] if with_item else []})
    report=q.qualify_candidate(candidate, runner=SimpleNamespace(run=run),state=state,qset=None,
        config=q.QualificationConfig(repeats=4),round_index=0)
    assert report['reason']=='incomplete_qualification'
    assert 'active' not in transitions


def test_guard_refuses_infrastructure_failure(tmp_path):
    state = pilot.RunState(tmp_path)
    blue = SimpleNamespace(run=lambda *a, **kw: SimpleNamespace(solved_within_budget=False,
        inconclusive=True, repair_attempts=[], attempts=[], record=lambda:{}))
    report=pilot.compare_guard(blue,state,[SimpleNamespace(challenge_id='guard')],
        SimpleNamespace(item_id='c',version=1),[],None,0)
    assert not report['passed']
    assert len(report['pairs'])==3


def test_evaluation_freezes_usage_history_and_reuses_identical_system(tmp_path):
    (tmp_path/'binding.json').write_text(json.dumps({'mode':'fake'}))
    observed = []
    requests = []
    def run(ch, **kw):
        requests.append(kw)
        return SimpleNamespace(solved_within_budget=True, inconclusive=False,
            attempts=[{'verdict_tier':'visible_pass'}],repair_attempts=[{}],record=lambda:{})
    blue=SimpleNamespace(run=run)
    rows={'rounds':[{'round':r,'active':[]} for r in range(5)],'episodes':[],'calls':[],
          'memory_usage':[{'round':r,'item':'k','outcome':'fixed_after_memory'} for r in [0,4]]}
    def items(keys):
        observed.append(blue.track_records()['k']['offered_before'])
        return []
    state=SimpleNamespace(root=tmp_path,checkpoint=lambda:{'completed_rounds':5},
        read=lambda name:rows[name],items_by_key=items,matcher=None)
    result=pilot.evaluate(state,blue,[SimpleNamespace(challenge_id='heldout')])
    assert observed==[1,1,1,1,2], 'early snapshots must not see round-five experience'
    assert len(requests)==3, 'identical empty-memory systems should reuse their common baseline'
    assert all(not r['allow_escalation'] and r['phase']=='evaluation' for r in requests)
    assert all(s['gained']==s['lost']==0 and s['valid_pairs']==3 for s in result['snapshots'])


@pytest.mark.parametrize('solved,inconclusive,ready', [(True,False,False),(False,True,False),(False,False,True)])
def test_calibration_requires_real_failures_not_api_errors(tmp_path, solved, inconclusive, ready):
    state = pilot.RunState(tmp_path)
    calls = []
    def run(ch, **kw):
        calls.append((ch.challenge_id, kw))
        return SimpleNamespace(solved_within_budget=solved, inconclusive=inconclusive,
            attempts=[{'verdict_tier':'visible_pass' if solved else 'visible_fail'}],
            repair_attempts=[{}, {}, {}], record=lambda: {})
    cases = [SimpleNamespace(challenge_id='practice')]
    if ready:
        assert pilot.calibrate(state, SimpleNamespace(run=run), cases) == cases
    else:
        with pytest.raises(ValueError, match='练习难度检查未通过'):
            pilot.calibrate(state, SimpleNamespace(run=run), cases)
    assert len(calls) == 3
    assert all(ch == 'practice' and kw['mode'] == 'none' and not kw['pool']
               and not kw['allow_escalation'] for ch,kw in calls)
    assert json.loads((tmp_path/'calibration.json').read_text())['ready'] == ready


def test_empty_memory_after_two_rounds_stops_before_exam(tmp_path):
    state = SimpleNamespace(root=tmp_path, read=lambda _: [{'decisions':[]}, {'decisions':[]}],
                            active_items=lambda: [])
    with pytest.raises(ValueError, match='最终考试尚未调用'):
        pilot.accumulation_check(state)
    assert (tmp_path/'needs_attention.json').exists()
    assert not (tmp_path/'comparison.json').exists()


def test_split_refuses_exam_in_practice():
    carriers, cases, _ = pilot.corpus()
    cases['holdout'].append(cases['learning'][0])
    with pytest.raises(ValueError, match='考试题混入'):
        pilot.validate_split(carriers, cases)


def test_split_refuses_reserved_variant_in_practice():
    carriers, cases, _ = pilot.corpus()
    cases['learning'].append(cases['prob003_eval'][0])
    cases['qualification'].append(cases['prob003_eval'][0])
    with pytest.raises(ValueError, match='保留评估题混入'):
        pilot.validate_split(carriers, cases)


def test_red_rejects_reserved_variant_with_formatting_changes(tmp_path):
    _, cases, _ = pilot.corpus()
    red = pilot.ReservedRedAgent(reserved=cases['prob003_eval'], mode='random', client=None,
                                simulator=pilot.Prob003Simulator(tmp_path/'simulation'))
    for challenge in cases['prob003_eval']:
        mutant = '\n\n' + challenge.buggy_rtl.replace('nstate=', 'nstate = ')
        reason, shape = red._admit(challenge.carrier, mutant)
        assert reason == 'reserved_evaluation_duplicate'
        assert shape is None


def test_public_trace_and_original_suites_detect_delivered_bugs(tmp_path):
    _, cases, _ = pilot.corpus()
    seed = next(ch for ch in cases['learning'] if ch.challenge_id == pilot.SEED_ID)
    simulator = pilot.Prob003Simulator(tmp_path/'simulation')
    assert simulator.verdict(seed.carrier.clean_rtl, seed.carrier).visible_ok
    for challenge in [seed, *cases['prob003_eval']]:
        assert simulator.verdict(challenge.buggy_rtl, challenge.carrier).tier == 'visible_fail'
    reset = (pilot.PROB003/'materials/package/variants/reset_control/rtl/sequence.sv').read_text()
    assert simulator.verdict(reset, seed.carrier).tier == 'visible_fail'
    report = pilot.qualify_prob003(pilot.PROB003, tmp_path/'original-suites')
    assert report['ready']
    assert report['matrix']['clean']['evaluator']['result'] == 'pass'
    assert report['matrix']['reset_control']['W_preserve']['result'] == 'fail'


def test_supplementary_audit_refuses_before_final_scoring(tmp_path):
    state = pilot.RunState(tmp_path)
    with pytest.raises(ValueError, match='最终公开评分结束后'):
        pilot.audit_prob003(state)
    assert not (tmp_path/'prob003_audit.json').exists()


def test_evaluation_reports_original_exam_and_seen_design_separately(tmp_path):
    (tmp_path/'binding.json').write_text(json.dumps({'mode':'fake'}))
    def run(ch, **kwargs):
        return SimpleNamespace(solved_within_budget=True, inconclusive=False,
            attempts=[{'verdict_tier':'visible_pass'}], repair_attempts=[{}], record=lambda:{})
    rows = {'rounds':[{'round':round_index, 'active':[]} for round_index in range(5)],
            'episodes':[], 'memory_usage':[], 'calls':[]}
    state = SimpleNamespace(root=tmp_path, checkpoint=lambda:{'completed_rounds':5},
        read=lambda name:rows[name], items_by_key=lambda keys:[], matcher=None)
    cases = [SimpleNamespace(challenge_id='original'),
             SimpleNamespace(challenge_id='handoff:Prob003:eval_match_branch')]
    result = pilot.evaluate(state, SimpleNamespace(run=run), cases)
    for snapshot in result['snapshots']:
        assert snapshot['groups']['original_exam']['valid_pairs'] == 3
        assert snapshot['groups']['prob003_seen_design']['valid_pairs'] == 3
        assert snapshot['groups']['original_exam']['gained'] == 0
    assert result['primary_evaluation_group'] == 'original_exam'


def test_supplementary_audit_scores_saved_candidates_without_changing_public_results(tmp_path):
    _, cases, _ = pilot.corpus()
    challenge = cases['prob003_eval'][0]
    artifacts = tmp_path/'prob003-artifacts'
    artifacts.mkdir()
    seed = next(ch for ch in cases['learning'] if ch.challenge_id == pilot.SEED_ID)
    hashes = []
    for rtl in [seed.buggy_rtl, seed.carrier.clean_rtl]:
        candidate_hash = pilot.hash_payload(rtl)
        hashes.append(candidate_hash)
        (artifacts/f'{candidate_hash[7:]}.sv').write_text(rtl)
    cache = tmp_path/'eval-cache'
    cache.mkdir()
    key = pilot.hash_payload((challenge.challenge_id, 0))[7:23]
    for filename, candidate_hash in [(f'baseline_{key}.json', hashes[0]), (f'R4_{key}.json', hashes[1])]:
        (cache/filename).write_text(json.dumps(dict(solved=True, inconclusive=False,
            record=dict(challenge_id=challenge.challenge_id,
                attempts=[dict(verdict_tier='visible_pass', candidate_hash=candidate_hash)]))))
    public = dict(source_kind='fake', snapshots=[dict(round=5, pairs=[dict(
        case_id=challenge.challenge_id, rep=0, baseline=True, evolved=True,
        inconclusive=False, reuse_reason=None)])])
    (tmp_path/'comparison.json').write_text(json.dumps(public))
    state = SimpleNamespace(root=tmp_path, checkpoint=lambda:{'completed_rounds':5}, read=lambda name:[])
    report = pilot.audit_prob003(state)
    assert report['model_calls'] == 0
    assert not report['learning_leaks']
    assert report['snapshots'][0]['gained'] == 1
    assert report['snapshots'][0]['baseline_rate'] == 0
    assert report['snapshots'][0]['evolved_rate'] == 1
    assert json.loads((tmp_path/'comparison.json').read_text()) == public
