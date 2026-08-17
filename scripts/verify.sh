#!/usr/bin/env bash
# Project-agnostic verify. Exit 1 on fail. Print PASS/FAIL.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0

has_npm_test() {
  python3 - <<'PY' 2>/dev/null
import json, sys
from pathlib import Path
p = Path("package.json")
if not p.is_file():
    sys.exit(1)
try:
    data = json.loads(p.read_text())
except Exception:
    sys.exit(1)
scripts = data.get("scripts") or {}
sys.exit(0 if "test" in scripts else 1)
PY
}

run() {
  echo "+ $*"
  if ! "$@"; then
    fail=1
  fi
}

if [[ -f verify.d/commands.sh ]]; then
  echo "using verify.d/commands.sh"
  if ! bash verify.d/commands.sh; then
    fail=1
  fi
else
  if [[ -d tests ]]; then
    if command -v pytest >/dev/null 2>&1; then
      run pytest -q
    elif python3 -c "import pytest" >/dev/null 2>&1; then
      run python3 -m pytest -q
    else
      echo "tests/ exists but pytest is not installed"
      fail=1
    fi
  fi
  if [[ -f package.json ]] && has_npm_test; then
    if command -v npm >/dev/null 2>&1; then
      run npm test
    else
      echo "package.json has a test script but npm is not installed"
      fail=1
    fi
  fi
  if [[ -f Cargo.toml ]]; then
    if command -v cargo >/dev/null 2>&1; then
      run cargo test
    else
      echo "Cargo.toml exists but cargo is not installed"
      fail=1
    fi
  fi
  if [[ -f go.mod ]]; then
    if command -v go >/dev/null 2>&1; then
      run go test ./...
    else
      echo "go.mod exists but go is not installed"
      fail=1
    fi
  fi
fi

echo "Add project-specific checks to verify.d/commands.sh"

if [[ "$fail" -ne 0 ]]; then
  echo FAIL
  exit 1
fi
echo PASS
exit 0
