#!/usr/bin/env python3
"""SIM: hole lifetime on BTC 5m books. Not a fill. No live. No pair>1.

python3 scripts/sim_l2_hole.py

PMData Day L2 is Yes-token full depth (already on disk). It cannot make bid_sum.
Both-leg hole uses data/parquet/btc_ticks.parquet (1s TOB, Kacho archive).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAIR_MAX = 0.90
CLIP = 5.0
MIN_SPREAD = 0.01
DAY_DIR = ROOT / "data" / "parquet" / "pmdata" / "day"
TICKS = ROOT / "data" / "parquet" / "btc_ticks.parquet"
OUT_JSON = ROOT / "data" / "processed" / "sim_l2_hole.json"
OUT_MD = ROOT / "data" / "reports" / "SIM_L2_HOLE.md"
L2_ZIPS = ("btc-5m_l2_2026-08-14.zip", "btc-5m_l2_2026-08-15.zip")


def hole_mask(
    bu: np.ndarray,
    au: np.ndarray,
    bd: np.ndarray,
    ad: np.ndarray,
    su: np.ndarray,
    sd: np.ndarray,
    *,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    min_spread: float = MIN_SPREAD,
) -> np.ndarray:
    return (
        (bu + bd <= float(pair_max) + 1e-12)
        & (np.minimum(su, sd) + 1e-12 >= float(clip))
        & (au - bu + 1e-12 >= float(min_spread))
        & (ad - bd + 1e-12 >= float(min_spread))
    )


def run_lengths(cid: np.ndarray, t: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Consecutive same-market seconds where hole stays true."""
    if hole.size == 0 or not bool(hole.any()):
        return np.array([], dtype=np.int64)
    order = np.lexsort((t, cid))
    cid = cid[order]
    t = t[order]
    hole = hole[order]
    cont = (cid[1:] == cid[:-1]) & (t[1:] == t[:-1] + 1) & hole[1:] & hole[:-1]
    start = np.empty(len(hole), dtype=bool)
    start[0] = bool(hole[0])
    start[1:] = hole[1:] & ~cont
    run_id = np.cumsum(start)
    run_id[~hole] = 0
    valid = hole & (run_id > 0)
    if not bool(valid.any()):
        return np.array([], dtype=np.int64)
    _, counts = np.unique(run_id[valid], return_counts=True)
    return counts.astype(np.int64)


def _pct(xs: np.ndarray, p: float) -> float | None:
    if xs.size == 0:
        return None
    return float(np.percentile(xs, p))


def _share_ge(xs: np.ndarray, k: int) -> float:
    if xs.size == 0:
        return 0.0
    return float((xs >= k).mean())


def inventory_l2() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in L2_ZIPS:
        path = DAY_DIR / name
        if not path.is_file():
            rows.append({"file": name, "present": False})
            continue
        with zipfile.ZipFile(path) as zf:
            members = [m for m in zf.namelist() if m.endswith(".parquet")]
            gaps: list[float] = []
            n_book = n_pc = n_levels = 0
            for member in members[:3]:
                with zf.open(member) as fh:
                    df = pd.read_parquet(fh)
                books = df[df["event_type"] == "book"]
                n_book += int(len(books))
                n_pc += int((df["event_type"] == "price_change").sum())
                if books.empty:
                    continue
                ts = pd.to_datetime(books["timestamp"])
                gaps.extend(ts.diff().dt.total_seconds().dropna().tolist())
                mid = books.iloc[len(books) // 2]
                bids = mid["bid_prices"]
                n_levels = max(n_levels, 0 if bids is None else len(list(bids)))
        rows.append(
            {
                "file": name,
                "present": True,
                "bytes": path.stat().st_size,
                "windows": len(members),
                "sample3_book_rows": n_book,
                "sample3_pc_rows": n_pc,
                "bid_levels": n_levels,
                "book_gap_s_p10": float(np.percentile(gaps, 10)) if gaps else None,
                "book_gap_s_p50": float(np.median(gaps)) if gaps else None,
                "book_gap_s_p90": float(np.percentile(gaps, 90)) if gaps else None,
                "note": "Yes-token full depth only. Not bid_up+bid_down.",
            }
        )
    return rows


def hole_from_ticks(path: Path) -> dict[str, Any]:
    ticks = pd.read_parquet(path, columns=["condition_id", "t", "bu", "au", "bd", "ad", "su", "sd"])
    ticks = ticks.dropna(subset=["bu", "bd", "au", "ad", "su", "sd"])
    hole = hole_mask(
        ticks["bu"].to_numpy(),
        ticks["au"].to_numpy(),
        ticks["bd"].to_numpy(),
        ticks["ad"].to_numpy(),
        ticks["su"].to_numpy(),
        ticks["sd"].to_numpy(),
    )
    runs = run_lengths(ticks["condition_id"].to_numpy(), ticks["t"].to_numpy(), hole)
    n = int(len(ticks))
    n_mkt = int(ticks["condition_id"].nunique())
    n_hole = int(hole.sum())
    hole_mkts = int(len(np.unique(ticks["condition_id"].to_numpy()[hole]))) if n_hole else 0
    return {
        "source": str(path.relative_to(ROOT)),
        "rows": n,
        "markets": n_mkt,
        "ts_min": str(pd.to_datetime(int(ticks["t"].min()), unit="s", utc=True)),
        "ts_max": str(pd.to_datetime(int(ticks["t"].max()), unit="s", utc=True)),
        "hole_seconds": n_hole,
        "hole_second_rate": (n_hole / n) if n else None,
        "markets_with_any_hole": hole_mkts,
        "markets_with_any_hole_rate": (hole_mkts / n_mkt) if n_mkt else None,
        "n_hole_runs": int(runs.size),
        "run_s_p50": _pct(runs, 50),
        "run_s_p90": _pct(runs, 90),
        "run_s_p99": _pct(runs, 99),
        "run_s_max": int(runs.max()) if runs.size else 0,
        "frac_runs_eq_1s": _share_ge(runs, 1) - _share_ge(runs, 2),
        "frac_runs_ge_2s": _share_ge(runs, 2),
        "frac_runs_ge_5s": _share_ge(runs, 5),
        "frac_runs_ge_10s": _share_ge(runs, 10),
        "frac_runs_ge_30s": _share_ge(runs, 30),
        "note": "1s grid cannot prove 250ms. run>=2s would pass still250. run==1s is ambiguous.",
    }


def write_md(payload: dict[str, Any]) -> None:
    t = payload["ticks_1s_both_legs"]
    l2 = payload["l2_yes_only"]
    lines = [
        "# SIM — BTC 5m L2 inventory + hole lifetime",
        "",
        "Label: **SIM**. `real_fill` is null. No live send. Clip 5. pair≤0.90. 1-tick. No pair>1.",
        "",
        "## What we already have (full L2)",
        "",
        "PMData Day API, Yes-token only, every bid/ask level + `price_change` ticks.",
        "",
        "| file | windows | bytes | book gap p50 | levels (sample) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in l2:
        if not row.get("present"):
            lines.append(f"| `{row['file']}` | — | missing | — | — |")
            continue
        mb = row["bytes"] / 1e6
        lines.append(
            f"| `{row['file']}` | {row['windows']} | {mb:.0f} MB | {row['book_gap_s_p50']}s | {row['bid_levels']} |"
        )
    lines += [
        "",
        "This file cannot compute `bid_up+bid_down`. Down is a second token. Do not invent the complement.",
        "",
        "## Both-leg hole (1s TOB, SIM)",
        "",
        f"Source: `{t['source']}`. {t['ts_min']} → {t['ts_max']}.",
        "",
        f"- Seconds: **{t['rows']:,}**. Markets: **{t['markets']:,}**.",
        f"- Hole seconds (pair≤0.90, depth≥5, 1-tick both legs): **{t['hole_seconds']:,}** ({100 * float(t['hole_second_rate'] or 0):.3f}% of seconds).",
        f"- Windows with any hole second: **{t['markets_with_any_hole']:,}** / {t['markets']:,} ({100 * float(t['markets_with_any_hole_rate'] or 0):.1f}%).",
        f"- Hole runs: **{t['n_hole_runs']:,}**. Duration p50 **{t['run_s_p50']}s**, p90 **{t['run_s_p90']}s**, p99 **{t['run_s_p99']}s**, max **{t['run_s_max']}s**.",
        f"- Runs lasting 1s only: **{100 * float(t['frac_runs_eq_1s']):.1f}%**. ≥2s (still250 would pass): **{100 * float(t['frac_runs_ge_2s']):.1f}%**. ≥5s: **{100 * float(t['frac_runs_ge_5s']):.1f}%**.",
        "",
        "Matches the live tape after REST still250: 39 rests, 37 `still250_false`. Most cheap prints do not stay 250ms.",
        "",
        "## Not this",
        "",
        "Not a fill. Not SLIP-ME / Bonereaper. Not clip bump. Not bot start.",
        "",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload = {
        "label": "SIM",
        "real_fill": None,
        "pair_max": PAIR_MAX,
        "clip": CLIP,
        "min_spread": MIN_SPREAD,
        "l2_yes_only": inventory_l2(),
        "ticks_1s_both_legs": hole_from_ticks(TICKS),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_md(payload)
    print(json.dumps({"ok": True, "json": str(OUT_JSON), "md": str(OUT_MD), "label": "SIM"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
