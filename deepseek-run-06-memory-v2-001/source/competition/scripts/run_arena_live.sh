#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
if [[ -x .venv/bin/python ]]; then
  arena_python=.venv/bin/python
elif [[ -x ../.venv/bin/python ]]; then
  arena_python=../.venv/bin/python
else
  arena_python=python3
fi
export PYTHONPATH=.
export PYTHONDONTWRITEBYTECODE=1
exec "$arena_python" -m competition.scripts.run_arena_live "$@"
