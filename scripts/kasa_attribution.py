#!/usr/bin/env python3
"""FULL KASA attribution on their tape. No live. pair_gt_1_trade=false."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.kasa import dump_if_needed, is_s1, is_s3, load_all_windows, s1_pnl, s3_pnl

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def main() -> int:
    if "--run" not in sys.argv:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run)", flush=True)
        return 0
    dumped = dump_if_needed(ROOT)
    print(json.dumps({"dumped": dumped}), flush=True)
    windows = load_all_windows(ROOT)
    s1 = [w for w in windows if is_s1(w)]
    s3 = [w for w in windows if is_s3(w)]
    s1_usd = sum(s1_pnl(w) for w in s1)
    s3_usd = sum(s3_pnl(w) for w in s3)
    by_wallet: dict[str, dict[str, float | int]] = {}
    for w in windows:
        cell = by_wallet.setdefault(str(w["wallet"]), {"s1_n": 0, "s1_usd": 0.0, "s3_n": 0, "s3_usd": 0.0})
        if is_s1(w):
            cell["s1_n"] = int(cell["s1_n"]) + 1
            cell["s1_usd"] = float(cell["s1_usd"]) + s1_pnl(w)
        if is_s3(w):
            cell["s3_n"] = int(cell["s3_n"]) + 1
            cell["s3_usd"] = float(cell["s3_usd"]) + s3_pnl(w)
    payload = {
        "s1_usd": s1_usd,
        "s3_usd": s3_usd,
        "s1_n": len(s1),
        "s3_n": len(s3),
        "pair_gt_1_trade": False,
        "primary": "paper_maker",
        "ask_fok_primary": False,
        "pnl_from_paper_intends": False,
        "wallets": by_wallet,
        "dumped": dumped,
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "kasa_attribution.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# KASA attribution",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "Their tape. Not paper intends. pair_gt_1_trade=false. paper_maker primary.",
        "Two-leg by market slug (Yes+No same binary). 06dc ladders are not event-wide sets.",
        "",
        f"**S1$** (maker pair<0.90) = **{s1_usd:.2f}** n={len(s1)}",
        f"**S3$** (taker pair≤0.96, not primary) = **{s3_usd:.2f}** n={len(s3)}",
        "",
        "| wallet | S1 n | S1$ | S3 n | S3$ |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, cell in by_wallet.items():
        lines.append(
            f"| {name} | {cell['s1_n']} | {cell['s1_usd']:.2f} | {cell['s3_n']} | {cell['s3_usd']:.2f} |"
        )
    lines.extend(["", "Ask FOK is not the 5m signal. No live.", ""])
    (REPORTS / "KASA.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"S1$": round(s1_usd, 2), "S3$": round(s3_usd, 2), "s1_n": len(s1), "s3_n": len(s3)}))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
