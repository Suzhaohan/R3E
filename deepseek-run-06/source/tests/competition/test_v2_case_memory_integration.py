"""Exercise the v2 memory at the actual competition executor boundary."""
from copy import deepcopy
import json
import re

import pytest

from competition.services.case_memory import entry_from_evaluation, visible_feedback
from competition.services.experience_memory import bank, ExperienceMemory, collect
from competition.services.experience_guard import guard, verify_guard
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.arena.evidence import read, signed
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.knowledge import build_repair_episode
from r3e.protocol.hashing import hash_payload
from test_m3_arena import ROOT, client


def provider(c, memory):
    return PolicyCandidateProvider(c, memory=ExperienceMemory(memory),
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version)


@pytest.fixture
def training(tmp_path):
    rows = read(ROOT / 'competition/manifests/demo18_red_sources.json')['rows']
    row = next(r for r in rows if r['case_id'] == 'assignment4v:mux21_1')
    calls = []
    service = ArenaEvaluationService(ROOT, tmp_path / 'training',
                                    provider=provider(client(calls, repair_all=True), bank([])))
    policy = service.repair._policy()
    receipt = service.evaluate_case_with_policy(policy, row, 1)
    assert receipt['oracle_ok']
    evaluation = read(service.output / receipt['artifact_id'] / 'evaluation.json')
    entry = entry_from_evaluation(evaluation, receipt_hash=receipt['receipt_hash'], design_cluster='mux21')
    context = evaluation['runtime_evidence']
    source = context['buggy_rtl_source']
    patch = evaluation['candidate_provider_receipts'][0]['patch_payload']['replacement_rtl']
    top = service._case(row)['top_module']
    donor_source = re.sub(r'\b' + re.escape(top) + r'\b', 'training_design', source)
    donor_patch = re.sub(r'\b' + re.escape(top) + r'\b', 'training_design', patch)
    # Rename the donor module to represent a different design; both patches
    # were already verified by the real EDA above. No model/API calls occur.
    feedback = visible_feedback({'runtime_observations': {'raw_mismatches':
        context['observations']['raw_by_k']['6']}})
    episode = build_repair_episode(case_id='training_case', design_cluster='training_design',
        buggy_rtl=donor_source, feedback=feedback,
        attempts=[{'verdict_tier': 'visible_fail', 'edit': 'unsuccessful selector'},
                  {'verdict_tier': 'visible_pass', 'edit': 'repair selector'}],
        passing_candidate_rtl=donor_patch)
    value = bank([{'receipt_hash': hash_payload('training'), 'episode': episode.to_dict()}])
    return row, policy, value, entry, evaluation, service


def test_real_receipts_build_case_chains_and_no_reference_source(training):
    row, policy, value, entry, evaluation, service = training
    assert entry['episode']['verified_repair']['source'] == 'blue_candidate'
    assert entry['episode']['verified_repair']['lines']['after']
    rendered = json.dumps(value)
    for forbidden in ('golden_rtl', 'reference_rtl', 'mutation_operator', 'hidden_testbench'):
        assert forbidden not in rendered
    case = service._case(row)
    evidence = {'runtime_observations': {'raw_mismatches':
        evaluation['runtime_evidence']['observations']['raw_by_k']['6']}}
    recalled = ExperienceMemory(value).retrieve(case, evidence=evidence)
    assert recalled and recalled[0]['past_cases'][0]['did_not_work']
    assert not ExperienceMemory(bank([entry])).retrieve(case, evidence=evidence)
    assert not ExperienceMemory(value).retrieve(case)  # no invented visible evidence
    corrupt = deepcopy(evaluation)
    corrupt['candidate_provider_receipts'][0]['patch_payload']['replacement_rtl'] = 'tampered'
    with pytest.raises(ValueError, match='hash'):
        entry_from_evaluation(corrupt, receipt_hash='x', design_cluster='mux21')
    # Synthetic test calls cannot be silently imported into a live memory bank.
    entries, rejected = collect(service.output.glob('*/receipt.json'))
    assert not entries and rejected['not_completed_live_model'] == 1


@pytest.mark.parametrize('first_succeeds', [False, True])
def test_actual_executor_delivers_only_after_failure_and_keeps_three_calls(tmp_path, training, first_succeeds):
    row, policy, value, *_ = training
    calls = []
    c = client(calls, repair_all=first_succeeds)
    service = ArenaEvaluationService(ROOT, tmp_path / 'execution', provider=provider(c, value))
    receipt = service.evaluate_case_with_policy(policy, row, 7)
    assert len(calls) == 3
    prompts = [json.loads(call['messages'][1]['content']) for call in calls]
    assert 'reference_cases' not in prompts[0]
    assert all(('reference_cases' in p) == (not first_succeeds) for p in prompts[1:])
    assert service.provider.client is c
    assert receipt['source_kind'] == 'injected_test'
    assert receipt['oracle_ok'] == first_succeeds


def test_paired_gate_requires_transfer_gain_and_reuses_its_decision(tmp_path, training):
    row, policy, value, _, evaluation, _ = training
    calls = []
    c = client(calls)
    patch = evaluation['candidate_provider_receipts'][0]['patch_payload']['replacement_rtl']

    def transport(**request):
        calls.append(request)
        prompt = json.loads(request['messages'][1]['content'])
        result = {'replacement_rtl': patch if 'reference_cases' in prompt else prompt['current_buggy_rtl'],
                  'edit': 'offline case-memory test'}
        return {'content': json.dumps(result), 'input_tokens': 100, 'output_tokens': 20,
                'provider_request_id': f'test-{len(calls)}'}

    c._transport = transport
    state = tmp_path / 'state'
    assert guard(ROOT, state, 'R001', c, policy, [row], [1, 2, 3], bank([]), value)
    report = verify_guard(read(state / 'experience/guards/R001/report.json'))
    assert report['statistics'] == {'coverage': 3, 'helped': 3, 'harmed': 0, 'p_value': 0.125}
    assert len(calls) == 18  # unchanged: three candidates per arm per seed
    assert guard(ROOT, state, 'R001', c, policy, [row], [1, 2, 3], bank([]), value)
    assert len(calls) == 18
    # One apparent win cannot activate memory under the v2 significance gate.
    assert not guard(ROOT, state, 'R002', c, policy, [row], [4], bank([]), value)
