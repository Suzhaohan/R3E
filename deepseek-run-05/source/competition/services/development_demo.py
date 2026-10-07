"""Two fixed development comparisons; never part of heldout selection."""
from pathlib import Path
from competition.arena.baseline import load_runtime
from competition.arena.cli import _client
from competition.arena.budget import BudgetedClient
from competition.arena.evidence import read, signed
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.experience_memory import bank, initial_bank, ExperienceMemory, snapshot
from competition.services.balanced_final import selected_policy
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.protocol.hashing import atomic_write_json
from r3e.policy.schema import PolicyState


def run(root, state, args, phase, *, raw_client=None):
    root,state=Path(root),Path(state)
    runtime,machine,baseline=load_runtime(state)
    raw=raw_client or _client(args.client_config)
    client=BudgetedClient(raw,state/'budgets'/f'DEMO-{phase}.json',max_calls=args.max_calls,max_tokens=args.max_tokens)
    client=BudgetedClient(client,state/'budgets/total.json',max_calls=args.max_calls,max_tokens=args.max_tokens)
    policy=selected_policy(state,runtime) if phase=='final' else PolicyState.from_dict(baseline['policy'])
    memory=bank([])
    if machine['arm']=='adversarial':
        memory=initial_bank(root) if phase=='preview' else snapshot(root,state,'T1',evolving=True)
    provider=PolicyCandidateProvider(client,memory=ExperienceMemory(memory),
        verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version,adapter_version='m3-policy-v1')
    service=ArenaEvaluationService(root,state/'replays',provider=provider)
    cases={r['case_id']:r for r in read(root/'competition/manifests/demo32_supplied_assets.json')['rows']}
    rows=[]
    for case in baseline['balanced_plan']['demo_cases']:
        for seed in baseline['seeds']:
            receipt=service.evaluate_case_cached(policy,cases[case],seed,cache_root=state/'demo_cache'/phase)
            rows.append({'case_id':case,'seed':seed,'oracle_ok':receipt['oracle_ok'],'receipt_hash':receipt['receipt_hash']})
            atomic_write_json(state/f'demo_{phase}.json',signed({'rows':rows,'phase':phase,
                'policy_hash':policy.policy_hash,'memory_hash':memory['result_hash'],
                'label':'开发预览，未经完整防退化' if phase=='preview' else '最终版本的开发题演示，不计入留出成绩'}))
    return rows
