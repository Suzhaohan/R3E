"""Five-round candidate promotion with paired validation and regression rollback."""
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
DESIGNS = ('Mux', 'Counter', 'Prob015')
MATERIAL_ROOT = HERE / 'materials-selected-v2'
CASES = HERE / 'cases-selected-v2.jsonl'
SELECTION = HERE / 'selection-selected-v2.json'
PLAN_ROOT = HERE / 'plan-promotion-cached-v2'
PROMOTION_SOURCE = HERE / 'source-promotion'
VALIDATION_ROOT = HERE / 'validation-promotion-v1'
BLUE_OUTPUT = 131072
CONTEXT = 262144
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
    evidence = read(SELECTION)
    rows = [json.loads(line) for line in CASES.read_text().splitlines()]
    expected = ['strider:mux_4_1_2', 'strider:first_counter_overflow_2',
                'chipbench:timing:Prob015_vending_machine2']
    if [r['case_id'] for r in rows] != expected or evidence['selected_case_ids'] != expected:
        raise ValueError('fixed question selection changed')
    for path, digest in {**evidence['assets'], **evidence['evidence']}.items():
        if sha(ROOT / path) != digest:
            raise ValueError('historical evidence or original question changed: ' + path)
    for row in rows:
        ev = row['selection_evidence']
        if row['family'] in ('Mux', 'Counter'):
            replay = read(Path(ev['material_dir']) / 'replay.json')
            variants = replay['variants']
            candidates = [v for v in variants if v.get('source')]
            if (ev['historical_static_passed'] != 0 or ev['historical_static_runs'] != 3
                    or not variants[0]['passed'] or variants[1]['passed']
                    or len(candidates) != 9 or any(v['passed'] for v in candidates)):
                raise ValueError('verified historical functional failures required')
        elif ev['passed'] != 0 or ev['functional_failures'] != 2:
            raise ValueError('current-configuration B0 failures required')
        task = Path(material(row['family'])['anchors'][0]['task_dir'])
        if (task / 'public/repo/rtl/sequence.sv').read_bytes() != (ROOT / row['buggy_rtl']).read_bytes():
            raise ValueError('exam defect differs from original bytes')
    return rows


def material(design):
    return read(MATERIAL_ROOT / design / 'materials.json')


def cap(design):
    # Same original formula; only the number of fixed exam questions varies.
    return 5 * (1 + 3 + 2 * (1 + 1)) + len(material(design)['anchors']) * 2 * 6 * (1 + 1) + 48


def runner(design):
    spec = importlib.util.spec_from_file_location('completed_run03_' + design, HERE / 'launcher-promotion.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    baseline = read(BASE / 'real-v1/collection/plan.json')
    base.HERE = HERE
    base.BUNDLE = BASE / 'handoff'
    base.SOURCE = PROMOTION_SOURCE
    base.__file__ = str(Path(__file__).resolve())
    base.MAX_CALLS = cap(design)
    base.materials = lambda: material(design)
    def verify_import():
        for name, digest in read(HERE / 'promotion_code.json').items():
            if sha(PROMOTION_SOURCE / name) != digest:
                raise ValueError('promotion source changed; refreeze the source manifest')
    base.verify_import = verify_import
    original_modules = base.modules
    def modules():
        result = original_modules()
        result[1].PROMOTION_VALIDATION = read(VALIDATION_ROOT / design / 'validation.json')['tasks']
        return result
    base.modules = modules

    def identity():
        return dict(version='cached_promotion_v2', design=design,
                    completed_baseline_plan_sha256=sha(BASE / 'real-v1/collection/plan.json'),
                    completed_launcher_sha256=sha(BASE / 'experiment.py'),
                    entrypoint_sha256=sha(Path(__file__)), run_script_sha256=sha(HERE / 'run.sh'),
                    materials_sha256=sha(MATERIAL_ROOT / design / 'materials.json'),
                    cases_sha256=sha(CASES), selection_sha256=sha(SELECTION),
                    scientific_change='cached fixed-validation promotion, certificate rollback, Blue output131072/context262144; final exam unchanged',
                    validation_sha256=sha(VALIDATION_ROOT / design / 'validation.json'),
                    source_manifest_sha256=sha(HERE / 'promotion_code.json'),
                    promotion_launcher_sha256=sha(HERE / 'launcher-promotion.py'),
                    independent_design_instances=True)
    base.override_identity = identity

    def budget(launch):
        result = deepcopy(launch.budget('sequence'))
        counts = dict(red=20, online=10, reference=10,
                      anchor=len(material(design)['anchors']) * 2 * 6 * 2)
        result['rows'].append(dict(result['rows'][1], role='promotion'))
        counts['promotion'] = 48
        for row in result['rows']:
            row['calls'] = counts[row['role']]
            row['output_limit'] = 32768 if row['role'] == 'red' else BLUE_OUTPUT
            row['maximum_local_input'] = CONTEXT - row['output_limit']
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
        if any(plan[k] != baseline[k] for k in FLOW_FIELDS if k not in ('blue_config', 'client_config')):
            raise ValueError('workflow mechanism differs from latest completed run03')
        if plan['code'] != read(HERE / 'promotion_code.json'):
            raise ValueError('promotion core differs from frozen source manifest')
        expected_blue = dict(baseline['blue_config'], output_reserve=BLUE_OUTPUT, context_tokens=CONTEXT)
        expected_client = dict(baseline['client_config'], maximum_output_tokens=BLUE_OUTPUT)
        if plan['blue_config'] != expected_blue or plan['client_config'] != expected_client:
            raise ValueError('only approved output/context settings may change')
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
        fixtures = read(VALIDATION_ROOT / design / 'training_fixtures.json')
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
        client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport, maximum_output_tokens=BLUE_OUTPUT)
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



def write_results(root, designs=DESIGNS, single=False):
    root = Path(root)
    records = {}
    for design in designs:
        run = root if single else root / design
        collection = run / 'collection'
        if not (collection / 'collection.json').exists():
            records[design] = {'status': 'not_started'}
            continue
        summary = read(collection / 'collection.json')
        gates = [json.loads(line) for line in (collection / 'promotions.jsonl').read_text().splitlines()]
        if summary['status'] == 'complete':
            base = runner(design)
            _, _, _, curriculum, _ = base.modules()
            if not (collection / 'report.json').exists():
                curriculum.report(collection)
            from experiments.loop_probes.continuous_audit import source_audit, exposure_audit
            if not (collection / 'audits/source_audit.json').exists(): source_audit(collection)
            if not (collection / 'audits/exposure_audit.json').exists(): exposure_audit(collection)
            report = read(collection / 'report.json')
            scores = {r['snapshot']: r['categories'].get('public_pass_hidden_pass', 0)
                      for r in report['reserved_variants_by_snapshot']}
        else:
            scores = None
        record = {'status': summary['status'], 'calls': summary['calls'],
                  'stand_in_only': (collection / 'simulation_only.json').exists(),
                  'certified_validation': {
                      'initial_passed': sum(read(collection / 'validation_baseline.json')['scores'].values())
                          if (collection / 'validation_baseline.json').exists() else None,
                      'retained_passed': gates[-1]['retained_validation_passed'] if gates else None,
                      'samples': 4, 'incumbent_scores_cached': True},
                  'accepted_promotions': sum(g['accepted'] for g in gates),
                  'retained_entries': gates[-1]['retained_entries'] if gates else 0,
                  'promotion_rounds': [{k:g.get(k) for k in ('round','accepted','reason','incumbent_passed',
                      'candidate_passed','scheduled_pairs','retained_validation_passed','retained_entries')} for g in gates],
                  'final_exam': scores, 'guarantee_scope': 'cached results on four fixed validation samples; no guarantees for unseen exams or fresh stochastic runs'}
        save(collection / 'promotion_result.json', record)
        records[design] = record
    completed = [r for r in records.values() if r.get('final_exam') is not None]
    comparison = {'complete': len(completed) == len(designs),
                  'completed_designs': len(completed), 'scheduled_trials_per_group': 2 * len(designs),
                  'static_passed_completed_designs': sum(r['final_exam']['B_0'] for r in completed),
                  'promotion_passed_completed_designs': sum(r['final_exam']['B_5'] for r in completed)}
    save(root / 'promotion_results.json', {'designs': records, 'comparison': comparison, 'model_calls_for_reporting': 0,
         'normal_max_requests': 153, 'hard_max_requests': 336, 'previous_actual_requests': 91})
    print(json.dumps(records, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check', 'smoke', 'collect', 'report', 'audits', 'status', 'results'])
    parser.add_argument('--design', choices=['all', *DESIGNS], default='all')
    parser.add_argument('--plan-dir', type=Path, default=PLAN_ROOT)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    verify_questions()
    chosen = DESIGNS if args.design == 'all' else (args.design,)
    if args.action == 'results':
        if not args.run_dir:
            parser.error('results requires --run-dir')
        write_results(args.run_dir, chosen, args.design != 'all')
        return
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
                          approved_changes=['cached promotion and rollback', 'fixed validation certificate protection',
                                            'candidate audit provenance', 'Blue output131072/context262144'],
                          model_calls=0, final_questions=len(p['anchors']), max_calls=p['max_calls']))
    finally:
        sys.argv = previous
    if args.action == 'freeze':
        save(args.plan_dir / 'suite.json', dict(designs=list(chosen),
                                               final_questions=sum(len(material(d)['anchors']) for d in chosen),
                                               normal_max_calls=sum(15 + len(material(d)['anchors']) * 2 * 6 + 24 for d in chosen),
                                               hard_max_calls=sum(cap(d) for d in chosen),
                                               mechanism='cached incumbent certificate promotion; one B0 baseline; fixed two tasks/two repeats; candidates only'))


if __name__ == '__main__':
    main()
