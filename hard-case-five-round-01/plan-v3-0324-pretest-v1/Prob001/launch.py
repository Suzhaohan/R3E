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
DESIGNS = ('Prob001', 'Prob023', 'Prob003')
MATERIAL_ROOT = HERE / 'materials-listed-v2'
CASES = HERE / 'cases-listed-v2.jsonl'
SELECTION = HERE / 'selection-listed-v2.json'
PLAN_ROOT = HERE / 'plan-v3-0324-pretest-v1'
PROMOTION_SOURCE = HERE / 'source-promotion-pretest-v1'
VALIDATION_ROOT = HERE / 'validation-listed-v2'
BLUE_OUTPUT = 16000
RED_OUTPUT = 16000
CONTEXT = 128000
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
    expected = ['chipbench:arithmetic:Prob001_continuous_input_sequence_detect',
                'chipbench:arithmetic:Prob023_gray_code_counter',
                'historical:RC_406d811b4d61a2']
    if [r['case_id'] for r in rows] != expected or evidence['selected_case_ids'] != expected:
        raise ValueError('fixed question selection changed')
    if evidence.get('selection_document') != '09_Low_Pass_Rate_RTL_Cases.md' or evidence.get('document_sections') != {'Prob001': 2, 'Prob023': 2, 'Prob003': 1}:
        raise ValueError('three questions must come from the specified low-pass-rate list')
    for path, digest in {**evidence['assets'], **evidence['evidence']}.items():
        if sha(ROOT / path) != digest:
            raise ValueError('historical evidence or original question changed: ' + path)
    for row, report in zip(rows, evidence['rows']):
        if (report['case_id'] != row['case_id'] or not report['reference_passed'] or not report['defect_failed']
                or report['practice_admitted'] != 5 or not report['historical_successes']):
            raise ValueError('qualified intermediate questions and historical success evidence required')
        task = Path(material(row['family'])['anchors'][0]['task_dir'])
        if (task / 'public/repo/rtl/sequence.sv').read_bytes() != (ROOT / row['buggy_rtl']).read_bytes():
            raise ValueError('exam defect differs from original bytes')
    return rows


def material(design):
    return read(MATERIAL_ROOT / design / 'materials.json')


def cap(design):
    # Same original formula; only the number of fixed exam questions varies.
    return 5 * (1 + 1 + 2 * (1 + 1)) + len(material(design)['anchors']) * 2 * 2 * (1 + 1) + 48


def runner(design):
    spec = importlib.util.spec_from_file_location('completed_run03_' + design, HERE / 'launcher-v3-0324.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    baseline = read(BASE / 'real-v1/collection/plan.json')
    base.HERE = HERE
    base.BUNDLE = BASE / 'handoff'
    base.SOURCE = PROMOTION_SOURCE
    base.__file__ = str(Path(__file__).resolve())
    base.MAX_CALLS = cap(design)
    base.COLLISION_RETRIES = 1
    base.materials = lambda: material(design)
    def verify_import():
        for name, digest in read(HERE / 'promotion_code_pretest_v1.json').items():
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
        return dict(version='v3_0324_static_exam_first_v1', design=design,
                    completed_baseline_plan_sha256=sha(BASE / 'real-v1/collection/plan.json'),
                    completed_launcher_sha256=sha(BASE / 'experiment.py'),
                    entrypoint_sha256=sha(Path(__file__)), run_script_sha256=sha(HERE / 'run.sh'),
                    materials_sha256=sha(MATERIAL_ROOT / design / 'materials.json'),
                    cases_sha256=sha(CASES), selection_sha256=sha(SELECTION),
                    scientific_change='Pure online Red batches, max four constrained candidates per request and one corrective request; no human-prepared replacement; empty practice is reported truthfully; independent experience per design; B0 exams first globally; stop on all samples passing; otherwise seal and reuse B0, train all five-round branches then examine only B5; V3-0324 and materials unchanged',
                    validation_sha256=sha(VALIDATION_ROOT / design / 'validation.json'),
                    source_manifest_sha256=sha(HERE / 'promotion_code_pretest_v1.json'),
                    promotion_launcher_sha256=sha(HERE / 'launcher-v3-0324.py'),
                    independent_design_instances=True)
    base.override_identity = identity

    def budget(launch):
        result = deepcopy(launch.budget('sequence'))
        counts = dict(red=10, online=10, reference=10,
                      anchor=len(material(design)['anchors']) * 2 * 2 * 2)
        result['rows'].append(dict(result['rows'][1], role='promotion'))
        counts['promotion'] = 48
        for row in result['rows']:
            row['calls'] = counts[row['role']]
            row['output_limit'] = RED_OUTPUT if row['role'] == 'red' else BLUE_OUTPUT
            row['maximum_local_input'] = CONTEXT - row['output_limit']
            row['maximum_allowed_provider_input'] = row['maximum_local_input'] * 105 // 100 + 128
            row['maximum_CNY'] = str(Decimal(row['calls']) *
                (row['maximum_allowed_provider_input'] * 2 + row['output_limit'] * 8) / 1_000_000)
        result['max_calls'] = sum(counts.values())
        result['maximum_CNY'] = str(sum(Decimal(r['maximum_CNY']) for r in result['rows']))
        result['spending_envelope_CNY'] = None
        result['scope'] = 'Historical CNY token-exposure proxy only; not OpenRouter pricing, billing, or a monetary cap. Request/token limits remain enforced.'
        return result
    base.budget = budget

    def check_scope(plan, launch):
        verify_questions()
        if any(plan[k] != baseline[k] for k in FLOW_FIELDS if k not in ('blue_config', 'client_config', 'red_output_tokens','reserved_collision_retries')):
            raise ValueError('workflow mechanism differs from latest completed run03')
        if plan['code'] != read(HERE / 'promotion_code_pretest_v1.json'):
            raise ValueError('promotion core differs from frozen source manifest')
        expected_blue = dict(baseline['blue_config'], output_reserve=BLUE_OUTPUT, context_tokens=CONTEXT)
        expected_client = dict(baseline['client_config'], maximum_output_tokens=BLUE_OUTPUT,
                               provider_id='openrouter', endpoint_id='openrouter-env-endpoint',
                               model_id='deepseek/deepseek-chat-v3-0324', model_version='env-declared;thinking=default')
        if plan['blue_config'] != expected_blue or plan['client_config'] != expected_client or plan['red_output_tokens'] != RED_OUTPUT:
            raise ValueError('only approved V3 endpoint/model/output/context settings may change')
        expected = material(design)
        if (plan['carriers'] != expected['carriers']
                or plan['mechanism_focus'] != expected['mechanism_focus']
                or [a['task_dir'] for a in plan['anchors']] != [a['task_dir'] for a in expected['anchors']]
                or plan['reserved_collision_retries'] != 1 or plan['max_calls'] != cap(design) or plan['cost_bound'] != budget(launch)
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
        format_used = False
        blue_calls = 0
        def transport(**request):
            nonlocal format_used, blue_calls
            u = json.loads(request['messages'][-1]['content'])
            if 'carrier' in u:
                value = {'abstain':'offline no-qualified-candidate fixture; verify empty rounds and deferred exams'}
            elif blue_calls < 6:
                blue_calls += 1
                value = {'files': [{'file': 'rtl/sequence.sv', 'content': u['files']['rtl/sequence.sv']['content']}], 'edit': 'offline baseline no-op fixture'}
            elif not format_used:
                format_used = True
                value = {'edits': [], 'edit': 'offline format-error fixture'}
            else:
                value = {'files': [{'file': 'rtl/sequence.sv', 'content': clean}], 'edit': 'offline fixture only'}
            return _reply(value, 1)
        client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport, maximum_output_tokens=BLUE_OUTPUT)
        p = loop.make_plan(m['carriers'], m['anchors'], counter=counter_type(), client_config=client.config.public_identity,
                          rounds=5, slots_per_round=1, seed=700, carrier_mode='fixed', fixed_carrier_index=0,
                          anchor_repeats=2, mechanism_focus=m['mechanism_focus'], red_output_tokens=RED_OUTPUT, reserved_collision_retries=1)
        result = loop.collect(p, out, client=BudgetedClient(client, max_calls=p['max_calls']), counter=counter_type())
        if result['status'] in {'skipped','pretested','trained'}:
            save(out / 'simulation_only.json', {'fake': True, 'model_calls': 0})
            return {**result, 'model_calls': 0, 'stand_in_only': True}
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
                               stop_reason=read(directory / 'stop_reason.json') if (directory / 'stop_reason.json').exists() else None,
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
                  'stop_reason': read(collection/'stop_reason.json') if (collection/'stop_reason.json').exists() else None,
                  'stand_in_only': (collection / 'simulation_only.json').exists(),
                  'certified_validation': {
                      'initial_passed': sum(read(collection / 'validation_baseline.json')['scores'].values())
                          if (collection / 'validation_baseline.json').exists() else None,
                      'retained_passed': gates[-1]['retained_validation_passed'] if gates else
                          sum(read(collection / 'validation_baseline.json')['scores'].values()) if (collection / 'validation_baseline.json').exists() else None,
                      'samples': 4, 'incumbent_scores_cached': True},
                  'accepted_promotions': sum(g['accepted'] for g in gates),
                  'retained_entries': gates[-1]['retained_entries'] if gates else 0,
                  'qualified_online_practices':summary['qualified_practice_slots'],
                  'empty_practice_slots':summary['empty_practice_slots'],
                  'human_prepared_replacements':0,
                  'promotion_rounds': [{k:g.get(k) for k in ('round','accepted','reason','incumbent_passed',
                      'candidate_passed','scheduled_pairs','retained_validation_passed','retained_entries')} for g in gates],
                  'initial_static_exam': {k:v for k,v in read(collection/'initial_exam.json').items() if k in ('passed','samples','valid_measurements','scores','reuse_for_final_comparison','teaches_training')} if (collection/'initial_exam.json').exists() else None,
                  'final_exam': scores, 'guarantee_scope': 'cached results on four fixed validation samples; no guarantees for unseen exams or fresh stochastic runs'}
        save(collection / 'promotion_result.json', record)
        records[design] = record
    completed = [r for r in records.values() if r.get('final_exam') is not None]
    comparison = {'complete': len(completed) == len(designs),
                  'all_designs_finished': all(r.get('status') in {'complete', 'skipped', 'stopped_exam_saturated', 'stopped_pretest_inconclusive'} for r in records.values()),
                  'skipped_designs': [d for d,r in records.items() if r.get('status') == 'skipped'],
                  'completed_designs': len(completed), 'scheduled_trials_per_group': 2 * len(designs),
                  'static_passed_completed_designs': sum(r['final_exam']['B_0'] for r in completed),
                  'promotion_passed_completed_designs': sum(r['final_exam']['B_5'] for r in completed)}
    save(root / 'promotion_results.json', {'designs': records, 'comparison': comparison, 'initial_exam_gate': read(root/'initial_exam_gate.json') if (root/'initial_exam_gate.json').exists() else None, 'model_calls_for_reporting': 0,
         'normal_max_requests': 129, 'hard_max_requests': 258,
         'actual_requests':sum(r.get('calls',0) for r in records.values()),
         'exam_questions':len(designs),'samples_per_question_per_group':2,
         'experience_policy':'independent_per_design','phase_policy':'static_exam_first_then_all_training_then_B5',
         'qualified_online_practices':sum(r.get('qualified_online_practices',0) for r in records.values()),
         'empty_practice_slots':sum(r.get('empty_practice_slots',0) for r in records.values()),
         'human_prepared_replacements':0, 'generation_mode':'online_red_constrained_candidates'})
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
        if args.action in {'smoke','collect'}:
            _,batch_loop,*_=runner(chosen[0]).modules()
            batch_loop.EXAM_QUEUE=[]
            batch_loop.TRAIN_QUEUE=[]
            batch_loop.PRETEST_DECISION=None
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
            if args.action == 'collect' and args.run_dir:
                directory = args.run_dir / design if args.design == 'all' else args.run_dir
                summary = read(directory / 'collection/collection.json')
                if summary['status'] == 'skipped':
                    print(f'{design} 验证基线满分，已跳过本题；不影响其他题目继续运行。', flush=True)
            if args.action in {'freeze', 'check'}:
                p = read(args.plan_dir / design / 'plan.json')
                baseline = read(BASE / 'real-v1/collection/plan.json')
                save(args.plan_dir / design / 'workflow_audit.json',
                     dict(baseline='prob003-five-round-03/real-v1',
                          fields={k: p[k] == baseline[k] for k in FLOW_FIELDS},
                          all_core_files_identical=p['code'] == baseline['code'],
                          approved_changes=['cached promotion and rollback', 'fixed validation certificate protection',
                                            'pure online constrained candidate batches; no prepared replacement; empty rounds reported',
                                            'B0 exams first with global saturation gate and sealed reuse; all training precedes B5', 'candidate audit provenance', 'DeepSeek V3-0324 (2025-03-24) via OpenRouter; output16000/context128000'],
                          model_calls=0, final_questions=len(p['anchors']), max_calls=p['max_calls']))
        if args.action in {'smoke','collect'}:
            # The first calls across the batch are B0 exam trials only.
            initial_members=[]
            for design in chosen:
                directory=(args.run_dir/design if args.design=='all' else args.run_dir)/'collection'
                summary=read(directory/'collection.json')
                initial=read(directory/'initial_exam.json')
                if summary['status']!='pretested' or summary['committed_rounds']!=0:
                    raise ValueError('all initial exams must precede training')
                initial_members.append(dict(design=design,passed=initial['passed'],samples=initial['samples'],
                    valid_measurements=initial['valid_measurements'],initial_exam_sha256=sha(directory/'initial_exam.json')))
            samples=sum(m['samples'] for m in initial_members)
            passed=sum(m['passed'] for m in initial_members)
            valid=sum(m['valid_measurements'] for m in initial_members)
            if samples!=2*len(chosen):
                raise ValueError('incomplete initial exam schedule')
            decision='stop_inconclusive' if valid!=samples else 'stop_saturated' if passed==samples else 'continue'
            batch_loop.PRETEST_DECISION=decision
            save(args.run_dir/'initial_exam_gate.json',dict(decision=decision,passed=passed,samples=samples,
                valid_measurements=valid,members=initial_members,scope='all_selected_designs',
                reuse_static_exam_for_final_comparison=True,teaches_training=False))
            if decision!='continue':
                for design in chosen:
                    directory=(args.run_dir/design if args.design=='all' else args.run_dir)/'collection'
                    summary=read(directory/'collection.json')
                    summary['status']='stopped_exam_saturated' if decision=='stop_saturated' else 'stopped_pretest_inconclusive'
                    save(directory/'collection.json',summary)
                    save(directory/'stop_reason.json',dict(reason=decision,passed=passed,samples=samples))
                batch_loop.TRAIN_QUEUE.clear()
                batch_loop.EXAM_QUEUE.clear()
                write_results(args.run_dir,chosen,args.design!='all')
                print('无经验组整套考试全部答对，本批停止，不进入训练。' if decision=='stop_saturated' else
                      '前测存在无效测量，本批停止，不能据此判断考试区分度。',flush=True)
                if decision=='stop_inconclusive':
                    raise SystemExit(2)
                return
            pending_training=list(batch_loop.TRAIN_QUEUE)
            if len(pending_training)!=len(chosen):
                raise ValueError('one deferred training job required per design')
            for design,job in zip(chosen,pending_training):
                print(f'无经验组前测 {passed}/{samples}，开始 {design} 的五轮流程；前测成绩封存复用。',flush=True)
                job()
            members=[]
            for design in chosen:
                directory=(args.run_dir/design if args.design=='all' else args.run_dir)/'collection'
                summary=read(directory/'collection.json')
                if summary['status']!='trained' or summary['committed_rounds']!=5 or summary['completed_probes']!=2:
                    raise ValueError('all independent five-round training branches must finish before exams')
                commit=read(directory/'rounds/5/commit.json')
                members.append(dict(design=design,plan_hash=summary['plan_hash'],final_state_hash=commit['blue']['state_hash'],
                                    training_calls=summary['calls'],qualified_practices=summary['qualified_practice_slots'],
                                    empty_practice_slots=summary['empty_practice_slots']))
            save(args.run_dir/'training_barrier.json',dict(status='all_training_complete',members=members,
                 experience_policy='independent_per_design',exam_policy='same held-out three questions; frozen B0 versus B5; no learning'))
            pending=list(batch_loop.EXAM_QUEUE)
            if len(pending)!=len(chosen):
                raise ValueError('one deferred final exam job required per trained design')
            for design,job in zip(chosen,pending):
                print(f'全部五轮流程已结束，开始 {design} 的对抗组考试；静态组复用前测。',flush=True)
                job()
            batch_loop.EXAM_QUEUE=None
            write_results(args.run_dir,chosen,args.design!='all')
    finally:
        if args.action in {'smoke','collect'} and 'batch_loop' in locals():
            batch_loop.EXAM_QUEUE=None
            batch_loop.TRAIN_QUEUE=None
            batch_loop.PRETEST_DECISION=None
        sys.argv = previous
    if args.action == 'freeze':
        save(args.plan_dir / 'suite.json', dict(designs=list(chosen),
                                               final_questions=sum(len(material(d)['anchors']) for d in chosen),
                                               normal_max_calls=sum(15 + len(material(d)['anchors']) * 2 * 2 + 24 for d in chosen),
                                               hard_max_calls=sum(cap(d) for d in chosen),
                                               mechanism='independent experience; online constrained Red batches only; no prepared replacement; B0 first; global full-pass stop; sealed B0 reused; five rounds then B5'))


if __name__ == '__main__':
    main()
