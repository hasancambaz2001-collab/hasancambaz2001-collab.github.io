#!/usr/bin/env python3
"""Queue v2 fill band. NOT go/no-go. Does not set size_ok. No live."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.book.source import BookSource
from infra.match.queue_sim_v2 import SCENARIOS, run_queue_v2

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue v2. Fill band only.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--clip", type=float, default=10.0)
    parser.add_argument("--glob", default="data/l2/*.jsonl")
    args = parser.parse_args()
    src = BookSource(args.source, glob_pat=args.glob)
    rows = {}
    if args.source == "record":
        ticks = list(src.ticks())
        for name in SCENARIOS:
            rows[name] = run_queue_v2(ticks=ticks, clip=float(args.clip), scenario=name)
    else:
        windows = src.windows()
        for name in SCENARIOS:
            rows[name] = run_queue_v2(windows=windows, clip=float(args.clip), scenario=name)
    payload = {
        "source": args.source,
        "clip": float(args.clip),
        "size_ok": False,
        "go_nogo": False,
        "note": "S1 go/no-go = replay edge, NOT queue fill%. Low fill% on short L2 = calibrate, don't kill S1.",
        "scenarios": rows,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / f"queue_sim_{args.source}.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        f"# QUEUE_SIM {args.source}",
        "",
        payload["note"],
        "",
        "| scenario | label | fill_ratio | n_rest | hidden | latency |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, cell in rows.items():
        lines.append(
            f"| {name} | {cell['label']} | {cell['fill_ratio']:.4f} | {cell['n_rest']} | "
            f"{cell['hidden_factor']} | {cell['latency_ticks']} |"
        )
    lines.extend(["", "size_ok=false. Optimistic is upper bound only, not for sizing.", ""])
    md = REPORTS / "QUEUE_SIM.md"
    prev = md.read_text(encoding="utf-8") if md.is_file() else "# QUEUE_SIM\n\n"
    block = "\n".join(lines)
    if f"# QUEUE_SIM {args.source}" in prev:
        # replace section
        parts = prev.split(f"# QUEUE_SIM {args.source}")
        rest = parts[1]
        nxt = rest.find("\n# QUEUE_SIM ")
        tail = rest[nxt:] if nxt >= 0 else ""
        prev = parts[0] + block + tail
    else:
        prev = prev.rstrip() + "\n\n" + block + "\n"
    md.write_text(prev, encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
