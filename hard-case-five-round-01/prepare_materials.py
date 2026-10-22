"""Adapt fixed original questions to the existing W_bug/W_preserve task format."""
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT / 'prob003-five-round-03'
sys.path.insert(0, str(BASE / 'source'))
from experiments.loop_probes import witness_matrix as wm, carrier_task
from r3e.protocol.hashing import hash_payload


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))


SEQUENCE = '''module tb;
reg clk=0, rst_n=0, a=0; wire match;
reg [7:0] history=0; integer word,j,check_count=0;
TopModule dut(clk,rst_n,a,match);
task reset;
begin clk=0;rst_n=0;#2;clk=1;#2;clk=0;#2;rst_n=1;history=0;end
endtask
task bit_step(input b);
reg expected;
begin
 clk=0;a=b;#2;expected=(history==8'b01110001);clk=1;#2;
 if(match!==expected) begin $display("CHECK_FAIL sequence sample=%0d",check_count);$finish;end
 history={history[6:0],b};check_count=check_count+1;clk=0;#2;
end
endtask
initial begin
reset;
for(word=0;word<256;word=word+1) begin
 for(j=7;j>=0;j=j-1) bit_step((8'b01110001>>j)&1);
 for(j=7;j>=0;j=j-1) bit_step((word>>j)&1);
end
$display("TESTBENCH PASS sequence");$finish;
end
endmodule
'''

SEQUENCE_RESET = '''module tb;
reg clk=0,rst_n=0,a=0;wire match;integer j;
TopModule dut(clk,rst_n,a,match);
initial begin
#2;clk=1;#2;clk=0;rst_n=1;
for(j=7;j>=0;j=j-1) begin a=(8'b01110001>>j)&1;#2;clk=1;#2;clk=0;end
a=0;#2;clk=1;#2;clk=0;
rst_n=0;#2;
if(match!==0) begin $display("CHECK_FAIL asynchronous output reset");$finish;end
rst_n=1;#2;
if(match!==0) begin $display("CHECK_FAIL reset release");$finish;end
$display("TESTBENCH PASS preserve");$finish;
end
endmodule
'''

VENDING = '''module tb;
reg clk=0,rst=0,d1=0,d2=1,sel=0;wire out1,out2,out3;
integer amount=0,word,j,s,checks=0;reg [2:0] expected;
TopModule dut(clk,rst,d1,d2,sel,out1,out2,out3);
task check_outputs;
begin
 case(amount)
 0,1,2:expected=0;
 3:expected=sel?3'b000:3'b100;
 4:expected=sel?3'b000:3'b101;
 5:expected=sel?3'b010:3'b101;
 6:expected=sel?3'b011:3'b101;
 default:expected=0;
 endcase
 if({out1,out2,out3}!==expected) begin
 $display("CHECK_FAIL vending check=%0d amount=%0d sel=%b got=%b%b%b expected=%b",checks,amount,sel,out1,out2,out3,expected);$finish;end
 checks=checks+1;
end
endtask
task reset;
begin clk=0;rst=0;d1=0;d2=1;#2;clk=1;#2;clk=0;#2;rst=1;amount=0;#2;end
endtask
task coin(input one_yuan);
begin
 clk=0;d1=!one_yuan;d2=one_yuan;#2;
 if((amount==3 || amount==4) && !sel) amount=0;
 else if(amount>=5) amount=0;
 else amount=amount+(one_yuan?2:1);
 clk=1;#2;check_outputs;clk=0;#2;
end
endtask
initial begin
for(s=0;s<2;s=s+1) begin
sel=s;
for(word=0;word<64;word=word+1) begin reset;for(j=5;j>=0;j=j-1) coin((word>>j)&1);end
end
$display("TESTBENCH PASS vending");$finish;
end
endmodule
'''

VENDING_RESET = '''module tb;
reg clk=0,rst=0,d1=1,d2=0,sel=0;wire out1,out2,out3;integer j;
TopModule dut(clk,rst,d1,d2,sel,out1,out2,out3);
initial begin
#2;clk=1;#2;clk=0;rst=1;
for(j=0;j<3;j=j+1) begin #2;clk=1;#2;clk=0;end
d1=0;rst=0;#2;
if({out1,out2,out3}!==0) begin $display("CHECK_FAIL reset outputs");$finish;end
rst=1;#2;
if({out1,out2,out3}!==0) begin $display("CHECK_FAIL asynchronous state reset");$finish;end
$display("TESTBENCH PASS preserve");$finish;
end
endmodule
'''


def prepare():
    rows = [json.loads(l) for l in (HERE / 'cases.jsonl').read_text().splitlines()]
    result = {}
    for family in ('Prob001', 'Prob015'):
        chosen = [r for r in rows if r['family'] == family]
        root = HERE / 'materials' / family
        if root.exists():
            raise FileExistsError(root)
        package = root / 'package'
        clean = (ROOT / chosen[0]['golden_rtl']).read_text()
        if family == 'Prob015':
            # Material-only width annotation: all state constants are 0..6.
            # Unsized constants trigger Yosys extension-loop diagnostics in the
            # original golden. Do not weaken the unchanged structural gate.
            clean = clean.replace('parameter S0=0', 'parameter [2:0] S0=0')
        primary = 'rtl/sequence.sv'  # keep the latest runner's editable scope
        write(package / 'src' / primary, clean)
        write(package / 'spec.md', (ROOT / chosen[0]['spec']).read_text())
        write(package / 'suites/W_bug/tb.sv', SEQUENCE if family == 'Prob001' else VENDING)
        write(package / 'suites/W_preserve/tb.sv', SEQUENCE_RESET if family == 'Prob001' else VENDING_RESET)
        variants = {'clean': {'role': 'clean'}, 'reset_control': {'role': 'shortcut'}}
        shortcut = clean.replace('always @(posedge clk or negedge rst_n)', 'always @(posedge clk)', 1) if family == 'Prob001' else clean.replace('always@(posedge clk or negedge rst)', 'always@(posedge clk)', 1)
        write(package / 'variants/reset_control' / primary, shortcut)
        names = []
        for r in chosen:
            name = 'exam_' + r.get('bug_type', 'defect')
            names.append(name)
            variants[name] = {'role': 'defect'}
            write(package / 'variants' / name / primary, (ROOT / r['buggy_rtl']).read_text())
        man = dict(carrier_id='chipbench_' + family + '_fixed_hard_questions', top_module='TopModule',
                   rtl=[primary], editable=[primary], spec='spec.md', parameters={}, tool='icarus',
                   defines={}, include_dirs=[], pass_marker='TESTBENCH PASS', fail_marker='CHECK_FAIL',
                   build_timeout=60, sim_timeout=30,
                   source=dict(repository='https://github.com/zhongkaiyu/ChipBench',
                               commit='b4ba3a06759804ec88c26c3cf15b28b9a90b3443', license='MIT', family=family),
                   suites={s: {'files': ['tb.sv'], 'top': 'tb'} for s in ('W_bug', 'W_preserve')}, variants=variants)
        write(package / 'carrier.json', man)
        freeze = dict(files={k: v for k, v in wm.package_files(package).items()
                             if k != 'carrier.json' and not k.startswith('variants/')},
                      frozen_manifest_fields_hash=hash_payload(wm.frozen_fields(man)))
        write(root / 'suite_freeze.json', freeze)
        qualification = wm.qualify(package, freeze)
        write(root / 'qualification.json', qualification)
        if not qualification['qualified']:
            raise ValueError(qualification['problems'])
        # The original converted reference test remains measurement-only.
        tb = (ROOT / chosen[0]['tb_sources'][-1]).read_text()
        tb = tb.replace('$display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);',
                        '$display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);\n'
                        'if(stats1.errors==0) $display("TESTBENCH PASS evaluator"); else $display("CHECK_FAIL evaluator mismatches");')
        write(root / 'evaluator/tb.sv', tb)
        write(root / 'evaluator/ref.sv', (ROOT / chosen[0]['tb_sources'][0]).read_text())
        ef = dict(files={str(f.relative_to(root)): hash_payload(f.read_text()) for f in (root / 'evaluator').glob('*.sv')},
                  run=dict(top='tb', rtl=[primary], pass_marker='TESTBENCH PASS', fail_marker='CHECK_FAIL'))
        write(root / 'evaluator_freeze.json', ef)
        anchors = []
        for name in names:
            task = carrier_task.export(package, name, root / 'reserved' / name, freeze)
            anchors.append(dict(task_dir=str(task.resolve()), carrier_index=0))
        if family == 'Prob001':
            seed = (ROOT / chosen[0]['buggy_rtl']).read_text()
            history = dict(challenge_id=chosen[0]['case_id'], runs=3, unrepaired=2,
                           label='historical_budgeted_failure_not_current_confirmation')
            mechanism = chosen[0]['mechanism']
            fixtures = [[{'find': clean, 'replace': clean.replace("8'b0111_0001", f"8'b{v:08b}")}]
                        for v in (0x70, 0x72, 0x61, 0x51, 0x31)]
        else:
            seed = (ROOT / 'datasets/low_pass_rate_rtl_cases/reconstructed_red/Prob015/buggy.sv').read_text()
            seed = seed.replace('parameter S0=0', 'parameter [2:0] S0=0')
            history = dict(challenge_id='reconstructed:RC_02caa510ba2821', runs=3, unrepaired=1,
                           label='historical_budgeted_failure_not_current_confirmation')
            mechanism = chosen[0]['mechanism']
            fixtures = []
            for old, new in [('d2? S1:', 'd2? S0_5:'), ('d1? S1:', 'd1? S0_5:'),
                             ('d1? S1_5:', 'd1? S0_5:'), ('d1? S2_5:', 'd1? S3:'), ('d1? S2:', 'd1? S1:')]:
                assert clean.count(old) == 1
                fixtures.append([{'find': old, 'replace': new}])
        focus = dict(version='continuous_mechanism_seed_v1', carrier_id=man['carrier_id'],
                     mechanism=mechanism, selection='human_selected_development_seed',
                     seed_edits=[{'find': clean, 'replace': seed}], history=history,
                     provenance={'clean_hash': hash_payload(clean), 'seed_hash': hash_payload(seed),
                                 'record_hashes': {'selection.json': hash_payload((HERE / 'selection.json').read_text())}})
        data = dict(carriers=[dict(package=str(package.resolve()), suite_freeze=str((root / 'suite_freeze.json').resolve()),
                                   evaluator_freeze=str((root / 'evaluator_freeze.json').resolve()), evaluator_root=str(root.resolve()))],
                    anchors=anchors, mechanism_focus=focus,
                    questions=[r['case_id'] for r in chosen])
        write(root / 'materials.json', data)
        write(root / 'practice_fixtures.json', fixtures)
        result[family] = data
    write(HERE / 'materials/index.json', result)
    return result


if __name__ == '__main__':
    prepare()
