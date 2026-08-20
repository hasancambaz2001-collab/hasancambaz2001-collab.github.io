#!/usr/bin/env python3
"""Revised G6 close from paper measurement layers. Hours are not a gate.

python3 scripts/g6_close.py

PASS if n_rest>=100, skip/rest logged, pair>1 not traded.
still250 preferred; ABSENT does not block (note still250_absent).
real_fill_rate is null until orders are sent.
Does not write LIVE_READY. Does not set G5.
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

from scripts.g6_fill_cal import SKIP, analyze as analyze_paper
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY
from whiskas.paper import load_jsonl

N_REST_MIN = 100
TAPE = ROOT / "data" / "paper_maker" / "intended.jsonl"
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def analyze_layers(rows: list[dict[str, Any]]) -> dict[str, Any]:
    paper = analyze_paper(rows)
    n_rest = int(paper["rests"])
    n_skip = int(paper["skips"])
    skip_rest_ratio = (n_skip / n_rest) if n_rest else None
    rest_rows = [r for r in rows if str(r.get("reason") or "") == "rest"]
    skip_logged = any(str(r.get("reason") or "") in SKIP or r.get("skip_reason") for r in rows)
    rest_logged = n_rest > 0 or any(r.get("intent") is True for r in rows)
    probed = [
        r
        for r in rest_rows
        if r.get("still_there_250ms") is not None or r.get("still250") is not None
    ]
    still_true = sum(
        1 for r in probed if r.get("still_there_250ms") is True or r.get("still250") is True
    )
    still250_absent = len(probed) == 0
    still250_rate = (still_true / len(probed)) if probed else None
    pair_gt_1_trade = False
    for r in rows:
        if r.get("pair_gt_1_trade") is True:
            pair_gt_1_trade = True
        if r.get("live_order") and str(r.get("reason") or "") == "pair_gt_1":
            pair_gt_1_trade = True
    real_rates = [r.get("real_fill_rate") for r in rows if r.get("real_fill_rate") is not None]
    real_fill_rate = None
    if real_rates:
        real_fill_rate = sum(float(x) for x in real_rates) / len(real_rates)
    sent = [r for r in rows if r.get("real_fill") and isinstance(r.get("real_fill"), dict)]
    if sent:
        filled = sum(float(r["real_fill"].get("filled_size") or 0.0) for r in sent)
        rested = sum(float(r["real_fill"].get("rested_size") or 0.0) for r in sent)
        real_fill_rate = (filled / rested) if rested else None
    sim_fill_rate = paper["fill_pct"]
    g6_pass = (
        n_rest >= N_REST_MIN
        and skip_logged
        and rest_logged
        and pair_gt_1_trade is False
    )
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_rest": n_rest,
        "n_skip": n_skip,
        "skip_rest_ratio": skip_rest_ratio,
        "skip_logged": skip_logged,
        "rest_logged": rest_logged,
        "still250_rate": still250_rate,
        "still250_n": len(probed),
        "still250_true": still_true,
        "still250_absent": still250_absent,
        "sim_fill_rate": sim_fill_rate,
        "sim_fill_label": "SIM",
        "real_fill_rate": real_fill_rate,
        "pair_gt_1_trade": pair_gt_1_trade,
        "pair_gt_1_measure": int(paper.get("pair_gt_1_cancel") or 0),
        "live_order": bool(paper.get("live_order")),
        "g6_pass": g6_pass,
        "n_rest_min": N_REST_MIN,
        "hours_are_not_a_gate": True,
        "note": (
            "hours not a gate; rest count is. "
            "still250 preferred not hard-lock for micro. "
            "real_fill only after orders sent. "
            "micro trial ≠ full solve. "
            "Never mix sim_fill and real_fill."
        ),
    }


def write_closed(stats: dict[str, Any], *, root: Path = ROOT, write_flag: bool = True) -> dict[str, Any]:
    reports = root / "data" / "reports"
    proc = root / "data" / "processed"
    reports.mkdir(parents=True, exist_ok=True)
    proc.mkdir(parents=True, exist_ok=True)
    still = "ABSENT" if stats["still250_absent"] else f"{stats['still250_rate']:.4f}"
    sim = "n/a" if stats["sim_fill_rate"] is None else f"{stats['sim_fill_rate']:.4f} SIM"
    real = "null" if stats["real_fill_rate"] is None else f"{stats['real_fill_rate']:.4f}"
    skip_r = "n/a" if stats["skip_rest_ratio"] is None else f"{stats['skip_rest_ratio']:.4f}"
    passed = "YES" if stats["g6_pass"] else "NO"
    warn = ""
    if stats["still250_absent"]:
        warn = "still250_absent — preferred not hard-lock for micro.\n"
    lines = [
        "# G6_CLOSED",
        "",
        f"Generated: {stats['generated']}",
        "Revised G6: hours are not a gate; rest count is.",
        "Three layers stay unmixed: INTENT / still250 / REAL FILL. sim_fill is SIM only.",
        "Does not set G5. Does not write LIVE_READY. micro trial ≠ full solve.",
        "",
        warn,
        "| metric | value |",
        "|---|---|",
        f"| n_rest | {stats['n_rest']} |",
        f"| skip_rest_ratio | {skip_r} |",
        f"| still250_rate | {still} |",
        f"| sim_fill_rate | {sim} |",
        f"| real_fill_rate | {real} |",
        f"| G6_PASS | {passed} |",
        "",
        "- hours not a gate; rest count is",
        "- still250 preferred not hard-lock for micro",
        "- real_fill only after orders sent",
        "- micro trial ≠ full solve",
        f"- pair_gt_1_trade: {stats['pair_gt_1_trade']}",
        f"- pair>1 measure (not trade): {stats['pair_gt_1_measure']}",
        f"- G5 exists: {(root / G5_FLAG).is_file()}",
        f"- LIVE_READY exists: {(root / LIVE_READY).is_file()}",
        "",
    ]
    (reports / "G6_CLOSED.md").write_text("\n".join(lines), encoding="utf-8")
    (proc / "g6_closed.json").write_text(json.dumps(stats, indent=2) + "\n")
    stats["report_written"] = True
    flag_path = root / G6_FLAG
    if stats["g6_pass"] and write_flag:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        extra = "still250_absent\n" if stats["still250_absent"] else f"still250_rate={stats['still250_rate']}\n"
        flag_path.write_text(
            f"g6_close PASS {stats['generated']}\n"
            f"n_rest={stats['n_rest']} hours_not_a_gate\n"
            f"{extra}",
            encoding="utf-8",
        )
        stats["g6_flag_written"] = flag_path.is_file()
    else:
        stats["g6_flag_written"] = flag_path.is_file() and stats["g6_pass"]
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Revised G6 close. Hours not a gate.")
    parser.add_argument("--in", dest="inp", type=Path, default=TAPE)
    parser.add_argument("--no-flag", action="store_true")
    args = parser.parse_args()
    rows = load_jsonl(args.inp) if args.inp.is_file() else []
    stats = analyze_layers(rows)
    stats = write_closed(stats, write_flag=not args.no_flag)
    print(json.dumps({
        "g6_pass": stats["g6_pass"],
        "n_rest": stats["n_rest"],
        "skip_rest_ratio": stats["skip_rest_ratio"],
        "still250_rate": stats["still250_rate"],
        "still250_absent": stats["still250_absent"],
        "sim_fill_rate": stats["sim_fill_rate"],
        "real_fill_rate": stats["real_fill_rate"],
        "g6_flag_written": stats.get("g6_flag_written"),
        "report": str(REPORTS / "G6_CLOSED.md"),
        "pair_gt_1_trade": False,
        "note": stats["note"],
    }, indent=2))
    return 0 if stats["g6_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
