#!/usr/bin/env python3
"""Reconstruct 5m windows and write PHASE1.md. No bot loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.phase1 import compute_phase1, fitted_config, render_phase1_md, write_yaml
from whiskas.resolve import resolve_winners
from whiskas.windows import build_windows, fills_to_records, windows_to_records


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing dump {path} — run scripts/dump_whiskas.py first")
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Whiskas windows + PHASE1")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "reports" / "PHASE1.md")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "whiskas.yaml")
    parser.add_argument("--no-gamma", action="store_true", help="do not call Gamma for missing winners")
    parser.add_argument("--gamma-limit", type=int, default=None)
    args = parser.parse_args()

    activity = _read_jsonl(args.raw_dir / "whiskas_activity.jsonl")
    closed = _read_jsonl(args.raw_dir / "whiskas_closed_positions.jsonl")
    print(f"loaded activity={len(activity)} closed={len(closed)}", flush=True)

    windows = build_windows(activity)
    print(f"btc-updown-5m windows: {len(windows)}", flush=True)
    winner_stats = resolve_winners(
        windows,
        closed,
        fetch_missing_gamma=not args.no_gamma,
        gamma_limit=args.gamma_limit,
    )
    print(f"winners: {winner_stats}", flush=True)

    win_recs = windows_to_records(windows.values())
    fill_recs = fills_to_records(windows.values())
    win_df = pd.DataFrame(win_recs)
    fill_df = pd.DataFrame(fill_recs)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    win_path = args.out_dir / "whiskas_windows.parquet"
    fill_path = args.out_dir / "whiskas_fills.parquet"
    win_df.to_parquet(win_path, index=False)
    fill_df.to_parquet(fill_path, index=False)
    print(f"wrote {win_path} ({len(win_df)}) and {fill_path} ({len(fill_df)})", flush=True)

    stats = compute_phase1(win_df, fill_df)
    extra = {
        "n_activity": len(activity),
        "n_closed": len(closed),
        "winners": winner_stats,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_phase1_md(stats, extra), encoding="utf-8")
    write_yaml(args.config, fitted_config(stats))
    (args.out_dir / "phase1_stats.json").write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    print(f"wrote {args.report}", flush=True)
    print(f"wrote {args.config}", flush=True)
    print("=== PHASE1 NUMBERS ===", flush=True)
    print(
        json.dumps(
            {
                "n_windows": stats["n_windows"],
                "n_resolved": stats["n_resolved"],
                "n_paired": stats["n_paired"],
                "pair_cost_p25": stats["pair_cost_p25"],
                "pair_cost_p50": stats["pair_cost_p50"],
                "pair_cost_p75": stats["pair_cost_p75"],
                "pair_pnl": stats["pair_pnl"],
                "residual_pnl": stats["residual_pnl"],
                "total_pnl": stats["total_pnl"],
                "residual_wr": stats["residual_wr"],
                "T1": stats["t1"],
                "T2": stats["t2"],
                "T3": stats["t3"],
                "T4": stats["t4"],
                "T5": stats["t5"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
