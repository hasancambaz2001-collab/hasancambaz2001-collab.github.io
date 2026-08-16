#!/usr/bin/env python3
"""Emit MICRO_LIVE_TRIAL.yaml only. Does not send orders. Not LIVE_READY.

python3 scripts/micro_live_bundle.py --i-accept-risk --allow-without-g5

Requires G6 flag. clip 5 without G5, clip 10 with G5.
assets=[btc] tf=[5m] max_daily_loss_usd=25 kill_switch max_open_windows=2
pair_gt_1_trade=false. No clip 67. No full ladder.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY, write_yaml

MICRO = Path("configs/generated/MICRO_LIVE_TRIAL.yaml")
CLIP_NO_G5 = 5.0
CLIP_WITH_G5 = 10.0
MAX_DAILY_LOSS = 25.0
MAX_OPEN = 2


def micro_payload(*, clip: float, g5: bool, g6: bool) -> dict[str, Any]:
    return {
        "status": "MICRO_LIVE_TRIAL",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "live_orders": True,
        "live": False,
        "full_live_ready": False,
        "bundle_placed_orders": False,
        "micro_trial": True,
        "clip": float(clip),
        "max_clip": float(clip),
        "assets": ["btc"],
        "tfs": ["5m"],
        "pair_max": 0.90,
        "cancel_above": 0.92,
        "pair_gt_1_trade": False,
        "size_ok": bool(g5),
        "max_daily_loss_usd": MAX_DAILY_LOSS,
        "kill_switch": True,
        "max_open_windows": MAX_OPEN,
        "g5": "PASS" if g5 else "FAIL",
        "g6": "PASS" if g6 else "FAIL",
        "notes": (
            "MICRO trial permit only. Bundle does not send orders. "
            "Not LIVE_READY. Not full ladder. No clip 67. pair_gt_1_trade=false. "
            "clip 5 without G5, clip 10 with G5."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write MICRO_LIVE_TRIAL.yaml. No orders.")
    parser.add_argument("--i-accept-risk", action="store_true", dest="accept_risk")
    parser.add_argument("--allow-without-g5", action="store_true")
    args = parser.parse_args()
    g6 = (ROOT / G6_FLAG).is_file()
    g5 = (ROOT / G5_FLAG).is_file()
    if not g6:
        print(json.dumps({"ok": False, "reason": "G6 flag missing; refuse MICRO"}))
        return 2
    if not args.accept_risk:
        print(json.dumps({"ok": False, "reason": "pass --i-accept-risk"}))
        return 2
    if not g5 and not args.allow_without_g5:
        print(json.dumps({"ok": False, "reason": "G5 missing; pass --allow-without-g5 for clip 5"}))
        return 2
    clip = CLIP_WITH_G5 if g5 else CLIP_NO_G5
    if clip > (CLIP_WITH_G5 if g5 else CLIP_NO_G5) + 1e-12:
        print(json.dumps({"ok": False, "reason": "clip cap"}))
        return 2
    payload = micro_payload(clip=clip, g5=g5, g6=g6)
    path = write_yaml(ROOT / MICRO, payload)
    live_ready = (ROOT / LIVE_READY).is_file()
    print(json.dumps({
        "ok": True,
        "path": str(path),
        "clip": clip,
        "g5": g5,
        "g6": g6,
        "live_ready_exists": live_ready,
        "bundle_placed_orders": False,
        "pair_gt_1_trade": False,
        "note": "MICRO permit written. Not LIVE_READY. No orders sent.",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
