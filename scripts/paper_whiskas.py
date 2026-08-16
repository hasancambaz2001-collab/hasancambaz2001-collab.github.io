#!/usr/bin/env python3
"""LEGACY ask-FOK paper. Never primary 5m PnL.

Primary 5m/15m signal = paper_maker (bid rest). This process is legacy_ask_fok.
Measure-only. No orders.
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

from whiskas.config import load_config, product_from_config
from whiskas.paper import PAPER_ASSETS, PAPER_TFS, load_jsonl, run_paper, summarize_paper

DEFAULT_OUT = ROOT / "data" / "paper" / "intended.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "paper" / "overnight_summary.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "PHASE3_PAPER.md"


def _parse_since(text: str | None) -> datetime | None:
    if not text:
        return None
    raw = text.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def write_paper_report(stats: dict, path: Path) -> str:
    lines = [
        "# PHASE3 paper (legacy_ask_fok)",
        "",
        "LEGACY ask-FOK. Never primary 5m PnL. Primary = paper_maker bid rest.",
        "Measure-only. No live. No pair>1. Clip 21. Repeat max 8. 4h = poll only.",
        "Ask buckets 0.90 / 0.96 unchanged. Bid bucket: log bid_sum; maker_intend when bid_sum≤0.98 on 5m/15m only.",
        "",
        "| asset | tf | bucket | polls | A_hits | A2_hits | repeat_hits | depth_ok | still250 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats.get("table") or []:
        lines.append(
            f"| {row['asset']} | {row['tf']} | {row['bucket']} | {row['polls']} | "
            f"{row['A_hits']} | {row['A2_hits']} | {row['repeat_hits']} | "
            f"{row['depth_ok']} | {row['still250']} |"
        )
    lines.extend(
        [
            "",
            f"Window: {stats.get('first_ts')} → {stats.get('last_ts')}",
            "",
            f"{stats.get('note', '')}",
            "",
            f"maker_intend={stats.get('n_maker_intend', 0)} bid_sum≤0.98={stats.get('n_bid_le_098', 0)} (measure only, no live)",
            "",
        ]
    )
    text = "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-log intended FOKs. Never sends orders.")
    parser.add_argument("--once", action="store_true", help="single poll of all assets")
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="loop duration; 0 with no --once means leave up",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between poll cycles")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--assets", type=str, default=",".join(PAPER_ASSETS), help="comma list")
    parser.add_argument("--tfs", type=str, default=",".join(PAPER_TFS), help="comma list: 5m,15m,4h")
    parser.add_argument("--summary", action="store_true", help="count intended.jsonl; do not poll")
    parser.add_argument("--since", type=str, default=None, help="ISO UTC; only count rows at/after this ts")
    parser.add_argument("--since-file", type=Path, default=None, help="file whose first line is --since")
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    cfg = product_from_config(load_config(ROOT / "configs" / "whiskas.yaml"))
    assets = tuple(a.strip().lower() for a in args.assets.split(",") if a.strip())
    tfs = tuple(t.strip().lower() for t in args.tfs.split(",") if t.strip())
    since = _parse_since(args.since)
    if args.since_file and args.since_file.is_file():
        since = _parse_since(args.since_file.read_text(encoding="utf-8").splitlines()[0])
    if args.summary:
        stats = summarize_paper(
            load_jsonl(args.out),
            since=since,
            pair_max=cfg["pair_max"],
            clip=cfg["clip"],
            assets=assets,
            tfs=tfs,
        )
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        report = write_paper_report(stats, args.report)
        print(report)
        print(json.dumps(stats, indent=2))
        return 0
    once = bool(args.once)
    quiet = not once
    rows = run_paper(
        out_path=args.out,
        once=once,
        seconds=args.seconds,
        interval=args.interval,
        pair_max=cfg["pair_max"],
        clip=cfg["clip"],
        collect=not quiet,
        heartbeat_every=12 if quiet else 0,
        assets=assets,
        tfs=tfs,
    )
    if not quiet:
        for rec in rows:
            print(json.dumps({
                "ts": rec.get("ts"),
                "asset": rec.get("asset"),
                "tf": rec.get("tf"),
                "slug": rec.get("slug"),
                "ask_up": rec.get("ask_up"),
                "ask_down": rec.get("ask_down"),
                "ask_sum": rec.get("ask_sum"),
                "bid_up": rec.get("bid_up"),
                "bid_down": rec.get("bid_down"),
                "bid_sum": rec.get("bid_sum"),
                "maker_intend": rec.get("maker_intend"),
                "intend": rec.get("intend"),
                "a_intend": rec.get("a_intend"),
                "a2_intend": rec.get("a2_intend"),
                "repeat_intend": rec.get("repeat_intend"),
                "clips_this_window": rec.get("clips_this_window"),
                "reason": rec.get("reason"),
                "depth_ok": rec.get("depth_ok"),
                "still_there_250ms": rec.get("still_there_250ms"),
                "live_order": rec.get("live_order"),
            }))
    print(f"appended to {args.out} assets={','.join(assets)} tfs={','.join(tfs)} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
