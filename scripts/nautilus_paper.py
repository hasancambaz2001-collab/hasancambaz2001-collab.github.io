#!/usr/bin/env python3
"""Try Nautilus as a paper data bus. No live. No G5/G6 unlock.

python3 scripts/nautilus_paper.py --run --source record
python3 scripts/nautilus_paper.py --run --source tape_bosona
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

from infra.book.source import BookSource
from infra.nautilus.paper_engine import NautilusPaperEngine, probe_nautilus
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Nautilus paper bus. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--source", default="record")
    parser.add_argument("--max-ticks", type=int, default=2000)
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run). No live.", flush=True)
        return 0
    probe = probe_nautilus()
    if not probe.get("installed"):
        print(json.dumps({"ok": False, "reason": "nautilus_trader not installed", **probe}))
        return 1
    src = BookSource(args.source)
    ticks = src.ticks()
    payload = NautilusPaperEngine().run(ticks, max_ticks=int(args.max_ticks))
    payload["source"] = args.source
    payload["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload["g5_flag_exists"] = (ROOT / G5_FLAG).is_file()
    payload["g6_flag_exists"] = (ROOT / G6_FLAG).is_file()
    payload["live_ready_exists"] = (ROOT / LIVE_READY).is_file()
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / f"nautilus_paper_{args.source}.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# NAUTILUS_PAPER",
        "",
        f"Generated: {payload['generated']}",
        f"nautilus {probe.get('version')} · source={args.source} · n_ticks={payload['n_ticks']} · n_quotes={payload['n_quotes']}",
        "live_orders=false · size_ok=false · g5_g6_unlocked=false",
        "Polymarket execution client not imported. Historical L2 still PMData/recorder.",
        "do not live without G5 G6",
        "",
        f"rest={payload['n_rest']} reasons={payload['reasons']}",
        "",
    ]
    (REPORTS / "NAUTILUS_PAPER.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "version": probe.get("version"),
        "n_ticks": payload["n_ticks"],
        "n_quotes": payload["n_quotes"],
        "n_rest": payload["n_rest"],
        "live_orders": False,
        "size_ok": False,
        "g5_g6_unlocked": False,
        "live_ready_exists": payload["live_ready_exists"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
