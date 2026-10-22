"""Fixed-split five-round pilot. No legacy state or automatic split merging."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / 'source'))

from r3e.knowledge import BugTypeInference, RepairEpisode
from r3e.loop.blue import BlueConfig, BlueRunner, first_attempt
from r3e.loop.budget import BudgetedClient, cost_from_calls
from r3e.loop.corpus import load_public_manifest, merge_clusters
from r3e.loop.env import build_client, load_llm_env
from r3e.loop.fakes import FakeBlueTransport, FakeRedTransport, nearest_clean_resolver
from r3e.loop.orchestrator import ClosedLoop, LoopConfig
from r3e.loop.memory_usage import usage_stats, track_record_view
from r3e.loop.qualification import QualificationConfig
from r3e.loop.red import RedProposal, has_logic_loop
from r3e.loop.sim import Simulator
from r3e.loop.state import RunState
from r3e.protocol.hashing import atomic_write_json, hash_payload
from r3e.protocol.ledger import read_ledger

ROLES = ('learning', 'qualification', 'holdout', 'guard')
SETTINGS = dict(rounds=5, proposals_per_round=4, max_candidates_per_round=2,
                budget_k=3, escalation_k=3, repeats=3, memory_from_attempt=2,
                max_calls=1300, max_output_tokens=131072, seed=7,
                output_caps={'red': 32768, 'blue_inference': 65536,
                             'escalation': 131072, 'qualification': 65536,
                             'evaluation': 65536},
                blue_thinking='low', red_thinking='low', max_infra_retries=0)


def read_json(path):
    return json.loads(Path(path).read_text())


def corpus():
    carriers, challenges, assets = {}, {}, {}
    for role in ROLES:
        path = HERE / 'manifests' / f'{role}.jsonl'
        rows = [json.loads(s) for s in path.read_text().splitlines()]
        carriers[role], challenges[role] = load_public_manifest(path, ROOT)
        if len(challenges[role]) != len(rows):
            raise ValueError(f'{role}: missing or ineligible assets')
        paths = [path]
        for row in rows:
            paths += [ROOT / row[k] for k in ('golden_rtl', 'buggy_rtl', 'spec', 'provenance') if row.get(k)]
            paths += [ROOT / p for k in ('tb_sources', 'deps') for p in row.get(k, [])]
        for p in paths:
            assets[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    clusters = merge_clusters([c for group in carriers.values() for c in group])
    owners = {}
    for role, group in carriers.items():
        for c in group:
            cluster = clusters[c.carrier_id]
            if cluster in owners and owners[cluster] != role:
                raise ValueError(f'design leakage: {owners[cluster]} / {role}')
            owners[cluster] = role
    for p in [HERE / 'pilot.py', HERE / 'run.sh', *sorted((HERE / 'source').rglob('*.py')),
              *sorted((HERE / 'source').rglob('*.txt'))]:
        assets[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return carriers, challenges, assets


def plan():
    carriers, cases, assets = corpus()
    return dict(schema='low-pass-pilot-v2-output-budget', settings=SETTINGS,
                core='isolated integrated-main snapshot; case-memory qualification',
                roles={r: [c.challenge_id for c in cases[r]] for r in ROLES},
                families={r: sorted({c.cluster_id for c in carriers[r]}) for r in ROLES},
                assets=assets, asset_hash=hash_payload(assets),
                caveats=['Prob003/Prob015 Red seeds are reconstructed, not historical artifacts.',
                         'Only visible-test correctness is scored; no full functional-correctness claim.',
                         'Holdout consists of two closely related designs in one family.',
                         'Qualification uses newer memory gate, not legacy run06 policy search.',
                         '1300 is a hard call cap, not planned consumption; no automatic cap increase.'])


def check():
    protocol = plan()
    _, cases, _ = corpus()
    results = []
    with tempfile.TemporaryDirectory(prefix='r3e-low-pass-check-') as tmp:
        sim = Simulator(Path(tmp))
        for role, group in cases.items():
            for ch in group:
                clean = sim.verdict(ch.carrier.clean_rtl, ch.carrier)
                buggy = sim.verdict(ch.buggy_rtl, ch.carrier)
                row = dict(role=role, case_id=ch.challenge_id, golden=clean.tier, buggy=buggy.tier,
                           passed=clean.visible_ok and buggy.tier == 'visible_fail')
                # This is an existing diagnostic bug, not a newly admitted Red mutant.
                if 'timing:Prob017' in ch.challenge_id:
                    row['has_logic_loop'] = has_logic_loop(ch.buggy_rtl, ch.carrier.top_module, Path(tmp)/'loop')
                    row['usage'] = 'qualification-only existing defect; never a Red-generated hit'
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    tools = {n: shutil.which(n) for n in ('iverilog', 'vvp', 'yosys')}
    versions = {}
    for name, arg in [('iverilog', '-V'), ('vvp', '-V'), ('yosys', '-V')]:
        out = subprocess.run([tools[name], arg], text=True, capture_output=True, timeout=10)
        versions[name] = (out.stdout or out.stderr).splitlines()[0]
    report = dict(ready=all(r['passed'] for r in results), model_calls=0,
                  asset_hash=protocol['asset_hash'], cases=results, tools=versions)
    atomic_write_json(HERE / 'preflight.json', report)
    atomic_write_json(HERE / 'protocol.json', protocol)
    print(json.dumps({'ready': report['ready'], 'model_calls': 0}))
    return 0 if report['ready'] else 1


class SeededRed:
    """Round 0 covers all fixed learning cases; later rounds replay two and generate two."""
    def __init__(self, original, learning):
        self.original = original
        self.learning = learning
        self.position = {}
        self.families = list({c.carrier.cluster_id: c.carrier for c in learning}.values())

    def propose(self, carrier, *, state, seed, round_index):
        i = self.position.get(round_index, 0)
        self.position[round_index] = i + 1
        if round_index == 0 or i < 2:
            j = i if round_index == 0 else ((round_index-1)*2+i) % len(self.learning)
            ch = self.learning[j]
            return RedProposal(dict(round=round_index, source='frozen_learning_seed',
                                    challenge_id=ch.challenge_id, buggy_hash=ch.buggy_hash,
                                    origin=dict(ch.provenance), historical_hit_claim=False), ch)
        selected = self.families[(round_index+i) % len(self.families)]
        return self.original.propose(selected, state=state, seed=seed, round_index=round_index)


def outcome(enc):
    return dict(solved=enc.solved_within_budget, inconclusive=enc.inconclusive,
                first=first_attempt(enc), attempts=len(enc.repair_attempts), record=enc.record())


def compare_guard(blue, state, cases, candidate, active, inference, round_index):
    rows = []
    for ch in cases:
        for rep in range(SETTINGS['repeats']):
            seed = 8009 + rep * 1009
            baseline = outcome(blue.run(ch, mode='matched', pool=active, inference=inference,
                                       matcher=state.matcher, seed=seed, allow_escalation=False,
                                       phase='qualification'))
            if baseline['inconclusive'] or baseline['first'] is None:
                rows.append(dict(case_id=ch.challenge_id, seed=seed, inconclusive=True))
                continue
            if baseline['first']['verdict_tier'] in ('visible_pass', 'hidden_pass', 'formal_pass'):
                candidate_run = baseline  # identical first attempt; memory cannot intervene
            else:
                candidate_run = outcome(blue.run(ch, mode='matched', pool=[*active, candidate],
                    inference=inference, matcher=state.matcher, seed=seed, allow_escalation=False,
                    phase='qualification', reuse_first=baseline['first']))
            rows.append(dict(case_id=ch.challenge_id, seed=seed,
                inconclusive=candidate_run['inconclusive'],
                baseline=baseline['solved'], candidate=candidate_run['solved'],
                regressed=baseline['solved'] and not candidate_run['solved']))
    report = dict(round=round_index, candidate=candidate.item_id, pairs=rows,
                  passed=all(not r.get('inconclusive') and not r.get('regressed') for r in rows))
    atomic_write_json(state.root / 'guards' / f'R{round_index}_{candidate.item_id}_v{candidate.version}.json', report)
    return report


def evaluate(state, blue, cases):
    """Post-chain, paired S0 vs each round, cached by encounter; no learning or escalation."""
    if state.checkpoint().get('completed_rounds') != SETTINGS['rounds']:
        raise ValueError('holdout refused before five completed rounds')
    blue.population_sink = None
    baseline = {}
    result = {'source_kind': read_json(state.root/'binding.json')['mode'],
              'metric': 'visible_test_solve_rate_within_3_attempts', 'snapshots': []}

    def cached(path, fn):
        if path.exists():
            return read_json(path)
        data = outcome(fn())
        atomic_write_json(path, data)
        return data

    for ch in cases:
        for rep in range(SETTINGS['repeats']):
            seed = 7001 + 1009*rep
            key = (ch.challenge_id, rep)
            path = state.root/'eval-cache'/f'baseline_{hash_payload(key)[7:23]}.json'
            baseline[key] = cached(path, lambda: blue.run(ch, mode='none', pool=[],
                inference=BugTypeInference(), matcher=state.matcher, seed=seed,
                allow_escalation=False, phase='evaluation'))
    for snap in state.read('rounds'):
        history = SimpleNamespace(read=lambda name: [r for r in state.read(name) if r['round'] <= snap['round']])
        tracks = {k: track_record_view(v) for k, v in usage_stats(history).items()}
        blue.track_records = lambda tracks=tracks: tracks
        pool = state.items_by_key((a[0], a[1]) for a in snap['active'])
        episodes = [RepairEpisode(r['episode']) for r in state.read('episodes') if r['round'] <= snap['round']]
        inference = BugTypeInference().fit(episodes)
        pairs = []
        for ch in cases:
            for rep in range(SETTINGS['repeats']):
                b = baseline[(ch.challenge_id, rep)]
                seed = 7001 + 1009*rep
                reason = None
                if b['inconclusive'] or not b['first']:
                    pairs.append(dict(case_id=ch.challenge_id, rep=rep, inconclusive=True))
                    continue
                if not pool:
                    evolved, reason = b, 'identical_empty_memory_system'
                elif b['first']['verdict_tier'] in ('visible_pass', 'hidden_pass', 'formal_pass'):
                    evolved, reason = b, 'shared_first_attempt_pass'
                else:
                    path = state.root/'eval-cache'/f"R{snap['round']}_{hash_payload((ch.challenge_id,rep))[7:23]}.json"
                    evolved = cached(path, lambda: blue.run(ch, mode='matched', pool=pool,
                        inference=inference, matcher=state.matcher, seed=seed, allow_escalation=False,
                        phase='evaluation', reuse_first=b['first']))
                pairs.append(dict(case_id=ch.challenge_id, rep=rep, baseline=b['solved'],
                                  evolved=evolved['solved'], inconclusive=evolved['inconclusive'],
                                  reuse_reason=reason))
        valid = [p for p in pairs if not p['inconclusive']]
        result['snapshots'].append(dict(round=snap['round']+1, active_items=len(pool), pairs=pairs,
            planned_pairs=len(cases)*SETTINGS['repeats'], valid_pairs=len(valid),
            baseline_rate=sum(p['baseline'] for p in valid)/len(valid) if valid else None,
            evolved_rate=sum(p['evolved'] for p in valid)/len(valid) if valid else None,
            gained=sum(p['evolved'] and not p['baseline'] for p in valid),
            lost=sum(p['baseline'] and not p['evolved'] for p in valid)))
    result['cost'] = cost_from_calls(state.read('calls'))
    atomic_write_json(state.root/'comparison.json', result)
    return result


def run(path, fake, env_file=None):
    protocol = plan()
    preflight = read_json(HERE/'preflight.json')
    if not preflight['ready'] or preflight['asset_hash'] != protocol['asset_hash']:
        raise ValueError('请先执行 check，输入文件或代码有变更')
    carriers, cases, _ = corpus()
    if fake:
        blue_fake = FakeBlueTransport(nearest_clean_resolver([c.clean_rtl for v in carriers.values() for c in v]),
                                      succeed=lambda user, n: n >= 1)
        red_fake = FakeRedTransport()
        def transport(**request):
            payload = json.loads(request['messages'][-1]['content'])
            return (blue_fake if 'current_buggy_rtl' in payload else red_fake)(**request)
        client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport,
                              maximum_output_tokens=SETTINGS['max_output_tokens'])
        red_client = client
        endpoint = 'fake-local'
    else:
        env = load_llm_env(env_file) if env_file else {}
        for dest, legacy in [('DEEPSEEK_API_KEY','R3E_PILOT_API_KEY'),
                             ('DEEPSEEK_BASE_URL','R3E_PILOT_BASE_URL'), ('DEEPSEEK_MODEL','R3E_PILOT_MODEL')]:
            env.setdefault(dest, os.environ.get(dest) or os.environ.get(legacy) or '')
        env['DEEPSEEK_BASE_URL'] = env['DEEPSEEK_BASE_URL'] or 'https://api.deepseek.com'
        env['DEEPSEEK_MODEL'] = env['DEEPSEEK_MODEL'] or 'deepseek-flash'
        if not env['DEEPSEEK_API_KEY']:
            raise ValueError('缺少 API 密钥；请在终端用 bash low-pass-pilot-02/run.sh start 安全输入')
        endpoint = hash_payload(env['DEEPSEEK_BASE_URL'])
        client = build_client(env, maximum_output_tokens=SETTINGS['max_output_tokens'],
                              thinking='low', timeout_seconds=1500)
        red_client = build_client(env, maximum_output_tokens=SETTINGS['output_caps']['red'],
                                  thinking='low', timeout_seconds=1500)
    binding = dict(asset_hash=protocol['asset_hash'], settings=SETTINGS,
                   mode='fake' if fake else 'live_model', model=client.config.model_id,
                   endpoint_hash=endpoint, tools=preflight['tools'])
    path.mkdir(parents=True, exist_ok=True)
    with (path/'.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (path/'binding.json').exists():
            if read_json(path/'binding.json') != binding:
                raise ValueError('禁止混用模型、配置、源码、数据或 fake/real 状态')
        elif any(path.glob('*.jsonl')):
            raise ValueError('不是本入口初始化的状态目录')
        else:
            atomic_write_json(path/'binding.json', binding)
        if (path/'inflight.json').exists():
            raise ValueError('上次在轮次中断；已保留全部记录，需检查后恢复，拒绝静默重跑或复用半轮记忆')
        state = RunState(path)
        budget = BudgetedClient(client, max_calls=SETTINGS['max_calls'])
        for row in state.read('calls'):
            budget.calls[row['phase']] += 1
            budget.tokens[row['phase']]['input'] += row.get('input_tokens', 0)
            budget.tokens[row['phase']]['output'] += row.get('output_tokens', 0)
        budget.on_call = lambda row: state.append('calls', row)
        budget.output_caps = dict(SETTINGS['output_caps'])
        red_budget = budget.sibling(red_client)
        sim = Simulator(path/'simulation')
        # Avoid reusing simulation output filenames after a restart.
        import itertools
        last = [int(p.name[4:]) for p in sim.workspace.glob('run_*') if p.name[4:].isdigit()]
        sim._counter = itertools.count(max(last, default=-1)+1)
        cfg = LoopConfig(rounds=5, proposals_per_round=4, seed=7, max_candidates_per_round=2,
            frozen_mutants_per_carrier=0,
            blue=BlueConfig(budget_k=3, escalation_k=3, memory_from_attempt=2, max_infra_retries=0),
            qualification=QualificationConfig(repeats=3, max_cases=4, seed=7))
        blue = BlueRunner(json_client=budget, simulator=sim, project_root=ROOT, config=cfg.blue)
        guard = lambda candidate, active, inference, r: compare_guard(blue, state, cases['guard'], candidate, active, inference, r)
        loop = ClosedLoop(config=cfg, state=state,
            splits={'discovery':carriers['learning'], 'qualification':carriers['qualification'], 'holdout':carriers['holdout']},
            public_challenges=cases['learning'], qualification_challenges=cases['qualification'],
            blue=blue, red_client=red_budget, simulator=sim, promotion_guard=guard)
        loop.red = SeededRed(loop.red, cases['learning'])
        for r in range(state.checkpoint().get('completed_rounds', 0), 5):
            atomic_write_json(path/'inflight.json', {'round':r})
            loop._round = r
            print(json.dumps({'round_started':r+1,'calls':budget.total_calls}), flush=True)
            summary = loop.round(r)
            state.save_checkpoint({'completed_rounds':r+1, 'frozen_hash':loop.frozen_hash})
            (path/'inflight.json').unlink()
            print(json.dumps({'round_completed':r+1, 'admitted':summary['admitted'],
                              'decisions':summary['decisions'],'active_items':len(summary['active']),
                              'calls':budget.total_calls}), flush=True)
        result = evaluate(state, blue, cases['holdout'])
        print(json.dumps({'completed':True, 'source_kind':binding['mode'],
                          'comparison':str(path/'comparison.json'), 'final':result['snapshots'][-1]}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan','check','smoke','start','status'])
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--llm-env', type=Path)
    args = parser.parse_args()
    if args.command in ('plan','check','smoke'):
        def deny_network(event, values):
            if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):
                raise RuntimeError('offline command: network disabled')
        sys.addaudithook(deny_network)
    if args.command == 'plan':
        p = plan(); p.pop('assets')
        print(json.dumps(p, ensure_ascii=False, indent=2)); return 0
    if args.command == 'check':
        return check()
    path = (args.state_dir or HERE / ('smoke-state' if args.command == 'smoke' else 'real-state')).resolve()
    if args.command == 'status':
        calls = read_ledger(path/'calls.jsonl')
        print(json.dumps(dict(initialized=(path/'binding.json').exists(),
            checkpoint=read_json(path/'checkpoint.json') if (path/'checkpoint.json').exists() else None,
            interrupted_round=(path/'inflight.json').exists(), cost=cost_from_calls(calls),
            completed=(path/'comparison.json').exists()), ensure_ascii=False, indent=2))
        return 0
    return run(path, args.command == 'smoke', args.llm_env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'停止：{exc}', file=sys.stderr)
        raise SystemExit(1)
