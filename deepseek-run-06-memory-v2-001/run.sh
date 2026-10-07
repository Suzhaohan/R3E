#!/usr/bin/env bash
set -euo pipefail
run_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname -- "$run_dir")"
run_python="${R3E_RUN_PYTHON:-$project_dir/.venv/bin/python}"
if [[ ! -x "$run_python" ]]; then
  echo "找不到 Python 环境：$run_python；请通过 R3E_RUN_PYTHON 指定已有 Python 3.11 环境。" >&2
  exit 1
fi
export PYTHONPATH="$run_dir/source"
export PYTHONDONTWRITEBYTECODE=1
cd -- "$run_dir/source"
if [[ "${1:-}" == start ]]; then
  mkdir -p -- "$run_dir/logs"
  "$run_python" -u "$run_dir/recovery/start.py" "${@:2}" 2>&1 | tee -a "$run_dir/logs/arm-start.log"
  exit "${PIPESTATUS[0]}"
fi
if [[ "${1:-}" == a0 || "${1:-}" == a || "${1:-}" == b ]]; then
  mkdir -p -- "$run_dir/logs"
  "$run_python" -u "$run_dir/recovery/run_resilient.py" "$@" 2>&1 | tee -a "$run_dir/logs/arm-$1.log"
else
  exec "$run_python" -u "$run_dir/recovery/run_resilient.py" "$@"
fi
