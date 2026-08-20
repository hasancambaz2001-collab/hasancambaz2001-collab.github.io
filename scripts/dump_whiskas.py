#!/usr/bin/env python3
"""Dump full public activity + closed positions for @x-moneyforwhiskas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.constants import WHISKAS_PROFILE, WHISKAS_USERNAME, WHISKAS_WALLET
from whiskas.dump import iter_activity, iter_closed_positions, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump Whiskas Polymarket activity")
    parser.add_argument("--user", default=WHISKAS_WALLET)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "raw")
    args = parser.parse_args()

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "username": WHISKAS_USERNAME,
        "profile": WHISKAS_PROFILE,
        "wallet": args.user,
        "source": "https://data-api.polymarket.com",
    }
    print(f"dumping activity for {args.user}", flush=True)
    n_act = write_jsonl(out / "whiskas_activity.jsonl", iter_activity(args.user))
    print(f"activity rows: {n_act}", flush=True)
    print("dumping closed-positions", flush=True)
    n_pos = write_jsonl(out / "whiskas_closed_positions.jsonl", iter_closed_positions(args.user))
    print(f"closed-position rows: {n_pos}", flush=True)
    meta["n_activity"] = n_act
    meta["n_closed_positions"] = n_pos
    (out / "whiskas_dump_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    if n_act == 0:
        print("ERROR: activity dump empty — not faking data", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
