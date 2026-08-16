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

from datetime import datetime, timezone

from whiskas.config import load_config, product_from_config
from whiskas.paper import load_jsonl, run_paper, summarize_paper

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


def write_paper_report(stats: dict, path: Path) -> None:
    zero = stats["n_le_096"] == 0
    gate = "PASS (paper)" if zero else "LIVE PRINT (still no orders)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# PHASE3 paper overnight

Replay was not touched. Clip stays 21. No live orders. PR not merged.

| | n |
|---|---:|
| polls | {stats["n_poll"]} |
| `ask_sum ≤ 0.96` | {stats["n_le_096"]} |
| of those, both depths `≥ 21` | {stats["n_le_096_depth_ge_clip"]} |
| poll errors | {stats["n_err"]} |

Window: {stats["first_ts"]} → {stats["last_ts"]}

**{gate}.** {stats["note"]}
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-log intended FOKs. Never sends orders.")
    parser.add_argument("--once", action="store_true", help="single snapshot")
    parser.add_argument("--seconds", type=float, default=0.0, help="loop duration (ignored with --once)")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", action="store_true", help="count intended.jsonl; do not poll")
    parser.add_argument("--since", type=str, default=None, help="ISO UTC; only count rows at/after this ts")
    parser.add_argument("--since-file", type=Path, default=None, help="file whose first line is --since")
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    cfg = product_from_config(load_config(ROOT / "configs" / "whiskas.yaml"))
    since = _parse_since(args.since)
    if args.since_file and args.since_file.is_file():
        since = _parse_since(args.since_file.read_text(encoding="utf-8").splitlines()[0])
    if args.summary:
        stats = summarize_paper(
            load_jsonl(args.out),
            since=since,
            pair_max=cfg["pair_max"],
            clip=cfg["clip"],
        )
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        write_paper_report(stats, args.report)
        print(json.dumps(stats, indent=2))
        return 0
    once = args.once or args.seconds <= 0
    quiet = (not once) and args.seconds >= 60
    rows = run_paper(
        out_path=args.out,
        once=once,
        seconds=args.seconds,
        interval=args.interval,
        pair_max=cfg["pair_max"],
        clip=cfg["clip"],
        collect=not quiet,
        heartbeat_every=60 if quiet else 0,
    )
    if not quiet:
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
    print(f"appended to {args.out} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
