#!/usr/bin/env bash
set -euo pipefail
pilot_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pilot_python="${R3E_RUN_PYTHON:-$pilot_dir/../.venv/bin/python}"
export PYTHONDONTWRITEBYTECODE=1
if [[ "${1:-}" == start && -z "${DEEPSEEK_API_KEY:-}${R3E_PILOT_API_KEY:-}" && " $* " != *" --llm-env "* ]]; then
  if [[ ! -t 0 ]]; then
    echo '请在交互终端启动并输入 API 密钥；不要把密钥发送到聊天。' >&2
    exit 1
  fi
  read -r -s -p '粘贴 DeepSeek API 密钥后按回车（输入不显示）：' R3E_PILOT_API_KEY
  export R3E_PILOT_API_KEY
  printf '\n'
fi
mkdir -p "$pilot_dir/logs"
"$pilot_python" -u "$pilot_dir/pilot.py" "$@" 2>&1 | tee -a "$pilot_dir/logs/${1:-help}.log"
