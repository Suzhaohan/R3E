"""Assert the caps reach API request payloads, including both matched arms."""
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pilot_budget_test', HERE/'pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def client(transport, cap):
    return pilot.build_client({'DEEPSEEK_MODEL':'fake-budget-test'}, transport=transport,
                              maximum_output_tokens=cap)


def test_phase_caps_reach_provider_and_ledger():
    requests, ledger = [], []
    def transport(**request):
        requests.append(request)
        return {'content':'{"ok":true}', 'input_tokens':2, 'output_tokens':3,
                'provider_request_id':'test-budget'}
    budget=pilot.BudgetedClient(client(transport,pilot.SETTINGS['max_output_tokens']),max_calls=20)
    budget.output_caps=dict(pilot.SETTINGS['output_caps'])
    budget.on_call=ledger.append
    red=budget.sibling(client(transport,pilot.SETTINGS['output_caps']['red']))
    for phase,cap in pilot.SETTINGS['output_caps'].items():
        executor=red if phase=='red' else budget
        # Baseline and evolved calls must receive exactly the same phase cap.
        for arm in ('baseline','evolved'):
            with executor.in_phase(phase):
                executor.complete_json(messages=[{'role':'user','content':'Return JSON.'}],seed=7)
            assert requests[-1]['max_tokens']==cap
            assert ledger[-1]['maximum_output_tokens']==cap
    assert budget.total_calls==10
    assert pilot.SETTINGS['output_caps']['qualification']==pilot.SETTINGS['output_caps']['evaluation']==65536
    assert pilot.SETTINGS['output_caps']['escalation']==131072


def test_truncation_keeps_cap_and_cost_without_retry():
    from r3e.providers.openai_compatible import OpenAICompatibleEmptyContentViolation
    requests, ledger=[],[]
    def transport(**request):
        requests.append(request)
        return {'content':'', 'finish_reason':'length', 'input_tokens':10,
                'output_tokens':request['max_tokens'], 'provider_request_id':'test-truncation'}
    budget=pilot.BudgetedClient(client(transport,131072),max_calls=2)
    budget.output_caps=dict(pilot.SETTINGS['output_caps'])
    budget.on_call=ledger.append
    with budget.in_phase('blue_inference'), pytest.raises(OpenAICompatibleEmptyContentViolation):
        budget.complete_json(messages=[{'role':'user','content':'Return JSON.'}],seed=7)
    assert len(requests)==1
    assert budget.total_calls==1
    assert ledger[0]['maximum_output_tokens']==65536
    assert ledger[0]['output_tokens']==65536
    assert ledger[0]['finish_reason']=='length'
    assert not ledger[0]['ok']
