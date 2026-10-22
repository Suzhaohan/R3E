"""Offline-only qualification of Prob017; no training replacement pool or model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE/'source-promotion-prob017-v1'))
from experiments.loop_probes import witness_matrix as wm,carrier_task,red907,red907_measure as measure
from r3e.loop.blue_provider import apply_text_edits
from r3e.loop import red_continuous as red
from r3e.loop.repo_blue import RepoTask
from r3e.protocol.hashing import hash_payload

DEST=HERE/'materials-listed-v3'
VALIDATION=HERE/'validation-listed-v3'
PRIMARY='rtl/sequence.sv'


def save(p,data):
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def edit(a,b):return [dict(find=a,replace=b)]


PUBLIC_CHECK='''module divider_check #(parameter MN=87,C=24,E=8,O=9,ID=0)(input clk,rst);
wire result; integer count=0,cycle_count=0,mode=0; reg expected;
TopModule #(.M_N(MN),.c89(C),.div_e(E),.div_o(O)) dut(clk,rst,result);
always @(posedge clk) begin
 if(!rst) begin count=0;cycle_count=0;mode=0;expected=0;end
 else begin
  expected=(count<=((mode?O:E)/4+1));
  count=(count==((mode?O:E)-1))?0:(count+1)%16;
  if(cycle_count==MN-1 || cycle_count==C-1) mode=1-mode;
  cycle_count=(cycle_count==MN-1)?0:cycle_count+1;
 end
 #1;
 if(result!==expected) begin $display("CHECK_FAIL divider config=%0d got=%b expected=%b count=%0d cycle=%0d mode=%0d",ID,result,expected,count,cycle_count,mode);$finish;end
end
endmodule
module tb;
reg clk=0,rst=0;integer i;
divider_check #(87,24,8,9,0) a(clk,rst);
divider_check #(17,6,4,5,1) b(clk,rst);
divider_check #(47,15,12,13,2) c(clk,rst);
divider_check #(31,9,6,7,3) d(clk,rst);
initial begin
 for(i=0;i<1400;i=i+1) begin
  rst=!(i<3 || (i>=93 && i<96) || (i>=721 && i<723));
  #3;clk=1;#2;clk=0;#2;
 end
 $display("TESTBENCH PASS divider public waveform");$finish;
end
endmodule
'''
PRESERVE='''module tb;
reg clk=0,rst=0;wire clk_out;reg held;integer i;
TopModule dut(clk,rst,clk_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst=1;
 for(i=0;i<100;i=i+1) begin
  #3;clk=1;#2;held=clk_out;#1;clk=0;#1;
  if(clk_out!==held) begin $display("CHECK_FAIL output changed without rising edge");$finish;end
  if(held===1'b1) begin
   rst=0;#1;
   if(clk_out!==0) begin $display("CHECK_FAIL asynchronous reset");$finish;end
   rst=1;#1;
   if(clk_out!==0) begin $display("CHECK_FAIL reset release");$finish;end
   $display("TESTBENCH PASS divider preserve");$finish;
  end
 end
 $display("CHECK_FAIL output never became high");$finish;
end
endmodule
'''
CLARIFICATION='''

## Public waveform contract for this experiment
The original prose above contains an inconsistent numerical example (53 output cycles
in 10 input cycles). That example is not an acceptance criterion. This task repairs
the selected benchmark implementation; no ideal 8.7 average-frequency claim is made.
The following public, parameterized, registered behavior defines the required waveform.
All reset state is zero. Reset is asynchronous active low. On a rising input-clock edge
with reset released, use PRE-EDGE values of count, cycle_count and mode:
- Output becomes 1 iff count <= floor((mode ? div_o : div_e)/4) + 1, otherwise 0.
- Count becomes 0 when count == (mode ? div_o : div_e)-1; otherwise (count+1) modulo 16 (the count register is four bits).
- Mode toggles iff cycle_count equals M_N-1 or c89-1; otherwise it holds.
- Cycle_count wraps to zero at M_N-1; otherwise it increments by one modulo 128 (the cycle counter is seven bits).
All four updates take effect together. Output holds between input rising edges, except
for asynchronous reset. Parameter declarations and ports must be preserved. Public tests
include the default parameters and additional safe parameter values, with div_e/div_o
between 4 and 15 and 0<c89<M_N<=127. The independent evaluator uses further traces.
'''


def hidden_check():
 n=2048;configs=[(87,24,8,9),(29,11,10,11),(53,19,14,15)]
 parts=['module tb; reg clk=0,rst=0;integer i;']
 for index,(mn,c,e,o) in enumerate(configs):
  count=cycle=mode=0;bits=[]
  for i in range(n):
   reset=i<2 or 57<=i<60 or 899<=i<901
   if reset:count=cycle=mode=0;expected=0
   else:
    old_count,old_cycle,old_mode=count,cycle,mode
    period=o if old_mode else e
    expected=int(old_count<=period//4+1)
    count=0 if old_count==period-1 else (old_count+1)%16
    cycle=(old_cycle+1)%mn
    mode=old_mode ^ int(old_cycle in (mn-1,c-1))
   bits.append(str(expected))
  hexval=hex(int(''.join(reversed(bits)),2))[2:]
  parts.append(f"wire out{index};localparam [{n-1}:0] TRACE{index}={n}'h{hexval};\nTopModule #(.M_N({mn}),.c89({c}),.div_e({e}),.div_o({o})) dut{index}(clk,rst,out{index});")
 parts.append('initial begin for(i=0;i<2048;i=i+1) begin rst=!(i<2 || (i>=57 && i<60) || (i>=899 && i<901));#4;clk=1;#2;')
 for index in range(len(configs)):
  parts.append(f'if(out{index}!==TRACE{index}[i]) begin $display("CHECK_FAIL independent divider config={index} cycle=%0d",i);$finish;end')
 parts.append('#1;clk=0;#2;end $display("TESTBENCH PASS independent divider");$finish;end endmodule')
 return '\n'.join(parts)+'\n'


def build():
 if DEST.exists() or VALIDATION.exists():raise FileExistsError('fresh versioned material directories required')
 DEST.mkdir();VALIDATION.mkdir()
 old_selection=json.loads((HERE/'selection-listed-v2.json').read_text())
 rows=[json.loads(s) for s in (HERE/'cases-listed-v2.jsonl').read_text().splitlines()][:2]
 for d in ('Prob001','Prob023'):
  # Preserve both questions and all original frozen material bytes by reference.
  save(DEST/d/'materials.json',json.loads((HERE/'materials-listed-v2'/d/'materials.json').read_text()))
  save(VALIDATION/d/'validation.json',json.loads((HERE/'validation-listed-v2'/d/'validation.json').read_text()))
 allrows=[json.loads(s) for s in (HERE/'cases-all-v1.jsonl').read_text().splitlines()]
 row=deepcopy(next(x for x in allrows if x['case_id']=='chipbench:assignment:Prob017_arbitrary_fractional_frequency_division'))
 root=DEST/'Prob017';package=root/'package';clean=(ROOT/row['golden_rtl']).read_text();exam=(ROOT/row['buggy_rtl']).read_text()
 man=json.loads((HERE/'materials-listed-v2/Prob023/package/carrier.json').read_text())
 man.update(carrier_id='chipbench_Prob017_fractional_divider',variants={'clean':{'role':'clean'},'exam_defect':{'role':'defect'},'preserve_control':{'role':'shortcut'}})
 man['source']['family']='chipbench_Prob017_arbitrary_fractional_frequency_division'
 save(package/'carrier.json',man);save(package/'src'/PRIMARY,clean)
 save(package/'spec.md',(ROOT/row['spec']).read_text()+CLARIFICATION)
 save(root/'source_spec_original.txt',(ROOT/row['spec']).read_text())
 save(package/'suites/W_bug/tb.sv',PUBLIC_CHECK);save(package/'suites/W_preserve/tb.sv',PRESERVE)
 save(package/'variants/exam_defect'/PRIMARY,exam)
 save(package/'variants/preserve_control'/PRIMARY,clean.replace('posedge clk_in or negedge rst','posedge clk_in'))
 freeze=dict(files={k:v for k,v in wm.package_files(package).items() if k!='carrier.json' and not k.startswith('variants/')},frozen_manifest_fields_hash=hash_payload(wm.frozen_fields(man)))
 save(root/'suite_freeze.json',freeze);q=wm.qualify(package,freeze);save(root/'qualification.json',q)
 if not q['qualified']:raise ValueError(q['problems'])
 structure=red907._loop_check(package,man,'clean');save(root/'structure.json',structure)
 if structure['status']!='ok':raise ValueError(structure)
 save(root/'evaluator/tb.sv',hidden_check());ef=dict(files={'evaluator/tb.sv':hash_payload((root/'evaluator/tb.sv').read_text())},run=dict(top='tb',rtl=[PRIMARY],pass_marker='TESTBENCH PASS',fail_marker='CHECK_FAIL'))
 save(root/'evaluator_freeze.json',ef);task=carrier_task.export(package,'exam_defect',root/'reserved/exam_defect',freeze)
 actual=RepoTask.load(task)
 eq={label:measure._evaluate(actual,{PRIMARY:rtl},ef,root/'evaluator') for label,rtl in [('reference',clean),('defect',exam)]}
 save(root/'evaluator_qualification.json',eq)
 if eq['reference']['result']!='pass' or eq['defect']['result']!='fail':raise ValueError(eq)
 public=red907.public_material(package,freeze)
 # Compare both listed original versions offline, without model inference.
 version_checks={}
 from r3e.loop.repo_blue import execute
 for label in ('assignment','arithmetic'):
  candidate=next(x for x in allrows if x['case_id']==f'chipbench:{label}:Prob017_arbitrary_fractional_frequency_division')
  rtl=(ROOT/candidate['buggy_rtl']).read_text()
  version_checks[label]=dict(public=execute(actual,{PRIMARY:rtl}).tier,evaluator=measure._evaluate(actual,{PRIMARY:rtl},ef,root/'evaluator')['result'])
 save(root/'original_version_checks.json',version_checks)
 if any(x!=dict(public='visible_fail',evaluator='fail') for x in version_checks.values()):raise ValueError(version_checks)
 validations=[edit('div_o>>2','div_o>>1')+edit('M_N-1','M_N-2'),
              edit('div_e-1','div_e+1')+edit('||','&&')]
 # M_N occurs in two expressions: use one unique context in the validation edit.
 validations[0][1]=dict(find='cyc_cnt==(M_N-1)?',replace='cyc_cnt==(M_N-2)?')
 vp=VALIDATION/'Prob017/package';shutil.copytree(package,vp);vm=wm.load(vp)
 for i,edits in enumerate(validations):
  vm['variants'][f'validation_{i}']={'role':'defect'}
  save(vp/'variants'/f'validation_{i}'/PRIMARY,apply_text_edits(clean,edits))
 save(vp/'carrier.json',vm);vq=wm.qualify(vp,freeze);save(VALIDATION/'Prob017/qualification.json',vq)
 if not vq['qualified']:raise ValueError(vq['problems'])
 tasks=[str(carrier_task.export(vp,f'validation_{i}',VALIDATION/f'Prob017/task_{i}',freeze).resolve()) for i in range(2)]
 save(VALIDATION/'Prob017/validation.json',dict(tasks=tasks,repeats=2,exam_used_for_selection=False,task_bytes={t:hash_payload((Path(t)/'public/repo'/PRIMARY).read_text()) for t in tasks}))
 history=[dict(case_id=row['case_id'],model='historical DeepSeek V4 Flash; not current V3',observations=2,passed=1,sources=['09_Low_Pass_Rate_RTL_Cases.md'],setting='section 2; without register trace; one repair attempt')]
 focus=None # No historical development seed is attributed to this newly selected design.
 save(root/'materials.json',dict(carriers=[dict(package=str(package.resolve()),suite_freeze=str((root/'suite_freeze.json').resolve()),evaluator_freeze=str((root/'evaluator_freeze.json').resolve()),evaluator_root=str(root.resolve()))],anchors=[dict(task_dir=str(task.resolve()),carrier_index=0)],mechanism_focus=focus,questions=[row['case_id']]))
 # Offline qualification witnesses only. They are never saved as a replacement pool or loaded by training.
 witnesses=[edit('div_o-1','div_o+1'),edit('cyc_cnt==(M_N-1)?','cyc_cnt==(M_N+1)?'),edit('cyc_cnt==(c89-1)?','cyc_cnt==(c89+1)?'),edit('clk_cnt<=((div_e>>2)+1)','clk_cnt<=((div_e>>2)+0)'),edit('clk_cnt<=((div_o>>2)+1)','clk_cnt<=((div_o>>2)+0)')]
 forbidden={hash_payload(exam),*(hash_payload(apply_text_edits(clean,x)) for x in validations)}
 witness_records=[]
 for i,edits in enumerate(witnesses):
  p=red.materialize_batch(dict(candidates=[dict(edits=edits,violated_requirement='offline public qualification witness',spec_basis='public waveform contract')]),public)['candidates'][0]
  if p['status']!='proposal' or hash_payload(p['buggy_rtl']) in forbidden:raise ValueError(p)
  a=red907.check_proposal(package,freeze,p,root/f'offline_qualification/{i}',seen=set())
  if a['status']!='admitted':raise ValueError((i,a))
  witness_records.append(dict(identity=hash_payload(p['buggy_rtl']),qualified=True))
 save(root/'offline_qualification_summary.json',dict(model_calls=0,qualification_only=True,training_uses_these_candidates=False,witnesses=witness_records))
 row['spec']=str((package/'spec.md').relative_to(ROOT));rows.append(row)
 assets={k:v for k,v in old_selection['assets'].items() if 'Prob003' not in k and 'prob003-five-round' not in k}
 for f in (row['golden_rtl'],row['buggy_rtl'],row['spec']):assets[f]=sha(ROOT/f)
 report=dict(case_id=row['case_id'],family='Prob017',reference_passed=True,defect_failed=True,clean_nonempty_lines=sum(bool(x.strip()) for x in clean.splitlines()),historical_successes=history,practice_admitted=5,current_v3_pass_rate=None)
 save(HERE/'cases-listed-v3.jsonl',''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
 save(HERE/'selection-listed-v3.json',dict(selected_case_ids=[x['case_id'] for x in rows],assets=assets,evidence=old_selection['evidence'],rows=old_selection['rows'][:2]+[report],model_calls=0,selection_document='09_Low_Pass_Rate_RTL_Cases.md',document_sections={'Prob001':2,'Prob023':2,'Prob017':2},scope='Replace only Prob003 with original Prob017 assignment case; original RTL bytes retained; public specification inconsistency explicitly clarified; no current V3 calibration.'))
 print(json.dumps(dict(status='PASS',design='Prob017',selected=row['case_id'],model_calls=0,original_version_checks=version_checks),ensure_ascii=False))

if __name__=='__main__':build()
