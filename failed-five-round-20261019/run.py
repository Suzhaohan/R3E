"""Five independent paired adversarial experiments with deferred frozen exams."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, hashlib, json, re, threading, time
import support as s
from token_count import TokenCounter

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent/'remaining-static-20261019'
COUNTER = TokenCounter(ROOT/'tokenizer.json')
PRINT_LOCK = threading.Lock()
CAP = 180

def read(p): return json.loads(p.read_text())
def save(p,v): s.save(p,v)
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
def say(case, stage, **values):
    with PRINT_LOCK:
        print(json.dumps({'case':case['id'],'stage':stage,**values},ensure_ascii=False),flush=True)

def decode(text):
    # Accept a JSON object inside a Markdown fence or surrounding prose without
    # another model request. Parsing does not change any model-supplied content.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{',text):
        try:
            obj,_ = decoder.raw_decode(text[match.start():])
            if isinstance(obj,dict) and any(k in obj for k in ('files','paths','candidates')): return obj
        except ValueError: pass
    raise ValueError('No supported JSON object in response')

class Client:
    def __init__(self,task,key):
        self.task,self.key = task,key
    def call(self,label,messages,limit=16000):
        folder = self.task/'calls'
        paired_label=re.sub(r'round_\d+_validation','validation',label).replace('initial_validation','validation')
        paired_label=paired_label.replace('_static','_paired').replace('_adaptive','_paired')
        seed=int(hashlib.sha256(paired_label.encode()).hexdigest()[:7],16)
        response = folder/(label+'.response.json')
        if response.exists():
            request = read(folder/(label+'.request.json'))
            if request['messages'] != messages or request['max_tokens']!=limit or request.get('seed')!=seed:
                raise ValueError('Cached request differs: '+label)
            return read(response)['choices'][0]['message']['content']
        tokens = COUNTER.request(messages)
        if tokens+limit>128000:
            raise ValueError(f'Context bound exceeded before HTTP: {tokens}+{limit}')
        for attempt in range(2):
            ledger_path = self.task/'request_ledger.json'
            ledger = read(ledger_path) if ledger_path.exists() else []
            if len(ledger)>=CAP: raise RuntimeError('Per-case 180-request hard cap reached')
            ledger.append({'label':label,'transport_attempt':attempt+1,'input_tokens_local':tokens,'output_limit':limit,'started':time.time()})
            save(ledger_path,ledger)
            try:
                value = s.api(messages,folder,label,self.key,limit,seed=seed)
                ledger[-1]['status']='response_saved'; save(ledger_path,ledger)
                return value
            except Exception as exc:
                ledger[-1].update(status='transport_error',error=str(exc)); save(ledger_path,ledger)
                if attempt or any(x in str(exc) for x in ('401','402','403')): raise
        raise AssertionError('unreachable')

def source_context(case,task,client):
    path = task/'contexts.json'
    if path.exists(): return read(path)
    if case['id'].startswith('chipbench:'):
        contexts = {'exam':{'buggy.sv':(task/'public/buggy.sv').read_text()},'clean':{'buggy.sv':(task/'private/golden.sv').read_text()}}
    else:
        repo = task/'public/repo'
        available = sorted(str(p.relative_to(repo)) for p in (repo/'rtl').rglob('*.sv'))
        messages = [{'role':'system','content':'Select RTL files needed to repair this issue from this public repository file list. Return JSON {"paths":["rtl/name.sv"]}, at most 12 files. You have no previous experience.'},
                    {'role':'user','content':(task/'public/spec.txt').read_text()+'\nFiles:\n'+'\n'.join(available)}]
        response=client.call('source_selection',messages,2000)
        try:
            selected=decode(response)['paths']
        except (ValueError,KeyError,TypeError):
            messages += [{'role':'assistant','content':response},{'role':'user','content':'Return only valid JSON {"paths":["rtl/name.sv"]}, at most 12 files from the supplied file list.'}]
            selected=decode(client.call('source_selection_format',messages,2000))['paths']
        if not isinstance(selected,list) or not 1<=len(selected)<=12 or any(p not in available for p in selected):
            raise ValueError('Invalid public source selection')
        clean = task/'evaluations/golden/repo'
        contexts = {'exam':{p:(repo/p).read_text() for p in selected},'clean':{p:(clean/p).read_text() for p in selected}}
    save(path,contexts)
    return contexts

def checked_edits(clean,edits):
    if not isinstance(edits,list) or not 1<=len(edits)<=4: raise ValueError('Need 1..4 source edits')
    files = dict(clean)
    for e in edits:
        name,a,b = e.get('file'),e.get('find'),e.get('replace')
        if name not in clean or not isinstance(a,str) or not a or not isinstance(b,str) or a==b or len(b)>max(3000,len(a)*3):
            raise ValueError('Invalid edit scope or replacement')
        if files[name].count(a)!=1: raise ValueError('Edit find must match exactly once: '+str(name))
        files[name]=files[name].replace(a,b,1)
    if files==clean: raise ValueError('No source change')
    return files

def grade(task,label,files,practice):
    stored = task/'grades'/(label+'.json')
    fingerprint = digest({'files':files,'reference_base':practice})
    if stored.exists():
        result=read(stored)
        if result['input_hash']!=fingerprint: raise ValueError('Grade cache mismatch')
        return result['evaluation']
    result=s.grade(task,label,files,base_reference=practice)
    save(stored,{'input_hash':fingerprint,'evaluation':result})
    return result

def feedback(task,label,result):
    evidence={'status':result['status']}
    if 'samples' in result:
        evidence.update(mismatches=result['mismatches'],samples=result['samples'])
    log = task/'evaluations'/label/('build.log' if result['status'].startswith('compile') else 'sim.log')
    if log.exists():
        text=log.read_text(errors='replace')
        if result['status'].startswith('compile'):
            evidence['diagnostics']='\n'.join(l for l in text.splitlines() if any(k in l for k in ('%Error','error:','syntax','PINNOTFOUND','PINMISSING')))[:5000] or text[-5000:]
        else:
            evidence['diagnostics']='\n'.join(l for l in text.splitlines() if any(k in l for k in ('Mismatches:','CHECK_FAIL','TB_FAIL','TB_PASS','TESTBENCH PASS')))[:3000]
    return evidence

def generate(case,task,client,contexts,label,wanted,seen):
    output=task/'generation'/(label+'.json')
    if output.exists():
        result=read(output)
        seen.update(digest(c['files']) for c in result['accepted'])
        return result['accepted']
    clean=contexts['clean']; accepted=[]; rejected=[]
    system=('You are the adversarial RTL exercise author. You receive a correct reference implementation and public specification. '
            'Generate distinct small reachable functional defects to teach transferable debugging of this design. Preserve syntax, module interfaces and synthesizability; '
            'do not change tests, add self-checking shortcuts, or merely rename variables. No combinational oscillation, dead clocks, permanent reset, or deleting all functionality. '
            'Return JSON {"candidates":[{"edits":[{"file":"path","find":"unique exact source text","replace":"mutated text"}],'
            '"requirement":"violated public requirement"}]}. Each candidate has 1 to 4 edits. Produce up to 4 independent candidates against the supplied clean source. '
            'Do not provide solutions, repair advice or any clean source to the solver. You never receive the held-out original exam defect.')
    for request_index in range(2):
        prompt={'specification':(task/'public/spec.txt').read_text(),'correct_source_for_author_only':clean,
                'stage':label,'needed':wanted-len(accepted),'already_used_mutation_hashes':sorted(seen),
                'generation_feedback':rejected[-8:]}
        try:
            response=decode(client.call(label+f'_red_{request_index}',[{'role':'system','content':system},{'role':'user','content':json.dumps(prompt)}]))
            proposals=response.get('candidates',[])
            if not isinstance(proposals,list): raise ValueError('Candidates must be a list')
        except (ValueError,TypeError) as exc:
            rejected.append({'reason':str(exc)}); continue
        for i,p in enumerate(proposals[:4]):
            try:
                if not isinstance(p,dict) or not isinstance(p.get('requirement'),str) or not p['requirement'].strip(): raise ValueError('Missing violated requirement')
                files=checked_edits(clean,p.get('edits'))
                fingerprint=digest(files)
                if fingerprint in seen or fingerprint==digest(contexts['exam']): raise ValueError('Duplicate or reserved original exam')
                test_label=label+f'_screen_{request_index}_{i}'
                result=grade(task,test_label,files,True)
                log=task/'evaluations'/test_label/'sim.log'
                text=log.read_text(errors='replace') if log.exists() else ''
                witnessed=(result.get('mismatches',0)>0 and result.get('samples',0)>0) if case['id'].startswith('chipbench:') else any(m in text for m in ('CHECK_FAIL','TB_FAIL'))
                if result['status']!='functional_fail' or not witnessed:
                    rejected.append({'candidate':i,'reason':'must compile, terminate and fail functionally','test':feedback(task,test_label,result)}); continue
                accepted.append({'files':files,'source_hash':fingerprint,'author_requirement_private':p['requirement'],'generation_request':request_index,'candidate':i})
                seen.add(fingerprint)
                if len(accepted)>=wanted: break
            except (ValueError,TypeError,KeyError) as exc:
                rejected.append({'candidate':i,'reason':str(exc)})
        if len(accepted)>=wanted: break
    save(output,{'accepted':accepted,'rejected':rejected,'prepared_fallback_used':False})
    say(case,'generation',slot=label,admitted=len(accepted),needed=wanted)
    return accepted

BLUE_SYSTEM=('You are an RTL repair engineer. Repair the supplied design from the public specification and actual test feedback. '
    'Do not edit testbenches, hardcode test outputs, or omit source. Public top-level behavior and interfaces must remain compatible; '
    'internal interfaces may be changed consistently across supplied files when required by the specification. '
    'Return JSON {"files":{"relative/path.sv":"complete replacement file text"},'
    '"transfer_summary":"brief reusable diagnostic and repair lesson"}. Return only changed files, with complete contents. '
    'No placeholders. Experience, if supplied, comes only from this experiment and may be imperfect. Never copy an old patch blindly.')

def repair(case,task,client,label,files,experience,practice):
    output=task/'trials'/(label+'.json')
    identity=digest({'files':files,'experience':experience,'practice':practice})
    if output.exists():
        result=read(output)
        if result['input_hash']!=identity: raise ValueError('Trial cache mismatch: '+label)
        return result
    messages=[{'role':'system','content':BLUE_SYSTEM},
              {'role':'user','content':json.dumps({'specification':(task/'public/spec.txt').read_text(),'files':files,'experience':experience})}]
    current=dict(files); attempts=[]; summary=''
    for attempt in range(2):
        response=client.call(label+f'_answer_{attempt}',messages)
        try:
            obj=decode(response); submitted=obj.get('files')
            if not isinstance(submitted,dict) or not submitted or any(p not in files or not isinstance(v,str) for p,v in submitted.items()):
                raise ValueError('files must map supplied paths to complete source text')
        except (ValueError,TypeError) as exc:
            messages += [{'role':'assistant','content':response},{'role':'user','content':'Invalid JSON response: '+str(exc)+'. Return only the required JSON object, complete source contents, and transfer_summary.'}]
            response=client.call(label+f'_format_{attempt}',messages)
            try:
                obj=decode(response); submitted=obj.get('files')
                if not isinstance(submitted,dict) or not submitted or any(p not in files or not isinstance(v,str) for p,v in submitted.items()):
                    raise ValueError('Invalid replacement files after format correction')
            except (ValueError,TypeError) as exc:
                result={'input_hash':identity,'status':'format_error','passed':False,'attempts':attempts,'transfer_summary':'','experience_entries':len(experience),'files':current,'error':str(exc)}
                save(output,result)
                return result
        current.update(submitted)
        test_label=label+f'_attempt_{attempt}'
        result=grade(task,test_label,current,practice)
        attempts.append({'evaluation':result,'files_hash':digest(current),'feedback':feedback(task,test_label,result)})
        summary=obj.get('transfer_summary','')
        if not isinstance(summary,str): summary=''
        summary=summary[:2400]
        if result['status']=='pass': break
        if result['status'] in ('setup_error','compile_timeout','simulation_timeout'):
            # Timeouts are infrastructure-inconclusive, never repair evidence.
            break
        messages += [{'role':'assistant','content':response},{'role':'user','content':json.dumps({'feedback':attempts[-1]['feedback'],'instruction':'Correct the defect using these actual diagnostics. Return the required JSON with complete changed file contents.'})}]
    result={'input_hash':identity,'status':attempts[-1]['evaluation']['status'],'passed':attempts[-1]['evaluation']['status']=='pass',
            'attempts':attempts,'transfer_summary':summary,'experience_entries':len(experience),'files':current}
    save(output,result)
    return result

def validation_scores(case,task,client,label,validation,experience):
    scores={}
    for index,v in enumerate(validation):
        for repeat in range(2):
            name=f'{index}_{repeat}'
            trial=repair(case,task,client,label+'_'+name,v['files'],experience,True)
            scores[name]=trial['passed']
    return scores

def train(case,key):
    task=s.ROOT/'work'/case['slug']
    if (task/'trained.json').exists(): return read(task/'trained.json')
    preflight=s.preflight(case)
    if preflight['status']!='ready': raise RuntimeError('Reference/defect preflight failed: '+json.dumps(preflight))
    client=Client(task,key)
    contexts=source_context(case,task,client)
    seen=set()
    validation=generate(case,task,client,contexts,'reserved_validation',2,seen)
    # All held-out mutations are frozen before any practice, and never exposed
    # to Red again or included as Blue experience entries.
    save(task/'validation_manifest.json',{'source_hashes':[v['source_hash'] for v in validation],'repeats':2,'exam_used':False})
    experience=[]; incumbent_scores=None; rounds=[]
    for round_number in range(1,6):
        slot=f'round_{round_number}'
        round_path=task/'rounds'/f'{round_number}.json'
        if round_path.exists():
            row=read(round_path); experience=row['outgoing_experience']; incumbent_scores=row.get('validation_scores')
            used=row.get('practice_hash')
            if used: seen.add(used)
            rounds.append(row); continue
        say(case,'round_started',round=round_number,experience_entries=len(experience))
        generated=generate(case,task,client,contexts,slot,1,seen)
        row={'round':round_number,'incoming_experience_hash':digest(experience),'admitted':bool(generated),'practice_hash':generated[0]['source_hash'] if generated else None}
        if not generated:
            row['reason']='no_qualified_online_question'; row['accepted']=False
        else:
            practice=generated[0]
            # Identical sources and feedback budget for both arms.
            static=repair(case,task,client,slot+'_static',practice['files'],[],True)
            adaptive=repair(case,task,client,slot+'_adaptive',practice['files'],experience,True)
            row.update(static_passed=static['passed'],adaptive_passed=adaptive['passed'])
            candidate=list(experience)
            if adaptive['passed'] and adaptive['transfer_summary'].strip():
                candidate.append({'round':round_number,'lesson':adaptive['transfer_summary'],'evidence':'own successful practice repair; public test passed','practice_hash':practice['source_hash']})
            row['accepted']=False
            if candidate==experience: row['reason']='no_successful_transfer_summary'
            elif len(validation)!=2: row['reason']='validation_generation_incomplete_no_promotion'
            else:
                if incumbent_scores is None:
                    incumbent_scores=validation_scores(case,task,client,'initial_validation',validation,experience)
                scores=validation_scores(case,task,client,slot+'_validation',validation,candidate)
                losses=[k for k in scores if incumbent_scores[k] and not scores[k]]
                gains=[k for k in scores if scores[k] and not incumbent_scores[k]]
                row.update(incumbent_passed=sum(incumbent_scores.values()),candidate_passed=sum(scores.values()),losses=losses,gains=gains)
                row['accepted']=not losses and bool(gains)
                row['reason']='strict_gain_no_regression' if row['accepted'] else 'regression' if losses else 'no_strict_gain'
                if row['accepted']: experience=candidate; incumbent_scores=scores
        row.update(outgoing_experience=experience,validation_scores=incumbent_scores)
        save(round_path,row); rounds.append(row)
        say(case,'round_finished',round=round_number,reason=row['reason'],accepted=row['accepted'],experience_entries=len(experience))
    result={'id':case['id'],'status':'trained','rounds':rounds,'frozen_experience':experience,'experience_hash':digest(experience)}
    save(task/'trained.json',result)
    say(case,'trained',rounds=5,experience_entries=len(experience))
    return result

def exam(case,key,frozen):
    task=ROOT/'work'/case['slug']; client=Client(task,key)
    contexts=read(task/'contexts.json')
    experience=frozen['frozen_experience']
    if digest(experience)!=frozen['experience_hash']: raise ValueError('Frozen experience changed')
    results={}
    for repeat in range(2):
        for arm,memory in (('static',[]),('adaptive',experience)):
            trial=repair(case,task,client,f'exam_{arm}_{repeat}',contexts['exam'],memory,False)
            results[f'{arm}_{repeat}']={'passed':trial['passed'],'status':trial['status'],'attempts':len(trial['attempts'])}
    result={'id':case['id'],'status':'complete','experience_hash':frozen['experience_hash'],'experience_entries':len(experience),
            'static_passed':sum(v['passed'] for k,v in results.items() if k.startswith('static')),
            'adaptive_passed':sum(v['passed'] for k,v in results.items() if k.startswith('adaptive')),'repeats':2,'samples':results}
    save(task/'exam.json',result); say(case,'exam_finished',**{k:v for k,v in result.items() if k not in ('id','samples')})
    return result

def summary(cases):
    rows=[]; receipts=[]; actual_requests=0
    for c in cases:
        task=ROOT/'work'/c['slug']
        if (task/'exam.json').exists(): row=read(task/'exam.json')
        elif (task/'trained.json').exists():
            t=read(task/'trained.json'); row={'id':c['id'],'status':'trained','experience_entries':len(t['frozen_experience'])}
        elif (task/'error.json').exists(): row={'id':c['id'],'status':'error','details':read(task/'error.json')}
        else: row={'id':c['id'],'status':'training','completed_rounds':len(list((task/'rounds').glob('*.json')))}
        rows.append(row)
        if (task/'request_ledger.json').exists(): actual_requests+=len(read(task/'request_ledger.json'))
        for p in (task/'calls').glob('*.response.json'):
            r=read(p); receipts.append({'case':c['id'],'file':p.name,'model':r.get('model'),'id':r.get('id'),'usage':r.get('usage',{})})
    save(ROOT/'results.json',rows); save(ROOT/'usage.json',receipts)
    lines=['# 五轮对抗结果','', '| 案例 | 状态 | 静态考试 | 对抗考试 | 冻结经验条数 |','|---|---|---|---|---|']
    for r in rows: lines.append(f"| {r['id']} | {r['status']} | {str(r['static_passed'])+'/2' if 'static_passed' in r else '待考试'} | {str(r['adaptive_passed'])+'/2' if 'adaptive_passed' in r else '待考试'} | {r.get('experience_entries','—')} |")
    cost=sum(x['usage'].get('cost',0) or 0 for x in receipts)
    lines += ['',f'HTTP 请求尝试：{actual_requests}；已保存响应：{len(receipts)}；服务返回已知费用：${cost:.6f}。', '', '每题独立空经验；五轮在线出题、双组等额反馈修复；仅自身成功修复摘要可成为经验候选，两个保留缺陷各重复两次检验严格提升且无退步才晋升。全部训练结束后统一冻结，再各做两次原始题考试。训练、验证、考试均使用本地原始测试；保留的是不同缺陷，不是独立测试集。', '', '这是适配这些案例的独立流程，未复用 01 中绑定原三题的启动器。与旧流程相比：沿用私有原始基准而未额外建立独立 evaluator；不做跨题经验共享；原静态结果仅用于选题，不作为训练经验。最终两组预算一致，最多两次功能作答及每次一次格式纠正。Prob017 仍有题面与参考矛盾；通过仅表示参考测试通过。', '']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines))
    return rows

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--run',action='store_true'); parser.add_argument('--check-only',action='store_true'); parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    previous=read(PREVIOUS/'results.json')
    selected={r['id'] for r in previous if r['status']=='functional_fail'}
    cases=[c for c in s.inventory() if c['id'] in selected]
    if len(cases)!=5: raise ValueError('Expected precisely five functional-failure cases')
    save(ROOT/'catalog.json',cases)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'run.py',ROOT/'support.py',ROOT/'hwe_adapter.py',ROOT/'token_count.py',ROOT/'tokenizer.json')}
    plan={'model':s.MODEL,'cases':[c['id'] for c in cases],'source_hashes':hashes,'rounds':5,'independent_experience':True,
          'max_requests_per_case':CAP,'max_total_requests':CAP*len(cases),'functional_attempts':2,'format_corrections':1,'validation_tasks':2,'validation_repeats':2,'exam_repeats':2,
          'prior_static_result_sha256':hashlib.sha256((PREVIOUS/'results.json').read_bytes()).hexdigest(),'all_training_before_any_final_exam':True,'prepared_fallback':False,'tokenizer':COUNTER.identity}
    if (ROOT/'plan.json').exists() and read(ROOT/'plan.json')!=plan: raise ValueError('Frozen plan changed; do not resume with different code')
    save(ROOT/'plan.json',plan)
    if args.check_only:
        for c in cases:
            result=s.preflight(c); say(c,'preflight',result=result)
            if result['status']!='ready': raise RuntimeError('Preflight did not pass')
        print(json.dumps({'status':'PASS','model_calls':0,'cases':len(cases),'max_calls':CAP*len(cases)}),flush=True)
        return
    if not args.run:
        summary(cases); return
    key=(PREVIOUS/'.secrets/openrouter.key').read_text().strip()
    if not key: raise ValueError('No configured API key')
    trained={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(train,c,key):c for c in cases}
        for future in as_completed(futures):
            c=futures[future]
            try: trained[c['id']]=future.result()
            except Exception as exc:
                save(ROOT/'work'/c['slug']/'error.json',{'phase':'training','error':str(exc)})
                say(c,'training_error',error=str(exc))
            summary(cases)
    if len(trained)!=len(cases):
        print('Training incomplete: no final exams started. Fix the recorded infrastructure/request issue and resume.',flush=True)
        return
    freeze={c['id']:trained[c['id']]['experience_hash'] for c in cases}
    if (ROOT/'global_freeze.json').exists() and read(ROOT/'global_freeze.json')!=freeze: raise ValueError('Global freeze changed')
    save(ROOT/'global_freeze.json',freeze)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(exam,c,key,trained[c['id']]):c for c in cases}
        for future in as_completed(futures):
            c=futures[future]
            try: future.result()
            except Exception as exc:
                save(ROOT/'work'/c['slug']/'error.json',{'phase':'exam','error':str(exc)})
                say(c,'exam_error',error=str(exc))
            summary(cases)
    print(json.dumps(summary(cases),ensure_ascii=False),flush=True)

if __name__=='__main__': main()
