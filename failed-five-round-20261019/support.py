"""Independent zero-experience evaluation; never imports or writes run 01."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, re, shutil, signal
import subprocess, tarfile, time, urllib.request, urllib.error
from hwe_adapter import extract_harness, PROFILES

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / 'datasets/low_pass_rate_rtl_cases'
TOOL = '/opt/pdk_klayout_openroad/oss-cad-suite/bin/verilator'
MODEL = 'deepseek/deepseek-chat-v3-0324'
os.environ['PATH'] = str(Path(TOOL).parent) + ':' + os.environ['PATH']

def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    temp.replace(p)

def command(argv, cwd, log, timeout=180):
    with log.open('wb') as stream:
        p = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = p.wait(timeout=timeout)
            return {'returncode': code, 'timeout': False}
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            return {'returncode': p.returncode, 'timeout': True}

def inventory():
    return [dict(x, slug=x['id'].replace(':', '__')) for x in json.loads((DATA/'index.json').read_text())
            if not any(t in x['id'] for t in ('Prob001_', 'Prob023_', 'RC_406d811b4d61a2'))]

def prepare(case):
    task = ROOT/'work'/case['slug']
    if (task/'ready.json').exists():
        return task
    task.mkdir(parents=True, exist_ok=True)
    source = DATA/case['directory']
    if case['id'].startswith('chipbench:'):
        public = task/'public'; public.mkdir(exist_ok=True)
        for name in ('buggy.sv','spec.txt'):
            shutil.copyfile(source/name, public/name)
        private = task/'private'; private.mkdir(exist_ok=True)
        for name in ('golden.sv','ref.sv','tb_visible.sv'):
            shutil.copyfile(source/name, private/name)
        recipe = {'kind': 'chipbench'}
    else:
        repo = task/'public/repo'; repo.mkdir(parents=True, exist_ok=True)
        with tarfile.open(source/'public/baseline-source.tar.gz') as tar:
            members = tar.getmembers()
            prefix = members[0].name.split('/')[0] + '/'
            for member in members:
                if member.name.rstrip('/') == prefix.rstrip('/'):
                    continue
                if not member.name.startswith(prefix):
                    raise ValueError('archive prefix mismatch')
                member.name = member.name[len(prefix):]
                tar.extract(member, repo, filter='data')
        shutil.copyfile(source/'public/spec.txt', task/'public/spec.txt')
        private = task/'private'; private.mkdir(exist_ok=True)
        for name in ('fix.patch','test.patch'):
            shutil.copyfile(source/'oracle'/name, private/name)
        harness = private/'harness'; harness.mkdir(exist_ok=True)
        recipe = extract_harness((source/'public/upstream_tb_script.sh').read_text(), PROFILES[int(case['id'].split('-')[-1])], harness)
        recipe['kind'] = 'hwe'
    save(task/'ready.json', recipe)
    save(task/'source_hashes.json', {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()})
    return task

def grade(task, variant, files=None, base_reference=False):
    dest = task/'evaluations'/variant
    dest.mkdir(parents=True, exist_ok=True)
    recipe = json.loads((task/'ready.json').read_text())
    if recipe['kind'] == 'chipbench':
        code = files['buggy.sv'] if files is not None else (task/('private/golden.sv' if variant=='golden' else 'public/buggy.sv')).read_text()
        (dest/'candidate.sv').write_text(code)
        argv = [TOOL,'--binary','--timing','--top-module','tb','-Wno-fatal','--Mdir',str(dest/'obj_dir'),'-o','sim',str(dest/'candidate.sv'),str(task/'private/ref.sv'),str(task/'private/tb_visible.sv')]
        binary = dest/'obj_dir/sim'
        cwd = dest
    else:
        cwd = dest/'repo'
        if cwd.exists(): shutil.rmtree(cwd)
        shutil.copytree(task/'public/repo', cwd)
        # A source archive inside the parent Git worktree otherwise causes git
        # apply to silently skip paths relative to that parent worktree.
        initialized = command(['git','init','--quiet'], cwd, dest/'git-init.log')
        if initialized['returncode']: return {'status':'setup_error','step':'git-init'}
        for name in ('test.patch','fix.patch'):
            if name == 'fix.patch' and variant != 'golden' and not base_reference: continue
            patch = task/'private'/name
            if patch.stat().st_size:
                result = command(['git','apply',str(patch)], cwd, dest/(name+'.log'))
                if result['returncode']: return {'status':'setup_error','patch':name}
        if files:
            for name, contents in files.items():
                (cwd/name).write_text(contents)
        harness = cwd/'.hwe_harness'
        shutil.copytree(task/'private/harness', harness)
        argv = [TOOL, *[a.replace('{harness}',str(harness)) for a in recipe['argv']]]
        binary = harness/'obj_dir'/recipe['binary']
    build = command(argv, cwd, dest/'build.log')
    if build['timeout'] or build['returncode']:
        return {'status':'compile_timeout' if build['timeout'] else 'compile_error','build':build}
    sim = command([str(binary)], cwd, dest/'sim.log', 15)
    log = (dest/'sim.log').read_text(errors='replace')
    result = {'build':build, 'simulation':sim}
    if recipe['kind']=='chipbench':
        totals = re.findall(r'Mismatches:\s*(\d+) in (\d+) samples', log)
        if totals:
            result.update(mismatches=int(totals[-1][0]), samples=int(totals[-1][1]))
        passed = bool(totals and int(totals[-1][0])==0 and int(totals[-1][1])>0)
    else:
        passed = recipe['pass_marker'] in log and recipe['fail_marker'] not in log
    result['status'] = 'simulation_timeout' if sim['timeout'] else 'pass' if passed and sim['returncode']==0 else 'functional_fail'
    return result

def preflight(case):
    if case['status']=='exact_red_artifact_missing':
        return {'id':case['id'], 'status':'missing_original_artifact','model_calls':0}
    task = prepare(case)
    if (task/'preflight.json').exists(): return json.loads((task/'preflight.json').read_text())
    golden = grade(task,'golden')
    baseline = grade(task,'baseline') if golden['status']=='pass' else {'status':'not_run'}
    result = {'id':case['id'],'status':'ready' if golden['status']=='pass' and baseline['status'] in ('functional_fail','simulation_timeout') else 'preflight_failed','golden':golden,'baseline':baseline,'model_calls':0}
    save(task/'preflight.json', result)
    return result

def api(messages, folder, label, key, limit=16000, seed=None):
    request = {'model':MODEL,'messages':messages,'temperature':0.2,'max_tokens':limit,'stream':False}
    if seed is not None:
        request['seed'] = seed
    save(folder/(label+'.request.json'), request)
    cached = folder/(label+'.response.json')
    if cached.exists():
        body = json.loads(cached.read_text())
        return body['choices'][0]['message']['content']
    # Feed credentials over stdin, never through argv, environment, or logs.
    config = '\n'.join(['url = "https://openrouter.ai/api/v1/chat/completions"',
        'header = '+json.dumps('Authorization: Bearer '+key),
        'header = "Content-Type: application/json"',
        'data-binary = '+json.dumps('@'+str(folder/(label+'.request.json')))])
    response = subprocess.run(['curl','--silent','--show-error','--fail-with-body','--connect-timeout','30','--max-time','1500','--config','-'],input=config,text=True,capture_output=True,timeout=1510)
    if response.returncode:
        raise RuntimeError('OpenRouter transport failed: '+response.stderr[:500])
    body = json.loads(response.stdout)
    save(folder/(label+'.response.json'), body)
    return body['choices'][0]['message']['content']

def json_answer(text):
    text = text.strip()
    if text.startswith('```'): text = re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    return json.loads(text)

def parse(text):
    obj = json_answer(text)
    files = obj.get('files')
    if not isinstance(files,dict) or not files or any(not isinstance(v,str) for v in files.values()):
        raise ValueError('files must map filenames to complete source text')
    return files

def solve(case, key):
    task = ROOT/'work'/case['slug']
    output = task/'result.json'
    if output.exists(): return json.loads(output.read_text())
    initial = preflight(case)
    if initial['status']!='ready': return initial
    result = {'id':case['id'],'model':MODEL,'model_calls':0,'experience':[],'functional_attempts':1}
    try:
        spec = (task/'public/spec.txt').read_text()
        is_chip = case['id'].startswith('chipbench:')
        system = 'You are an RTL repair engineer. Work only from this independent task. You have no prior experience or previous attempts. Repair the defect while preserving other behavior and interfaces. Return only JSON: {"files":{"relative/path.sv":"complete replacement file contents"}}. Do not edit tests. Do not use placeholders or omit unchanged portions of a replacement file.'
        if is_chip:
            sources = {'buggy.sv':(task/'public/buggy.sv').read_text()}
        else:
            repo = task/'public/repo'
            available = sorted(str(p.relative_to(repo)) for p in (repo/'rtl').rglob('*.sv'))
            selection = [{'role':'system','content':'Select the RTL source files needed to diagnose and repair this issue. Return only JSON {"paths":["rtl/name.sv"]}. Select at most 12 files. This is a fresh task without experience.'},{'role':'user','content':spec+'\nAvailable files:\n'+'\n'.join(available)}]
            result['model_calls'] += 1
            selected = json_answer(api(selection, task,'selection',key,2000))['paths']
            if not isinstance(selected,list) or not 1 <= len(selected) <= 12 or any(p not in available for p in selected): raise ValueError('invalid source selection')
            sources = {p:(repo/p).read_text() for p in selected}
        prompt = 'Specification:\n'+spec+'\n\nSource files:\n'+json.dumps(sources,ensure_ascii=False)
        if len(prompt)>400000: raise ValueError('source context exceeds configured bound')
        messages = [{'role':'system','content':system},{'role':'user','content':prompt}]
        result['model_calls'] += 1
        answer = api(messages,task,'answer',key)
        try: files = parse(answer)
        except (ValueError,TypeError):
            messages += [{'role':'assistant','content':answer},{'role':'user','content':'Invalid response format. Return valid JSON with a nonempty files object mapping paths to complete source strings. No Markdown.'}]
            result['model_calls'] += 1
            files = parse(api(messages,task,'format_correction',key))
        for name in files:
            if name not in sources: raise ValueError('replacement outside supplied source scope: '+name)
        save(task/'submitted_files.json',files)
        evaluation = grade(task,'answer',files)
        result.update(status=evaluation['status'],evaluation=evaluation)
    except Exception as exc:
        result.update(status='execution_error',error=str(exc))
    save(output,result)
    return result

def report(results):
    save(ROOT/'results.json', results)
    lines = ['# 独立无经验静态测试','',f'模型：`{MODEL}`。每题空经验，一次功能作答；最多一次 JSON 格式纠正。Ibex 额外一次文件选择。无红队、无训练、无历史经验。','', '| 题目 | 状态 | 不一致采样 / 总采样 | 模型请求阶段数 |','|---|---|---|---|']
    labels = {'pass':'通过','functional_fail':'功能测试失败','compile_error':'编译失败','simulation_timeout':'仿真超时','missing_original_artifact':'缺少原始 RTL，无法运行','ready':'离线检查通过，待作答','execution_error':'请求或执行错误','preflight_failed':'离线检查失败'}
    for row in results:
        e = row.get('evaluation',{})
        mismatch = f"{e['mismatches']} / {e['samples']}" if 'samples' in e else '—'
        lines.append(f"| {row['id']} | {labels.get(row['status'],row['status'])} | {mismatch} | {row.get('model_calls',0)} |")
    receipts = []
    for p in sorted((ROOT/'work').glob('*/*.response.json')):
        obj = json.loads(p.read_text())
        receipts.append({'case':p.parent.name,'stage':p.name,'id':obj.get('id'),'model':obj.get('model'),'usage':obj.get('usage',{})})
    save(ROOT/'usage.json', receipts)
    tokens = sum(r['usage'].get('total_tokens',0) for r in receipts)
    cost = sum(r['usage'].get('cost',0) or 0 for r in receipts)
    lines += ['',f'已保存模型响应：{len(receipts)}；返回的总 token：{tokens}；服务返回的已知费用合计：${cost:.6f}（网络未返回响应的请求费用未知）。', '', '首次 urllib 传输遇到沙箱限制和 TLS 错误，随后切换 curl。已有答案原样保留；仅补发没有响应的请求阶段。网络失败记录另存 sandbox_network_error.json / urllib_network_error.json，不能算模型答错。', '', '通过仅表示本地基准测试通过；不代表完整形式验证。Prob017 原题面与参考实现存在矛盾，以原始参考实现和测试为评分标准。缺少历史原始 RTL 的案例不会以重建版本替代。', '']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    args = parser.parse_args()
    cases = inventory(); save(ROOT/'catalog.json', cases)
    results = []
    # Independent tasks compile concurrently; no model requests during preflight.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for case, future in zip(cases, [pool.submit(preflight,c) for c in cases]):
            try: row = future.result()
            except Exception as exc: row = {'id':case['id'],'status':'preflight_error','error':str(exc),'model_calls':0}
            results.append(row); report(results)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    if args.run:
        key = (ROOT/'.secrets/openrouter.key').read_text().strip()
        for i,case in enumerate(cases):
            if results[i]['status']!='ready': continue
            results[i] = solve(case,key); report(results)
            print(json.dumps(results[i],ensure_ascii=False),flush=True)

if __name__=='__main__': main()
