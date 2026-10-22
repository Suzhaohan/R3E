"""Fresh Prob003-only five-round verification using the current frozen experiment."""
import argparse
from datetime import datetime
import getpass
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,default=HERE/('prob003-handoff-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();directory=args.run_dir.resolve()
    if directory.exists():parser.error('运行目录已存在，请使用新目录；不隐式恢复旧经验')
    if args.env_file is not None and not args.env_file.is_file():parser.error('--env-file 不存在')
    def run(action,env_file=None,pass_fds=()):
        cmd=[sys.executable,'-u',str(HERE/'experiment.py'),action,'--design','Prob003','--run-dir',str(directory)]
        if env_file is not None:cmd+=['--env-file',str(env_file)]
        return subprocess.run(cmd,pass_fds=pass_fds,check=False).returncode
    result=run('check')
    if result or args.check_only:return result
    print('仅运行Prob003：新批次空经验；先前测，2/2则停止，否则五轮后考试。所有蓝队角色均用完整文件修复，不提供人工专项解题提示。练习两分支均最多4次功能尝试，考试与验证仍最多2次。硬上限202次模型请求。',flush=True)
    print('运行目录：'+str(directory),flush=True)
    fd=None
    try:
        env_file,pass_fds=args.env_file,()
        if env_file is None:
            if not sys.stdin.isatty():parser.error('请在交互终端运行，或提供 --env-file')
            key=getpass.getpass('输入OpenRouter API密钥（不显示、不保存到磁盘）：').strip()
            if not key or len(key)>4096 or any(c in key for c in ('\n','\r','\x00')):parser.error('密钥须为非空单行文本')
            fd=os.memfd_create('r3e-prob003-credentials',os.MFD_CLOEXEC)
            payload=('OPENROUTER_API_KEY='+shlex.quote(key)+'\nOPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n').encode()
            os.write(fd,payload);os.lseek(fd,0,os.SEEK_SET);del key,payload
            env_file,pass_fds=f'/proc/self/fd/{fd}',(fd,)
        result=run('collect',env_file,pass_fds)
    finally:
        if fd is not None:os.close(fd)
    if result:
        print('运行停止，已有证据保留，退出码：'+str(result),flush=True)
        return result
    return run('results')


if __name__=='__main__':raise SystemExit(main())
