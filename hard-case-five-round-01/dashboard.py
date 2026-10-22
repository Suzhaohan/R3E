"""Local, read-only presentation layer; frozen experiment code remains unchanged."""

import argparse
import getpass
import errno
import socket
import shlex
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 2


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def read_rows(path):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def snapshot(run_dir):
    root = run_dir/'collection' if (run_dir/'collection').is_dir() else run_dir
    plan = read_json(root/'plan.json')
    collection = read_json(root/'collection.json')
    calls = read_rows(root/'calls.jsonl')
    usage = read_rows(run_dir/'usage_guard.jsonl')
    responses = [row for row in usage if row.get('event') == 'response']
    starts = [row for row in usage if row.get('event') == 'started']
    report = read_json(root/'report.json')
    promotions = read_rows(root/'promotions.jsonl')
    slots = {row['round']: row for row in read_rows(root/'slots.jsonl')}
    commits = [read_json(root/'rounds'/str(index)/'commit.json') for index in range(1, 6)]
    rounds = []
    for index, commit in enumerate(commits, 1):
        slot = slots.get(index, {})
        trials = slot.get('trials', {})
        round_calls = [row for row in calls if row.get('slot_id') == f'r{index}_s0']
        failed_request = any(not row.get('ok') for row in round_calls)
        rounds.append({'round': index,
                       'admission': slot.get('admission', 'provider_failure' if failed_request else None),
                       'reason': slot.get('reason'),
                       'generation_source': slot.get('generation_source'),
                       'online': trials.get('online', {}).get('status'),
                       'reference': trials.get('reference', {}).get('status'),
                       'entries': len(commit.get('blue', {}).get('entries', [])) if commit else None,
                       'training_entries':len(commit.get('practice_blue',commit.get('blue',{})).get('entries',[])) if commit else None,
                       'snapshot': commit.get('blue', {}).get('snapshot_id'),
                       'state_hash': commit.get('blue', {}).get('state_hash'),
                       'decisions': [{'reason': row.get('reason')} for row in commit.get('update_decisions', [])],
                       'committed': bool(commit)})
    latest = usage[-1] if usage else {}
    stop = read_json(run_dir/'launch_stop.json')
    quality_stop = read_json(root/'stop_reason.json')
    diagnostics = stop.get('diagnostics', {})
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    provider_error = {key: diagnostics[key] for key in
                      ('cause', 'http_status', 'error_code', 'consecutive_failures', 'halt', 'billing')
                      if key in diagnostics}
    state = collection.get('status', 'running' if calls or starts else 'waiting')
    if stop:
        state = 'aborted'
    completed_rounds = sum(bool(commit) for commit in commits)
    phase = '尚未启动'
    if state == 'complete':
        phase = '全部收集完成；离线报告已生成' if report else '全部收集完成；等待离线报告'
    elif state == 'pretested':
        phase = '无经验组前测已完成；等待整套前测门槛判断或开始训练；成绩封存复用'
        if any(row.get('event')=='training_started_after_initial_exam_gate' for row in read_rows(root/'events.jsonl')):
            phase = f'无经验组成绩已封存；本题五轮流程已完成 {completed_rounds}/5 轮'
    elif state == 'stopped_exam_saturated':
        phase = '无经验组整套前测全对；本批停止，未开始训练'
    elif state == 'stopped_pretest_inconclusive':
        phase = '前测存在无效测量；本批停止，无法判断区分度'
    elif state == 'trained':
        phase = f'五轮流程已结束（有效练习 {collection.get("qualified_practice_slots",0)}/5）；等待统一考试'
        if any(row.get('event')=='final_exam_started' for row in read_rows(root/'events.jsonl')):
            phase = f'统一考试中：已完成 {len(read_rows(root/"probes.jsonl"))}/{len(plan.get("anchor_probes",[]))} 次'
    elif state == 'skipped':
        phase = '本题验证基线满分，跳过训练与考试；批次继续下一题'
    elif state == 'aborted':
        phase = '实验已停止；请查看终端日志，不会自动重试'
        reasons = {'generation_attempts_exhausted': '出题纠错次数耗尽，已停止，未继续考试',
                   'validation_baseline_saturated': '验证基线已满分，无晋升空间，已停止',
                   'no_effective_practice_two_rounds': '连续两轮没有有效修复经验，已停止，未继续考试'}
        if quality_stop:
            phase = reasons.get(quality_stop.get('reason'), '质量检查停止')
        if diagnostics.get('http_status') == 503:
            phase = '实验中断：DeepSeek 返回 HTTP 503（服务繁忙），不是五轮完成'
    elif state == 'running':
        phase = f'五轮在线部分：已完成 {completed_rounds}/5 轮'
        if plan.get('initial_exam_policy') and not (root/'initial_exam.json').exists():
            phase = f'无经验组前测中：本题已完成 {len(read_rows(root/"probes.jsonl"))}/2 次；尚未训练'
        if completed_rounds == 5:
            phase = f'最终保留题考核：已完成 {len(read_rows(root/"probes.jsonl"))} / {len(plan.get("anchor_probes", []))} 次'
        if latest.get('event') == 'started':
            phase += '；模型请求等待返回'
        else:
            phase += '；测试/更新或准备下一请求'
    counted = responses if usage else calls
    def tokens(key):
        return sum(row[key] for row in counted if type(row.get(key)) is int and row[key] >= 0)

    latest_commit = next((commit for commit in reversed(commits) if commit), {})
    memory = []
    for entry in latest_commit.get('blue', {}).get('entries', []):
        body = entry.get('body', {})
        content = body.get('content', {})
        memory.append({'created_round': body.get('created_round'),
                       'validation': content.get('validation'),
                       'public_rows': content.get('public_rows', {}),
                       'repair_evidence': content.get('repair_evidence'),
                       'applied_patch': content.get('applied_patch', '')})
    return {'schema_version': SCHEMA_VERSION, 'run_dir': str(run_dir), 'status': state, 'phase': phase,
            'model': plan.get('client_config', {}).get('model_id'),
            'mock': plan.get('client_config', {}).get('model_id') == 'fake-local',
            'rounds': rounds, 'completed_rounds': completed_rounds,
            'promotions': [{k:g.get(k) for k in ('round','accepted','reason','incumbent_passed','candidate_passed','scheduled_pairs','retained_entries','measured_gain','training_entries')} for g in promotions],
            'accepted_promotions': sum(g.get('accepted', False) for g in promotions),
            'strict_gain_promotions': sum(g.get('accepted',False) and g.get('reason')=='strict_gain_no_regression' for g in promotions),
            'retentions_without_measured_gain': sum(g.get('accepted',False) and g.get('reason')=='retained_no_regression_no_measured_gain' for g in promotions),
            'human_prepared_replacements': 0,
            'empty_practice_slots':len(read_rows(root/'empty_practice.jsonl')),
            'admitted_challenges': sum(row.get('admission') == 'admitted' for row in slots.values()),
            'successful_responses': sum(row.get('ok') is True for row in calls),
            'unknown_usage_requests': sum(row.get('event') == 'transport_error' for row in usage),
            'provider_error': provider_error, 'memory': memory,
            'trace': [{key: row.get(key) for key in
                       ('role', 'slot_id', 'snapshot_id', 'ok', 'error', 'input_tokens', 'output_tokens')}
                      for row in calls],
            'calls': len(starts) if usage else len(calls), 'max_calls': plan.get('max_calls', 88),
            'input_tokens': tokens('input_tokens'),
            'output_tokens': tokens('output_tokens'),
            'http_event': latest.get('event'), 'http_time': latest.get('time_utc'),
            'probes_completed': len(read_rows(root/'probes.jsonl')),
            'probes_scheduled': len(plan.get('anchor_probes', [])),
            'exam_questions': len(plan.get('anchors', [])),
            'anchor_repeats': plan.get('anchor_repeats'),
            'report_available': bool(report),
            'final': report.get('reserved_variants_by_snapshot', []),
            'online': [{'round': row.get('round'),
                        'online': row.get('online', {}).get('category'),
                        'reference': row.get('reference', {}).get('category')}
                       for row in report.get('online_and_frozen_reference', [])],
            'audits_available': all((root/'audits'/name).is_file()
                                    for name in ('exposure_audit.json', 'source_audit.json'))}


def make_server(run_dir, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/api/status':
                data = json.dumps(snapshot(run_dir), ensure_ascii=False).encode()
                content_type = 'application/json; charset=utf-8'
            elif self.path in {'/', '/index.html'}:
                data = (HERE/'dashboard.html').read_bytes()
                content_type = 'text/html; charset=utf-8'
            elif self.path == '/static/styles.css':
                data = (HERE/'dashboard.css').read_bytes()
                content_type = 'text/css; charset=utf-8'
            elif self.path == '/static/prob003.js':
                data = (HERE/'dashboard.js').read_bytes()
                content_type = 'text/javascript; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


class ViewerPortOccupied(RuntimeError):
    pass


def ensure_viewer(run_dir, port):
    url = f'http://127.0.0.1:{port}/'
    opener = build_opener(ProxyHandler({}))

    def current():
        try:
            with opener.open(url+'api/status', timeout=1) as response:
                return json.load(response)
        except (OSError, ValueError, URLError):
            return None

    existing = current()
    if existing is not None:
        if existing.get('run_dir') != str(run_dir):
            raise ViewerPortOccupied(f'端口 {port} 已展示其他运行')
        if existing.get('schema_version') != SCHEMA_VERSION:
            raise ViewerPortOccupied(f'端口 {port} 仍是旧版网页服务')
        return url
    # Also detect services that do not expose our status endpoint.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise ViewerPortOccupied(f'端口 {port} 已被占用') from None
            raise
    log_dir = HERE/'viewer-logs'
    log_dir.mkdir(exist_ok=True)
    with (log_dir/f'{port}.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, str(HERE/'dashboard.py'), 'serve',
                                    '--run-dir', str(run_dir), '--port', str(port)],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    for attempt in range(40):
        status = current()
        if status and status.get('run_dir') == str(run_dir):
            print(f'网页服务 PID：{process.pid}（关闭终端后仍可查看；关机后需重新启动 view）', flush=True)
            return url
        if process.poll() is not None:
            break
        time.sleep(0.1)
    if process.poll() is None:
        process.terminate()
    raise RuntimeError(f'网页启动失败，请查看 {log_dir}/{port}.log；端口可能被占用')


def available_viewer(run_dir, preferred_port):
    if not 1 <= preferred_port <= 65535:
        raise ValueError('端口必须在 1 到 65535 之间')
    for port in range(preferred_port, min(preferred_port + 20, 65536)):
        try:
            return ensure_viewer(run_dir, port)
        except ViewerPortOccupied as error:
            print(f'{error}，自动尝试下一端口。', flush=True)
    print('相邻端口均不可用，自动选择系统空闲端口。', flush=True)
    for attempt in range(10):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        try:
            return ensure_viewer(run_dir, port)
        except ViewerPortOccupied:
            # Another process may claim the port after the probe closes.
            continue
    raise RuntimeError('自动选择空闲端口失败，请稍后重新启动 view')


def run_step(action, args):
    command = [sys.executable, '-u', str(HERE/'experiment.py'), action,
               '--run-dir', str(args.run_dir), '--plan-dir', str(args.plan_dir), '--design', args.design]
    if action == 'collect':
        if args.env_file is not None:
            command += ['--env-file', str(args.env_file)]
        else:
            if not sys.stdin.isatty():
                raise ValueError('请在交互终端启动，然后粘贴密钥并按回车')
            key = getpass.getpass('粘贴 OpenRouter API 密钥后按回车（输入不显示）：').strip()
            if not key or len(key) > 4096 or any(c in key for c in ('\n', '\r', '\x00')):
                raise ValueError('密钥不能为空，且必须为单行文本')
            # A regular file descriptor held only in RAM satisfies the frozen
            # credential loader without writing a key file or changing the plan.
            fd = os.memfd_create('prob003-credentials', os.MFD_CLOEXEC)
            try:
                data = ('OPENROUTER_API_KEY=' + shlex.quote(key) + '\n'
                        'OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n').encode()
                os.write(fd, data)
                os.lseek(fd, 0, os.SEEK_SET)
                del key, data
                command += ['--env-file', f'/proc/self/fd/{fd}']
                return subprocess.run(command, check=False, pass_fds=(fd,)).returncode
            finally:
                os.close(fd)
    return subprocess.run(command, check=False).returncode


def open_browser(url):
    if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        try:
            webbrowser.open_new_tab(url)
        except webbrowser.Error:
            print('自动打开浏览器失败，请手动打开上方链接。', flush=True)


def main():
    parser = argparse.ArgumentParser(description='恢复本地实时进度与结果网页，不修改冻结实验')
    parser.add_argument('action', nargs='?', default='start', choices=['start', 'view', 'serve'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--plan-dir', type=Path, default=HERE/'plan-v3-0324-handoff-prob003-red-only-v1')
    parser.add_argument('--design', choices=['Prob003', 'Prob023', 'Prob017'], default='Prob003')
    parser.add_argument('--port', type=int, default=8093)
    args = parser.parse_args()
    args.run_dir = args.run_dir.resolve()
    args.plan_dir = args.plan_dir.resolve()
    if args.action == 'serve':
        with make_server(args.run_dir, args.port) as server:
            server.serve_forever()
        return 0
    if args.action == 'start':
        if args.env_file is not None and not args.env_file.is_file():
            parser.error('--env-file 必须指向已有文件；省略此参数可在终端输入密钥')
        if args.run_dir.exists():
            parser.error('运行目录已存在，禁止重跑或隐式恢复。仅看结果请用 view')
    url = available_viewer(args.run_dir, args.port)
    print(f'实时进度与结果网页：{url}', flush=True)
    print('远程服务器请转发此端口后在自己电脑的浏览器打开；网页本身不会调用模型。', flush=True)
    open_browser(url)
    if args.action == 'view':
        print('仅展示现有记录，没有启动实验或模型请求。', flush=True)
        return 0
    print('开始原五轮实验；本入口仅补回展示及结束后的离线报告。', flush=True)
    result = run_step('collect', args)
    if result == 0 and read_json(args.run_dir/'collection/collection.json').get('status') == 'complete':
        result = run_step('report', args)
        if result == 0:
            result = run_step('audits', args)
    if read_json(args.run_dir/'collection/collection.json').get('status') == 'aborted':
        status = snapshot(args.run_dir)
        print(status['phase'], flush=True)
        print('没有最终考核成绩；已提交的失败槽位不等于有效修复轮次。', flush=True)
        if status['unknown_usage_requests']:
            print('接口失败未返回 token 用量，账单未知；不能据此认定免费。', flush=True)
    print(f'实验进程已结束（退出码 {result}），网页继续保留：{url}', flush=True)
    return result


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(f'停止：{error}', file=sys.stderr)
        raise SystemExit(1)
