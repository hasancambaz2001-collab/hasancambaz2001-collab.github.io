#!/usr/bin/env python3
"""FULL KASA replay on their tape. S1 only (paper_maker primary). No live.

Default = their size (parity their-size). --clip 10 = parity clip10.
pair_gt_1_trade=false. Do not treat paper intends as PnL.
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

from whiskas.kasa import CLIP_NOW, is_s1, load_all_windows, s1_pnl

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="FULL KASA S1 replay. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--clip", type=float, default=None, help="fixed clip; omit = their size")
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run)", flush=True)
        return 0
    windows = [w for w in load_all_windows(ROOT) if is_s1(w)]
    clip = args.clip
    usd = sum(s1_pnl(w, clip=clip) for w in windows)
    label = "clip10" if clip is not None and abs(float(clip) - CLIP_NOW) < 1e-12 else (
        f"clip{clip:g}" if clip is not None else "their-size"
    )
    payload = {
        "book": "S1",
        "primary": "paper_maker",
        "ask_fok_primary": False,
        "pair_gt_1_trade": False,
        "clip": clip,
        "label": label,
        "n": len(windows),
        "usd": usd,
        "pnl_from_paper_intends": False,
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_json = PROC / f"replay_full_{label}.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n")
    md = REPORTS / "REPLAY_FULL.md"
    prev = md.read_text(encoding="utf-8") if md.is_file() else "# REPLAY_FULL\n\nTheir tape. S1 maker pair<0.90. pair_gt_1_trade=false.\n\n"
    if f"parity {label}" not in prev:
        prev = prev.rstrip() + f"\n\n- parity {label} = **{usd:.2f}** n={len(windows)} clip={clip} ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})\n"
        md.write_text(prev, encoding="utf-8")
    print(json.dumps({"parity": label, "usd": round(usd, 2), "n": len(windows), "clip": clip, "pair_gt_1_trade": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
