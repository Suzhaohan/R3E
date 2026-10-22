"""Start one independent V3-0324 run with an in-memory credential file."""
import argparse
from datetime import datetime
import getpass
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def step(action, run_dir, env_file=None, pass_fds=()):
    command = [sys.executable, '-u', str(HERE/'experiment.py'), action,
               '--run-dir', str(run_dir)]
    if env_file is not None:
        command += ['--env-file', str(env_file)]
    return subprocess.run(command, pass_fds=pass_fds).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path,
                        default=HERE/('real-v3-0324-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--port', type=int, default=8104)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if run_dir == HERE or HERE not in run_dir.parents:
        parser.error('运行目录必须位于本次 V3 独立目录内')
    if run_dir.exists():
        parser.error('运行目录已存在；禁止覆盖或恢复，请选择新目录')
    if not 1 <= args.port <= 65515:
        parser.error('端口必须在1到65515之间')
    if args.env_file is not None and not args.env_file.is_file():
        parser.error('凭据文件不存在')
    result = step('check', run_dir)
    if result or args.check_only:
        return result
    print('DeepSeek V3-0324，通过 OpenRouter / SiliconFlow 调用。', flush=True)
    print('沿用01：空经验起步、五轮、每组一次修复、两个考试变体各重复两次，最多39次模型请求。', flush=True)
    print(f'新记录目录：{run_dir}', flush=True)
    fd = None
    try:
        env_file, pass_fds = args.env_file, ()
        if env_file is None:
            if not sys.stdin.isatty():
                parser.error('请在交互终端运行以隐藏输入密钥，或指定 --env-file')
            key = getpass.getpass('粘贴 OpenRouter API 密钥后按回车（输入不显示）：').strip()
            if not key or len(key) > 4096 or any(c in key for c in ('\n', '\r', '\x00')):
                parser.error('密钥必须是非空单行文本')
            fd = os.memfd_create('prob003-v3-0324-credentials', os.MFD_CLOEXEC)
            payload = ('OPENROUTER_API_KEY='+shlex.quote(key)+'\n'
                       'OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n').encode()
            os.write(fd, payload)
            os.lseek(fd, 0, os.SEEK_SET)
            del key, payload
            env_file, pass_fds = f'/proc/self/fd/{fd}', (fd,)
        from dashboard import ensure_viewer
        for port in range(args.port, args.port+20):
            try:
                url = ensure_viewer(run_dir, port)
                print(f'实时网页：{url}（远程服务器请转发端口 {port}）', flush=True)
                break
            except (OSError, ValueError, RuntimeError):
                continue
        else:
            print('网页未能启动，实验记录仍会保存。', flush=True)
        result = step('collect', run_dir, env_file, pass_fds)
    finally:
        if fd is not None:
            os.close(fd)
    if result:
        print('实验已停止，记录保留；不自动重试或恢复。', flush=True)
        return result
    for action in ('report', 'audits'):
        result = step(action, run_dir)
        if result:
            return result
    import json
    report = json.loads((run_dir/'collection/report.json').read_text())
    for row in report['reserved_variants_by_snapshot']:
        passed = row['categories'].get('public_pass_hidden_pass', 0)
        print(f"{row['snapshot']}：公开及补充评测通过 {passed}/{row['scheduled']}", flush=True)
    print(f'实验完成：{run_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
