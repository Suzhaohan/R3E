"""Freeze the three audited existing questions; no network or model calls."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from prepare_materials import write, wm, carrier_task, hash_payload, VENDING_RESET

DEST = HERE / 'materials-selected-v2'
PRIMARY = 'rtl/sequence.sv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulate(files, top='tb'):
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for name, text in files.items():
            (work / name).write_text(text)
        build = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', 'sim', *files],
                               cwd=work, capture_output=True, text=True, timeout=60)
        if build.returncode:
            raise ValueError(build.stderr)
        run = subprocess.run(['vvp', '-n', 'sim'], cwd=work, capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise ValueError(run.stderr)
        return run.stdout


def strider_checker(tb, oracle, signals):
    """Keep upstream stimulus and sampling; compare all original oracle rows."""
    rows = [line.split(',') for line in oracle.splitlines()[1:] if line.strip()]
    width = len(rows[0]) - 1
    declarations = 'integer sample_index=0, errors=0; reg [%d:0] expected;\n' % (width - 1)
    cases = '\n'.join('%d: expected=%d\'b%s;' % (i, width, ''.join(row[1:])) for i, row in enumerate(rows))
    checker = '''case(sample_index)
%s
default: begin $display("CHECK_FAIL excess oracle samples"); errors=errors+1; end
endcase
if ({%s} !== expected) begin
 $display("CHECK_FAIL oracle sample=%%0d got=%%b expected=%%b",sample_index,{%s},expected);
 errors=errors+1;
end
sample_index=sample_index+1;
''' % (cases, signals, signals)
    tb = re.sub(r'module\s+\w+\s*;', 'module tb;\n' + declarations, tb, count=1)
    tb = tb.replace('$fwrite(f, "%g,', checker + '$fwrite(f, "%g,', 1)
    final = '''
final begin
 if(errors==0 && sample_index==%d) $display("TESTBENCH PASS original oracle");
 else $display("CHECK_FAIL oracle errors=%%0d samples=%%0d",errors,sample_index);
end
''' % len(rows)
    return tb.replace('endmodule', final + '\nendmodule')


MUX_PRESERVE = '''module tb;
reg [3:0] a=0,b=2,c=4,d=8;reg [1:0] sel=0;wire [3:0] out;integer i;
mux_4to1_case dut(a,b,c,d,sel,out);
initial begin
#1;a=15;#2;
for(i=0;i<16;i=i+1) begin a=i;#2;
if(out!==a) begin $display("CHECK_FAIL preserve selected a");$finish;end end
$display("TESTBENCH PASS preserve");$finish;end
endmodule
'''
COUNTER_PRESERVE = '''module tb;
reg clk=0,reset=1,enable=0;wire [3:0] counter_out;wire overflow_out;integer i;
first_counter dut(clk,reset,enable,counter_out,overflow_out);
task tick;begin #3;clk=1;#3;clk=0;#3;end endtask
initial begin tick;reset=0;enable=1;
for(i=1;i<8;i=i+1) begin tick;if(counter_out!==i || overflow_out!==0) begin
$display("CHECK_FAIL preserve low count");$finish;end end
reset=1;tick;
if(counter_out!==0 || overflow_out!==0) begin $display("CHECK_FAIL reset with enable");$finish;end
$display("TESTBENCH PASS preserve");$finish;end
endmodule
'''


def prob015_checker(row):
    """Use original edge checker with immutable expected samples, not public reference RTL."""
    tb = (ROOT / row['tb_sources'][-1]).read_text()
    original = tb.replace('stats1.clocks++;',
                          '$display("ORACLE_SAMPLE %b%b%b",out1_ref,out2_ref,out3_ref);\n stats1.clocks++;')
    output = simulate({'tb.sv': original, 'ref.sv': (ROOT / row['tb_sources'][0]).read_text(),
                       'dut.sv': (ROOT / row['golden_rtl']).read_text()})
    assert 'Mismatches: 0 ' in output
    samples = re.findall(r'ORACLE_SAMPLE ([01xz]{3})', output)
    assert samples
    tb, n = re.subn(r'RefModule good1\s*\(.*?\);', '', tb, flags=re.S)
    assert n == 1
    table = 'reg [2:0] expected [0:%d];\ninitial begin\n' % (len(samples)-1)
    table += '\n'.join("expected[%d]=3'b%s;" % (i, value) for i, value in enumerate(samples))
    table += '\nend\n'
    tb = tb.replace('stats stats1;', 'stats stats1;\n' + table)
    tb = tb.replace('stats1.clocks++;', '{out1_ref,out2_ref,out3_ref}=expected[stats1.clocks];\n stats1.clocks++;')
    # tb_match is a continuous wire; compare directly after assigning this sample.
    tb = tb.replace('if (!tb_match)', 'if (!({out1_ref,out2_ref,out3_ref} === '
                    '({out1_ref,out2_ref,out3_ref}^{out1_dut,out2_dut,out3_dut}^{out1_ref,out2_ref,out3_ref})))')
    tb = tb.replace('$display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);',
                    '$display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);\n'
                    f'if(stats1.errors==0 && stats1.clocks=={len(samples)}) $display("TESTBENCH PASS original samples"); '
                    'else $display("CHECK_FAIL original samples");')
    return tb


def prepare():
    if DEST.exists():
        raise FileExistsError(DEST)
    audit = json.loads((ROOT / 'analysis/static-failure-audit/selected_candidates.json').read_text())
    old_rows = [json.loads(line) for line in (HERE / 'cases.jsonl').read_text().splitlines()]
    timing = next(row for row in old_rows if row['case_id']=='chipbench:timing:Prob015_vending_machine2')
    manifest_path = ROOT / 'deepseek-run-01/source/competition/manifests/strider14_sealed.json'
    manifest = json.loads(manifest_path.read_text())
    rows = []
    specs = {
        'Mux': 'Four-bit combinational 4:1 multiplexer. sel is a two-bit binary selector: 00 selects a, 01 b, 10 c, 11 d. Output follows the selected input when it or sel changes. Preserve the interface and all comments.\n',
        'Counter': 'Four-bit up counter on rising clk. Synchronous active-high reset clears count and overflow; enable increments count modulo 16, otherwise count holds. The independent overflow test observes the pre-edge count: if it is 15, set sticky overflow even when enable is high. Overflow holds until reset; preserve the original delayed counter assignments and reset/overflow scheduling. Preserve interface and comments.\n'}
    focus_text = {
        'Mux': 'Across five rounds build transferable repair experience for sized literal radix, truncation, duplicate case labels, selector coverage and combinational sensitivity. Generate distinct nearby defects using actual prior repair observations; preserve sel=00 behavior. Aim for reusable diagnostic experience, not copies of the held-out defect. Do not emit a solution or assume historical failures still apply.',
        'Counter': 'Across five rounds build transferable repair experience for pre-edge versus post-edge values, independent if versus else-if priority, sticky overflow, enable interaction and nonblocking scheduling. Generate distinct nearby defects using actual prior repair observations; preserve low counts and reset with enable. Aim for reusable diagnostic experience, not copies of the held-out defect. Do not emit a solution or assume historical failures still apply.',
        'Prob015': 'Across five rounds build transferable repair experience for combinational output timing versus registered outputs, asynchronous reset, input selection between clock edges, next-state hold behavior and event scheduling. Vary defects using prior real repair observations and the original sampled behavior checks. Aim for reusable diagnostic experience, not copies of the held-out defect. Do not emit a solution or assume historical failures still apply.'}
    for candidate, family in zip(audit['candidates'], ('Mux', 'Counter')):
        original = next(r for r in manifest['rows'] if r['case_id']==candidate['case_id'])
        prefix = 'deepseek-run-01/source/'
        row = dict(case_id=candidate['case_id'], family=family,
                   golden_rtl=prefix+original['golden_rtl'], buggy_rtl=prefix+original['buggy_rtl'],
                   tb_sources=[prefix+original['testbench']] if 'testbench' in original else
                   [prefix+next(f['path'] for f in original['files'] if f['role']=='testbench')],
                   oracle=prefix+original['metadata']['oracle_output'],
                   spec=str((DEST/family/'spec-source.txt').relative_to(ROOT)),
                   top_module='mux_4to1_case' if family=='Mux' else 'first_counter',
                   selection_evidence=candidate)
        write(ROOT / row['spec'], specs[family])
        rows.append(row)
    timing['selection_evidence'] = audit['latest_configuration_failures'][0]
    rows.append(timing)
    index = {}
    for row in rows:
        family = row['family']; root = DEST / family; package = root / 'package'
        clean = (ROOT / row['golden_rtl']).read_text()
        if family=='Prob015':
            clean=clean.replace('parameter S0=0', 'parameter [2:0] S0=0')
            bug_tb=prob015_checker(row); preserve=VENDING_RESET
            shortcut=clean.replace('always@(posedge clk or negedge rst)', 'always@(posedge clk)', 1)
            pairs=[('d2? S1:', 'd2? S0_5:'), ('d1? S1:', 'd1? S0_5:'),
                   ('d1? S1_5:', 'd1? S0_5:'), ('d1? S2_5:', 'd1? S3:'), ('d1? S2:', 'd1? S1:')]
        elif family=='Mux':
            bug_tb=strider_checker((ROOT / row['tb_sources'][0]).read_text(), (ROOT / row['oracle']).read_text(), 'out')
            preserve=MUX_PRESERVE;shortcut=clean.replace('out <= a;', "out <= (a==4'd3 ? b : a);")
            pairs=[("2'b01", "2'b11"), ("2'b10", "2'b01"), ('out <= c;', 'out <= b;'),
                   ('out <= d;', 'out <= c;'), ('a or b or c or d or sel', 'a or b or c or d')]
        else:
            bug_tb=strider_checker((ROOT / row['tb_sources'][0]).read_text(), (ROOT / row['oracle']).read_text(), 'counter_out,overflow_out')
            preserve=COUNTER_PRESERVE
            shortcut=clean.replace("counter_out <= #1 4'b0000;", "counter_out <= #1 (enable ? 4'b0001 : 4'b0000);")
            pairs=[("counter_out == 4'b1111", "counter_out == 4'b1110"),
                   ("overflow_out <= 1'b1;", "overflow_out <= 1'b0;"),
                   ("counter_out == 4'b1111", "counter_out == 4'b1101"),
                   ("counter_out == 4'b1111", "counter_out == 4'b1011"),
                   ("counter_out == 4'b1111", "counter_out == 4'b0111")]
        fixtures=[]
        for old,new in pairs:
            assert clean.count(old)==1, (family, old)
            fixtures.append([dict(find=old,replace=new)])
        write(package/'src'/PRIMARY,clean)
        write(package/'spec.md',(ROOT/row['spec']).read_text())
        write(package/'suites/W_bug/tb.sv',bug_tb)
        write(package/'suites/W_preserve/tb.sv',preserve)
        write(package/'variants/exam_defect'/PRIMARY,(ROOT/row['buggy_rtl']).read_text())
        write(package/'variants/preserve_control'/PRIMARY,shortcut)
        man=dict(carrier_id='selected_'+family,top_module=row['top_module'],rtl=[PRIMARY],editable=[PRIMARY],
                 spec='spec.md',parameters={},tool='icarus',defines={},include_dirs=[],pass_marker='TESTBENCH PASS',
                 fail_marker='CHECK_FAIL',build_timeout=60,sim_timeout=30,
                 source=dict(case_id=row['case_id'],original_buggy_sha256=sha(ROOT/row['buggy_rtl']),
                             repository='https://github.com/zhongkaiyu/ChipBench' if family=='Prob015' else 'https://github.com/hejy47/Strider',
                             commit='b4ba3a06759804ec88c26c3cf15b28b9a90b3443' if family=='Prob015' else 'ab13ec8861cfe35d67183a40d0da5b4b631d9639',
                             license='MIT' if family=='Prob015' else 'GPL-3.0-only',family=family),
                 suites={s:dict(files=['tb.sv'],top='tb') for s in ('W_bug','W_preserve')},
                 variants=dict(clean=dict(role='clean'),exam_defect=dict(role='defect'),preserve_control=dict(role='shortcut')))
        write(package/'carrier.json',man)
        freeze=dict(files={k:v for k,v in wm.package_files(package).items() if k!='carrier.json' and not k.startswith('variants/')},
                    frozen_manifest_fields_hash=hash_payload(wm.frozen_fields(man)))
        write(root/'suite_freeze.json',freeze)
        q=wm.qualify(package,freeze);write(root/'qualification.json',q)
        if not q['qualified']: raise ValueError((family,q['problems'],q['logs']))
        if family=='Prob015':
            # Retain the independent original reference evaluator, measurement only.
            source=HERE/'materials/Prob015/evaluator'
            for file in source.glob('*.sv'): write(root/'evaluator'/file.name,file.read_text())
        else:
            write(root/'evaluator/tb.sv',bug_tb)
        ef=dict(files={str(p.relative_to(root)):hash_payload(p.read_text()) for p in (root/'evaluator').glob('*.sv')},
                run=dict(top='tb',rtl=[PRIMARY],pass_marker='TESTBENCH PASS',fail_marker='CHECK_FAIL'))
        write(root/'evaluator_freeze.json',ef)
        task=carrier_task.export(package,'exam_defect',root/'reserved/exam_defect',freeze)
        if family=='Mux':
            seed=clean.replace('out <= c;', 'out <= d;')
        elif family=='Counter':
            seed=clean.replace("counter_out == 4'b1111", "counter_out == 4'b1010")
        else:
            seed=(ROOT/'datasets/low_pass_rate_rtl_cases/reconstructed_red/Prob015/buggy.sv').read_text()
            seed=seed.replace('parameter S0=0', 'parameter [2:0] S0=0')
        evidence=row['selection_evidence']
        history=dict(challenge_id=row['case_id'],runs=evidence.get('historical_static_runs',evidence.get('observations')),
                     unrepaired=evidence.get('historical_static_runs',evidence.get('functional_failures')),
                     label='historical_budgeted_failure_not_current_confirmation')
        focus=dict(version='continuous_mechanism_seed_v1',carrier_id=man['carrier_id'],mechanism=focus_text[family],
                   selection='human_selected_development_seed',seed_edits=[dict(find=clean,replace=seed)],history=history,
                   provenance=dict(clean_hash=hash_payload(clean),seed_hash=hash_payload(seed),
                                   record_hashes={'selection_audit':hash_payload(json.dumps(audit,sort_keys=True))}))
        data=dict(carriers=[dict(package=str(package.resolve()),suite_freeze=str((root/'suite_freeze.json').resolve()),
                                evaluator_freeze=str((root/'evaluator_freeze.json').resolve()),evaluator_root=str(root.resolve()))],
                  anchors=[dict(task_dir=str(task.resolve()),carrier_index=0)],mechanism_focus=focus,questions=[row['case_id']])
        write(root/'materials.json',data);write(root/'practice_fixtures.json',fixtures);index[family]=data
    write(DEST/'index.json',index)
    write(HERE/'cases-selected-v2.jsonl',''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    assets={path:sha(ROOT/path) for row in rows for path in
            [row['golden_rtl'],row['buggy_rtl'],row['spec'],*row['tb_sources'],*([row['oracle']] if 'oracle' in row else [])]}
    sources=[ROOT/'analysis/static-failure-audit/selected_candidates.json']
    for row in rows:
        ev=row['selection_evidence']
        if 'material_dir' in ev:
            replay=Path(ev['material_dir'])/'replay.json';sources.append(replay)
            sources.extend(ROOT/v['source'] for v in json.loads(replay.read_text())['variants'] if v.get('source'))
        else: sources.extend(ROOT/s for s in ev['sources'])
    write(HERE/'selection-selected-v2.json',dict(selected_case_ids=[r['case_id'] for r in rows],assets=assets,
         evidence={str(p.relative_to(ROOT)):sha(p) for p in sources},model_calls=0))


if __name__=='__main__': prepare()
