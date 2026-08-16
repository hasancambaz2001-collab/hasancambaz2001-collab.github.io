#!/usr/bin/env python3
"""G6 paper fill calibration from paper_maker tape. Does NOT write the G6 flag.

python3 scripts/g6_fill_cal.py --run

Counts rests / skips / residual-sim fills. still@250ms is not on this 2s poller.
Do not treat intends as PnL. Do not set size_ok.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.paper import load_jsonl

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DEFAULT_IN = ROOT / "data" / "paper_maker" / "intended.jsonl"
SKIP = {"rich_bid_sum", "thin_bid", "missing_bid", "gamma_error", "clob_error", "missing_tokens"}
FILL = {"complete", "filled_both"}
REST_LIKE = {"rest", "requote", "hold"}


def _day(ts: str | None) -> str:
    if not ts:
        return "unknown"
    return str(ts)[:10]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    days: dict[str, Counter[str]] = defaultdict(Counter)
    n_still = 0
    n_still_true = 0
    first = last = None
    live_order = False
    for rec in rows:
        if rec.get("book") and rec.get("book") != "maker":
            continue
        reason = str(rec.get("reason") or "none")
        reasons[reason] += 1
        day = _day(str(rec.get("ts") or ""))
        days[day][reason] += 1
        ts = str(rec.get("ts") or "")
        if ts and (first is None or ts < first):
            first = ts
        if ts and (last is None or ts > last):
            last = ts
        if rec.get("live_order"):
            live_order = True
        if "still_there_250ms" in rec:
            n_still += 1
            if rec.get("still_there_250ms") is True:
                n_still_true += 1
    n = sum(reasons.values())
    n_rest = int(reasons.get("rest", 0))
    n_skip = sum(int(reasons.get(k, 0)) for k in SKIP)
    n_fill = sum(int(reasons.get(k, 0)) for k in FILL)
    n_hold = int(reasons.get("hold", 0))
    fill_pct = (n_fill / n_rest) if n_rest else None
    still_pct = (n_still_true / n_still) if n_still else None
    day_rows = []
    worst = None
    for day, ctr in sorted(days.items()):
        rest = int(ctr.get("rest", 0))
        fill = sum(int(ctr.get(k, 0)) for k in FILL)
        skip = sum(int(ctr.get(k, 0)) for k in SKIP)
        pct = (fill / rest) if rest else None
        rec = {"day": day, "rest": rest, "fill_sim": fill, "skip": skip, "fill_pct": pct}
        day_rows.append(rec)
        if pct is not None and (worst is None or pct < worst["fill_pct"]):
            worst = rec
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "paper_maker intended.jsonl",
        "n_rows": n,
        "first_ts": first,
        "last_ts": last,
        "rests": n_rest,
        "skips": n_skip,
        "hold": n_hold,
        "requote": int(reasons.get("requote", 0)),
        "fill_sim": n_fill,
        "complete": int(reasons.get("complete", 0)),
        "filled_both": int(reasons.get("filled_both", 0)),
        "pair_gt_1_cancel": int(reasons.get("pair_gt_1", 0)),
        "fill_pct": fill_pct,
        "still_250ms_n": n_still,
        "still_250ms_true": n_still_true,
        "still_250ms_pct": still_pct,
        "reasons": dict(reasons),
        "days": day_rows,
        "worst_day": worst,
        "live_order": live_order,
        "g6_flag_written": False,
        "g6_pass": False,
        "note": (
            "residual-sim fill on 2s paper poll. still@250ms not recorded on paper_maker. "
            "Not PnL. Does not write G6 flag. do not live without G5 G6"
        ),
    }


def write_report(stats: dict[str, Any]) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "g6_fill_cal.json").write_text(json.dumps(stats, indent=2) + "\n")
    fill = "n/a" if stats["fill_pct"] is None else f"{stats['fill_pct']:.4f}"
    still = "not recorded (paper_maker interval=2s)"
    if stats["still_250ms_n"]:
        still = f"{stats['still_250ms_true']}/{stats['still_250ms_n']}"
    worst = stats.get("worst_day") or {}
    worst_s = "n/a"
    if worst:
        wp = "n/a" if worst.get("fill_pct") is None else f"{worst['fill_pct']:.4f}"
        worst_s = f"{worst.get('day')} fill_sim%={wp} rest={worst.get('rest')} skip={worst.get('skip')}"
    lines = [
        "# G6_FILL_CAL",
        "",
        f"Generated: {stats['generated']}",
        "paper_maker residual-sim only. Not live fill. Not PnL. G6 flag **not** written.",
        "do not live without G5 G6",
        "",
        f"- rows: {stats['n_rows']} · {stats['first_ts']} → {stats['last_ts']}",
        f"- rests: **{stats['rests']}**",
        f"- skips: **{stats['skips']}** (rich/thin/missing)",
        f"- still@250ms: {still}",
        f"- fill% (residual-sim complete+filled_both / rest): **{fill}** "
        f"(complete={stats['complete']} filled_both={stats['filled_both']})",
        f"- worst day: {worst_s}",
        f"- pair>1 cancel (measure, not trade): {stats['pair_gt_1_cancel']}",
        "",
        "G6 stays FAIL until a human writes `data/ops/G6_fill_calibrated.flag` after reviewing this tape vs queue sim.",
        "Do not treat paper intends as PnL. Low fill% on short L2 = calibrate, don't kill S1.",
        "",
    ]
    (REPORTS / "G6_FILL_CAL.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="G6 paper fill cal. No flag. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run). No G6 flag.", flush=True)
        return 0
    rows = load_jsonl(args.inp)
    stats = analyze(rows)
    write_report(stats)
    print(json.dumps({
        "ok": True,
        "rests": stats["rests"],
        "skips": stats["skips"],
        "fill_pct": stats["fill_pct"],
        "still_250ms_n": stats["still_250ms_n"],
        "worst_day": stats["worst_day"],
        "g6_flag_written": False,
        "g6_pass": False,
        "live_order": stats["live_order"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
