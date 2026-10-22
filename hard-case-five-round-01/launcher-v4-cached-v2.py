"""Five rounds with full-file repair submissions and one bounded format correction."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
BUNDLE = HERE/'handoff'
SOURCE = HERE/'source'
ROUNDS = 5
ENVELOPE = None
RED_OUTPUT = 32768
BLUE_OUTPUT = 131072
COLLISION_RETRIES = 3
FORMAT_CORRECTIONS = 1
MAX_CALLS = (1 + COLLISION_RETRIES + 2 * (1 + FORMAT_CORRECTIONS)) * ROUNDS + 2*2*(ROUNDS+1)*(1 + FORMAT_CORRECTIONS)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_import():
    manifest = read(BUNDLE/'handoff_manifest.json')['files_sha256']
    for relative, digest in manifest.items():
        if sha(BUNDLE/relative) != digest:
            raise ValueError(f'delivered material changed: {relative}')
    code = read(BUNDLE/'plan/code_snapshot_manifest.json')['files_sha256']
    changes = read(HERE/'protocol_changes.json')['files_sha256']
    if set(changes) != {'experiments/loop_probes/continuous_loop.py', 'r3e/loop/red_continuous.py', 'r3e/loop/repo_blue.py', 'r3e/loop/env.py'}:
        raise ValueError('unexpected implementation overrides')
    for relative, digest in code.items():
        if sha(SOURCE/relative) != changes.get(relative, digest):
            raise ValueError(f'delivered implementation changed: {relative}')


def modules():
    verify_import()
    sys.path.insert(0, str(SOURCE))
    os.environ['R3E_TOKENIZER'] = str(BUNDLE/'tokenizer/tokenizer.json')
    from experiments.loop_probes import continuous_launch, continuous_loop, red907_launch, sequence_curriculum
    from r3e.loop.token_count import TokenCounter
    return continuous_launch, continuous_loop, red907_launch, sequence_curriculum, TokenCounter


def materials():
    data = read(BUNDLE/'materials/materials.json')
    root = BUNDLE/'materials'
    data['carriers'] = [dict(package=str(root/'package'), suite_freeze=str(root/'suite_freeze.json'),
                             evaluator_freeze=str(root/'evaluator_freeze.json'), evaluator_root=str(root))]
    for anchor in data['anchors']:
        anchor['task_dir'] = str(root/'reserved'/Path(anchor['task_dir']).name)
    return data


def budget(launch):
    result = deepcopy(launch.budget('sequence'))
    counts = {'red': ROUNDS * (1 + COLLISION_RETRIES), 'online': ROUNDS*(1+FORMAT_CORRECTIONS), 'reference': ROUNDS*(1+FORMAT_CORRECTIONS), 'anchor': 2*2*(ROUNDS+1)*(1+FORMAT_CORRECTIONS)}
    for row in result['rows']:
        row['calls'] = counts[row['role']]
        row['output_limit'] = RED_OUTPUT if row['role'] == 'red' else BLUE_OUTPUT
        row['maximum_local_input'] = 131072 - row['output_limit']
        row['maximum_allowed_provider_input'] = row['maximum_local_input'] * 105 // 100 + 128
        row['maximum_CNY'] = str(Decimal(row['calls'])*(
            row['maximum_allowed_provider_input']*2+row['output_limit']*8)/1_000_000)
    result['max_calls'] = sum(counts.values())
    result['maximum_CNY'] = str(sum(Decimal(row['maximum_CNY']) for row in result['rows']))
    result['spending_envelope_CNY'] = ENVELOPE
    result['scope'] = ('Conditional bound at the delivered historical tariff, not current pricing or an invoice. '
                       'Monetary stopping is disabled by explicit user instruction; request and usage limits remain.')
    return result


def override_identity():
    return {'version': 'prob003_round_count_override_v1', 'original_rounds': 3, 'rounds': ROUNDS,
            'original_plan_sha256': sha(BUNDLE/'plan/plan.json'),
            'entrypoint_sha256': sha(Path(__file__)), 'run_script_sha256': sha(HERE/'run.sh'),
            'scientific_change': 'five rounds; bounded exam collision retries; full-file repair; one format-only correction per repair; Red 32768, Blue 65536',
            'protocol_changes_sha256': sha(HERE/'protocol_changes.json'),
            'budget_change': 'monetary ceiling removed; 88-call bound includes 15 collision regenerations and 34 format corrections',
            'environment_change': 'local material paths, interpreter and tool identities refrozen'}


def check_scope(plan, launch):
    original = read(BUNDLE/'plan/plan.json')
    unchanged = ['slots_per_round', 'seed', 'carrier_mode', 'fixed_carrier_index', 'anchor_repeats',
                 'mechanism_focus', 'learning', 'retrieval',
                 'red_bank_tokens', 'tokenizer', 'path_policy']
    if any(plan[key] != original[key] for key in unchanged):
        raise ValueError('an unapproved protocol setting changed')
    expected_code = dict(read(BUNDLE/'plan/code_snapshot_manifest.json')['files_sha256'])
    expected_code.update(read(HERE/'protocol_changes.json')['files_sha256'])
    expected_blue = dict(original['blue_config'], output_reserve=BLUE_OUTPUT, format_corrections=FORMAT_CORRECTIONS)
    if (plan['red_output_tokens'] != RED_OUTPUT or plan['blue_config'] != expected_blue
            or plan['reserved_collision_retries'] != COLLISION_RETRIES or plan['rounds'] != ROUNDS or len(plan['carriers']) != 1 or len(plan['anchors']) != 2
            or plan['client_config'] != original['client_config']
            or plan['client_config'] != launch.client_identity()
            or plan['max_calls'] != MAX_CALLS or plan['cost_bound'] != budget(launch)
            or plan['spending_envelope_CNY'] != ENVELOPE
            or plan['five_round_override'] != override_identity()
            or plan['code'] != expected_code):
        raise ValueError('five-round scope, implementation or budget differs from the frozen protocol')
    if [Path(anchor['task_dir']).name for anchor in plan['anchors']] != ['eval_match_branch', 'eval_miss_branch']:
        raise ValueError('reserved tasks changed')


def check(directory):
    launch, loop, shared, curriculum, counter_type = modules()
    plan = shared.check_archive(directory, SOURCE)
    loop.validate_plan(plan)
    check_scope(plan, launch)
    counter = counter_type()
    if counter.identity != plan['tokenizer']:
        raise ValueError('tokenizer identity changed')
    if sha(directory/'launch.py') != sha(Path(__file__)):
        raise ValueError('frozen entrypoint changed')
    return plan, counter


def freeze(directory):
    launch, loop, shared, curriculum, counter_type = modules()
    if directory.exists():
        raise ValueError('fresh plan directory required')
    material = materials()
    plan = loop.make_plan(material['carriers'], material['anchors'], counter=counter_type(),
        client_config=launch.client_identity(), rounds=ROUNDS, slots_per_round=1, seed=700,
        carrier_mode='fixed', fixed_carrier_index=0, anchor_repeats=2,
        mechanism_focus=material['mechanism_focus'], red_output_tokens=RED_OUTPUT, reserved_collision_retries=COLLISION_RETRIES)
    plan.update(cost_bound=budget(launch), spending_envelope_CNY=ENVELOPE, launch_profile='sequence',
        five_round_override=override_identity(),
        authorization='offline preparation only; separate approval required before paid collection')
    check_scope(plan, launch)
    directory.mkdir(parents=True, exist_ok=False)
    for relative, digest in plan['code'].items():
        target = directory/'code_snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE/relative, target)
        if sha(target) != digest:
            raise ValueError('source changed during freeze')
    shutil.copy2(Path(__file__), directory/'launch.py')
    shared.save(directory/'plan.json', plan)
    shared.save(directory/'plan_hash.json', {'hash': loop.hash_payload(plan)})
    shared.save(directory/'code_snapshot_manifest.json', {'files_sha256': plan['code']})
    shared.save(directory/'budget.json', plan['cost_bound'])
    shared.save(directory/'launch_manifest.json', {'files_sha256': {'launch.py': sha(directory/'launch.py')}})
    files = ['plan.json', 'plan_hash.json', 'code_snapshot_manifest.json', 'budget.json', 'launch_manifest.json']
    shared.save(directory/'delivery_manifest.json', {'files_sha256': {name: sha(directory/name) for name in files}})
    check(directory)
    return plan


def smoke(out):
    launch, loop, shared, curriculum, counter_type = modules()
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    material = materials()
    clean = (Path(material['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
    fixtures = curriculum.training_edits(clean)
    fixtures.extend([[edit] for edit in fixtures[0]])
    anchor = (Path(material['anchors'][0]['task_dir'])/'public/repo/rtl/sequence.sv').read_text()
    proposals = iter([[{'find': clean, 'replace': anchor}], *fixtures])

    format_fixture_used = False

    def transport(**request):
        nonlocal format_fixture_used
        user = json.loads(request['messages'][-1]['content'])
        if 'carrier' in user:
            result = {'edits': next(proposals), 'violated_requirement': 'consume each bit once',
                      'spec_basis': 'non-overlapping six-bit groups'}
        else:
            current = user['files'][curriculum.PRIMARY]['content']
            if not format_fixture_used:
                format_fixture_used = True
                return _reply({'edits': [{'file': curriculum.PRIMARY, 'find': current, 'replace': clean}],
                               'edit': 'deliberate format failure in offline acceptance'}, 1)
            result = {'files': [{'file': curriculum.PRIMARY, 'content': clean}],
                      'edit': 'scripted fixture only; not model performance'}
        return _reply(result, 1)

    client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport, maximum_output_tokens=131072)
    plan = loop.make_plan(material['carriers'], material['anchors'], counter=counter_type(),
        client_config=client.config.public_identity, rounds=ROUNDS, mechanism_focus=material['mechanism_focus'],
        anchor_repeats=2, red_output_tokens=RED_OUTPUT, reserved_collision_retries=COLLISION_RETRIES)
    result = loop.collect(plan, out, client=BudgetedClient(client, max_calls=plan['max_calls']), counter=counter_type())
    curriculum.report(out)
    from experiments.loop_probes.continuous_audit import exposure_audit, source_audit
    exposure_audit(out)
    source_audit(out)
    return {**result, 'model_calls': 0, 'stand_in_only': True}


def launch_collection(args, plan, counter, collect, shared, allowed_systems):
    from r3e.loop.env import load_llm_env, ThinkingTransport, deepseek_balance
    if args.run_dir.exists():
        raise ValueError('fresh run directory required; no resume')
    env = load_llm_env(args.env_file, names=('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL'))
    if not env.get('DEEPSEEK_API_KEY'):
        raise ValueError('missing DEEPSEEK_API_KEY')
    if env.get('DEEPSEEK_BASE_URL', '').rstrip('/') not in ('https://api.deepseek.com', 'https://api.deepseek.com/v1'):
        raise ValueError('launch requires the official direct billing endpoint')
    balance = deepseek_balance(env)
    if not balance['is_available']:
        raise ValueError('provider account is unavailable')
    args.run_dir.mkdir(parents=True, exist_ok=False)
    transport = ThinkingTransport(env, key_name='DEEPSEEK_API_KEY', url_name='DEEPSEEK_BASE_URL',
        thinking='low', timeout_seconds=1500, failure_dir=args.run_dir/'unparseable',
        error_log=args.run_dir/'provider_errors.jsonl', response_log=args.run_dir/'provider_responses.jsonl')
    guard = shared.UsageGuard(transport, counter, args.run_dir, envelope=Decimal('Infinity'),
                             direct_only=True, allowed_systems=allowed_systems)
    client = shared.build_launch_client(env, plan, guard)
    shared.save(args.run_dir/'launch_identity.json', {
        'client': client.config.public_identity, 'max_calls': plan['max_calls'], 'balance_precheck': balance,
        'plan_hash': read(args.plan_dir/'plan_hash.json')['hash'],
        'snapshot_manifest_sha256': sha(args.plan_dir/'code_snapshot_manifest.json'),
        'launcher_sha256': sha(Path(__file__)), 'launch_manifest': read(args.plan_dir/'launch_manifest.json'),
        'input_usage_guard': 'stop above floor(counted * 1.05) + 128',
        'output_usage_guard': 'stop above the requested stage cap',
        'spending_envelope_CNY': None, 'monetary_stop_enabled': False,
        'allowed_system_hashes': {hashlib.sha256(system.encode()).hexdigest(): limit
                                  for system, limit in allowed_systems.items()},
        'implicit_resume': False})
    try:
        result = collect(plan, args.run_dir/'collection', client=client, counter=counter)
    except Exception as error:
        shared.save(args.run_dir/'launch_stop.json', {'error_type': type(error).__name__,
            'ledger_calls': client.total_calls, 'http_attempts': guard.calls, 'usage_stop': guard.stopped,
            'resume_allowed': False, 'diagnostics': getattr(error, 'diagnostics', {})})
        raise
    print(json.dumps({'status': result['status'], 'calls': client.total_calls,
                      'http_attempts': guard.calls, 'classification': 'separate offline step'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check', 'smoke', 'collect', 'report', 'audits', 'status'])
    parser.add_argument('--plan-dir', type=Path, default=HERE/'plan-v4')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.action != 'collect':
        def offline(event, values):
            if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
                raise RuntimeError('offline action: network disabled')
        sys.addaudithook(offline)
    args.plan_dir = args.plan_dir.resolve()
    if args.run_dir:
        args.run_dir = args.run_dir.resolve()
    if args.action == 'freeze':
        plan = freeze(args.plan_dir)
        print(json.dumps({'status': 'PASS', 'model_calls': 0, 'max_calls': plan['max_calls'],
            'conditional_full_context_CNY': plan['cost_bound']['maximum_CNY'], 'hard_spending_cap_CNY': ENVELOPE}))
        return
    if args.action == 'smoke':
        if args.run_dir is None:
            parser.error('smoke requires a fresh --run-dir')
        print(json.dumps(smoke(args.run_dir)))
        return
    if args.action == 'status':
        if args.run_dir is None:
            parser.error('status requires --run-dir')
        root = args.run_dir/'collection'
        print(json.dumps({'collection': read(root/'collection.json') if (root/'collection.json').exists() else None,
            'launch_stop': read(args.run_dir/'launch_stop.json') if (args.run_dir/'launch_stop.json').exists() else None,
            'usage_events': len((args.run_dir/'usage_guard.jsonl').read_text().splitlines())
                if (args.run_dir/'usage_guard.jsonl').exists() else 0,
            'report_available': (root/'report.json').exists()}))
        return
    plan, counter = check(args.plan_dir)
    if args.action == 'check':
        print(json.dumps({'status': 'PASS', 'model_calls': 0, 'max_calls': plan['max_calls'],
                          'hard_spending_cap_CNY': ENVELOPE}))
        return
    launch, loop, shared, curriculum, counter_type = modules()
    if args.run_dir is None:
        parser.error('action requires --run-dir')
    if args.action == 'collect':
        if args.env_file is None:
            parser.error('collect requires --env-file and separate spending approval')
        args.repo_root = SOURCE
        print(f'真实调用即将启动：最多{MAX_CALLS}次请求；撞考试题最多重出{COLLISION_RETRIES}次；无金额硬上限。', flush=True)

        def collect(plan, out, *, client, counter):
            client.on_call = lambda row: print(json.dumps({'event': 'request_finished',
                'phase': row.get('phase'), 'input_tokens': row.get('input_tokens'),
                'output_tokens': row.get('output_tokens')}), flush=True)
            return loop.collect(plan, out, client=client, counter=counter)

        launch_collection(args, plan, counter, collect, shared, allowed_systems={
            loop.red.SYSTEM: plan['red_output_tokens'], loop.rb.SYSTEM_REPAIR: BLUE_OUTPUT})
    elif args.action == 'report':
        print(json.dumps(curriculum.report(args.run_dir/'collection')))
    else:
        if read(args.run_dir/'collection/collection.json')['status'] != 'complete':
            raise ValueError('audits require complete collection; no evaluator during learning')
        if read(args.run_dir/'collection/plan.json') != plan:
            raise ValueError('collection differs from the selected frozen plan')
        from experiments.loop_probes.continuous_audit import exposure_audit, source_audit
        exposure_audit(args.run_dir/'collection')
        source_audit(args.run_dir/'collection')
        print('PASS: offline audits; no model calls')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'停止：{error}', file=sys.stderr)
        raise SystemExit(1)
