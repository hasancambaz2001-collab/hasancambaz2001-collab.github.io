#!/usr/bin/env python3
"""Optional event-driven L2 recorder. GET/WS subscribe only. Never posts.

python3 scripts/l2_ws_recorder.py --once
Do not start this if you were not asked. Does not replace l2_recorder.
Does not cover 06dc daily/monthly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.l2_recorder import snapshot_tick
from whiskas.l2 import ASSETS, TFS
from whiskas.paper import append_jsonl

DEFAULT_OUT = ROOT / "data" / "l2_ws"


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional WS-shaped L2 snapshot. Never posts.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--assets", default=",".join(ASSETS))
    parser.add_argument("--tfs", default=",".join(TFS))
    args = parser.parse_args()
    one_pass = bool(args.once) or args.seconds is not None
    if not one_pass:
        print(f"SCAFFOLD {Path(__file__).name} (pass --once or --seconds). Not started. GET only.", flush=True)
        return 0
    assets = tuple(a.strip().lower() for a in args.assets.split(",") if a.strip())
    tfs = tuple(t.strip().lower() for t in args.tfs.split(",") if t.strip())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for asset in assets:
        for tf in tfs:
            tick = snapshot_tick(asset=asset, tf=tf)
            rec = tick.to_record()
            rec["source"] = "l2_ws_recorder_once"
            rec["live_order"] = False
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            append_jsonl(args.out_dir / f"{asset}_{tf}_{day}.jsonl", rec)
            n += 1
    print(json.dumps({"ok": True, "rows": n, "live_order": False, "note": "once snapshot; REST fallback"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
