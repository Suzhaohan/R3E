#!/usr/bin/env bash
set -euo pipefail
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec "${R3E_RUN_PYTHON:-$task_dir/../.venv/bin/python}" -u "$task_dir/start.py" "$@"
