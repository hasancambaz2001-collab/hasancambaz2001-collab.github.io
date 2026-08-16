#!/usr/bin/env python3
"""Paper loop: log intended BUY FOKs on live btc-updown-5m books. No orders."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.config import load_config, product_from_config
from whiskas.paper import run_paper

DEFAULT_OUT = ROOT / "data" / "paper" / "intended.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-log intended FOKs. Never sends orders.")
    parser.add_argument("--once", action="store_true", help="single snapshot")
    parser.add_argument("--seconds", type=float, default=0.0, help="loop duration (ignored with --once)")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    cfg = product_from_config(load_config(ROOT / "configs" / "whiskas.yaml"))
    once = args.once or args.seconds <= 0
    rows = run_paper(
        out_path=args.out,
        once=once,
        seconds=args.seconds,
        interval=args.interval,
        pair_max=cfg["pair_max"],
        clip=cfg["clip"],
    )
    for rec in rows:
        print(json.dumps({
            "ts": rec.get("ts"),
            "slug": rec.get("slug"),
            "ask_up": rec.get("ask_up"),
            "ask_down": rec.get("ask_down"),
            "ask_sum": rec.get("ask_sum"),
            "intend": rec.get("intend"),
            "reason": rec.get("reason"),
            "depth_ok": rec.get("depth_ok"),
            "live_order": rec.get("live_order"),
        }))
    print(f"appended {len(rows)} row(s) to {args.out} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
