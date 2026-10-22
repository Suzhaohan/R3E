import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prob003_five', HERE/'experiment.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_original_materials_and_explicit_implementation_overrides():
    experiment.verify_import()
    assert experiment.read(HERE/'import_identity.json')['verified_frozen_files'] == 57


def test_five_round_plan_has_requested_limits_and_bounded_regeneration():
    plan, counter = experiment.check(HERE/'plan-v4')
    original = experiment.read(HERE/'handoff/plan/plan.json')
    assert plan['rounds'] == 5
    assert plan['slots'][:3] == original['slots']
    assert len(plan['slots']) == 5
    assert len(plan['anchor_probes']) == 24
    assert {probe['snapshot'] for probe in plan['anchor_probes']} == set(range(6))
    assert all(sum(probe['snapshot'] == snapshot for probe in plan['anchor_probes']) == 4
               for snapshot in range(6))
    assert plan['blue_config']['budget_k'] == 1
    assert plan['blue_config']['max_infra_retries'] == 0
    assert plan['max_calls'] == 88
    assert plan['reserved_collision_retries'] == 3
    assert plan['red_output_tokens'] == 32768
    assert plan['blue_config']['output_reserve'] == 65536
    assert counter.identity == original['tokenizer']


def test_monetary_ceiling_is_removed_but_request_schedule_is_preserved():
    launch, *_ = experiment.modules()
    budget = experiment.budget(launch)
    assert {row['role']: row['calls'] for row in budget['rows']} == dict(red=20, online=10, reference=10, anchor=48)
    assert budget['maximum_CNY'] == '54.404184'
    assert budget['spending_envelope_CNY'] is None


@pytest.mark.parametrize('field,value', [('red_output_tokens', 16384), ('anchor_repeats', 3),
                                         ('spending_envelope_CNY', '18'), ('rounds', 3), ('reserved_collision_retries', 4)])
def test_unrequested_protocol_changes_are_rejected(field, value):
    launch, *_ = experiment.modules()
    plan = deepcopy(experiment.read(HERE/'plan-v4/plan.json'))
    plan[field] = value
    with pytest.raises(ValueError):
        experiment.check_scope(plan, launch)


def test_disabled_money_ceiling_allows_schedule_above_twelve_yuan(tmp_path):
    _, loop, shared, *_ = experiment.modules()
    attempts = []
    class Counter:
        def request(self, messages):
            return 65536
    def transport(**request):
        attempts.append(request)
        return {'input_tokens': 65536, 'output_tokens': 65536, 'finish_reason': 'stop'}
    guard = shared.UsageGuard(transport, Counter(), tmp_path, envelope='Infinity',
                             allowed_systems={loop.rb.SYSTEM_REPAIR: 65536})
    request = {'model': 'deepseek-v4-flash', 'max_tokens': 65536,
               'messages': [{'role': 'system', 'content': loop.rb.SYSTEM_REPAIR}]}
    for attempt_index in range(88):
        guard(**request)
    assert len(attempts) == 88
    assert not guard.stopped
    assert guard.known_cost > 12


def test_removing_money_ceiling_keeps_per_request_usage_guards(tmp_path):
    _, loop, shared, *_ = experiment.modules()
    class Counter:
        def request(self, messages):
            return 100
    guard = shared.UsageGuard(lambda **kwargs: {'input_tokens':100, 'output_tokens':65537},
        Counter(), tmp_path, envelope='Infinity', allowed_systems={loop.rb.SYSTEM_REPAIR:65536})
    with pytest.raises(shared.UsageStop, match='provider_output_exceeds_requested_limit'):
        guard(model='deepseek-v4-flash', max_tokens=65536,
              messages=[{'role':'system', 'content':loop.rb.SYSTEM_REPAIR}])
    assert guard.stopped


def test_reserved_collision_regenerates_without_consuming_another_round():
    run = HERE/'smoke-v4'
    rows = [experiment.json.loads(line) for line in (run/'slots.jsonl').read_text().splitlines()]
    assert len(rows) == 5
    assert all(row['admission'] == 'admitted' for row in rows)
    first = rows[0]
    assert first['calls'] == 5
    assert [item['reserved_collision'] for item in first['generation_attempts']] == [True, False]
    retry = experiment.read(run/'rounds/1/r1_s0/red_retry_1/request.json')
    payload = experiment.json.loads(retry['messages'][-1]['content'])
    assert len(payload['excluded_previous_proposals']['edits']) == 1
    assert 'anchors' not in payload
    calls = [experiment.json.loads(line) for line in (run/'calls.jsonl').read_text().splitlines()]
    assert len(calls) == 41
    requests = list((run/'rounds').glob('*/*/red*/request.json'))
    assert all(experiment.read(path)['output_tokens'] == 32768 for path in requests)
    assert experiment.read(run/'collection.json')['status'] == 'complete'
    assert (run/'audits/source_audit.json').exists()
    assert (run/'audits/exposure_audit.json').exists()


def test_reserved_collision_retries_are_bounded_and_other_rejections_are_not_retried(tmp_path):
    _, loop, _, curriculum, counter_type = experiment.modules()
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    material = experiment.materials()
    clean = (Path(material['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
    anchor = (Path(material['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv').read_text()
    plan = experiment.read(HERE/'plan-v4/plan.json')
    seen = []
    def transport(**request):
        seen.append(request)
        # Four exam collisions exhaust round 1. Round 2 repeats the historical seed;
        # round 3 produces no answer; rounds 4 and 5 explicitly abstain.
        if len(seen) <= 4:
            edits = [{'find': clean, 'replace': anchor}]
        elif len(seen) == 5:
            edits = material['mechanism_focus']['seed_edits']
        elif len(seen) == 6:
            return {'content': '', 'input_tokens': 1, 'output_tokens': 32768, 'finish_reason': 'length'}
        else:
            return _reply({'abstain': 'offline test'}, 1)
        return _reply({'edits': edits, 'violated_requirement': 'test', 'spec_basis': 'test'}, 1)
    client = build_client({}, model_override='deepseek-v4-flash', thinking='low', timeout_seconds=1500,
                         maximum_output_tokens=65536, temperature=0.2, require_seed=False, transport=transport)
    # No Blue trial should occur in the online rounds; deferred exams still execute.
    # Supply normal Blue answers only during the deferred exams.
    real_transport = transport
    def bounded_transport(**request):
        user = experiment.json.loads(request['messages'][-1]['content'])
        if 'carrier' in user:
            assert request['max_tokens'] == 32768
            return real_transport(**request)
        assert request['max_tokens'] == 65536
        current = user['files'][curriculum.PRIMARY]['content']
        return _reply({'files': [{'file': curriculum.PRIMARY, 'content': clean}],
                       'edit': 'offline test'}, 1)
    client._transport = bounded_transport
    loop.collect(plan, tmp_path/'collection', client=BudgetedClient(client, max_calls=88), counter=counter_type())
    rows = [experiment.json.loads(line) for line in (tmp_path/'collection/slots.jsonl').read_text().splitlines()]
    assert [len(row['generation_attempts']) for row in rows] == [4, 1, 1, 1, 1]
    assert rows[0]['reason'] == 'reserved_task_collision'
    assert rows[1]['reason'] == 'historical_seed_repeat'
    assert rows[2]['generation_status'] == 'no_answer'
    assert len(seen) == 8
    assert all(not row['trials'] for row in rows)
