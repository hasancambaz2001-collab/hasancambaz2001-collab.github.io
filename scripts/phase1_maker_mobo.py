#!/usr/bin/env python3
"""Scaffold only. Phase1 maker/mobo. No live. No dump. No --run."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if "--run" in sys.argv:
        print("refusing --run (scaffold only)", file=sys.stderr)
        return 2
    print(f"SCAFFOLD {Path(__file__).name} cfg={ROOT / 'configs' / 'mobo.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
