"""Select complex existing failed cases and construct question materials offline."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from prepare_selected import strider_checker,simulate,write,wm,carrier_task,hash_payload

DEST=HERE/'materials-medium-high-v2'
VALIDATION=HERE/'validation-medium-high-v2'
AUDIT=ROOT/'analysis/medium-high-selection-20261016'
PRIMARY='rtl/sequence.sv'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


ARBITER_PRESERVE='''module tb;
reg clock=0,reset=1,req_0=0,req_1=0,req_2=0,req_3=0;
wire gnt_0,gnt_1,gnt_2,gnt_3;
fsm_full dut(clock,reset,req_0,req_1,req_2,req_3,gnt_0,gnt_1,gnt_2,gnt_3);
task tick;begin #3;clock=1;#3;clock=0;#3;end endtask
initial begin tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==0) begin $display("CHECK_FAIL reset");$finish;end
reset=0;req_0=1;req_1=1;tick;tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==4'b1000) begin $display("CHECK_FAIL priority and hold");$finish;end
reset=1;tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==0) begin $display("CHECK_FAIL reset grant");$finish;end
$display("TESTBENCH PASS preserve");$finish;
end
endmodule
'''


def edit(old,new): return [{'find':old,'replace':new}]


def apply(clean,edits):
 for e in edits:
  assert clean.count(e['find'])==1,e['find']
  clean=clean.replace(e['find'],e['replace'])
 return clean


def build():
 if DEST.exists() or VALIDATION.exists():raise FileExistsError('new material directories required')
 oldrows=[json.loads(l) for l in (HERE/'cases-selected-v2.jsonl').read_text().splitlines()]
 timing=next(r for r in oldrows if r['family']=='Prob015')
 timing=dict(timing,family='VendingTiming')
 manifest=ROOT/'deepseek-run-01/source/competition/manifests/strider14_sealed.json'
 original=next(r for r in json.loads(manifest.read_text())['rows'] if r['case_id']=='strider:fsm_full_3')
 prefix='deepseek-run-01/source/'
 arbiter=dict(case_id=original['case_id'],family='Arbiter',golden_rtl=prefix+original['golden_rtl'],
              buggy_rtl=prefix+original['buggy_rtl'],tb_sources=[prefix+next(f['path'] for f in original['files'] if f['role']=='testbench')],
              oracle=prefix+original['metadata']['oracle_output'],top_module='fsm_full',
              spec=str((DEST/'Arbiter/spec-source.txt').relative_to(ROOT)))
 write(ROOT/arbiter['spec'],'''Four-agent synchronous arbitration FSM, preserving the original cycle contract.
Inputs: clock, active-high synchronous reset, req_0..req_3. Outputs: registered gnt_0..gnt_3.
IDLE chooses the lowest numbered asserted request. Each grant state holds while its own request remains asserted; otherwise it returns to IDLE.
On a rising edge, state takes the combinational next state. Registered grants use the pre-edge current state: IDLE clears all grants; a grant state asserts its own grant and otherwise holds existing grant registers. Reset clears state and all grants.
Combinational next-state evaluation must respond to changes of state as well as requests. Define defaults for unspecified states. Preserve interfaces, parameters, comments, and the original #1 delayed sequential assignments. The frozen public trace defines exact sample timing.
''')
 task=ROOT/'hard-case-five-round-01/real-all-20261015-224806/Prob015/collection/rounds/4/r4_s0/admission/blue_task'
 state=dict(case_id='historical:selected_Prob015__083cb0fcc7f0d5d3',family='VendingState',
            golden_rtl=str((task/'oracle/clean'/PRIMARY).relative_to(ROOT)),
            buggy_rtl=str((task/'public/repo'/PRIMARY).relative_to(ROOT)),
            spec=str((task/'public/spec.txt').relative_to(ROOT)),top_module='TopModule',tb_sources=timing['tb_sources'])
 rows=[arbiter,timing,state]
 evidence=[manifest,AUDIT/'summary.json',AUDIT/'records.jsonl',AUDIT/'selected_originals/fsm_full_3/replay.json',
           task/'export.json',task.parent/'proposal.json',task.parent/'../reference/blue/encounters.jsonl',
           task.parent/'../reference/delivery.json']
 # Resolve parent-relative archive provenance without storing ambiguous paths.
 evidence=[p.resolve() for p in evidence]
 report=[]
 for row in rows:
  family=row['family'];root=DEST/family;package=root/'package'
  clean=(ROOT/row['golden_rtl']).read_text()
  if family=='Arbiter':
   tb=(ROOT/row['tb_sources'][0]).read_text().replace('module fsm_full_tb();','module tb;')
   bug_tb=strider_checker(tb,(ROOT/row['oracle']).read_text(),'gnt_0,gnt_1,gnt_2,gnt_3')
   # Match the original oracle's unknown-bit don't-care semantics.
   bug_tb=bug_tb.replace('if ({gnt_0,gnt_1,gnt_2,gnt_3} !== expected)',
                         'if (!(expected === (expected ^ {gnt_0,gnt_1,gnt_2,gnt_3} ^ expected)))')
   preserve=ARBITER_PRESERVE
   shortcut=clean.replace("gnt_0 <= #1 1'b1;","gnt_0 <= #1 (req_1 ? 1'b0 : 1'b1);")
   seed=edit('next_state= GNT2;','next_state= GNT1;')
   val1=edit('always @ (state or req_0 or req_1 or req_2 or req_3)', 'always @ (req_0 or req_1 or req_2 or req_3)')+edit('  next_state = 0;\n','')+edit('   default : next_state = IDLE;\n','')+edit("gnt_3 <= #1 1'b1;","gnt_3 <= #1 1'b0;")
   val2=edit('always @ (state or req_0 or req_1 or req_2 or req_3)', 'always @ (state or req_0 or req_2 or req_3)')+edit('next_state= GNT3;','next_state= GNT1;')
   fixtures=[edit('next_state= GNT1;','next_state= GNT2;'),edit('next_state= GNT3;','next_state= GNT2;'),
             edit("gnt_2 <= #1 1'b1;","gnt_2 <= #1 1'b0;"),edit("gnt_3 <= #1 1'b1;","gnt_3 <= #1 1'b0;"),
             edit('always @ (state or req_0 or req_1 or req_2 or req_3)','always @ (state or req_0 or req_1 or req_3)')]
   focus='Across five rounds build transferable repair experience for the held-out arbitration FSM: event-driven combinational sensitivity to state and held requests, complete next-state defaults, current-state versus next-state registered grants, request priority and release timing. Sequence early practice around event sensitivity/defaults, then combine timing and state-transition interactions; use actual prior repair results to choose distinct follow-up defects. Preserve reset and priority-0 behavior. Teach reusable diagnosis and repair patches, not copies of the fixed exam defect. Do not treat old failures as current-model probabilities.'
   history=dict(challenge_id=row['case_id'],runs=3,unrepaired=2,label='historical_budgeted_failure_not_current_confirmation')
   source=dict(repository=original['source']['url'],commit=original['source']['commit'],license=original['source']['license'],family=family)
  else:
   old=HERE/'materials-selected-v2/Prob015'
   if family=='VendingTiming':clean=clean.replace('parameter S0=0','parameter [2:0] S0=0')
   bug_tb=(old/'package/suites/W_bug/tb.sv').read_text();preserve=(old/'package/suites/W_preserve/tb.sv').read_text()
   shortcut=clean.replace('always@(posedge clk or negedge rst)','always@(posedge clk)',1)
   fixtures=[edit('d2? S1:','d2? S0_5:'),edit('d1? S2_5:','d1? S3:'),edit('d1? S2:','d1? S1:'),
             edit('d2? S2:','d2? S0_5:'),edit("S2_5        : {out1, out2, out3} = ~sel? 3'b101: 3'b010;","S2_5        : {out1, out2, out3} = ~sel? 3'b000: 3'b010;")]
   seed=edit('d2? S1_5:','d2? S1:')
   val1=edit('d1? S1:','d1? S0_5:')+edit('d2? S3:','d2? S2_5:')
   val2=edit('d1? S1_5:','d1? S0_5:')+edit("S3          : {out1, out2, out3} = ~sel? 3'b101: 3'b011;","S3          : {out1, out2, out3} = ~sel? 3'b101: 3'b010;")
   if family=='VendingTiming':
    focus='Across five rounds build transferable repair experience for the fixed seven-state vending output-timing defect: registered versus combinational outputs, use of current state versus predicted next state, asynchronous reset, input changes between clock edges, and avoiding unrelated next-state rewrites. Include distinct nearby temporal defects as well as state/output interactions; adapt later challenges to actual prior repair observations. Preserve the public specification and reset behavior. Do not copy the exam mutation or present reference implementation to Blue.'
    history=dict(challenge_id=row['case_id'],runs=2,unrepaired=2,label='historical_budgeted_failure_not_current_confirmation')
   else:
    focus='Across five rounds build transferable repair experience for the fixed seven-state vending transition defect: distinguish half-yuan and one-yuan increments, d1/d2 priority, transitions at intermediate balances, selection-dependent return-to-zero and change outputs, next-state hold behavior and simulation scheduling. Prefer varied linked transition/output defects that require tracing multi-cycle coin sequences; avoid merely swapping arbitrary output constants. Use actual prior repair results to decide follow-up practice. Preserve asynchronous reset and avoid copies of the fixed exam mutation.'
    history=dict(challenge_id=row['case_id'],runs=1,unrepaired=1,label='historical_budgeted_failure_not_current_confirmation')
   source=dict(repository='https://github.com/zhongkaiyu/ChipBench',commit='b4ba3a06759804ec88c26c3cf15b28b9a90b3443',license='MIT',family=family)
  write(package/'src'/PRIMARY,clean);write(package/'spec.md',(ROOT/row['spec']).read_text())
  write(package/'suites/W_bug/tb.sv',bug_tb);write(package/'suites/W_preserve/tb.sv',preserve)
  variants={'clean':{'role':'clean'},'exam_defect':{'role':'defect'},'preserve_control':{'role':'shortcut'}}
  write(package/'variants/exam_defect'/PRIMARY,(ROOT/row['buggy_rtl']).read_text())
  write(package/'variants/preserve_control'/PRIMARY,shortcut)
  man=dict(carrier_id='medium_high_'+family,top_module=row['top_module'],rtl=[PRIMARY],editable=[PRIMARY],spec='spec.md',
           parameters={},tool='icarus',defines={},include_dirs=[],pass_marker='TESTBENCH PASS',fail_marker='CHECK_FAIL',
           build_timeout=60,sim_timeout=30,source=source,suites={s:{'files':['tb.sv'],'top':'tb'} for s in ('W_bug','W_preserve')},variants=variants)
  write(package/'carrier.json',man)
  freeze=dict(files={k:v for k,v in wm.package_files(package).items() if k!='carrier.json' and not k.startswith('variants/')},frozen_manifest_fields_hash=hash_payload(wm.frozen_fields(man)))
  write(root/'suite_freeze.json',freeze)
  q=wm.qualify(package,freeze);write(root/'qualification.json',q)
  if not q['qualified']:raise ValueError((family,q['problems'],q['logs']))
  if family=='Arbiter':write(root/'evaluator/tb.sv',bug_tb)
  else:
   for p in (HERE/'materials-selected-v2/Prob015/evaluator').glob('*.sv'):write(root/'evaluator'/p.name,p.read_text())
  ef=dict(files={str(p.relative_to(root)):hash_payload(p.read_text()) for p in (root/'evaluator').glob('*.sv')},run=dict(top='tb',rtl=[PRIMARY],pass_marker='TESTBENCH PASS',fail_marker='CHECK_FAIL'))
  write(root/'evaluator_freeze.json',ef)
  exam=carrier_task.export(package,'exam_defect',root/'reserved/exam_defect',freeze)
  seed_code=apply(clean,seed)
  focus_data=dict(version='continuous_mechanism_seed_v1',carrier_id=man['carrier_id'],mechanism=focus,selection='human_selected_development_seed',seed_edits=seed,history=history,
                  provenance=dict(clean_hash=hash_payload(clean),seed_hash=hash_payload(seed_code),record_hashes={'selection_audit':hash_payload((AUDIT/'summary.json').read_text())}))
  data=dict(carriers=[dict(package=str(package.resolve()),suite_freeze=str((root/'suite_freeze.json').resolve()),evaluator_freeze=str((root/'evaluator_freeze.json').resolve()),evaluator_root=str(root.resolve()))],
            anchors=[dict(task_dir=str(exam.resolve()),carrier_index=0)],mechanism_focus=focus_data,questions=[row['case_id']])
  write(root/'materials.json',data);write(root/'practice_fixtures.json',fixtures)
  # Independent validation variants remain question material; no new gate mechanism.
  vp=VALIDATION/family/'package';shutil.copytree(package,vp);vm=wm.load(vp)
  for i,edits in enumerate((val1,val2)):
   name='validation_'+str(i);vm['variants'][name]={'role':'defect'};write(vp/'variants'/name/PRIMARY,apply(clean,edits))
  write(vp/'carrier.json',vm);vq=wm.qualify(vp,freeze);write(VALIDATION/family/'qualification.json',vq)
  if not vq['qualified']:raise ValueError((family,vq['problems'],vq['logs']))
  tasks=[str(carrier_task.export(vp,'validation_'+str(i),VALIDATION/family/('task_'+str(i)),freeze).resolve()) for i in range(2)]
  write(VALIDATION/family/'validation.json',dict(tasks=tasks,repeats=2,exam_used_for_selection=False,task_bytes={t:hash_payload((Path(t)/'public/repo'/PRIMARY).read_text()) for t in tasks}))
  write(VALIDATION/family/'training_fixtures.json',fixtures)
  # Replay the latest stored static candidate for the selected historical state defect.
  if family=='VendingState':
   blue=task.parent.parent/'reference/blue';enc=json.loads((blue/'encounters.jsonl').read_text().splitlines()[0])['result']
   assert enc['attempts'][-1]['tier']=='visible_fail'
   assert json.loads((blue.parent/'delivery.json').read_text())['payload']['entries']==[]
   archive=next(p for p in (blue/'archive').glob('*.json') if json.loads(p.read_text())['candidate_hash']==enc['final_candidate_hash'])
   candidate=json.loads(archive.read_text())['files'][PRIMARY]
   out=simulate({'dut.sv':candidate,'tb.sv':bug_tb})
   assert 'CHECK_FAIL' in out
   evidence.append(archive)
  stripped=re.sub(r'//[^\n]*|/\*.*?\*/','',clean,flags=re.S)
  metrics=dict(noncomment_lines=sum(bool(l.strip()) for l in stripped.splitlines()),always_blocks=len(re.findall(r'\balways\b',stripped)),case_blocks=len(re.findall(r'\bcase\s*\(',stripped)),register_declarations=len(re.findall(r'\breg\b',stripped)))
  report.append(dict(case_id=row['case_id'],family=family,complexity=metrics,history=history,reference_passed=True,defect_failed=True))
 assets={p:sha(ROOT/p) for row in rows for p in [row['golden_rtl'],row['buggy_rtl'],row['spec'],*row['tb_sources'],*([row['oracle']] if 'oracle' in row else [])]}
 write(HERE/'cases-medium-high-v2.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 write(HERE/'selection-medium-high-v2.json',dict(selected_case_ids=[r['case_id'] for r in rows],assets=assets,evidence={str(p.relative_to(ROOT)):sha(p) for p in evidence},rows=report,model_calls=0))
 write(AUDIT/'chosen_medium_high.json',dict(selected=report,model_calls=0,scope='Observed historical difficulty and code complexity; not a V3 probability estimate',fsm_replay='one of nine saved candidates passes function; do not describe as functional zero-pass',excluded=['Mux: small combinational decode','Counter: newer static 2/2','Prob017: contradictory original specification']))

if __name__=='__main__':build()
