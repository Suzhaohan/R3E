"""One command, resumable A/B pipeline and read-only live dashboard."""
import argparse
from contextlib import contextmanager
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import time

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN/'source'
sys.path.insert(0, str(ROOT))
from competition.arena.evidence import read, signed, freeze, verify_signed
from r3e.protocol.hashing import atomic_write_json, utc_now


def pipeline_status(run, **fields):
    path = Path(run)/'pipeline.json'
    previous = read(path) if path.exists() else {}
    atomic_write_json(path, {**previous, **fields, 'updated_at': utc_now()})


def snapshot(run=RUN):
    run = Path(run)
    data = {'pipeline': read(run/'pipeline.json') if (run/'pipeline.json').exists() else
            {'status':'ready', 'message':'尚未启动本轮实验。历史结果已载入。'},
            'arms':{}, 'rounds':[], 'metrics':{}, 'demos':{}, 'historical':[],
            'guard':None, 'memory':{}, 'errors':[], 'available':True}
    history = verify_signed(read(run/'source/competition/manifests/historical_demo_evidence.json'))
    for row in history['rows']:
        for arm in row['evidence'].values():
            for record in arm:
                verify_signed(record['receipt'], 'receipt_hash')
        data['historical'].append({k:row[k] for k in ('case_id','static_successes','memory_successes','repetitions')})
    for arm in ('a','b'):
        state = run/('arm-'+arm)
        value = {}
        for key, file in (('progress','live_progress.json'), ('budget','budgets/total.json')):
            if (state/file).exists(): value[key] = read(state/file)
        data['arms'][arm] = value
        for phase in ('preview','final'):
            path = state/f'demo_{phase}.json'
            if path.exists(): data['demos'][arm+'_'+phase] = verify_signed(read(path))['rows']
    state = run/'arm-b'
    for p in sorted((state/'rounds').glob('R*/round_summary.json')):
        from competition.arena.presentation import round_view
        row = round_view(p.parent,include_local_diffs=True)
        data['rounds'].append({'round_id':row['round_id'],'promoted':row['promoted'],
                              'active_policy_id':row['active_policy_id'], 'status':'暂选版本；最终以完整检查为准',
                              'cases':row['cases']})
    if (state/'final_selection.json').exists():
        from competition.services.balanced_final import verify_selection
        g = verify_selection(read(state/'final_selection.json'))
        data['guard'] = {k:g[k] for k in ('complete','accepted','losses','message')}
        data['guard']['completed_pairs'] = len(g['pairs'])
    p = state/'experience/library.json'
    if p.exists():
        library = verify_signed(read(p))
        data['memory'] = {'stored':len(library['entries']), 'eligible':len(library['eligible_receipts']),
                          'local_improvements':len(library['local_improvements']), 'deleted':0}
    else:
        memory = verify_signed(read(run/'source/competition/manifests/history_memory.json'))
        archive = verify_signed(read(run/'source/competition/manifests/history_archive.json'))
        data['memory'] = {'stored':len(archive['entries']), 'eligible':len(memory['entries']), 'local_improvements':0,'deleted':0}
    if (run/'comparison.json').exists():
        from competition.services.arena_comparison_service import verify_comparison
        data['metrics'] = verify_comparison(read(run/'comparison.json'))['metrics']
    return data


def serve(run=RUN, port=8085):
    run = Path(run)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ('/', '/index.html'):
                body = (run/'recovery/dashboard.html').read_bytes()
                kind, code = 'text/html; charset=utf-8', 200
            elif self.path in ('/api/status','/api/arena/status'):
                try:
                    body = json.dumps(snapshot(run), ensure_ascii=False).encode()
                    code = 200
                except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                    body = json.dumps({'available':False, 'error':type(exc).__name__,
                                       'message':'结果文件正在更新或核验未通过，请查看运行日志。'},ensure_ascii=False).encode()
                    code = 503
                kind = 'application/json; charset=utf-8'
            else:
                code, body, kind = 404, b'Not found', 'text/plain'
            self.send_response(code)
            self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
        def log_message(self,*args): pass
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'网页：http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()


def ensure_web(port):
    from urllib.request import build_opener, ProxyHandler
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}/api/status', timeout=2) as response:
            data = json.load(response)
            if 'pipeline' in data and 'historical' in data:
                return
        raise ValueError(f'端口 {port} 已被其他服务占用')
    except OSError:
        pass
    (RUN/'logs').mkdir(exist_ok=True)
    with (RUN/'logs/web.log').open('ab') as log:
        process = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'view','--port',str(port)],
                                   cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    atomic_write_json(RUN/'web_process.json', {'pid':process.pid, 'port':port})
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError('网页服务未启动，请检查 logs/web.log 中的端口或权限信息。')
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/status',timeout=1) as response:
                if 'pipeline' in json.load(response):return
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError('网页服务未在预期时间内就绪，运行尚未开始。')


def demonstration(arm, phase, *, max_calls, max_tokens):
    from types import SimpleNamespace
    from competition.arena.cli import _client
    from competition.services.development_demo import run
    from resilience import Recovery
    state=RUN/('arm-'+arm)
    raw=_client(RUN/'client.json')
    args=SimpleNamespace(client_config=str(RUN/'client.json'),max_calls=max_calls,max_tokens=max_tokens)
    return Recovery(state,raw.config,endpoint=os.environ.get(raw.config.base_url_env,'')).run(
        lambda:run(ROOT,state,args,phase))


def run_pipeline(args):
    import run_resilient as launcher
    from competition.arena.cli import main as arena
    from competition.services.experience_library import archive
    os.environ.setdefault('R3E_PILOT_BASE_URL','https://api.deepseek.com')
    launcher.configure_route(os.environ['R3E_PILOT_BASE_URL'],os.environ.get('R3E_NETWORK_ROUTE','direct'))
    try:
        ensure_web(args.port)
    except (OSError,RuntimeError,ValueError) as exc:
        pipeline_status(RUN,status='blocked',message=str(exc))
        print(str(exc),flush=True)
        return 1
    with (RUN/'pipeline.lock').open('a+') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('已有完整流程正在运行；请查看网页。',flush=True)
            return 1
        report = launcher.preflight(ROOT,RUN/'client.json')
        if not report['ready']:
            missing = [k for k,v in report['checks'].items() if not v]
            labels={'credentials':'当前终端未读取到模型 API 密钥','committed_source':'源码尚未完成冻结',
                    'tools':'编译或仿真工具未就绪','dataset_separation':'题目检查未通过',
                    'experience_memory':'历史经验未就绪','client_config':'模型连接配置未就绪'}
            message='；'.join(labels.get(k,k) for k in missing)
            pipeline_status(RUN,status='waiting',message=message,checks=report['checks'])
            print('网页已启动。'+message,flush=True)
            return 2
        plan = signed({'max_calls':args.max_calls,'max_tokens':args.max_tokens,
                       'a_max_calls':400,'a_max_tokens':12000000,'stages':['preview','a0','b','a','compare']})
        freeze(RUN/'pipeline_plan.json',plan)
        pipeline_status(RUN,status='running',message='正在准备本轮实验',pid=os.getpid(),port=args.port)
        def step(name, message, fn):
            started=utc_now()
            pipeline_status(RUN,status='running',stage=name,message=message)
            print(message,flush=True)
            result = fn()
            if isinstance(result,int) and result != 0:
                state=RUN/('arm-b' if name=='b' else 'arm-a')
                path=state/'last_error.json'
                if path.exists():
                    detail=read(path)
                    if detail['time']>=started:
                        raise RuntimeError(detail['message'])
                raise RuntimeError(f'{message}未完成，进度已保存。')
            return result
        try:
            if not (RUN/'baseline.json').exists(): step('init','准备实验',lambda:launcher.main(['init']))
            for arm,name in (('a','static'),('b','adversarial')):
                if not (RUN/('arm-'+arm)/'machine_manifest.json').exists():
                    arena(['arena-init','--config',str(ROOT/f'competition/configs/arena/{name}.yaml'),
                           '--baseline',str(RUN/'baseline.json'),'--state-root',str(RUN/('arm-'+arm))],ROOT)
            budgets={'a':(400,12000000),'b':(args.max_calls,args.max_tokens)}
            for arm in ('a','b'):
                calls,tokens=budgets[arm]
                step('preview-'+arm,f'先展示两道开发题：{arm.upper()} 组',
                     lambda arm=arm,calls=calls,tokens=tokens:demonstration(arm,'preview',max_calls=calls,max_tokens=tokens))
            for command,message in [('a0','普通版本初始评测'),('b','红蓝探索：两轮、每轮最多两个改法'),('a','普通版本最终评测')]:
                calls,tokens=budgets['b' if command=='b' else 'a']
                step(command,message,lambda command=command,calls=calls,tokens=tokens:launcher.main(
                    [command,'--max-calls',str(calls),'--max-tokens',str(tokens)]))
            step('compare','生成最终 A/B 比较',lambda:launcher.main(['compare']))
            pipeline_status(RUN,status='complete',stage='complete',message='本轮已完成，最终结果已生成。')
            return 0
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            from resilience import error_report
            detail=error_report(exc)
            pipeline_status(RUN,status='blocked',message=str(exc),error=detail)
            print(json.dumps(detail,ensure_ascii=False),flush=True)
            return 1
        finally:
            for arm in ('a','b'):
                state=RUN/('arm-'+arm)
                if state.exists(): archive(ROOT,state)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == 'start':
        p=argparse.ArgumentParser(description='一次启动，自动完成开发预览、红蓝探索、最终检查和网页结果。')
        p.add_argument('--port',type=int,default=8085)
        p.add_argument('--max-calls',type=int,default=6000)
        p.add_argument('--max-tokens',type=int,default=120000000)
        args=p.parse_args(argv[1:] if argv else [])
        if args.max_calls<1 or args.max_tokens<1:p.error('预算必须为正数')
        return run_pipeline(args)
    if argv[0]=='view':
        p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8085)
        return serve(port=p.parse_args(argv[1:]).port)
    if argv[0]=='status':
        print(json.dumps(snapshot(),ensure_ascii=False,indent=2));return 0
    import run_resilient
    return run_resilient.main(argv)


if __name__=='__main__':
    raise SystemExit(main())
