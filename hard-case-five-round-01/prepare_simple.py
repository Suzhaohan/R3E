"""Build simpler existing questions and independently qualify all local variants."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / 'source-promotion-simple-v1'))
from experiments.loop_probes import witness_matrix as wm, carrier_task, red907
from r3e.loop.blue_provider import apply_text_edits
from r3e.protocol.hashing import hash_payload

DEST = HERE / 'materials-simple-v1'
VALIDATION = HERE / 'validation-simple-v1'
PRIMARY = 'rtl/sequence.sv'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if DEST.exists() or VALIDATION.exists():
        raise FileExistsError('Use fresh versioned material directories')
    oldrows = [json.loads(s) for s in (HERE / 'cases-selected-v2.jsonl').read_text().splitlines()]
    seqrows = [json.loads(s) for s in (HERE / 'cases.jsonl').read_text().splitlines()]
    rows = [dict(oldrows[0]), dict(oldrows[1]), dict(seqrows[0])]
    mux_original = next(r for r in json.loads((ROOT / 'deepseek-run-01/source/competition/manifests/strider14_sealed.json').read_text())['rows']
                        if r['case_id'] == 'strider:mux_4_1_1')
    rows[0].update(case_id='strider:mux_4_1_1', buggy_rtl='deepseek-run-01/source/' + mux_original['buggy_rtl'])
    summary_file = ROOT / 'analysis/medium-high-selection-20261016/summary.json'
    summaries = json.loads(summary_file.read_text())['summaries']
    targets = {'Mux': 'strider:mux_4_1_1', 'Counter': 'selected_Counter__exam_defect',
               'Prob001': 'chipbench_Prob001_fixed_hard_questions__exam_arithmetic'}
    reports, assets, evidence = [], {}, {str(summary_file.relative_to(ROOT)): sha(summary_file)}
    for row in rows:
        design = row['family']
        row.pop('selection_evidence', None)
        old = HERE / ('materials' if design == 'Prob001' else 'materials-selected-v2') / design
        root = DEST / design
        package = root / 'package'
        shutil.copytree(old / 'package', package)
        for file in (old / 'evaluator').glob('*'):
            if file.is_file():
                save(root / 'evaluator' / file.name, file.read_text())
        man = wm.load(package)
        if design == 'Prob001':
            shutil.copytree(package/'variants/reset_control', package/'variants/preserve_control')
        # Keep the existing clean implementation and test contract. Only use one original exam.
        man['variants'] = {'clean': {'role': 'clean'}, 'exam_defect': {'role': 'defect'},
                           'preserve_control': {'role': 'shortcut'}}
        clean = (package / 'src' / PRIMARY).read_text()
        save(package / 'variants/exam_defect' / PRIMARY, (ROOT / row['buggy_rtl']).read_text())
        if design == 'Mux':
            pairs = [('out <= b;', 'out <= a;'), ('out <= c;', 'out <= a;'),
                     ('out <= d;', 'out <= a;'), ('out <= b;', 'out <= c;'),
                     ('out <= b;', 'out <= d;'), ('out <= c;', 'out <= b;'),
                     ('out <= c;', 'out <= d;'), ('out <= d;', 'out <= b;')]
            mechanism = 'Small combinational mux: selector coverage, distinct case labels and correct selected data. Preserve sel=00. Prefer one uniquely located edit. Generate distinct nearby defects from the clean RTL.'
        elif design == 'Counter':
            pairs = [("counter_out == 4'b1111", f"counter_out == 4'b{n:04b}") for n in (14,13,12,11,10,9,8,7)]
            mechanism = 'Small four-bit counter: enable/reset priority, overflow threshold, independent condition checks and sticky overflow. Preserve the exact original pre-edge and #1 timing contract; avoid unrelated rewrites. Preserve low counts and reset with enable.'
        else:
            pairs = [("8'b0111_0001", f"8'b{n:08b}") for n in (0x70,0x72,0x61,0x51,0x31,0x73,0x75,0x79)]
            mechanism = 'Small eight-bit sequence detector: history shift direction, comparison constant and registered one-cycle alignment. Preserve asynchronous reset and the specified sampling cycle. Prefer one uniquely located edit and distinct practice defects.'
        edits = [[{'find': a, 'replace': b}] for a,b in pairs]
        for group in edits:
            assert clean.count(group[0]['find']) == 1
        seed, validation, training = edits[0], edits[1:3], edits[3:]
        save(package / 'carrier.json', man)
        freeze = dict(files={k:v for k,v in wm.package_files(package).items()
                             if k != 'carrier.json' and not k.startswith('variants/')},
                      frozen_manifest_fields_hash=hash_payload(wm.frozen_fields(man)))
        save(root / 'suite_freeze.json', freeze)
        q = wm.qualify(package, freeze)
        save(root / 'qualification.json', q)
        if not q['qualified']:
            raise ValueError((design, q['problems']))
        structure = red907._loop_check(package, man, 'clean')
        if structure['status'] != 'ok':
            raise ValueError((design, structure))
        ef = dict(files={str(f.relative_to(root)): hash_payload(f.read_text()) for f in (root/'evaluator').glob('*.sv')},
                  run=dict(top='tb', rtl=[PRIMARY], pass_marker='TESTBENCH PASS', fail_marker='CHECK_FAIL'))
        save(root / 'evaluator_freeze.json', ef)
        exam = carrier_task.export(package, 'exam_defect', root / 'reserved/exam_defect', freeze)
        history = [s for s in summaries if s['case_id'] == targets[design] and s['passed'] > 0]
        if not history:
            raise ValueError('No recorded static repair success for ' + design)
        for record in history:
            for name in record['sources']:
                evidence[name] = sha(ROOT / name)
        provenance = dict(challenge_id=row['case_id'], runs=history[0]['observations'],
                          unrepaired=history[0]['observations']-history[0]['passed'],
                          label='historical_budgeted_failure_not_current_confirmation')
        focus = dict(version='continuous_mechanism_seed_v1', carrier_id=man['carrier_id'],
                     mechanism='Across five rounds build transferable repair experience. ' + mechanism,
                     selection='human_selected_development_seed', seed_edits=seed, history=provenance,
                     provenance=dict(clean_hash=hash_payload(clean), seed_hash=hash_payload(apply_text_edits(clean, seed)),
                                     record_hashes={'selection_audit': hash_payload(summary_file.read_text())}))
        save(root / 'materials.json', dict(carriers=[dict(package=str(package.resolve()),
             suite_freeze=str((root/'suite_freeze.json').resolve()), evaluator_freeze=str((root/'evaluator_freeze.json').resolve()),
             evaluator_root=str(root.resolve()))], anchors=[dict(task_dir=str(exam.resolve()), carrier_index=0)],
             mechanism_focus=focus, questions=[row['case_id']]))
        save(root / 'practice_fixtures.json', training)
        vp = VALIDATION / design / 'package'
        shutil.copytree(package, vp)
        vm = wm.load(vp)
        for i, group in enumerate(validation):
            name = f'validation_{i}'
            vm['variants'][name] = {'role': 'defect'}
            save(vp / 'variants' / name / PRIMARY, apply_text_edits(clean, group))
        save(vp / 'carrier.json', vm)
        vq = wm.qualify(vp, freeze)
        save(VALIDATION / design / 'qualification.json', vq)
        if not vq['qualified']:
            raise ValueError((design, vq['problems']))
        tasks = [str(carrier_task.export(vp, f'validation_{i}', VALIDATION/design/f'task_{i}', freeze).resolve()) for i in range(2)]
        save(VALIDATION/design/'validation.json', dict(tasks=tasks, repeats=2, exam_used_for_selection=False,
             task_bytes={t: hash_payload((Path(t)/'public/repo'/PRIMARY).read_text()) for t in tasks}))
        save(VALIDATION/design/'training_fixtures.json', training)
        public = red907.public_material(package, freeze)
        seen = set()
        forbidden = {hash_payload(apply_text_edits(clean, seed)), hash_payload((ROOT/row['buggy_rtl']).read_text()),
                     *(hash_payload(apply_text_edits(clean, group)) for group in validation)}
        for i, group in enumerate(training):
            mutant = apply_text_edits(clean, group)
            assert hash_payload(mutant) not in forbidden
            from r3e.loop.red_continuous import materialize
            proposal = materialize(dict(edits=group, violated_requirement='practice defect', spec_basis='unchanged public spec'), public)
            result = red907.check_proposal(package, freeze, proposal, root/'practice_checks'/str(i), seen=seen)
            if result['status'] != 'admitted':
                raise ValueError((design, i, result.get('reason')))
        row['spec'] = str((package/'spec.md').relative_to(ROOT))
        for name in [row['golden_rtl'],row['buggy_rtl'],row['spec']]:
            assets[name] = sha(ROOT/name)
        reports.append(dict(case_id=row['case_id'], family=design, reference_passed=True, defect_failed=True,
                            clean_nonempty_lines=sum(bool(s.strip()) for s in clean.splitlines()),
                            historical_successes=history, practice_admitted=5,
                            current_v3_pass_rate=None))
    save(HERE/'cases-simple-v1.jsonl', ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    save(HERE/'selection-simple-v1.json', dict(selected_case_ids=[r['case_id'] for r in rows], assets=assets,
         evidence=evidence, rows=reports, model_calls=0,
         scope='Simpler design structure and recorded historical successes; not a current V3 calibration.'))


if __name__ == '__main__':
    build()
