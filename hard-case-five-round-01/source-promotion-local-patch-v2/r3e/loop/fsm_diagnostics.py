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
        localization=localize_trace(target,rtl,traces),
        failure=failure_lines,limitation='Numeric states describe this submitted candidate; expected outputs derive only from the public group contract.')


FOCUS_VERSION='prob003_public_fault_focus_v1'
_TRACE=re.compile(r'PUBLIC_FSM_TRACE cycle=(\d+) position=(\d+) sampled_prefix=([01]{6}) pre_state=(-?\d+) pre_next=(-?\d+) post_state=(-?\d+) actual=([01xz]{2}) expected=([01]{2})')


def state_tables(source):
    """Read only supported, literal public case arms. Never guess a missing arm."""
    text=re.sub(r'//[^\n]*|/\*.*?\*/',' ',source,flags=re.S)
    constants={}
    declarations=' '.join(re.findall(r'\b(?:parameter|localparam)\b([^;]+);',text,re.S))
    for name,base,value in re.findall(r"\b(\w+)\s*=\s*\d+'([dDhHbB])([0-9a-fA-F_]+)",declarations):
        try:constants[name]=int(value.replace('_',''),{'d':10,'h':16,'b':2}[base.lower()])
        except ValueError:continue
    case=re.search(r'\bcase\s*\(\s*pstate\s*\)(.*?)\bendcase\b',text,re.S)
    if not case:return constants,{}
    arms={}
    pattern=r'(?m)^\s*([A-Za-z_]\w*)\s*:\s*(.*?)(?=^\s*[A-Za-z_]\w*\s*:|\Z)'
    for match in re.finditer(pattern,case[1],re.S):
        name,body=match[1],match[2].strip()
        direct=re.fullmatch(r'nstate\s*=\s*(\w+)\s*;',body)
        ternary=re.fullmatch(r'nstate\s*=\s*data\s*\?\s*(\w+)\s*:\s*(\w+)\s*;',body)
        conditional=re.fullmatch(r'if\s*\(\s*data\s*==\s*([01])\s*\)\s*nstate\s*=\s*(\w+)\s*;\s*else\s*nstate\s*=\s*(\w+)\s*;',body,re.S)
        row=None
        if direct:row={'0':direct[1],'1':direct[1]}
        elif ternary:row={'0':ternary[2],'1':ternary[1]}
        elif conditional:row={conditional[1]:conditional[2],str(1-int(conditional[1])):conditional[3]}
        if row is not None and all(v in constants for v in row.values()):arms[name]=row
    return constants,arms


def localize_trace(target,source,records):
    """Separate observed failure from a state-context conflict; no reference FSM.

    State-context conflict is a localization hint for the public single-state FSM,
    not proof of a unique faulty expression or an expected numeric state.
    """
    constants,arms=state_tables(source)
    names={value:name for name,value in constants.items()}
    rows=[];seen={};conflict=None
    for line in records:
        match=_TRACE.fullmatch(line)
        if not match:continue
        cycle,position=int(match[1]),int(match[2]);prefix=match[3][-position:]
        pre,next_state,post=map(int,match.group(4,5,6))
        if cycle==1:seen={pre:dict(cycle=0,position=0,prefix_valid=None)}
        valid=prefix==target[:position]
        context=dict(cycle=cycle,position=position%6,prefix_valid=valid if position<6 else None)
        previous=seen.get(post)
        if previous and (previous['position'],previous['prefix_valid'])!=(context['position'],context['prefix_valid']) and conflict is None:
            conflict=dict(cycle=cycle,post_state=post,state_name=names.get(post),earlier_context=previous,current_context=context,
                interpretation='The same candidate state was observed at incompatible group positions or prefix-validity contexts. For a pstate-only FSM this can lose information needed to classify later inputs. Inspect this transition and its incoming path; it is not a supplied repair.')
        seen.setdefault(post,context)
        row=dict(cycle=cycle,position=position,input_bit=int(prefix[-1]),consumed_prefix=prefix,prefix_matches_target=valid,
            pre_state=pre,pre_state_name=names.get(pre),observed_next=next_state,post_state=post,post_state_name=names.get(post),actual=match[7],expected=match[8])
        table=arms.get(names.get(pre))
        if table:
            selected=table[str(row['input_bit'])]
            row['current_branch']=dict(input_0=table['0'],input_1=table['1'],selected=selected,agrees_with_simulator=constants[selected]==next_state)
        rows.append(row)
    failed=next((r for r in rows if r['actual']!=r['expected']),None)
    if not rows:return dict(version=FOCUS_VERSION,status='unavailable',reason='unsupported trace records')
    focus=conflict['cycle'] if conflict else failed['cycle'] if failed else None
    selected=[r for r in rows if focus is not None and focus-2<=r['cycle']<=focus+2]
    if failed and failed['cycle']<=6:selected=[r for r in rows if r['cycle']<=failed['cycle']]
    if failed and failed not in selected:selected.append(failed)
    if failed and failed['cycle']<=6:
        method='The first group already fails. Inspect its consumed-prefix path before editing a transition used only after a completed group.'
    else:
        method='Follow the observed group boundary and position progression; check how the next group first bit is consumed. Preserve branches not implicated by public evidence.'
    return dict(version=FOCUS_VERSION,status='observed',source='current submitted RTL, public specification and same public test only',
        first_output_mismatch=failed,earliest_observed_state_context_conflict=conflict,focus_window=selected,
        repair_focus=method,limitation='An output mismatch is observed. A context conflict is a hint for a pstate-only architecture; finite public traces cannot always uniquely locate the original faulty expression. No expected state target or reference patch is provided.')


def failure_focus(task_id,specification,evidence):
    if target_from_spec(task_id,specification) is None:return None
    rows={name:row['public_state_trace']['localization'] for name,row in evidence.get('suites',{}).items()
          if row.get('public_state_trace',{}).get('localization',{}).get('status')=='observed'}
    return dict(version=FOCUS_VERSION,suites=rows,scope='current sample public evidence only') if rows else None


def attempt_delta(task_id,specification,before,after,before_evidence,after_evidence):
    """Feedback about this sample's most recent patch, never another sample/run."""
    if target_from_spec(task_id,specification) is None:return None
    from .online_mutation import tokens
    import difflib
    changes=[]
    for file in sorted(set(before)|set(after)):
        old,new=before.get(file,''),after.get(file,'')
        if old==new:continue
        old_params,old_arms=state_tables(old);new_params,new_arms=state_tables(new)
        branches=[]
        for name in sorted(set(old_arms)&set(new_arms)):
            a,b=old_arms[name],new_arms[name]
            if a!=b:branches.append(dict(state=name,before=a,after=b,
                swapped_binary_targets=a['0']==b['1'] and a['1']==b['0'] and a['0']!=a['1']))
        drop_sensitivity=lambda text:re.sub(r'\balways\s*@\s*\([^)]*\)','always @(*)',text)
        same_tokens=tokens(old)==tokens(new)
        sensitivity_only=not same_tokens and tokens(drop_sensitivity(old))==tokens(drop_sensitivity(new))
        changes.append(dict(file=file,token_sequence_unchanged=same_tokens,only_sensitivity_lists_changed=sensitivity_only,
            branch_truth_table_changes=branches,patch='\n'.join(difflib.unified_diff(old.splitlines(),new.splitlines(),n=1))[:2200]))
    signatures=lambda ev:{name:row.get('log','') for name,row in ev.get('suites',{}).items() if row.get('result') not in ('visible_pass',None)}
    old_sig,new_sig=signatures(before_evidence),signatures(after_evidence)
    unchanged_failure=bool(old_sig and new_sig and old_sig==new_sig)
    no_token_change=not changes or all(c['token_sequence_unchanged'] for c in changes)
    notes=[]
    if no_token_change:notes.append('The last submission made no syntax-token change. Formatting/comments alone did not repair the failing behavior.')
    if changes and all(c['only_sensitivity_lists_changed'] or c['token_sequence_unchanged'] for c in changes):
        notes.append('Only sensitivity lists or formatting changed. Use the observed transition/prefix evidence before proposing another unrelated change; unchanged failure is not evidence of a state-transition repair.')
    if unchanged_failure:notes.append('The public failure marker is unchanged after the last submission. Revisit the first implicated input/branch; do not repeat the same patch.')
    notes.append('Truth tables are mechanically decoded from your actual before/after sources. In data ? A : B, input 1 chooses A and input 0 chooses B. A swapped branch is not automatically a repair.')
    return dict(version=FOCUS_VERSION,source='this sample immediately preceding attempt only',changes=changes,
        no_syntax_token_change=no_token_change,public_failure_unchanged=unchanged_failure,feedback=notes,
        current_fault_focus=failure_focus(task_id,specification,after_evidence))
