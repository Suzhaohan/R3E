"""Public-only FSM observations; auxiliary traces never determine the scored verdict."""
from __future__ import annotations
import re
from pathlib import Path

VERSION='public_group_trace_v1'


def target_from_spec(task_id, specification):
    if 'prob003' not in task_id.lower():return None
    targets=set(re.findall(r'(?<![01])([01]{6})(?![01])',specification))
    return next(iter(targets)) if len(targets)==1 else None


def worksheet(task_id,specification):
    target=target_from_spec(task_id,specification)
    if target is None:return None
    return dict(version=VERSION,source='public specification only',target=target,
        positions=[dict(position=i,matching_prefix=target[:i],consumed_bits=i,
                        expected_outputs='match=1, not_match=0 for target; otherwise match=0, not_match=1' if i==6 else 'match=0, not_match=0') for i in range(1,7)],
        boundary='After a completed group, the very next edge consumes position 1 of the next group, on both the matching and mismatching path.',
        trace_legend='pre_state and pre_next are the submitted implementation BEFORE the edge; post_state and outputs are observed after nonblocking updates. Names and numeric values come from the current source. The trace is not a reference-state table.',
        repair_method='Compare the observed prefix validity and consumed-bit count with the submitted transitions. Locate the earliest divergence before editing. Preserve independently correct paths and check successive groups without reset.')


def trace_failure(task,repo:Path,harness:Path,suite,original_output:str,run,build_timeout,sim_timeout):
    """Replay only the same public failing suite with a passive probe in scratch files.

    Reads no oracle, clean carrier, exam answer, validation or other trial. If the
    candidate architecture has changed, or the probe cannot reproduce the exact
    public failure, leave the original evidence and verdict alone.
    """
    target=target_from_spec(task.task['task_id'],task.spec)
    if target is None:return None
    failure_lines=[l for l in original_output.splitlines() if task.build['fail_marker'] in l]
    if not failure_lines:return None
    rtl='\n'.join((repo/f).read_text() for f in task.build['rtl'])
    if not re.search(r'\breg\s*\[[^]]+\]\s*pstate\s*,\s*nstate\s*;',rtl):
        return dict(version=VERSION,status='unavailable',reason='candidate has no supported public pstate/nstate pair')
    selected=None
    for name in suite['files']:
        text=(harness/name).read_text()
        instance=re.search(r'\bTopModule\s+(\w+)\s*\(\s*clk\s*,\s*rst_n\s*,\s*data\s*,',text)
        if instance and len(re.findall(r'\bmodule\b',text))==1:
            selected=(name,text,instance[1]);break
    if selected is None:return dict(version=VERSION,status='unavailable',reason='unsupported public harness shape')
    name,text,dut=selected
    probe='''
// Passive public diagnostic observer: never drives a DUT or test signal.
integer r3e_public_cycle=0, r3e_public_phase=0;
integer r3e_public_pre, r3e_public_next;
reg [5:0] r3e_public_word=0;
reg [1:0] r3e_public_expected;
always @(posedge clk or negedge rst_n) begin
 if(!rst_n) begin r3e_public_cycle=0; r3e_public_phase=0; r3e_public_word=0; end
 else begin
  r3e_public_cycle=r3e_public_cycle+1;
  r3e_public_phase=(r3e_public_phase%6)+1;
  if(r3e_public_phase==1) r3e_public_word=0;
  r3e_public_word={r3e_public_word[4:0],data};
  r3e_public_pre=DUT.pstate; r3e_public_next=DUT.nstate;
  r3e_public_expected=(r3e_public_phase==6)?((r3e_public_word==6'bTARGET)?2'b10:2'b01):2'b00;
  #1;
  $display("PUBLIC_FSM_TRACE cycle=%0d position=%0d sampled_prefix=%b pre_state=%0d pre_next=%0d post_state=%0d actual=%b%b expected=%b",r3e_public_cycle,r3e_public_phase,r3e_public_word,r3e_public_pre,r3e_public_next,DUT.pstate,match,not_match,r3e_public_expected);
 end
end
'''.replace('DUT',dut).replace('TARGET',target)
    diagnostic=harness/(Path(name).stem+'_public_probe.sv')
    diagnostic.write_text(text[:text.rfind('endmodule')]+probe+'\nendmodule\n')
    binary=harness/(suite['name']+'_public_probe.vvp')
    sources=[str(diagnostic if f==name else harness/f) for f in suite['files']]
    try:
        rc,_=run(['iverilog','-g2012','-s',suite['top'],'-o',str(binary),*task.build['rtl'],*sources],repo,min(build_timeout,10))
        if rc!=0:return dict(version=VERSION,status='unavailable',reason='passive probe could not compile; original verdict retained')
        rc,out=run(['vvp','-n',str(binary)],repo,min(sim_timeout,10))
    except OSError:
        return dict(version=VERSION,status='unavailable',reason='diagnostic tool unavailable; original verdict retained')
    reproduced=rc==0 and all(line in out.splitlines() for line in failure_lines)
    if not reproduced:return dict(version=VERSION,status='unavailable',reason='diagnostic replay did not reproduce original public failure')
    traces=[line for line in out.splitlines() if line.startswith('PUBLIC_FSM_TRACE ')]
    return dict(version=VERSION,status='observed',source='same public test and submitted RTL only',
        scoring_unchanged=True,failure_reproduced=True,records=traces[-14:],
        failure=failure_lines,limitation='Numeric states describe this submitted candidate; expected outputs derive only from the public group contract.')
