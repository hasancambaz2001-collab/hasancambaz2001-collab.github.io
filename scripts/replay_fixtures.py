#!/usr/bin/env python3
"""Replay S1 first-send fixtures. Assert expected ALLOW/BLOCK. Not a sender."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.s1_gate import first_send_decision  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "s1"
DEFAULT_CASES = ("0714", "0827", "0759")


def load_case(case_id: str) -> dict:
    path = FIXTURE_DIR / f"{case_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing fixture {path}")
    return json.loads(path.read_text())


def replay_one(case_id: str) -> tuple[bool, str]:
    case = load_case(case_id)
    decision, reason = first_send_decision(case["book"])
    expected = case["expected"]
    expected_reason = case.get("expected_reason")
    ok = decision == expected
    if expected == "BLOCK" and expected_reason and reason != expected_reason:
        ok = False
    if expected == "ALLOW" and reason is not None:
        ok = False
    line = (
        f"{case_id} window={case.get('window')} expected={expected} "
        f"got={decision} reason={reason} ok={ok}"
    )
    return ok, line


def main(argv: list[str]) -> int:
    cases = tuple(argv) if argv else DEFAULT_CASES
    failed = 0
    for case_id in cases:
        try:
            ok, line = replay_one(case_id)
        except Exception as exc:  # noqa: BLE001 — surface fixture errors as FAIL
            print(f"{case_id} ERROR {exc}")
            failed += 1
            continue
        print(line)
        if not ok:
            failed += 1
    if failed:
        print(f"replay_fixtures FAIL ({failed}/{len(cases)})")
        return 1
    print(f"replay_fixtures PASS ({len(cases)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
