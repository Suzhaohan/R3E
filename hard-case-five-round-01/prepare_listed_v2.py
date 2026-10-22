"""Build three exact cases selected from 09_Low_Pass_Rate_RTL_Cases.md and independently qualify all local variants."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / 'source-promotion-batch-v1'))
from experiments.loop_probes import witness_matrix as wm, carrier_task, red907
from r3e.loop.blue_provider import apply_text_edits
from r3e.protocol.hashing import hash_payload

DEST = HERE / 'materials-listed-v2'
VALIDATION = HERE / 'validation-listed-v2'
PRIMARY = 'rtl/sequence.sv'

GRAY_CHECK = """module tb;
reg clk=0,rst_n=0;wire [3:0] gray_out;integer cycle;reg[3:0] binary_expected,expected;
TopModule dut(clk,rst_n,gray_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(cycle=0;cycle<256;cycle=cycle+1) begin
  #3;clk=1;#2;
  binary_expected=(cycle+1)/2;
  expected=(binary_expected>>1)^binary_expected;
  if(gray_out!==expected) begin $display("CHECK_FAIL gray cycle=%0d got=%b expected=%b",cycle,gray_out,expected);$finish;end
  #1;clk=0;
 end
 $display("TESTBENCH PASS gray cycles=256");$finish;
end
endmodule
"""

GRAY_RESET = """module tb;
reg clk=0,rst_n=0;wire [3:0] gray_out;integer i;reg[3:0] held;
TopModule dut(clk,rst_n,gray_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(i=0;i<8;i=i+1) begin #3;clk=1;#2;held=gray_out;#1;clk=0;#2;
  if(gray_out!==held) begin $display("CHECK_FAIL output must hold without rising edge");$finish;end
 end
 rst_n=0;#1;
 if(gray_out!==0) begin $display("CHECK_FAIL asynchronous reset");$finish;end
 rst_n=1;#1;
 if(gray_out!==0) begin $display("CHECK_FAIL reset release");$finish;end
 $display("TESTBENCH PASS gray preserve");$finish;
end
endmodule
"""


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if DEST.exists() or VALIDATION.exists():
        raise FileExistsError('Use fresh versioned material directories')
    allrows = [json.loads(s) for s in (HERE / 'cases-all-v1.jsonl').read_text().splitlines()]
    rows = [dict(next(r for r in allrows if r['family'] == d)) for d in ('Prob001', 'Prob023')]
    original = ROOT / 'prob003-five-round-03/handoff/materials'
    rows.append(dict(next(r for r in allrows if r['case_id']=='historical:RC_406d811b4d61a2')))
    summary_file = ROOT / 'analysis/medium-high-selection-20261016/summary.json'
    summaries = json.loads(summary_file.read_text())['summaries']
    targets = {'Prob001': 'chipbench:arithmetic:Prob001_continuous_input_sequence_detect',
               'Prob023': 'chipbench:arithmetic:Prob023_gray_code_counter',
               'Prob003': 'chipbench_prob003_group_boundary_v1__eval_miss_branch'}
    selection_doc = ROOT/'09_Low_Pass_Rate_RTL_Cases.md'
    reports, assets, evidence = [], {}, {str(summary_file.relative_to(ROOT)): sha(summary_file), str(selection_doc.relative_to(ROOT)): sha(selection_doc)}
    for row in rows:
        design = row['family']
        row.pop('selection_evidence', None)
        old = original if design == 'Prob003' else HERE/'materials/Prob001'
        root = DEST / design
        package = root / 'package'
        shutil.copytree(old / 'package', package)
        for file in (old / 'evaluator').glob('*'):
            if file.is_file():
                save(root / 'evaluator' / file.name, file.read_text())
        man = wm.load(package)
        shutil.copytree(package/'variants/reset_control', package/'variants/preserve_control')
        if design == 'Prob023':
            man['carrier_id'] = 'chipbench_Prob023_gray_counter'
            man['source']['family'] = 'chipbench_Prob023_gray_code_counter'
            save(package/'src'/PRIMARY, (ROOT/row['golden_rtl']).read_text())
            save(package/'spec.md', (ROOT/row['spec']).read_text())
            save(package/'suites/W_bug/tb.sv', GRAY_CHECK)
            save(package/'suites/W_preserve/tb.sv', GRAY_RESET)
            save(root/'evaluator/tb.sv', GRAY_CHECK.replace('cycle<256','cycle<512').replace('#3;clk=1;#2;', '#5;clk=1;#3;'))
            shortcut = (ROOT/row['golden_rtl']).read_text().replace('posedge clk or negedge rst_n', 'posedge clk')
            save(package/'variants/preserve_control'/PRIMARY, shortcut)
        # Keep the existing clean implementation and test contract. Only use one original exam.
        man['variants'] = {'clean': {'role': 'clean'}, 'exam_defect': {'role': 'defect'},
                           'preserve_control': {'role': 'shortcut'}}
        clean = (package / 'src' / PRIMARY).read_text()
        save(package / 'variants/exam_defect' / PRIMARY, (ROOT / row['buggy_rtl']).read_text())
        def edit(a, b):
            return [{'find': a, 'replace': b}]
        if design == 'Prob001':
            seed = edit("8'b0111_0001", "8'b01100001")
            validation = [edit("8'b0111_0001", "8'b01110000") + edit('{a_tem[6:0],a}', '{a,a_tem[7:1]}'),
                edit("8'b0111_0001", "8'b01110010") + edit("else \n\t\t\tbegin\t\n\t\t\t\tmatch <= 1'b0;", "else \n\t\t\tbegin\t\n\t\t\t\tmatch <= match;")]
            training = [edit("8'b0111_0001", f"8'b{n:08b}") for n in (0x51,0x31,0x73,0x75,0x79)]
            mechanism = 'Eight-bit history ordering and registered comparison timing. Practice distinct shift, mask and comparison defects; retain asynchronous reset and original output phase.'
        elif design == 'Prob023':
            seed = edit("bin_out + 1'b1", "bin_out + 1'b0")
            validation = [edit('(bin_add_wire >> 1)', '(bin_add_wire >> 3)') + edit('gray_wire[2]^bin_out[3]', 'gray_wire[2]^gray_wire[1]'),
                          edit("bin_out + 1'b1", "bin_out + 2'd2") + edit('(bin_add_wire >> 1) ^ bin_add_wire', '(bin_add_wire >> 1) | bin_add_wire')]
            training = [edit('bin_out[3] = gray_wire[3];', 'bin_out[3] = ~gray_wire[3];'),
                        edit('gray_wire[2]^bin_out[3]', 'gray_wire[2]|bin_out[3]'),
                        edit('gray_wire[1]^bin_out[2]', 'gray_wire[1]&bin_out[2]'),
                        edit('gray_wire[0]^bin_out[1]', 'gray_wire[0]|bin_out[1]'),
                        edit('gray_out <= gray_wire;', 'gray_out <= bin_add_wire;')]
            mechanism = 'Four-bit Gray counter: Gray-to-binary decode, binary increment, adjacent-bit XOR conversion, every-two-clock update cadence and asynchronous reset. Generate distinct reachable functional defects while preserving reset and registered output stability.'

        else:
            # Two terminal transitions share text: use branch context for unique locations.
            seed = edit('        sf6:\n\t\t\tnstate=data?sf1:s1;', '        sf6:\n\t\t\tnstate=data?s1:sf1;')
            validation = [edit('nstate=data?s2:sf2;', 'nstate=data?sf2:s2;') + edit('nstate=sf4;', 'nstate=sf5;'),
                          edit('nstate=data?sf5:s5;', 'nstate=data?s5:sf5;') + edit('nstate=sf3;', 'nstate=sf4;')]
            training = [edit('nstate=data?s2:sf2;', 'nstate=data?sf2:s2;'),
                        edit('nstate=data?s3:sf3;', 'nstate=data?sf3:s3;'),
                        edit('nstate=data?s4:sf4;', 'nstate=data?sf4:s4;'),
                        edit('nstate=data?sf5:s5;', 'nstate=data?s5:sf5;'),
                        edit('nstate=data?sf6:s6;', 'nstate=data?s6:sf6;')]
            mechanism = 'Nonoverlapping six-bit group detector: state transitions, success/failure paths, consumption of the next group first bit at terminal boundaries, mutually exclusive outputs and original output phase. Use surrounding branch context to uniquely locate every edit.'
        for group in [seed, *validation, *training]:
            for e in group:
                if clean.count(e['find']) != 1:
                    raise ValueError((design, 'nonunique material edit', e['find']))
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
        if design == 'Prob003':
            ef['run'] = json.loads((old/'evaluator_freeze.json').read_text())['run']
        save(root / 'evaluator_freeze.json', ef)
        exam = carrier_task.export(package, 'exam_defect', root / 'reserved/exam_defect', freeze)
        # Check the independent evaluator itself, including its entry module.
        from experiments.loop_probes import red907_measure as measure
        from r3e.loop.repo_blue import RepoTask
        task = RepoTask.load(exam)
        reference_check = measure._evaluate(task, {PRIMARY: clean}, ef, root/'evaluator')
        defect_check = measure._evaluate(task, {PRIMARY: (ROOT/row['buggy_rtl']).read_text()}, ef, root/'evaluator')
        save(root/'evaluator_qualification.json', dict(reference=reference_check, defect=defect_check))
        if reference_check['result'] != 'pass' or defect_check['result'] != 'fail':
            raise ValueError((design, 'independent evaluator qualification failed', reference_check, defect_check))
        history = [s for s in summaries if s['case_id'] == targets[design] and 0 < s['passed'] < s['observations']]
        if design == 'Prob023':
            history = [dict(case_id=row['case_id'], model='DeepSeek V4 Flash register probe; not current V3-0324', observations=2, passed=1, sources=['09_Low_Pass_Rate_RTL_Cases.md'], setting='section 2; without register trace; one repair attempt; seeds 7 and 1016')]
        if design == 'Prob003':
            history = [dict(case_id=row['case_id'], model='historical Part A; not current V3', observations=3, passed=1, sources=['09_Low_Pass_Rate_RTL_Cases.md'], setting='up to three repair attempts; section 1')]
        if not history:
            raise ValueError('No mixed historical static outcomes for ' + design)
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
    save(HERE/'cases-listed-v2.jsonl', ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    save(HERE/'selection-listed-v2.json', dict(selected_case_ids=[r['case_id'] for r in rows], assets=assets,
         evidence=evidence, rows=reports, model_calls=0, selection_document='09_Low_Pass_Rate_RTL_Cases.md',
         document_sections={'Prob001':2,'Prob023':2,'Prob003':1},
         scope='Intermediate sequence tasks with mixed historical outcomes and composite independent validation; not a current V3 calibration.'))


if __name__ == '__main__':
    build()
