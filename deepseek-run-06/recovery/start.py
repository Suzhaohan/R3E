"""Sequence the original run03 commands; serve its original observer UI."""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import URLError

import run_resilient as launcher
from r3e.protocol.hashing import atomic_write_json, utc_now

RUN=Path(__file__).resolve().parents[1]


def ensure_observer(port):
    """Reuse a slow observer; only a refused connection permits starting one."""
    opener = build_opener(ProxyHandler({}))
    url = f'http://127.0.0.1:{port}/api/arena/status'
    deadline = time.monotonic() + 60
    process = None
    last_error = None
    waiting_reported = False
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=min(15, max(.1, deadline - time.monotonic()))) as response:
                status = json.load(response)
            if not isinstance(status, dict) or not isinstance(status.get('available'), bool):
                raise ValueError('unexpected observer response')
            return
        except (OSError, ValueError) as exc:
            last_error = exc
            reason = exc.reason if isinstance(exc, URLError) else exc
            refused = isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
            timed_out = isinstance(reason, TimeoutError)
            if refused:
                if process is None:
                    (RUN / 'logs').mkdir(exist_ok=True)
                    with (RUN / 'logs/web.log').open('ab') as log:
                        process = subprocess.Popen(
                            [sys.executable, str(RUN / 'recovery/run_resilient.py'),
                             'view', '--port', str(port)],
                            stdout=log, stderr=log, start_new_session=True)
                elif process.poll() is not None:
                    raise RuntimeError('网页启动失败，请检查 logs/web.log') from exc
            elif timed_out:
                if not waiting_reported:
                    print('网页状态响应较慢，正在等待；不会重复启动网页服务。', flush=True)
                    waiting_reported = True
            else:
                raise RuntimeError(
                    f'端口 {port} 的网页状态检查失败（{type(reason).__name__}）；'
                    '请检查 logs/web.log。实验尚未启动。') from exc
        time.sleep(.25)
    raise RuntimeError(
        f'网页状态在 60 秒内未就绪（端口 {port}）；未重复启动服务，实验尚未启动。'
    ) from last_error


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8086)
    parser.add_argument('--max-calls',type=int,default=6000)
    parser.add_argument('--max-tokens',type=int,default=120000000)
    args=parser.parse_args(argv)
    if args.max_calls<1 or args.max_tokens<1: parser.error('预算必须为正数')
    os.environ.setdefault('R3E_PILOT_BASE_URL','https://api.deepseek.com')
    with (RUN/'pipeline.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('同一次运行已经在执行，请查看网页。');return 1
        ensure_observer(args.port)
        print(f'原版界面：http://127.0.0.1:{args.port}',flush=True)
        report=launcher.preflight(launcher.ROOT,RUN/'client.json')
        if not report['ready']:
            labels={'credentials':'当前终端没有模型 API 密钥','committed_source':'源码尚未冻结',
                    'tools':'仿真工具未就绪','dataset_separation':'题目隔离检查未通过',
                    'client_config':'模型配置未就绪'}
            print('运行条件尚未满足：'+'；'.join(labels.get(k,k) for k,v in report['checks'].items() if not v),flush=True)
            return 2
        if not (RUN/'baseline.json').exists():
            if launcher.main(['init']):return 1
        stages=[('a0',400,12000000),('b',args.max_calls,args.max_tokens),('a',400,12000000)]
        for command,calls,tokens in stages:
            atomic_write_json(RUN/'pipeline.json',{'stage':command,'status':'running','updated_at':utc_now()})
            result=launcher.main([command,'--max-calls',str(calls),'--max-tokens',str(tokens)])
            if result:
                atomic_write_json(RUN/'pipeline.json',{'stage':command,'status':'stopped','updated_at':utc_now()})
                return result
        result=launcher.main(['compare'])
        atomic_write_json(RUN/'pipeline.json',{'stage':'compare','status':'complete' if result==0 else 'stopped','updated_at':utc_now()})
        return result


if __name__=='__main__':
    raise SystemExit(main())
