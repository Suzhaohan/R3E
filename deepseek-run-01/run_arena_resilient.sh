#!/usr/bin/env bash
set -euo pipefail
recovery_run_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$recovery_run_dir/source/.venv/bin/python" ]]; then
  recovery_python="$recovery_run_dir/source/.venv/bin/python"
elif [[ -x "$recovery_run_dir/.venv/bin/python" ]]; then
  recovery_python="$recovery_run_dir/.venv/bin/python"
else
  # Match the frozen launcher's interpreter selection: use the active shell
  # environment, rather than silently choosing a different parent venv.
  recovery_python=python3
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$recovery_python" "$recovery_run_dir/recovery/run_resilient.py" "$@"
