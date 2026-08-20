#!/usr/bin/env python3
"""Rank MICRO latency-grid variants by post_ack_ms p50/p95. No send."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.latency_grid import (
    load_jsonl,
    maybe_write_rust_sketch,
    rank_variants,
    write_grid_report,
)

DEFAULT_TAPE = ROOT / "data" / "micro_live" / "intended.jsonl"
DEFAULT_MD = ROOT / "data" / "reports" / "MICRO_LATENCY_GRID.md"
DEFAULT_JSON = ROOT / "data" / "processed" / "micro_latency_grid.json"
DEFAULT_RUST = ROOT / "data" / "reports" / "MICRO_RUST_SKETCH.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank latency-grid variants. GET tape only.")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_TAPE)
    parser.add_argument("--out", type=Path, default=DEFAULT_MD)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--rust-out", type=Path, default=DEFAULT_RUST)
    args = parser.parse_args()
    rows = load_jsonl(args.jsonl)
    result = rank_variants(rows)
    write_grid_report(result, args.out, tape=str(args.jsonl))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    wrote_rust = maybe_write_rust_sketch(result, args.rust_out)
    print(json.dumps({**result, "md": str(args.out), "rust_written": wrote_rust}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
