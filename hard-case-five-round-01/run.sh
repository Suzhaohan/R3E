#!/usr/bin/env bash
set -euo pipefail
pilot_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pilot_python="${R3E_RUN_PYTHON:-$pilot_dir/../.venv/bin/python}"
export PYTHONDONTWRITEBYTECODE=1
exec "$pilot_python" -u "$pilot_dir/experiment.py" "$@"
