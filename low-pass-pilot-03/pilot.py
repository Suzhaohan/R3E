"""Five-round practice on low-pass cases, followed by a separate final exam."""
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
from r3e.loop.prob003_handoff import (
    BENCHMARK, EVAL_IDS, SEED_ID, Prob003Simulator, ReservedRedAgent,
    normalized_rtl, qualification as qualify_prob003, run_suite, verify_materials,
)
from r3e.loop.red import RedProposal, has_logic_loop
from r3e.loop.sim import Simulator
from r3e.loop.state import RunState
from r3e.protocol.hashing import atomic_write_json, hash_payload
from r3e.protocol.ledger import read_ledger

ROLES = ('learning', 'qualification', 'holdout', 'guard', 'prob003_eval')
PROB003 = HERE / 'materials/prob003'
SETTINGS = dict(rounds=5, proposals_per_round=7, max_candidates_per_round=4,
                budget_k=3, escalation_k=3, repeats=3, memory_from_attempt=2,
                max_calls=1300, max_output_tokens=131072, seed=7,
                output_caps={'red': 32768, 'blue_inference': 65536,
                             'escalation': 131072, 'qualification': 65536,
                             'evaluation': 65536, 'confirmation': 65536},
                blue_thinking='low', red_thinking='low', max_infra_retries=0)


def read_json(path):
    return json.loads(Path(path).read_text())


def corpus():
    carriers, challenges, assets = {}, {}, {}
    verify_materials(PROB003, read_json(PROB003/'handoff_manifest.json'))
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
    validate_split(carriers, challenges)
    for p in [HERE / 'pilot.py', HERE / 'run.sh', HERE/'selection.json', ROOT/'datasets/low_pass_rate_rtl_cases/chipbench8.jsonl',
              *sorted(p for p in PROB003.rglob('*') if p.is_file()),
              *sorted((HERE / 'source').rglob('*.py')),
              *sorted((HERE / 'source').rglob('*.txt'))]:
        assets[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return carriers, challenges, assets


def validate_split(carriers, challenges):
    # Practice and promotion intentionally use the same front-of-course cases.
    # The exam measures transfer to different tasks, including related designs;
    # it does NOT claim independence between broad circuit families.
    ids = {r: {c.challenge_id for c in challenges[r]} for r in ROLES}
    if ids['learning'] != ids['qualification']:
        raise ValueError('晋升必须使用五轮练习题，不能换回另一组容易题')
    if ids['learning'] & ids['holdout']:
        raise ValueError('考试题混入五轮练习')
    if ids['prob003_eval'] != EVAL_IDS:
        raise ValueError('Prob003 保留评估变体必须保持两题')
    if ids['prob003_eval'] & set.union(*(ids[role] for role in ROLES if role != 'prob003_eval')):
        raise ValueError('Prob003 保留评估题混入其他分区')
    seed = next((ch for ch in challenges['learning'] if ch.challenge_id == SEED_ID), None)
    if seed is None:
        raise ValueError('缺少交接包 Prob003 训练种子')
    reserved = {normalized_rtl(ch.buggy_rtl) for ch in challenges['prob003_eval']}
    if len(reserved) != 2 or any(normalized_rtl(ch.buggy_rtl) in reserved for ch in challenges['learning']):
        raise ValueError('Prob003 保留缺陷与练习重复')
    if any(ch.carrier.source.get('benchmark') != BENCHMARK or
           ch.carrier.clean_rtl != seed.carrier.clean_rtl for ch in challenges['prob003_eval']):
        raise ValueError('Prob003 保留题必须属于交接包的同一设计')
    front_hashes = {hash_payload(c.clean_rtl) for c in carriers['learning']}
    if any(hash_payload(c.clean_rtl) in front_hashes for c in carriers['holdout']):
        raise ValueError('考试与练习含同一份正确 RTL')
    expected = {json.loads(s)['case_id'] for s in
                (ROOT/'datasets/low_pass_rate_rtl_cases/chipbench8.jsonl').read_text().splitlines()}
    excluded = set(read_json(HERE/'selection.json')['excluded_case_ids'])
    if excluded != {'chipbench:assignment:Prob017_arbitrary_fractional_frequency_division',
                    'chipbench:arithmetic:Prob017_arbitrary_fractional_frequency_division'}:
        raise ValueError('排除题目必须与 02 结果支持的冻结选题一致')
    if excluded & set.union(*ids.values()):
        raise ValueError('排除题目仍在活动分区中')
    if not expected <= ids['learning'] | ids['holdout'] | excluded:
        raise ValueError('Low Pass Rate 清单的可运行 ChipBench 题未充分分配')


def plan():
    carriers, cases, assets = corpus()
    return dict(schema='low-pass-pilot-v3-prob003-focused-exam', settings=SETTINGS,
                core='low-pass practice replay and same-task promotion; held-out-task exam',
                roles={r: [c.challenge_id for c in cases[r]] for r in ROLES},
                families={r: sorted({c.cluster_id for c in carriers[r]}) for r in ROLES},
                assets=assets, asset_hash=hash_payload(assets),
                primary_evaluation_group='original_exam',
                historical_selection=read_json(HERE/'selection.json'),
                prob003_handoff=dict(source_commit=read_json(PROB003/'delivery_status.json')['github_main'],
                    historical_seed=SEED_ID, reserved_variants=sorted(EVAL_IDS),
                    supplementary_usage='offline qualification and post-collection audit only'),
                caveats=['Prob003 uses delivered historical RTL; Prob015 remains reconstructed.',
                         'Prob003 reserved variants measure new bugs on a practiced design; report separately from the original exam.',
                         'Prob003 uses a prospective timing contract and new tests; do not overwrite earlier pilot results.',
                         'Only visible-test correctness is scored; no full functional-correctness claim.',
                         'Practice and promotion share tasks, with different sampling seeds; promotion is practice retention, not unseen-task transfer.',
                         'Prob001 practice and Prob002 exam are related designs: near transfer, not independent-family generalization.',
                         'Exam tasks were observed in pilot-02; this is a revised development experiment, not a pristine benchmark.',
                         'Two saturated Prob017 variants are excluded using pilot-02 results; report the selected exam scope explicitly.',
                         'Calibration uses only practice cases and requires failures within the same three-attempt budget.',
                         'Ibex tasks lack a validated repository simulator here; Prob004 exact historical defect is unavailable.',
                         '1300 is a hard call cap, not planned consumption; no automatic cap increase.'])


def check():
    protocol = plan()
    _, cases, _ = corpus()
    results = []
    with tempfile.TemporaryDirectory(prefix='r3e-low-pass-check-') as tmp:
        sim = Prob003Simulator(Path(tmp)/'simulation')
        for role, group in cases.items():
            for ch in group:
                clean = sim.verdict(ch.carrier.clean_rtl, ch.carrier)
                buggy = sim.verdict(ch.buggy_rtl, ch.carrier)
                row = dict(role=role, case_id=ch.challenge_id, golden=clean.tier, buggy=buggy.tier,
                           passed=clean.visible_ok and buggy.tier == 'visible_fail')
                # This is an existing diagnostic bug, not a newly admitted Red mutant.
                if 'timing:Prob017' in ch.challenge_id:
                    row['has_logic_loop'] = has_logic_loop(ch.buggy_rtl, ch.carrier.top_module, Path(tmp)/'loop')
                    row['usage'] = 'existing diagnostic defect; never a Red-generated hit'
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        prob003_report = qualify_prob003(PROB003, Path(tmp)/'qualification')
    tools = {n: shutil.which(n) for n in ('iverilog', 'vvp', 'yosys')}
    versions = {}
    for name, arg in [('iverilog', '-V'), ('vvp', '-V'), ('yosys', '-V')]:
        out = subprocess.run([tools[name], arg], text=True, capture_output=True, timeout=10)
        versions[name] = (out.stdout or out.stderr).splitlines()[0]
    report = dict(ready=all(r['passed'] for r in results) and prob003_report['ready'], model_calls=0,
                  asset_hash=protocol['asset_hash'], cases=results, tools=versions,
                  prob003_qualification=prob003_report)
    atomic_write_json(HERE / 'preflight.json', report)
    atomic_write_json(HERE / 'protocol.json', protocol)
    print(json.dumps({'ready': report['ready'], 'model_calls': 0}))
    return 0 if report['ready'] else 1


class SeededRed:
    """Every round practices all five selected low-pass cases, then two new bugs."""
    def __init__(self, original, learning):
        self.original = original
        self.learning = learning
        self.position = {}
        self.families = list({c.carrier.cluster_id: c.carrier for c in learning}.values())

    def propose(self, carrier, *, state, seed, round_index):
        i = self.position.get(round_index, 0)
        self.position[round_index] = i + 1
        if i < len(self.learning):
            ch = self.learning[i]
            return RedProposal(dict(round=round_index, source='frozen_learning_seed',
                                    challenge_id=ch.challenge_id, buggy_hash=ch.buggy_hash,
                                    origin=dict(ch.provenance), historical_hit_claim=False), ch)
        selected = self.families[(round_index+i) % len(self.families)]
        return self.original.propose(selected, state=state, seed=seed, round_index=round_index)


def calibrate(state, blue, cases):
    """Measure actual no-memory difficulty on practice only, never on exam tasks."""
    rows = []
    for ch in cases:
        runs = []
        for rep in range(SETTINGS['repeats']):
            seed = 17011 + 1009 * rep
            path = state.root/'calibration-cache'/f'{hash_payload((ch.challenge_id, seed))[7:23]}.json'
            if path.exists():
                result = read_json(path)
            else:
                result = outcome(blue.run(ch, mode='none', pool=[],
                    inference=BugTypeInference(), matcher=state.matcher, seed=seed,
                    allow_escalation=False, phase='confirmation'))
                atomic_write_json(path, result)
            runs.append(dict(seed=seed, solved=result['solved'], inconclusive=result['inconclusive']))
            print(json.dumps(dict(calibration_case=ch.challenge_id, **runs[-1]), ensure_ascii=False), flush=True)
        valid = [r for r in runs if not r['inconclusive']]
        rows.append(dict(case_id=ch.challenge_id, runs=runs,
                         failures=sum(not r['solved'] for r in valid), valid=len(valid)))
    failures = sum(r['failures'] for r in rows)
    complete = all(r['valid'] == SETTINGS['repeats'] for r in rows)
    report = dict(cases=rows, no_memory_failures=failures, complete=complete,
                  ready=complete and failures >= 3,
                  scope='practice only; three repair attempts; no memory; no escalation')
    atomic_write_json(state.root/'calibration.json', report)
    if not report['ready']:
        raise ValueError('练习难度检查未通过：存在接口异常，或三次修复后失败不足3次。已保存记录，未启动五轮、未调用考试题。')
    order = {r['case_id']: r['failures'] for r in rows}
    return sorted(cases, key=lambda ch: (-order[ch.challenge_id], ch.challenge_id))


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
              'metric': 'visible_test_solve_rate_within_3_attempts',
              'comparison_scope': 'original exam and Prob003 seen-design variants reported separately',
              'historical_selection': read_json(HERE/'selection.json'),
              'primary_evaluation_group': 'original_exam', 'snapshots': []}

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
                    pairs.append(dict(case_id=ch.challenge_id, rep=rep, inconclusive=True,
                                      evaluation_group=evaluation_group(ch.challenge_id)))
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
                                  evaluation_group=evaluation_group(ch.challenge_id),
                                  memory_items=evolved['record'].get('shown_items', []) if reason is None else [],
                                  reuse_reason=reason))
        valid = [p for p in pairs if not p['inconclusive']]
        by_case = []
        for ch in cases:
            group = [p for p in valid if p['case_id'] == ch.challenge_id]
            by_case.append(dict(case_id=ch.challenge_id, valid=len(group),
                evaluation_group=evaluation_group(ch.challenge_id),
                baseline_solved=sum(p['baseline'] for p in group),
                with_memory_solved=sum(p['evolved'] for p in group),
                helped=sum(p['evolved'] and not p['baseline'] for p in group),
                harmed=sum(p['baseline'] and not p['evolved'] for p in group),
                memory_delivered=sum(bool(p['memory_items']) for p in group)))
        result['snapshots'].append(dict(round=snap['round']+1, active_items=len(pool), pairs=pairs, by_case=by_case,
            groups={name: paired_summary([pair for pair in pairs if pair['evaluation_group'] == name])
                    for name in ('original_exam', 'prob003_seen_design')},
            planned_pairs=len(cases)*SETTINGS['repeats'], valid_pairs=len(valid),
            baseline_rate=sum(p['baseline'] for p in valid)/len(valid) if valid else None,
            evolved_rate=sum(p['evolved'] for p in valid)/len(valid) if valid else None,
            gained=sum(p['evolved'] and not p['baseline'] for p in valid),
            lost=sum(p['baseline'] and not p['evolved'] for p in valid)))
    result['cost'] = cost_from_calls(state.read('calls'))
    atomic_write_json(state.root/'comparison.json', result)
    return result


def evaluation_group(case_id):
    return 'prob003_seen_design' if case_id in EVAL_IDS else 'original_exam'


def paired_summary(pairs):
    valid = [pair for pair in pairs if not pair['inconclusive']]
    return dict(planned_pairs=len(pairs), valid_pairs=len(valid),
        baseline_rate=sum(pair['baseline'] for pair in valid)/len(valid) if valid else None,
        evolved_rate=sum(pair['evolved'] for pair in valid)/len(valid) if valid else None,
        gained=sum(pair['evolved'] and not pair['baseline'] for pair in valid),
        lost=sum(pair['baseline'] and not pair['evolved'] for pair in valid))


def audit_prob003(state):
    if state.checkpoint().get('completed_rounds') != SETTINGS['rounds'] or not (state.root/'comparison.json').exists():
        raise ValueError('Prob003 补充评估只允许在五轮收集及最终公开评分结束后执行')
    artifacts = state.root/'prob003-artifacts'
    checks, encounters = {}, []
    with tempfile.TemporaryDirectory(prefix='r3e-prob003-post-') as workspace:
        for path in sorted((state.root/'eval-cache').glob('*.json')):
            encounter = read_json(path)
            case_id = encounter['record']['challenge_id']
            if case_id not in EVAL_IDS:
                continue
            attempts = encounter['record']['attempts']
            passing = next((attempt for attempt in attempts if attempt.get('verdict_tier') == 'visible_pass'), None)
            candidate_hash = passing.get('candidate_hash') if passing else None
            if candidate_hash and candidate_hash not in checks:
                candidate = artifacts/f'{candidate_hash[7:]}.sv'
                checks[candidate_hash] = (run_suite(candidate.read_text(), PROB003/'materials/evaluator/tb.sv',
                    Path(workspace)/candidate_hash[7:]) if candidate.exists()
                    else dict(result='error', log='candidate artifact missing'))
            encounters.append(dict(cache=path.name, case_id=case_id, public_solved=encounter['solved'],
                inconclusive=encounter['inconclusive'], candidate_hash=candidate_hash,
                supplementary_result=checks[candidate_hash]['result'] if candidate_hash else 'not_run'))
    comparison = read_json(state.root/'comparison.json')
    lookup = {row['cache']: row for row in encounters}
    snapshots = []
    for snapshot in comparison['snapshots']:
        pairs = []
        for pair in snapshot['pairs']:
            if pair['case_id'] not in EVAL_IDS:
                continue
            key = hash_payload((pair['case_id'], pair['rep']))[7:23]
            baseline = lookup.get(f'baseline_{key}.json')
            evolved = (baseline if pair.get('reuse_reason') else
                       lookup.get(f"R{snapshot['round']-1}_{key}.json"))
            unavailable = lambda row: row is None or row['inconclusive'] or row['supplementary_result'] == 'error'
            passed = lambda row: row['public_solved'] and row['supplementary_result'] == 'pass'
            pairs.append(dict(case_id=pair['case_id'], rep=pair['rep'],
                inconclusive=unavailable(baseline) or unavailable(evolved),
                baseline=passed(baseline) if baseline else False,
                evolved=passed(evolved) if evolved else False))
        snapshots.append(dict(round=snapshot['round'], pairs=pairs, **paired_summary(pairs)))
    _, cases, _ = corpus()
    reserved_hashes = {challenge.buggy_hash for challenge in cases['prob003_eval']}
    leaks = [row['episode']['case_id'] for row in state.read('episodes')
             if row['episode']['case_id'] in EVAL_IDS or row['episode']['buggy_rtl_hash'] in reserved_hashes]
    exposure = [dict(round=row['round'], challenge_id=row.get('challenge_id'),
                     edits=(row.get('chosen') or {}).get('edit_text', []))
                for row in state.read('red') if row.get('admitted') and
                row.get('carrier_id') in {ch.carrier.carrier_id for ch in cases['prob003_eval']}]
    report = dict(source_kind=comparison['source_kind'], model_calls=0, checks=checks,
        encounters=encounters, snapshots=snapshots, learning_leaks=leaks, training_edits=exposure,
        scope='new variants on the practiced Prob003 design; shared edit locations may be exposed')
    atomic_write_json(state.root/'prob003_audit.json', report)
    if leaks:
        raise ValueError('Prob003 保留评估题进入学习记录，见 prob003_audit.json')
    return report


def accumulation_check(state):
    rounds = state.read('rounds')
    if len(rounds) >= 2 and not state.active_items():
        report = dict(status='needs_attention', completed_rounds=len(rounds),
            reason='前两轮之后仍无有效经验，停止空跑；最终考试尚未调用。',
            decisions=[r['decisions'] for r in rounds])
        atomic_write_json(state.root/'needs_attention.json', report)
        raise ValueError(report['reason'])


def run(path, fake, env_file=None):
    protocol = plan()
    preflight = read_json(HERE/'preflight.json')
    if not preflight['ready'] or preflight['asset_hash'] != protocol['asset_hash']:
        raise ValueError('请先执行 check，输入文件或代码有变更')
    carriers, cases, _ = corpus()
    if fake:
        blue_fake = FakeBlueTransport(nearest_clean_resolver([c.clean_rtl for v in carriers.values() for c in v]),
                                      succeed=lambda user, n: n >= 3 or bool((user.get('reference_cases') or {}).get('items')))
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
            raise ValueError('缺少 API 密钥；请在终端用 bash low-pass-pilot-03/run.sh start 安全输入')
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
        sim = Prob003Simulator(path/'simulation')
        # Avoid reusing simulation output filenames after a restart.
        import itertools
        last = [int(p.name[4:]) for p in sim.workspace.glob('run_*') if p.name[4:].isdigit()]
        sim._counter = itertools.count(max(last, default=-1)+1)
        cfg = LoopConfig(rounds=SETTINGS['rounds'], proposals_per_round=SETTINGS['proposals_per_round'],
            seed=SETTINGS['seed'], max_candidates_per_round=SETTINGS['max_candidates_per_round'],
            frozen_mutants_per_carrier=0,
            blue=BlueConfig(budget_k=3, escalation_k=3, memory_from_attempt=2, max_infra_retries=0),
            qualification=QualificationConfig(repeats=3, max_cases=5, seed=27011))
        blue = BlueRunner(json_client=budget, simulator=sim, project_root=ROOT, config=cfg.blue)
        accumulation_check(state)
        qualification_cases = calibrate(state, blue, cases['qualification'])
        guard = lambda candidate, active, inference, r: compare_guard(blue, state, cases['guard'], candidate, active, inference, r)
        loop = ClosedLoop(config=cfg, state=state,
            splits={'discovery':carriers['learning'], 'qualification':carriers['qualification'], 'holdout':carriers['holdout']},
            public_challenges=cases['learning'], qualification_challenges=qualification_cases,
            blue=blue, red_client=red_budget, simulator=sim, promotion_guard=guard)
        red = ReservedRedAgent(reserved=cases['prob003_eval'], mode=cfg.red_mode,
            client=red_budget, simulator=sim, seed=cfg.seed)
        loop.red = SeededRed(red, cases['learning'])
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
            accumulation_check(state)
        result = evaluate(state, blue, [*cases['holdout'], *cases['prob003_eval']])
        audit_prob003(state)
        print(json.dumps({'completed':True, 'source_kind':binding['mode'],
                          'comparison':str(path/'comparison.json'), 'final':result['snapshots'][-1]}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan','check','smoke','start','status','audit'])
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--llm-env', type=Path)
    args = parser.parse_args()
    if args.command in ('plan','check','smoke','audit'):
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
    if args.command == 'audit':
        audit_prob003(RunState(path))
        print(json.dumps({'model_calls': 0, 'audit': str(path/'prob003_audit.json')}))
        return 0
    if args.command == 'status':
        calls = read_ledger(path/'calls.jsonl')
        print(json.dumps(dict(initialized=(path/'binding.json').exists(),
            checkpoint=read_json(path/'checkpoint.json') if (path/'checkpoint.json').exists() else None,
            round_in_progress=(path/'inflight.json').exists(), cost=cost_from_calls(calls),
            last_call=calls[-1].get('timestamp') if calls else None,
            calibration=read_json(path/'calibration.json') if (path/'calibration.json').exists() else None,
            needs_attention=read_json(path/'needs_attention.json') if (path/'needs_attention.json').exists() else None,
            completed=(path/'comparison.json').exists()), ensure_ascii=False, indent=2))
        return 0
    return run(path, args.command == 'smoke', args.llm_env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'停止：{exc}', file=sys.stderr)
        raise SystemExit(1)
