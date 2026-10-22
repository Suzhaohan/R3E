"""One terminal entry for all frozen designs; paired promotion and independent final results."""
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
    command = [sys.executable, '-u', str(HERE / 'experiment.py'), action,
               '--run-dir', str(run_dir)]
    if env_file is not None:
        command += ['--env-file', str(env_file)]
    return subprocess.run(command, check=False, pass_fds=pass_fds).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path,
                        default=HERE / ('real-all-' + datetime.now().strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--port', type=int, default=8098)
    parser.add_argument('--check-only', action='store_true', help='offline check; no credentials, viewer, or model requests')
    args = parser.parse_args()
    if not 1 <= args.port <= 65533:
        parser.error('--port 必须在 1 到 65533 之间，为三个网页保留起始端口')
    run_dir = args.run_dir.resolve()
    if run_dir.exists():
        parser.error('运行目录已存在，禁止重跑或隐式恢复；请指定新的 --run-dir')
    if args.env_file is not None and not args.env_file.is_file():
        parser.error('--env-file 不存在')
    result = step('check', run_dir)
    if result or args.check_only:
        return result
    print('三题经验独立：先让无经验组考完整套题，全对则整批停止；否则封存成绩，完成各五轮流程后仅对抗组考试；无人工备用题，空轮如实记录。正常最多129次，硬上限258次模型请求。', flush=True)
    print('模型：DeepSeek V3-0324（2025年3月版，deepseek/deepseek-chat-v3-0324），通过 OpenRouter 调用。', flush=True)
    print(f'本次运行目录：{run_dir}', flush=True)
    fd = None
    try:
        env_file, pass_fds = args.env_file, ()
        if env_file is None:
            if not sys.stdin.isatty():
                parser.error('请在交互终端运行，或通过 --env-file 指定已有凭据文件')
            key = getpass.getpass('粘贴 OpenRouter API 密钥后按回车（输入不显示，只需一次）：').strip()
            if not key or len(key) > 4096 or any(c in key for c in ('\n', '\r', '\x00')):
                parser.error('密钥必须是非空单行文本')
            fd = os.memfd_create('r3e-all-credentials', os.MFD_CLOEXEC)
            payload = ('OPENROUTER_API_KEY=' + shlex.quote(key) + '\n'
                       'OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n').encode()
            os.write(fd, payload)
            os.lseek(fd, 0, os.SEEK_SET)
            del key, payload
            env_file, pass_fds = f'/proc/self/fd/{fd}', (fd,)
        from dashboard import available_viewer, open_browser
        for index, design in enumerate(('Prob001', 'Prob023', 'Prob003')):
            try:
                url = available_viewer(run_dir / design, args.port + index)
            except (OSError, RuntimeError) as error:
                print(f'{design} 网页未启动：{error}；继续实验，稍后可用 view 查看。', flush=True)
                continue
            print(f'{design} 结果网页：{url}', flush=True)
            open_browser(url)
        print('远程服务器请转发上面打印的端口。', flush=True)
        result = step('collect', run_dir, env_file, pass_fds)
    finally:
        if fd is not None:
            os.close(fd)
    if result:
        print(f'实验已停止（退出码 {result}），保留现有证据，不自动重跑。', flush=True)
        step('results', run_dir)
        return result
    for action in ('results',):
        result = step(action, run_dir)
        if result:
            return result
    import json
    gate=json.loads((run_dir/'initial_exam_gate.json').read_text())
    if gate['decision']=='stop_saturated':
        print(f'无经验组前测 {gate["passed"]}/{gate["samples"]} 全对，本批已停止，未开始训练。目录：{run_dir}',flush=True)
        return 0
    print(f'本批训练和统一考试已结束，详见静态组与对抗组成绩。目录：{run_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
