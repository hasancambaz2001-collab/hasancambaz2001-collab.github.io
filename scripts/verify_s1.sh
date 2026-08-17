#!/usr/bin/env bash
# S1 verify: pytest (if tests exist) + fixture replay + config invariants.
# Not a deploy. Exit non-zero on fail. Print PASS/FAIL.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0

if compgen -G "tests/test_*.py" > /dev/null; then
  if ! python3 -c "import pytest" >/dev/null 2>&1; then
    python3 -m pip install -q pytest || fail=1
  fi
  if [[ "$fail" -eq 0 ]]; then
    python3 -m pytest tests || fail=1
  fi
fi

python3 scripts/replay_fixtures.py 0714 0827 0759 || fail=1
python3 scripts/check_invariants.py || fail=1

if [[ "$fail" -ne 0 ]]; then
  echo FAIL
  exit 1
fi
echo PASS
exit 0
