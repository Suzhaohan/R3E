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
    assert {r: len(v) for r, v in cases.items()} == dict(learning=4, qualification=4, holdout=2, guard=3)
    assert {c.cluster_id for c in carriers['holdout']} == {'sequence_shift_family'}
    assert all(any(p in ch.challenge_id for p in ('Prob003','Prob015')) for ch in cases['learning'])
    assert all(any(p in ch.challenge_id for p in ('Prob017','Prob023')) for ch in cases['qualification'])
    assert all(any(p in ch.challenge_id for p in ('Prob001','Prob002')) for ch in cases['holdout'])
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
        for _ in range(4):
            proposal = red.propose(None, state=None, seed=7, round_index=r)
            if r == 0:
                original.append(proposal.challenge.challenge_id)
    assert set(original) == {c.challenge_id for c in cases['learning']}
    assert len(selected) == 8
    assert len(set(selected)) == 2


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
