"""A final, complete regression gate for exploratory policy and memory changes."""
from pathlib import Path

from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.arena.baseline import load_runtime
from competition.arena.budget import BudgetedClient
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.experience_memory import bank, ExperienceMemory
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.policy.schema import PolicyState
from r3e.arena.manifests import verify_manifest


def verify_selection(value):
    verify_signed(value)
    manifest = verify_manifest(value['manifest'])
    initial = PolicyState.from_dict(value['initial_policy'])
    candidate = PolicyState.from_dict(value['candidate_policy'])
    old_memory, new_memory = (verify_signed(value[k]) for k in ('initial_memory', 'candidate_memory'))
    if old_memory != bank([]) or value['seeds'] != [1, 2, 3]:
        raise ValueError('final gate baseline/repetitions changed')
    expected = {(r['case_id'], s) for r in manifest['rows'] for s in value['seeds']}
    seen, losses, unavailable = set(), 0, 0
    for pair in value['pairs']:
        a, b = (verify_signed(pair[k], 'receipt_hash') for k in ('before', 'after'))
        key = a['case_id'], a['seed']
        if key in seen or key not in expected:
            raise ValueError('invalid final guard membership')
        seen.add(key)
        for field in ('case_id', 'seed', 'case_asset_hash', 'provider_fingerprint', 'budget_hash', 'verifier_hash'):
            if a[field] != b[field]:
                raise ValueError('final guard paired conditions differ')
        if (a['policy_hash'] != initial.policy_hash or b['policy_hash'] != candidate.policy_hash
                or a['experience_memory_hash'] != old_memory['result_hash']
                or b['experience_memory_hash'] != new_memory['result_hash']):
            raise ValueError('final guard policy/memory mismatch')
        losses += bool(a['oracle_ok']) and not bool(b['oracle_ok'])
        unavailable += a.get('status') != 'evaluated' or b.get('status') != 'evaluated'
    complete = seen == expected
    accepted = complete and losses == 0 and unavailable == 0
    if value['complete'] != complete or value['accepted'] != accepted or value['losses'] != losses or value['unavailable'] != unavailable:
        raise ValueError('final guard verdict differs from receipts')
    if not complete and not losses and not unavailable:
        raise ValueError('incomplete final guard cannot select a result')
    policy, memory = (candidate, new_memory) if accepted else (initial, old_memory)
    if value['selected_policy'] != policy.to_dict() or value['selected_memory'] != memory:
        raise ValueError('unverified final selection')
    return value


def selected_policy(state, runtime):
    path = Path(state) / 'final_selection.json'
    if path.exists():
        return PolicyState.from_dict(verify_selection(read(path))['selected_policy'])
    return runtime.active_policy()


def run_final_gate(root, state, args, progress=print, *, raw_client=None):
    from competition.arena.cli import _client
    root, state = Path(root), Path(state)
    runtime, _, baseline = load_runtime(state)
    target = state / 'final_selection.json'
    if target.exists():
        return verify_selection(read(target))
    client = raw_client or _client(args.client_config)
    client = BudgetedClient(client, state/'budgets/FINAL-GUARD.json', max_calls=args.max_calls, max_tokens=args.max_tokens)
    client = BudgetedClient(client, state/'budgets/total.json', max_calls=args.max_calls, max_tokens=args.max_tokens)
    initial, candidate = PolicyState.from_dict(baseline['policy']), runtime.active_policy()
    initial_memory = bank([])
    contexts = sorted((state/'experience').glob('R[0-9][0-9][0-9].json'))
    memory = verify_signed(read(contexts[-1])) if contexts else initial_memory
    manifest = read(root/'competition/manifests/demo32_regression.json')
    services = []
    for context in (initial_memory, memory):
        provider = PolicyCandidateProvider(client, memory=ExperienceMemory(context),
            verifier_id=PublicManifestOracleVerifier.verifier_id,
            verifier_version=PublicManifestOracleVerifier.verifier_version, adapter_version='m3-policy-v1')
        services.append(ArenaEvaluationService(root, state/'replays', provider=provider))
    pairs = []
    for row in manifest['rows']:
        for seed in baseline['seeds']:
            progress(f"最终防退化：{row['case_id']}，第 {seed}/3 次（已完成 {len(pairs)}/48 对）", flush=True)
            before, after = [service.evaluate_case_cached(policy, row, seed, cache_root=state/'final_guard_cache')
                             for service, policy in zip(services, (initial, candidate))]
            pairs.append({'before': before, 'after': after})
            if ((before['oracle_ok'] and not after['oracle_ok'])
                    or before['status'] != 'evaluated' or after['status'] != 'evaluated'):
                break
        if any((p['before']['oracle_ok'] and not p['after']['oracle_ok'])
               or p['before']['status'] != 'evaluated' or p['after']['status'] != 'evaluated' for p in pairs):
            break
    losses = sum(p['before']['oracle_ok'] and not p['after']['oracle_ok'] for p in pairs)
    complete = len(pairs) == manifest['row_count'] * len(baseline['seeds'])
    unavailable = sum(p['before']['status'] != 'evaluated' or p['after']['status'] != 'evaluated' for p in pairs)
    accepted = complete and losses == 0 and unavailable == 0
    result = signed({'schema_version': 'r3e-balanced-final-selection-v1',
        'baseline_hash': baseline['baseline_hash'], 'manifest': manifest, 'seeds': baseline['seeds'],
        'initial_policy': initial.to_dict(), 'candidate_policy': candidate.to_dict(),
        'initial_memory': initial_memory, 'candidate_memory': memory, 'pairs': pairs,
        'complete': complete, 'accepted': accepted, 'losses': losses, 'unavailable': unavailable,
        'selected_policy': (candidate if accepted else initial).to_dict(),
        'selected_memory': memory if accepted else initial_memory,
        'message': ('完整防退化通过，采用候选版本。' if accepted else
                    '存在未完成的功能验证，最终使用原始版本，不声明完整防退化通过。' if unavailable else
                    '候选出现退步，最终使用原始版本；候选和经验仍保留。')})
    verify_selection(result)
    return freeze(target, result)
