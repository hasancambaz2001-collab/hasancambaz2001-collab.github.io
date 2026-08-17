#!/usr/bin/env bash
# Project checks from docs/GOAL.md verify commands. Not a deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! python3 -c "import pytest" >/dev/null 2>&1; then
  python3 -m pip install -q pytest
fi
python3 -m pytest -q tests
python3 scripts/replay_fixtures.py 0714 0827 0759
python3 scripts/check_invariants.py
