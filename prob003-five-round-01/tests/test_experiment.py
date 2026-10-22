import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prob003_five', HERE/'experiment.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_delivered_implementation_and_materials_are_unchanged():
    experiment.verify_import()
    assert experiment.read(HERE/'import_identity.json')['verified_frozen_files'] == 57


def test_only_round_count_and_derived_schedule_change():
    plan, counter = experiment.check(HERE/'plan-v2')
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
    assert plan['max_calls'] == 39
    assert counter.identity == original['tokenizer']


def test_monetary_ceiling_is_removed_but_request_schedule_is_preserved():
    launch, *_ = experiment.modules()
    budget = experiment.budget(launch)
    assert {row['role']: row['calls'] for row in budget['rows']} == dict(red=5, online=5, reference=5, anchor=24)
    assert budget['maximum_CNY'] == '17.801352'
    assert budget['spending_envelope_CNY'] is None


@pytest.mark.parametrize('field,value', [('red_output_tokens', 32768), ('anchor_repeats', 3),
                                         ('spending_envelope_CNY', '18'), ('rounds', 3)])
def test_unrequested_protocol_changes_are_rejected(field, value):
    launch, *_ = experiment.modules()
    plan = deepcopy(experiment.read(HERE/'plan-v2/plan.json'))
    plan[field] = value
    with pytest.raises(ValueError):
        experiment.check_scope(plan, launch)


def test_disabled_money_ceiling_allows_schedule_above_twelve_yuan(tmp_path):
    _, loop, shared, *_ = experiment.modules()
    attempts = []
    class Counter:
        def request(self, messages):
            return 98304
    def transport(**request):
        attempts.append(request)
        return {'input_tokens': 98304, 'output_tokens': 32768, 'finish_reason': 'stop'}
    guard = shared.UsageGuard(transport, Counter(), tmp_path, envelope='Infinity',
                             allowed_systems={loop.rb.SYSTEM_REPAIR: 32768})
    request = {'model': 'deepseek-v4-flash', 'max_tokens': 32768,
               'messages': [{'role': 'system', 'content': loop.rb.SYSTEM_REPAIR}]}
    for attempt_index in range(39):
        guard(**request)
    assert len(attempts) == 39
    assert not guard.stopped
    assert guard.known_cost > 12


def test_removing_money_ceiling_keeps_per_request_usage_guards(tmp_path):
    _, loop, shared, *_ = experiment.modules()
    class Counter:
        def request(self, messages):
            return 100
    guard = shared.UsageGuard(lambda **kwargs: {'input_tokens':100, 'output_tokens':32769},
        Counter(), tmp_path, envelope='Infinity', allowed_systems={loop.rb.SYSTEM_REPAIR:32768})
    with pytest.raises(shared.UsageStop, match='provider_output_exceeds_requested_limit'):
        guard(model='deepseek-v4-flash', max_tokens=32768,
              messages=[{'role':'system', 'content':loop.rb.SYSTEM_REPAIR}])
    assert guard.stopped
