#!/usr/bin/env python3
"""Run s1 / s06dc / whiskas / whiskas_full_measure. No live. size_ok=false."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.book.source import BookSource
from infra.match.fill_model import apply_fill
from infra.size.ladder import load_ladder
from infra.strategies.s06dc import S06dc
from infra.strategies.s1_maker import S1Maker
from infra.strategies.whiskas_full import WhiskasAskFok, WhiskasFullMeasure

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def _run_windows(source: BookSource, fill: str) -> dict[str, Any]:
    windows = source.windows()
    strats = [S1Maker(), S06dc(), WhiskasAskFok(), WhiskasFullMeasure(allow_pair_gt1=True)]
    table: dict[str, dict[str, Any]] = {}
    for strat in strats:
        n = 0
        intend = 0
        raw = 0.0
        filled = 0.0
        measure = 0.0
        for win in windows:
            d = strat.on_window(win)
            n += 1
            if d.intend:
                intend += 1
            raw += d.edge
            measure += d.measure_edge
            filled += apply_fill(model=fill, intended_edge=d.edge if strat.trade else 0.0, window=win)
        table[strat.name] = {
            "n": n,
            "intend": intend,
            "trade": strat.trade,
            "edge_raw": raw,
            "edge_filled": filled,
            "measure_edge": measure,
        }
    return {"mode": "windows", "n_windows": len(windows), "strategies": table}


def _run_ticks(source: BookSource, fill: str) -> dict[str, Any]:
    strats = [S1Maker(), S06dc(), WhiskasAskFok(), WhiskasFullMeasure(allow_pair_gt1=True)]
    states = {s.name: None for s in strats}
    table = {
        s.name: {"n": 0, "intend": 0, "trade": s.trade, "edge_raw": 0.0, "edge_filled": 0.0, "measure_edge": 0.0}
        for s in strats
    }
    n = 0
    for tick in source.ticks():
        n += 1
        for strat in strats:
            d, states[strat.name] = strat.on_tick(tick, states[strat.name])
            cell = table[strat.name]
            cell["n"] += 1
            if d.intend:
                cell["intend"] += 1
            cell["edge_raw"] += d.edge
            cell["measure_edge"] += d.measure_edge
            cell["edge_filled"] += apply_fill(model=fill, intended_edge=d.edge if strat.trade else 0.0)
    return {"mode": "ticks", "n_ticks": n, "strategies": table}


def run_harness(*, source_name: str, fill: str, glob_pat: str = "data/l2/*.jsonl") -> dict[str, Any]:
    src = BookSource(source_name, glob_pat=glob_pat)
    if source_name == "record" or source_name == "parquet":
        body = _run_ticks(src, fill)
    else:
        body = _run_windows(src, fill)
    ladder = load_ladder()
    payload = {
        "source": source_name,
        "fill": fill,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "live": False,
        "size_ok": False,
        "pair_gt_1_trade": False,
        "primary": "paper_maker",
        "legacy_ask_fok": "whiskas",
        "ladder": ladder,
        "note": "S1 go/no-go = replay edge, NOT queue fill%. Whiskas full measure ≠ license to trade pair>1.",
        **body,
    }
    return payload


def _update_report(payload: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "HARNESS.md"
    prev = path.read_text(encoding="utf-8") if path.is_file() else "# HARNESS\n\nNo live. size_ok=false. pair_gt_1_trade=false.\n\n"
    strats = payload.get("strategies") or {}
    line = (
        f"| {payload['source']} | {payload['fill']} | "
        f"{strats.get('s1', {}).get('edge_raw', 0):.2f} | "
        f"{strats.get('s1', {}).get('edge_filled', 0):.2f} | "
        f"{strats.get('s06dc', {}).get('measure_edge', 0):.2f} | "
        f"{strats.get('whiskas', {}).get('measure_edge', 0):.2f} | "
        f"{strats.get('whiskas_full_measure', {}).get('measure_edge', 0):.2f} | "
        f"{payload.get('generated')} |"
    )
    header = (
        "| source | fill | s1_raw | s1_filled | s06dc_measure | whiskas_measure | whiskas_full_measure | ts |\n"
        "|---|---|---:|---:|---:|---:|---:|---|\n"
    )
    if header.strip() not in prev:
        prev = prev.rstrip() + "\n\n" + header
    key = f"| {payload['source']} | {payload['fill']} |"
    lines = prev.splitlines()
    out = []
    replaced = False
    for ln in lines:
        if ln.startswith(key):
            out.append(line)
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness. No live.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--fill", default="parity_tape")
    parser.add_argument("--glob", default="data/l2/*.jsonl")
    args = parser.parse_args()
    payload = run_harness(source_name=args.source, fill=args.fill, glob_pat=args.glob)
    PROC.mkdir(parents=True, exist_ok=True)
    out = PROC / f"harness_{args.source}_{args.fill}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _update_report(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
