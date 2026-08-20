#!/usr/bin/env python3
"""Scaffold only. 06dc maker Phase1. No live. No --run. Do not overwrite paper_06dc.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if "--run" in sys.argv:
        print("refusing --run (scaffold only)", file=sys.stderr)
        return 2
    print(f"SCAFFOLD {Path(__file__).name} cfg={ROOT / 'configs' / '06dc.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
