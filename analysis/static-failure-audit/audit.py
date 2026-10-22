"""Read existing static/no-memory records and replay saved RTL locally; no LLM calls."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT / 'prob003-five-round-03/source'))
from r3e.loop.icarus import simulate
from r3e.knowledge.feedback import compare_traces


def read(p):
    return json.loads(p.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def relative(p):
    return str(p.relative_to(ROOT))


records, seen, coverage = [], set(), Counter()


def add(row, key):
    identity = digest(key)
    if identity in seen:
        coverage['duplicate_observations_removed'] += 1
        return
    seen.add(identity)
    row['observation_id'] = identity
    records.append(row)


# Explicit static arms, proven disabled memory and declared real provider.
for root in sorted(ROOT.glob('deepseek-run-*')):
    arm = root / 'arm-a'
    if not (arm / 'memory.json').exists():
        continue
    memory = read(arm / 'memory.json')
    if memory.get('enabled') or memory.get('entries'):
        continue
    for p in sorted((arm / 'eval').glob('**/evaluation.json')):
        coverage['static_portfolio_files_read'] += 1
        x, receipt = read(p), read(p.parent / 'receipt.json')
        if receipt.get('source_kind') != 'live_model':
            coverage['non_live_portfolios_excluded'] += 1
            continue
        vs = x.get('candidate_verification_receipts', [])
        valid = [v for v in vs if v.get('parse_ok') and v.get('compile_ok') and v.get('scope_ok')]
        passed = bool(x.get('oracle_ok'))
        trace_results = []
        for candidate in vs:
            cell = p.parent / 'verifier' / candidate['candidate_id'] / 'oracle'
            golden_files = {f.name: f for f in (cell / 'golden').glob('*.txt')}
            candidate_files = {f.name: f for f in (cell / 'cand').glob('*.txt')}
            common = sorted(set(golden_files) & set(candidate_files))
            matched = None
            if common:
                matched = all(not compare_traces(golden_files[n].read_text(), candidate_files[n].read_text()).divergences for n in common)
            trace_results.append({'candidate_id': candidate['candidate_id'], 'scope_ok': candidate.get('scope_ok'),
                                  'saved_trace_matches': matched})
        trace_correct = sum(v['saved_trace_matches'] is True for v in trace_results)
        trace_failed = sum(v['saved_trace_matches'] is False for v in trace_results)
        category = ('pass' if passed else 'functionally_correct_but_rejected' if trace_correct else
                    'functional_failure' if trace_failed == len(vs) and trace_failed else
                    'scope_compile_or_unverified_failure')
        providers = x.get('candidate_provider_receipts', [])
        identity = [(q.get('raw_response_hash'), q.get('prompt_hash'), q.get('candidate_seed')) for q in providers]
        add(dict(case_id=x['case_id'], model=receipt.get('model_id'),
                 setting=digest([receipt.get('case_asset_hash'), receipt.get('budget_hash'), receipt.get('verifier_hash')]),
                 category=category, public_pass=passed, functional_failure=category == 'functional_failure',
                 role='explicit_static_arm', seed=x.get('seed'), candidates=len(vs),
                 valid_candidates=len(valid), source=relative(p),
                 candidate_saved_trace_checks=trace_results,
                 provenance='disabled arm-a memory + live_model receipt',
                 latest_run=root.name),
            ['portfolio', x['case_id'], receipt.get('case_asset_hash'), identity or x.get('portfolio_execution_hash')])

# Original serial-repair calibration and cached baselines. Episode hashes
# deduplicate the same baseline reused by several qualification comparisons.
for root in sorted(ROOT.glob('low-pass-pilot-*')):
    for run in sorted(root.glob('real*')):
        binding = read(run / 'binding.json') if (run / 'binding.json').exists() else {}
        if binding.get('mode') != 'live_model':
            continue
        sources = []
        for cache in sorted(run.glob('*cache')):
            if cache.is_dir():
                for p in sorted(cache.glob('*.json')):
                    x = read(p)
                    if isinstance(x, dict) and isinstance(x.get('record'), dict):
                        sources.append((p, x['record'], x))
        journal = run / 'encounters.jsonl'
        if journal.exists():
            for line in journal.read_text().splitlines():
                x = json.loads(line)
                if isinstance(x.get('encounter'), dict):
                    sources.append((journal, x['encounter'], {}))
        for p, x, wrapper in sources:
            coverage['serial_records_read'] += 1
            if (x.get('mode') != 'none' or x.get('inconclusive') or wrapper.get('inconclusive')
                    or x.get('accounting', {}).get('memory_delivered')
                    or any(d.get('injected') for d in x.get('deliveries', []))
                    or any(a.get('memory_offered') for a in x.get('attempts', []))):
                coverage['memory_or_inconclusive_serial_excluded'] += 1
                continue
            attempts = x.get('attempts', [])
            passed = bool(x.get('solved_within_budget', wrapper.get('solved')))
            last = attempts[-1].get('verdict_tier') if attempts else 'no_attempt'
            category = 'pass' if passed else 'functional_failure' if last == 'visible_fail' else last
            add(dict(case_id=x['challenge_id'], model=binding.get('model'),
                     setting=digest([binding.get('asset_hash'), binding.get('settings'), p.parent.name]),
                     category=category, public_pass=passed, functional_failure=category == 'functional_failure',
                     role='verified_no_memory_serial', attempts=len(attempts),
                     first_attempt=attempts[0].get('verdict_tier') if attempts else None,
                     provider_failures=x.get('accounting', {}).get('provider_failures', 0),
                     source=relative(p), episode_hash=x.get('episode_hash'), latest_run=root.name),
                ['serial', x.get('episode_hash') or digest(x)])

# Recent repository-repair runs: explicitly frozen B0/reference only. Keep
# public and post-run evaluator outcomes separate, without counting format or
# infrastructure failures as functional failures.
for root in sorted([*ROOT.glob('prob003-five-round-*'), *ROOT.glob('hard-case-five-round-*')]):
    for p in sorted(root.glob('**/collection/plan.json')):
        if any(part in {'source', 'handoff', 'code_snapshot', 'superseded-directed-flow'} or part.startswith('smoke') for part in p.parts):
            continue
        plan = read(p)
        model = plan.get('client_config', {}).get('model_id', '')
        if not model or model.startswith('fake'):
            continue
        directory = p.parent
        classifications = {}
        if (directory / 'report.json').exists():
            report = read(directory / 'report.json')
            for row in report['online_and_frozen_reference']:
                classifications[f'rounds/{row["round"]}/{row["slot_id"]}/reference'] = row.get('reference', {})
            for row in report['probes']:
                if row['snapshot'] == 0:
                    name = f'b0_a{row["anchor_index"]}_repeat{row["repeat"]}'
                    classifications['anchors/' + name] = row['endpoint']
        for trial, grade in classifications.items():
            f = directory / trial / 'blue/encounters.jsonl'
            if not f.exists():
                continue
            coverage['repository_static_records_read'] += 1
            raw = json.loads(f.read_text().splitlines()[0])
            x = raw['result']
            delivery = read(directory / trial / 'delivery.json')
            if delivery['payload']['entries']:
                continue
            attempts = x['attempts']
            category = grade.get('category', 'unclassified')
            passed = category == 'public_pass_hidden_pass'
            functional = category in {'public_pass_hidden_fail', 'public_functional_failure'}
            if trial.startswith('anchors/'):
                index = int(trial.split('_a')[1].split('_')[0])
                task = Path(plan['anchors'][index]['task_dir'])
            else:
                task = directory / Path(trial).parent / 'admission/blue_task'
            public = read(task / 'public/task.json')
            add(dict(case_id=x['task_id'], model=model,
                     setting=digest([delivery['task_hash'], plan['blue_config'], plan['identities']]),
                     category='pass' if passed else 'functional_failure' if functional else category,
                     raw_category=category, public_pass=x['outcome'] == 'fixed',
                     functional_failure=functional, role='frozen_B0_or_reference', seed=raw['seed'],
                     attempts=len(attempts), calls=x['calls'], source=relative(f),
                     task_dir=str(task), original_primary=str(task / 'public' / public['source_root'] / public['editable'][0]),
                     reference_primary=str(task / 'oracle/clean' / public['editable'][0]),
                     latest_run=root.name),
                ['repo', delivery['task_hash'], raw['seed'], [a.get('candidate_hash') for a in attempts], relative(directory)])

groups = defaultdict(list)
for row in records:
    groups[(row['case_id'], row['model'], row['setting'])].append(row)
summaries = []
for (case, model, setting), rows in groups.items():
    categories = Counter(r['category'] for r in rows)
    summaries.append(dict(case_id=case, model=model, setting=setting, observations=len(rows),
                          passed=categories['pass'], functional_failures=categories['functional_failure'],
                          other_failures=len(rows)-categories['pass']-categories['functional_failure'],
                          categories=dict(categories), sources=sorted({r['source'] for r in rows}),
                          observation_ids=[r['observation_id'] for r in rows]))
summaries.sort(key=lambda x: (x['passed'] / x['observations'], -x['functional_failures'], -x['observations'], x['case_id']))

# Re-run the two unambiguously failed original portfolios and their stored
# candidate RTL, using original files/oracle; this is all local simulation.
replay = []
base = ROOT / 'deepseek-run-01/source'
manifest = read(base / 'competition/manifests/strider14_sealed.json')['rows']
for case_id in ('strider:fsm_full_3', 'strider:mux_4_1_2', 'strider:first_counter_overflow_2'):
    row = next(r for r in manifest if r['case_id'] == case_id)
    case_dir = OUT / 'selected_originals' / case_id.split(':')[1]
    case_dir.mkdir(parents=True, exist_ok=True)
    for f in row['files']:
        source = base / f['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != f['sha256']:
            raise ValueError('original benchmark asset hash differs')
        (case_dir / Path(f['path']).name).write_bytes(source.read_bytes())
    oracle = (base / row['oracle_path']).read_text()
    variants = [('golden', (base / row['golden_rtl']).read_text(), None),
                ('buggy', (base / row['buggy_rtl']).read_text(), None)]
    for record in records:
        if record['case_id'] != case_id or not record['source'].startswith('deepseek-run-01/'):
            continue
        evaluation = read(ROOT / record['source'])
        for i, provider in enumerate(evaluation['candidate_provider_receipts']):
            variants.append((f'seed{evaluation["seed"]}_candidate{i}', provider['patch_payload']['replacement_rtl'], record['source']))
    result = dict(case_id=case_id, original_manifest=relative(base / 'competition/manifests/strider14_sealed.json'),
                  variants=[], model_calls=0)
    with tempfile.TemporaryDirectory(prefix='saved-static-replay-') as tmp:
        for name, rtl, provenance in variants:
            dut = Path(tmp) / 'dut' / 'saved.v'
            dut.parent.mkdir(exist_ok=True)
            dut.write_text(rtl)
            text, error = simulate([dut], [base / f for f in row['testbench_files']],
                                    row['metadata']['sim_output'], Path(tmp) / name, 20)
            passed = text is not None and not compare_traces(oracle, text).divergences
            result['variants'].append(dict(name=name, passed=passed, compiled_and_ran=text is not None,
                                            error=error, source=provenance))
    result['recommended_functional_failure_candidate'] = (
        result['variants'][0]['passed'] and not result['variants'][1]['passed']
        and not any(v['passed'] for v in result['variants'][2:])
        and len(result['variants'][2:]) == 9)
    replay.append(result)
    (case_dir / 'replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))

(OUT / 'records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
(OUT / 'summary.json').write_text(json.dumps(dict(coverage=dict(coverage), distinct_observations=len(records),
    settings=len(summaries), summaries=summaries, offline_replays=replay, model_calls=0,
    notes=['Only explicit disabled static arms or verified no-memory episodes were retained.',
           'Copied receipts / reused episode observations are deduplicated; settings are never pooled.',
           'Old model identities and budgets do not establish current failure probabilities.',
           'Portfolio source_kind=live_model is recorded provenance, not a fresh provider attestation.',
           'Scope/compile/format/provider errors are not counted as functional failures.']), ensure_ascii=False, indent=2))
(OUT / 'selected_candidates.json').write_text(json.dumps(dict(
    candidates=[{'case_id': r['case_id'], 'historical_static_passed': 0, 'historical_static_runs': 3,
                 'stored_candidates_replayed': 9, 'stored_candidate_functional_passes': 0,
                 'material_dir': str(OUT / 'selected_originals' / r['case_id'].split(':')[1]),
                 'reference_passed': True, 'original_defect_failed': True,
                 'model': 'deepseek-flash', 'status': 'historical_failure_verified_not_current_probability'}
                for r in replay if r['recommended_functional_failure_candidate']],
    latest_configuration_failures=[r for r in summaries if r['model'] == 'deepseek-v4-flash' and r['passed'] == 0 and r['functional_failures'] >= 2],
    rejected_after_replay=[r['case_id'] for r in replay if not r['recommended_functional_failure_candidate']],
    model_calls=0), ensure_ascii=False, indent=2))
lines = ['# 已有静态失败记录核查', '', f'去重后 {len(records)} 份无经验观察，分为 {len(summaries)} 个题目/模型/检查设置组合。新增模型调用：0。', '',
         '这是对已有失败证据的盘点，不是当前配置下的难度承诺。所有不同设置分别统计，不把重复缓存当独立样本。', '',
         '## 已离线重放的候选', '', '| 原题 | 原静态成绩 | 保存候选重放 | 参考答案 / 原缺陷 |', '|---|---:|---|---|']
for r in replay:
    candidates = r['variants'][2:]
    lines.append(f'| {r["case_id"]} | 原账本记为 0/3 | {sum(v["passed"] for v in candidates)}/{len(candidates)} 个候选功能通过 | 参考通过，原缺陷失败 |')
lines += ['', '## 各设置中的功能失败证据', '', '| 题目 | 模型 | 通过 / 观察数 | 功能失败 | 其他失败 | 证据文件 |', '|---|---|---:|---:|---:|---|']
for r in summaries:
    if r['functional_failures'] and r['passed'] / r['observations'] <= .5:
        source = r['sources'][0]
        lines.append(f'| {r["case_id"]} | {r["model"]} | {r["passed"]}/{r["observations"]} | {r["functional_failures"]} | {r["other_failures"]} | `{source}` |')
lines += ['', '机器可读完整证据：`summary.json`、`records.jsonl`。两个重放候选的原始材料位于 `selected_originals/`；不修改运行代码、冻结题单或既有成绩。',
          '', '原始 oracle_ok=false 不直接当成功能失败：逐候选比较保存的 golden/cand 轨迹，发现正确轨迹但仍被旧范围规则拒绝的，单列 functionally_correct_but_rejected。不能因为账本零通过就推荐为功能难题。',
          '', 'fsm_full_3 重放有一个完整文件答案通过功能测试，但原记录 scope_ok=false；因此它不再列为纯功能 0/3 的首选。mux_4_1_2 和 first_counter_overflow_2 的原候选重放结果见上表。推荐名单为 selected_candidates.json，只接受九个候选均失败且参考答案通过的候选。',
          '', '这些题已有结果被查看，后续可作为开发/定向验证题，不能再宣称是未见留出集。']
(OUT / 'REPORT.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(dict(coverage=dict(coverage), observations=len(records), settings=len(summaries),
                     replay=[{'case_id':r['case_id'], 'golden_pass':r['variants'][0]['passed'],
                              'buggy_pass':r['variants'][1]['passed'], 'candidate_passes':sum(v['passed'] for v in r['variants'][2:]),
                              'candidates':len(r['variants'])-2} for r in replay], model_calls=0), ensure_ascii=False))
