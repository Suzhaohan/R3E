import json
import sys
from types import SimpleNamespace

import pytest

from test_experiment import experiment, HERE


@pytest.fixture
def api():
    _, loop, _, curriculum, counter_type = experiment.modules()
    return loop.rb, loop, curriculum, counter_type


def test_full_file_schema_rejects_ambiguous_or_unusable_submissions(api):
    rb, *_ = api
    good = {'files': [{'file': 'rtl/sequence.sv', 'content': 'module TopModule; endmodule'}],
            'edit': 'repair'}
    assert rb.validate_full_submission(good, {'rtl/sequence.sv'}) is None
    bad = [None, {}, {**good, 'edits': []}, {**good, 'edit': ''},
           {**good, 'files': []},
           {**good, 'files': good['files'] * 2},
           {**good, 'files': [{'file': '../sequence.sv', 'content': 'module X; endmodule'}]},
           {**good, 'files': [{'file': 'rtl/sequence.sv', 'content': ''}]},
           {**good, 'files': [{'file': 'rtl/sequence.sv', 'content': '```verilog\ncode\n```'}]},
           {**good, 'files': [{'file': 'rtl/sequence.sv', 'find': 'old', 'replace': 'new'}]}]
    assert all(rb.validate_full_submission(item, {'rtl/sequence.sv'}) for item in bad)


def repair_fixture(api, tmp_path, monkeypatch, replies):
    rb, loop, curriculum, counter_type = api
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    material = experiment.materials()
    task = rb.RepoTask.load(material['anchors'][0]['task_dir'])
    clean = (experiment.Path(material['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
    counter = counter_type()
    setup = rb.setup(task, counter, loop.CONFIG)
    requests, test_runs = [], []
    execute = rb.execute
    def spy(*args, **kwargs):
        test_runs.append(True)
        return execute(*args, **kwargs)
    monkeypatch.setattr(rb, 'execute', spy)
    def transport(**request):
        user = json.loads(request['messages'][-1]['content'])
        assert 'find' not in user['required_output_schema']['files'][0]
        assert 'edits' not in user['required_output_schema']
        requests.append(user)
        reply = replies[len(requests) - 1]
        if reply == 'valid':
            reply = {'files': [{'file': curriculum.PRIMARY, 'content': clean}], 'edit': 'repair'}
        elif reply == 'unchanged':
            reply = {'files': [{'file': curriculum.PRIMARY,
                               'content': user['files'][curriculum.PRIMARY]['content']}], 'edit': 'no-op'}
        elif reply == 'malformed':
            return {'content': '{broken JSON', 'input_tokens': 100, 'output_tokens': 40,
                    'provider_request_id': 'fake-malformed', 'finish_reason': 'stop'}
        elif reply == 'length':
            return {'content': '', 'input_tokens': 100, 'output_tokens': 65536,
                    'provider_request_id': 'fake-length', 'finish_reason': 'length'}
        return _reply(reply, len(requests))
    client = BudgetedClient(build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport,
                                        maximum_output_tokens=65536), max_calls=2)
    runner = rb.RepoBlueRunner(client=client, counter=counter, archive=tmp_path/'archive', cfg=loop.CONFIG)
    result = runner.run(task, setup, seed=1)
    return result, requests, test_runs


def test_format_correction_happens_before_tests_and_retains_both_responses(api, tmp_path, monkeypatch):
    invalid = {'edits': [], 'edit': 'old format'}
    result, requests, tests = repair_fixture(api, tmp_path, monkeypatch, [invalid, 'valid'])
    assert result['outcome'] == 'fixed' and result['calls'] == 2
    assert len(tests) == 1
    assert [r['submission_kind'] for r in requests] == ['repair', 'format_correction']
    assert requests[1]['format_correction']['previous_response'] == invalid
    assert requests[0]['current_failure_evidence'] == requests[1]['current_failure_evidence']
    assert requests[0]['files'] == requests[1]['files']
    assert len(result['attempts']) == 1
    assert len(result['attempts'][0]['submissions']) == 2
    assert result['attempts'][0]['repair_tokens']['output'] == 80
    records = sorted((tmp_path/'submissions').glob('response_*.json'))
    assert len(records) == 2
    assert json.loads(records[0].read_text())['result'] == invalid


def test_two_invalid_formats_stop_without_running_tests(api, tmp_path, monkeypatch):
    result, requests, tests = repair_fixture(api, tmp_path, monkeypatch, [{}, {}])
    assert result['outcome'] == 'not_fixed' and result['calls'] == 2
    assert not tests and len(requests) == 2
    assert result['attempts'][0]['tier'] == 'invalid_edit'


def test_valid_but_wrong_repair_does_not_receive_a_format_retry(api, tmp_path, monkeypatch):
    result, requests, tests = repair_fixture(api, tmp_path, monkeypatch, ['unchanged'])
    assert result['outcome'] == 'not_fixed' and result['calls'] == 1
    assert len(tests) == len(requests) == 1


def test_malformed_json_can_be_corrected_without_functional_feedback(api, tmp_path, monkeypatch):
    result, requests, tests = repair_fixture(api, tmp_path, monkeypatch, ['malformed', 'valid'])
    assert result['outcome'] == 'fixed' and result['calls'] == 2
    assert len(tests) == 1
    assert requests[1]['format_correction']['previous_response'] is None
    assert json.loads((tmp_path/'submissions/response_0001.json').read_text())['error_type']


def test_output_exhaustion_is_not_retried_as_a_format_error(api, tmp_path, monkeypatch):
    result, requests, tests = repair_fixture(api, tmp_path, monkeypatch, ['length'])
    assert result['outcome'] == 'not_fixed' and result['calls'] == 1
    assert result['attempts'][0]['tier'] == 'no_answer'
    assert len(requests) == 1 and not tests


def test_transport_records_original_answer_before_json_cleanup(api, tmp_path, monkeypatch):
    from r3e.loop.env import ThinkingTransport
    original = '```json\n{"files": [], "edit": "test"}\n```'
    reply = SimpleNamespace(id='fake-request',
        choices=[SimpleNamespace(message=SimpleNamespace(content=original), finish_reason='stop')],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40))
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply)))
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=lambda **kw: fake_client))
    path = tmp_path/'provider_responses.jsonl'
    transport = ThinkingTransport({'KEY': 'fake-secret', 'URL': 'https://example.invalid'},
        key_name='KEY', url_name='URL', thinking='low', timeout_seconds=1, response_log=path)
    response = transport(model='fake-local', messages=[])
    assert json.loads(response['content']) == {'files': [], 'edit': 'test'}
    assert json.loads(path.read_text())['content'] == original
    assert 'fake-secret' not in path.read_text()
