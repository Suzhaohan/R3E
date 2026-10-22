"""Change fixed hard-question materials; reuse run03's completed workflow verbatim.

Each design is an instance of the same original five-round protocol. No new
learning, retrieval, repair, admission, or evaluation algorithm is introduced.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT / 'prob003-five-round-03'
DESIGNS = ('Prob001', 'Prob015')
FLOW_FIELDS = ('rounds', 'slots_per_round', 'seed', 'carrier_mode', 'fixed_carrier_index',
               'anchor_repeats', 'blue_config', 'client_config', 'learning', 'retrieval',
               'red_bank_tokens', 'red_output_tokens', 'reserved_collision_retries',
               'path_policy', 'tokenizer')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def verify_questions():
    evidence = read(HERE / 'selection.json')
    rows = [json.loads(l) for l in (HERE / 'cases.jsonl').read_text().splitlines()]
    if [r['case_id'] for r in rows] != evidence['selected_case_ids']:
        raise ValueError('fixed question selection changed')
    for ref in [evidence['binding'], evidence['protocol'], *evidence['records']]:
        if sha(ROOT / ref['source']) != ref['sha256']:
            raise ValueError('historical evidence changed')
    protocol = read(ROOT / evidence['protocol']['source'])
    if protocol['asset_hash'] != read(ROOT / evidence['binding']['source'])['asset_hash']:
        raise ValueError('historical source binding mismatch')
    for row in rows:
        for path in [row[k] for k in ('golden_rtl', 'buggy_rtl', 'spec')] + row['tb_sources']:
            if sha(ROOT / path) != protocol['assets'].get(path):
                raise ValueError('question differs from historically measured bytes')
        records = [r for r in evidence['records'] if r['case_id'] == row['case_id']]
        if len(records) != 3 or len({r['source'] for r in records}) != 3:
            raise ValueError('three distinct calibration observations required')
        failures = successes = 0
        for ref in records:
            raw = read(ROOT / ref['source'])
            rec = raw['record']
            if (rec['challenge_id'] != row['case_id'] or rec['mode'] != 'none'
                    or raw['inconclusive'] or rec['accounting']['memory_delivered']
                    or rec['accounting']['provider_failures']
                    or any(x.get('injected') for x in rec['deliveries'])
                    or any(a.get('memory_offered') for a in rec['attempts'])):
                raise ValueError('conclusive no-memory evidence required')
            successes += bool(raw['solved'])
            failures += not raw['solved'] and rec['attempts'][-1]['verdict_tier'] == 'visible_fail'
        if successes > 1 or failures < 2:
            raise ValueError('question lacks repeated functional failure evidence')
    return rows


def material(design):
    return read(HERE / 'materials' / design / 'materials.json')


def cap(design):
    # Same original formula; only the number of fixed exam questions varies.
    return 5 * (1 + 3 + 2 * (1 + 1)) + len(material(design)['anchors']) * 2 * 6 * (1 + 1)


def runner(design):
    spec = importlib.util.spec_from_file_location('completed_run03_' + design, BASE / 'experiment.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    baseline = read(BASE / 'real-v1/collection/plan.json')
    base.HERE = HERE
    base.BUNDLE = BASE / 'handoff'
    base.SOURCE = BASE / 'source'
    base.__file__ = str(Path(__file__).resolve())
    base.MAX_CALLS = cap(design)
    base.materials = lambda: material(design)

    def identity():
        return dict(version='question_material_only_v3', design=design,
                    completed_baseline_plan_sha256=sha(BASE / 'real-v1/collection/plan.json'),
                    completed_launcher_sha256=sha(BASE / 'experiment.py'),
                    entrypoint_sha256=sha(Path(__file__)), run_script_sha256=sha(HERE / 'run.sh'),
                    materials_sha256=sha(HERE / 'materials' / design / 'materials.json'),
                    cases_sha256=sha(HERE / 'cases.jsonl'), selection_sha256=sha(HERE / 'selection.json'),
                    scientific_change='question materials and derived exam count only; all workflow mechanisms reused',
                    independent_design_instances=True)
    base.override_identity = identity

    def budget(launch):
        result = deepcopy(launch.budget('sequence'))
        counts = dict(red=20, online=10, reference=10,
                      anchor=len(material(design)['anchors']) * 2 * 6 * 2)
        for row in result['rows']:
            row['calls'] = counts[row['role']]
            row['output_limit'] = 32768 if row['role'] == 'red' else 65536
            row['maximum_local_input'] = 131072 - row['output_limit']
            row['maximum_allowed_provider_input'] = row['maximum_local_input'] * 105 // 100 + 128
            row['maximum_CNY'] = str(Decimal(row['calls']) *
                (row['maximum_allowed_provider_input'] * 2 + row['output_limit'] * 8) / 1_000_000)
        result['max_calls'] = sum(counts.values())
        result['maximum_CNY'] = str(sum(Decimal(r['maximum_CNY']) for r in result['rows']))
        result['spending_envelope_CNY'] = None
        result['scope'] = baseline['cost_bound']['scope']
        return result
    base.budget = budget

    def check_scope(plan, launch):
        verify_questions()
        if any(plan[k] != baseline[k] for k in FLOW_FIELDS):
            raise ValueError('workflow mechanism differs from latest completed run03')
        if plan['code'] != baseline['code']:
            raise ValueError('core code must be byte-identical to completed run03')
        expected = material(design)
        if (plan['carriers'] != expected['carriers']
                or plan['mechanism_focus'] != expected['mechanism_focus']
                or [a['task_dir'] for a in plan['anchors']] != [a['task_dir'] for a in expected['anchors']]
                or plan['max_calls'] != cap(design) or plan['cost_bound'] != budget(launch)
                or plan['five_round_override'] != identity()
                or plan['spending_envelope_CNY'] is not None
                or plan['client_config'] != launch.client_identity()):
            raise ValueError('frozen question material/count/budget differs')
    base.check_scope = check_scope

    def smoke(out):
        launch, loop, shared, curriculum, counter_type = base.modules()
        from r3e.loop.env import build_client
        from r3e.loop.budget import BudgetedClient
        from r3e.loop.fakes import _reply
        m = material(design)
        clean = (Path(m['carriers'][0]['package']) / 'src/rtl/sequence.sv').read_text()
        anchor = (Path(m['anchors'][0]['task_dir']) / 'public/repo/rtl/sequence.sv').read_text()
        fixtures = read(HERE / 'materials' / design / 'practice_fixtures.json')
        proposals = iter([[{'find': clean, 'replace': anchor}], *fixtures])
        format_used = False
        def transport(**request):
            nonlocal format_used
            u = json.loads(request['messages'][-1]['content'])
            if 'carrier' in u:
                value = dict(edits=next(proposals), violated_requirement='target mechanism', spec_basis='unchanged specification')
            elif not format_used:
                format_used = True
                value = {'edits': [], 'edit': 'offline format-error fixture'}
            else:
                value = {'files': [{'file': 'rtl/sequence.sv', 'content': clean}], 'edit': 'offline fixture only'}
            return _reply(value, 1)
        client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport, maximum_output_tokens=65536)
        p = loop.make_plan(m['carriers'], m['anchors'], counter=counter_type(), client_config=client.config.public_identity,
                          rounds=5, slots_per_round=1, seed=700, carrier_mode='fixed', fixed_carrier_index=0,
                          anchor_repeats=2, mechanism_focus=m['mechanism_focus'], red_output_tokens=32768, reserved_collision_retries=3)
        result = loop.collect(p, out, client=BudgetedClient(client, max_calls=p['max_calls']), counter=counter_type())
        curriculum.report(out)
        from experiments.loop_probes.continuous_audit import exposure_audit, source_audit
        exposure_audit(out)
        source_audit(out)
        save(out / 'simulation_only.json', {'fake': True, 'model_calls': 0})
        return {**result, 'model_calls': 0, 'stand_in_only': True}
    base.smoke = smoke
    return base


def combined_status(root, designs=DESIGNS, single=False):
    records = {}
    for design in designs:
        directory = (root if single else root / design) / 'collection'
        def count(name):
            f = directory / name
            return len(f.read_text().splitlines()) if f.exists() else 0
        records[design] = dict(collection=read(directory / 'collection.json') if (directory / 'collection.json').exists() else None,
                               stand_in_only=(directory / 'simulation_only.json').exists(),
                               recorded_calls=count('calls.jsonl'), completed_slots=count('slots.jsonl'), completed_probes=count('probes.jsonl'))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check', 'smoke', 'collect', 'report', 'audits', 'status'])
    parser.add_argument('--design', choices=['all', *DESIGNS], default='all')
    parser.add_argument('--plan-dir', type=Path, default=HERE / 'plan-questions-v4')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    verify_questions()
    chosen = DESIGNS if args.design == 'all' else (args.design,)
    if args.action == 'status':
        if not args.run_dir:
            parser.error('status requires --run-dir')
        print(json.dumps(combined_status(args.run_dir, chosen, args.design != 'all'), ensure_ascii=False))
        return
    if args.action in {'smoke', 'collect'}:
        if not args.run_dir or args.run_dir.exists():
            parser.error('fresh --run-dir required; no implicit resume')
        if args.action == 'collect' and not args.env_file:
            parser.error('collect requires --env-file')
        if args.design == 'all':
            args.run_dir.mkdir(parents=True, exist_ok=False)
    if args.action == 'freeze':
        args.plan_dir.mkdir(parents=True, exist_ok=False)
    previous = sys.argv
    try:
        for design in chosen:
            base = runner(design)
            if args.action == 'smoke':
                target = (args.run_dir / design if args.design == 'all' else args.run_dir) / 'collection'
                print(json.dumps({'design': design, **base.smoke(target)}, ensure_ascii=False))
                continue
            sys.argv = [str(HERE / 'experiment.py'), args.action, '--plan-dir', str(args.plan_dir / design)]
            if args.run_dir:
                sys.argv.extend(['--run-dir', str(args.run_dir / design if args.design == 'all' else args.run_dir)])
            if args.env_file:
                sys.argv.extend(['--env-file', str(args.env_file)])
            base.main()
            if args.action in {'freeze', 'check'}:
                p = read(args.plan_dir / design / 'plan.json')
                baseline = read(BASE / 'real-v1/collection/plan.json')
                save(args.plan_dir / design / 'workflow_audit.json',
                     dict(baseline='prob003-five-round-03/real-v1',
                          fields={k: p[k] == baseline[k] for k in FLOW_FIELDS},
                          all_core_files_identical=p['code'] == baseline['code'],
                          model_calls=0, final_questions=len(p['anchors']), max_calls=p['max_calls']))
    finally:
        sys.argv = previous
    if args.action == 'freeze':
        save(args.plan_dir / 'suite.json', dict(designs=list(chosen),
                                               final_questions=sum(len(material(d)['anchors']) for d in chosen),
                                               normal_max_calls=sum(15 + len(material(d)['anchors']) * 2 * 6 for d in chosen),
                                               hard_max_calls=sum(cap(d) for d in chosen),
                                               mechanism='unchanged run03 workflow independently instantiated per design'))


if __name__ == '__main__':
    main()
