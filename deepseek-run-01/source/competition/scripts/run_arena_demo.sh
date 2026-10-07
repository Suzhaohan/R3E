#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
if [[ -x .venv/bin/python ]]; then
  demo_python=.venv/bin/python
elif [[ -x ../.venv/bin/python ]]; then
  demo_python=../.venv/bin/python
else
  demo_python=python3
fi
export PYTHONPATH=.
exec "$demo_python" -m competition.scripts.run_arena_demo "$@"
