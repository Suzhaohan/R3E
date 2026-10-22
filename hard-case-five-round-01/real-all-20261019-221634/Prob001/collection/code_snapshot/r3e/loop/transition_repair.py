"""Prob003-only model-supplied transition edits. No solver or reference-code input."""
from __future__ import annotations
from copy import deepcopy
import re
from .fsm_diagnostics import target_from_spec,state_tables

VERSION='prob003_transition_rows_v1'
SYSTEM=('Repair the public FSM by supplying actual transition rows, not a replacement file. '
        'Return one JSON object with exactly transitions and edit. transitions is a nonempty list '
        'of objects with exactly state, on_0, on_1, all strings naming existing states. '
        'For each listed state, on_0 is the destination for sampled data=0 and on_1 for data=1. '
        'You may list all current rows or just changed rows, but change only one or two rows per attempt. '
        'An unchanged table is not a repair, even if edit claims it was fixed; it consumes this attempt and is tested unchanged. '
        'Derive the correction from the public target, consumed-prefix path and current table. '
        'Mismatch paths must still consume every group position. Completed groups must consume '
        'the next input on the next edge. Preserve correct rows. '
        'Do not change output decoding, parameters, reset, ports or clocks. '
        'Past verified examples apply only when their conditions match this current task. '
        'edit is a concise factual description of the actual row changes. No Markdown or extra keys.')


def _case_rows(source):
    # Keep character offsets into the actual public source; ignore comments only in the reader.
    case=re.search(r'\bcase\s*\(\s*pstate\s*\)(.*?)\bendcase\b',source,re.S)
    if not case:return {}
    pattern=r'(?m)^\s*([A-Za-z_]\w*)\s*:\s*(.*?)(?=^\s*[A-Za-z_]\w*\s*:|\Z)'
    return {m[1]:(case.start(1)+m.start(2),case.start(1)+m.end(2)) for m in re.finditer(pattern,case[1],re.S)}


def context(task_id,specification,files,allowed):
    if target_from_spec(task_id,specification) is None:return None
    candidates=[]
    for path in sorted(allowed):
        if path not in files:continue
        constants,rows=state_tables(files[path]);spans=_case_rows(files[path])
        editable={name:row for name,row in rows.items() if name in constants and name in spans}
        if editable and {'idle','s1','s6','sf1','sf6'}<=editable.keys():
            candidates.append(dict(version=VERSION,file=path,
                rows=[dict(state=name,on_0=row['0'],on_1=row['1']) for name,row in editable.items()],
                declared_states=sorted(editable),maximum_changed_rows=2,
                scope='Only model-supplied rows are changed. The program does not fill missing corrections, search candidates or read a reference implementation.'))
    return candidates[0] if len(candidates)==1 else None


def validate(result):
    if not isinstance(result,dict) or set(result)!={'transitions','edit'}:
        return 'Return exactly transitions and edit. Complete source files or find/replace edits are not accepted for this FSM.'
    if not isinstance(result['edit'],str) or not result['edit'].strip():return 'edit must be a nonempty factual description.'
    rows=result['transitions']
    if not isinstance(rows,list) or not 1<=len(rows)<=13:return 'transitions must list one to thirteen rows.'
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'state','on_0','on_1'} or not all(isinstance(v,str) and re.fullmatch(r'[A-Za-z_]\w*',v) for v in row.values()):
            return 'Each transition needs exactly state, on_0 and on_1, containing state identifiers.'
        if row['state'] in seen:return 'List each state at most once.'
        seen.add(row['state'])
    return None


def apply(files,allowed,ctx,result):
    why=validate(result)
    if why:return None,why
    path=ctx['file']
    if path not in allowed:return None,'Transition source is not editable in this request.'
    source=files[path];constants,rows=state_tables(source);spans=_case_rows(source);changes=[]
    requested={}
    for row in result['transitions']:
        name=row['state'];dest={'0':row['on_0'],'1':row['on_1']}
        if name not in spans or name not in rows or name not in constants:return None,'Unknown or unsupported current state: '+name
        if any(state not in constants for state in dest.values()):return None,'Every destination must be an existing declared state.'
        requested[name]=dest
        if rows[name]==dest:continue
        start,end=spans[name]
        expression=dest['0'] if dest['0']==dest['1'] else 'data?'+dest['1']+':'+dest['0']
        changes.append((start,end,'nstate='+expression+';\n        '))
    if not changes:return None,'no_transition_change: all supplied 0/1 destinations are unchanged. The claimed repair made no functional edit. Use the public failing path to select an actual correction.'
    if len(changes)>2:return None,'Only one or two current transition rows may change per attempt; preserve the other rows.'
    updated=source
    for start,end,replacement in sorted(changes,reverse=True):updated=updated[:start]+replacement+updated[end:]
    _,actual=state_tables(updated)
    expected={**rows,**requested}
    if actual!=expected:raise RuntimeError('transition materialization did not preserve the requested/public row table')
    return {**files,path:updated},None


def compact_request(user,ctx):
    """Remove redundant diagnostic copies; retain public sources and observed branch data."""
    result=deepcopy(user)
    result['current_transition_table']=ctx
    result['required_output_schema']={'transitions':[{'state':'existing state','on_0':'destination on data=0','on_1':'destination on data=1'}],'edit':'actual row changes'}
    result['output_constraints']={'required_top_level_keys':['transitions','edit'],'additional_keys_allowed':False,
        'maximum_changed_rows':2,'unchanged_table_is_no_effective_repair':True,'no_complete_source_files':True}
    result['public_repair_guidance']=('Use current_transition_table and the earliest implicated prefix path below. '
        'For the target group, follow one edge per sampled input. A state reached on a mismatching prefix must still advance the group position. '
        'Do not change a correct output merely because the wrong state was reached. For data ? A : B, input 1 chooses A and input 0 chooses B. '
        'Use retained within-batch repair_experience when applicable; independently check all faults in the current table.')
    evidence=result.get('current_failure_evidence',{})
    result['current_failure_evidence']={'result':evidence.get('result'),'suites':{name:{k:row[k] for k in ('result','log') if k in row} for name,row in evidence.get('suites',{}).items()}}
    focus=result.pop('public_fault_focus',None)
    if focus:
        short={}
        for name,row in focus.get('suites',{}).items():
            short[name]={k:row[k] for k in ('first_output_mismatch','earliest_observed_state_context_conflict','focus_window','repair_focus') if k in row}
        result['public_fault_focus']=short
    result.pop('public_group_worksheet',None)
    delta=result.get('public_previous_patch_feedback')
    if delta:
        result['public_previous_patch_feedback']={k:v for k,v in delta.items() if k in ('no_syntax_token_change','public_failure_unchanged','feedback')}
    if 'public_feedback_correction' in result:
        result['public_feedback_correction']['instruction']='Correct the actual 0/1 transition rows implicated by the current public failure. Preserve correct rows. Return transitions and edit, not complete files.'
    # Raw attempt records remain on disk; do not repeat their long evidence strings in the prompt.
    result['previous_attempts']=[{k:v for k,v in row.items() if k in ('attempt','edit','result','reason')} for row in result.get('previous_attempts',[])]
    return result
