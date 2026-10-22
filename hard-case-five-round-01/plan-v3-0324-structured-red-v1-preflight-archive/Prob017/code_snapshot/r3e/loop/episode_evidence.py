"""Compact, reproducible evidence from an original defective task and its own repair.

No clean implementation, private evaluator, historical answer or authored repair rule.
The full submitted patch remains in the authenticated archive; these are bounded excerpts.
"""
import difflib
from r3e.knowledge.verilog_utils import safe_tokenize
from r3e.protocol.hashing import hash_payload

VERSION='public_repair_context_v1'
SCOPE='Current-run public task and submitted repair only; excerpts are not a standalone patch.'


def _snippet(text, tokens, start, end):
    # Include a neighbouring source line to retain state/assignment context.
    offset=tokens[start].start if start<len(tokens) else len(text)
    finish=tokens[end-1].end if end>start else offset
    first=text[:offset].count('\n')
    last=text[:finish].count('\n')
    lines=text.splitlines()
    lo=max(0,first-1);hi=min(len(lines),last+2)
    original='\n'.join(lines[lo:hi])
    return {'line_start':lo+1,'line_end':hi,'text':original[:360],'truncated':len(original)>360}


def public_witness(evidence):
    out={}
    for name in ('W_bug','W_preserve'):
        cell=evidence.get('suites',{}).get(name,{})
        lines=[line[:200] for line in str(cell.get('log','')).splitlines()
               if 'CHECK_FAIL' in line or 'TESTBENCH PASS' in line][:2]
        out[name]={'result':cell.get('result'),'markers':lines}
    return out


def extract(original_files, archive, baseline_evidence, replay_evidence):
    changes=[];total=0
    for path,after in sorted(archive['files'].items()):
        before=original_files[path]
        a,b=safe_tokenize(before),safe_tokenize(after)
        matcher=difflib.SequenceMatcher(a=[t.value for t in a],b=[t.value for t in b],autojunk=False)
        regions=[]
        for tag,i,j,k,l in matcher.get_opcodes():
            if tag=='equal':continue
            old,new=_snippet(before,a,i,j),_snippet(after,b,k,l)
            if regions and old['line_start']<=regions[-1]['before']['line_end'] and new['line_start']<=regions[-1]['after']['line_end']:
                previous=regions[-1]
                previous['j']=j;previous['l']=l
                previous['before']=_snippet(before,a,previous['i'],j)
                previous['after']=_snippet(after,b,previous['k'],l)
            else:
                regions.append({'file':path,'i':i,'j':j,'k':k,'l':l,'before':old,'after':new})
        total+=len(regions)
        changes.extend(regions[:max(0,3-len(changes))])
    patch=[];changed=[];ranges=[]
    for item in changes:
        old,new=item['before'],item['after']
        patch.extend([f"--- original_buggy/{item['file']}",f"+++ repaired/{item['file']}",
            f"@@ original lines {old['line_start']}-{old['line_end']}; repaired lines {new['line_start']}-{new['line_end']} @@",
            *('-'+line for line in old['text'].splitlines()),*('+'+line for line in new['text'].splitlines())])
        changed.extend(['- '+old['text'].replace('\n',' ')[:238],'+ '+new['text'].replace('\n',' ')[:238]])
        ranges.append({'file':item['file'],'before_lines':[old['line_start'],old['line_end']],
            'after_lines':[new['line_start'],new['line_end']],'truncated':old['truncated'] or new['truncated']})
    # Macro/directive-only edits can be semantically relevant but absent from safe_tokenize.
    # Preserve a bounded literal fallback rather than inventing a token-level explanation.
    if not patch:
        patch=[archive['patch'][:1800]]
        changed=[line[:240] for line in archive['patch'].splitlines()
                 if line.startswith(('+','-')) and not line.startswith(('+++','---')) and line[1:].strip()][:6]
    evidence={'version':VERSION,'full_patch_hash':hash_payload(archive['patch']),
        'changed_ranges':ranges,'omitted_change_regions':max(0,total-len(changes)),
        'public_before':public_witness(baseline_evidence),'public_after':public_witness(replay_evidence),
        'scope':SCOPE}
    return '\n'.join(patch),changed[:6],evidence


def valid(value):
    return (isinstance(value,dict) and set(value)=={'version','full_patch_hash','changed_ranges','omitted_change_regions','public_before','public_after','scope'}
        and value['version']==VERSION and value['scope']==SCOPE
        and isinstance(value['full_patch_hash'],str) and value['full_patch_hash'].startswith('sha256:')
        and isinstance(value['changed_ranges'],list) and len(value['changed_ranges'])<=3
        and isinstance(value['omitted_change_regions'],int) and value['omitted_change_regions']>=0
        and all(isinstance(value[k],dict) and set(value[k])=={'W_bug','W_preserve'} for k in ('public_before','public_after'))
        and all(isinstance(value[phase][k],dict) and set(value[phase][k])=={'result','markers'}
            and isinstance(value[phase][k]['markers'],list) and len(value[phase][k]['markers'])<=2
            and all(isinstance(line,str) and len(line)<=200 for line in value[phase][k]['markers'])
            for phase in ('public_before','public_after') for k in ('W_bug','W_preserve'))
        and value['public_before']['W_bug']['result']=='visible_fail'
        and value['public_before']['W_preserve']['result']=='visible_pass'
        and all(value['public_after'][k]['result']=='visible_pass' for k in ('W_bug','W_preserve')))
