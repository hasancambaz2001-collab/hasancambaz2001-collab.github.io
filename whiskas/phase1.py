from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from whiskas.constants import (
    CRYPTO_TAKER_FEE_RATE,
    LATE_T_SECONDS,
    WHISKAS_PROFILE,
    WHISKAS_USERNAME,
    WHISKAS_WALLET,
)


def _quantile(series: pd.Series, q: float) -> float | None:
    s = series.dropna()
    if s.empty:
        return None
    return float(s.quantile(q))


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _histogram(series: pd.Series, edges: list[float]) -> list[tuple[str, int]]:
    s = series.dropna()
    rows: list[tuple[str, int]] = []
    for i, lo in enumerate(edges[:-1]):
        hi = edges[i + 1]
        if i == len(edges) - 2:
            n = int(((s >= lo) & (s <= hi)).sum())
            label = f"[{lo:.2f}, {hi:.2f}]"
        else:
            n = int(((s >= lo) & (s < hi)).sum())
            label = f"[{lo:.2f}, {hi:.2f})"
        rows.append((label, n))
    return rows


def compute_phase1(windows: pd.DataFrame, fills: pd.DataFrame) -> dict[str, Any]:
    w = windows.copy()
    resolved = w[w["winner"].notna()].copy()
    paired = w[w["pair_cost"].notna()].copy()
    residual = resolved[(resolved["residual"] > 0) & (resolved["residual_leg"].notna())].copy()
    late_fills = fills[fills["late"] == True] if not fills.empty else fills  # noqa: E712

    pair_pnl = float(paired["pair_pnl"].sum()) if not paired.empty else 0.0
    res_pnl = float(residual["residual_pnl"].sum()) if not residual.empty else 0.0
    tot_pnl = float(resolved["total_pnl"].sum()) if not resolved.empty else 0.0
    fees = float(w["fee_up"].sum() + w["fee_down"].sum()) if not w.empty else 0.0
    rebates = float(w["rebate_usdc"].sum()) if not w.empty else 0.0

    residual_wr = None
    if not residual.empty and residual["residual_won"].notna().any():
        rw = residual["residual_won"].dropna()
        residual_wr = float(rw.mean()) if len(rw) else None

    window_wr = None
    if not resolved.empty:
        won = resolved["total_pnl"] > 0
        window_wr = float(won.mean())

    sell_n = int(w["n_sell"].sum()) if not w.empty else 0
    buy_n = int(w["n_buy"].sum()) if not w.empty else 0
    sell_rate = sell_n / (sell_n + buy_n) if (sell_n + buy_n) else 0.0

    clip = fills[fills["side"] == "BUY"]["size"] if not fills.empty else pd.Series(dtype=float)
    late_prices = late_fills["price"] if not late_fills.empty else pd.Series(dtype=float)

    daily = pd.DataFrame()
    if not resolved.empty and resolved["t0"].notna().any():
        tmp = resolved.copy()
        tmp["day"] = pd.to_datetime(tmp["t0"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
        daily = tmp.groupby("day", as_index=False).agg(
            windows=("t0", "count"),
            pnl=("total_pnl", "sum"),
            pair_pnl=("pair_pnl", "sum"),
        )

    t1_median = _quantile(paired["pair_cost"], 0.50) if not paired.empty else None
    t1 = bool(t1_median is not None and t1_median < 1.0 and pair_pnl > 0)
    t2 = bool(residual_wr is not None and residual_wr >= 0.55)
    late_resolved = late_fills[late_fills["winner"].notna()] if not late_fills.empty else late_fills
    late_markout = None
    if not late_resolved.empty:
        # BUY markout: winner-leg pays 1-price, loser-leg pays -price
        def _mo(row: pd.Series) -> float:
            if row["leg"] == row["winner"]:
                return (1.0 - float(row["price"])) * float(row["size"]) - float(row["fee"])
            return -float(row["price"]) * float(row["size"]) - float(row["fee"])

        late_markout = float(late_resolved.apply(_mo, axis=1).sum())
    t3 = bool(late_markout is not None and late_markout > 0 and len(late_resolved) >= 20)
    t4 = bool(sell_rate < 0.01)
    clip_med = _quantile(clip, 0.50)
    t5 = bool(clip_med is not None and 5.0 <= clip_med <= 50.0 and not w.empty and int((w["n_fills"] >= 4).sum()) > 0)

    hist_edges = [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 0.99, 1.00, 1.02, 1.10, 1.50]
    return {
        "wallet": WHISKAS_WALLET,
        "username": WHISKAS_USERNAME,
        "profile": WHISKAS_PROFILE,
        "n_windows": int(len(w)),
        "n_resolved": int(len(resolved)),
        "n_unresolved": int(len(w) - len(resolved)),
        "n_paired": int(len(paired)),
        "n_residual": int(len(residual)),
        "n_fills": int(len(fills)),
        "n_buy": buy_n,
        "n_sell": sell_n,
        "sell_rate": sell_rate,
        "pair_cost_p10": _quantile(paired["pair_cost"], 0.10) if not paired.empty else None,
        "pair_cost_p25": _quantile(paired["pair_cost"], 0.25) if not paired.empty else None,
        "pair_cost_p50": t1_median,
        "pair_cost_p75": _quantile(paired["pair_cost"], 0.75) if not paired.empty else None,
        "pair_cost_p90": _quantile(paired["pair_cost"], 0.90) if not paired.empty else None,
        "pair_cost_p95": _quantile(paired["pair_cost"], 0.95) if not paired.empty else None,
        "pair_cost_hist": _histogram(paired["pair_cost"], hist_edges) if not paired.empty else [],
        "pair_pnl": pair_pnl,
        "residual_pnl": res_pnl,
        "total_pnl": tot_pnl,
        "fees": fees,
        "rebates": rebates,
        "residual_wr": residual_wr,
        "window_wr": window_wr,
        "clip_p25": _quantile(clip, 0.25),
        "clip_p50": clip_med,
        "clip_p75": _quantile(clip, 0.75),
        "clip_p90": _quantile(clip, 0.90),
        "max_residual_p75": _quantile(w["residual_ratio"], 0.75) if not w.empty else None,
        "max_residual_p90": _quantile(w["residual_ratio"], 0.90) if not w.empty else None,
        "burst_p75": _quantile(w["n_fills"], 0.75) if not w.empty else None,
        "burst_p90": _quantile(w["n_fills"], 0.90) if not w.empty else None,
        "late_n": int(len(late_fills)),
        "late_price_p50": _quantile(late_prices, 0.50),
        "late_price_p90": _quantile(late_prices, 0.90),
        "late_markout": late_markout,
        "daily": daily.to_dict(orient="records"),
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t4": t4,
        "t5": t5,
    }


def render_phase1_md(stats: dict[str, Any], extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    hist_lines = ["| bin | n |", "|---|---|"]
    for label, n in stats.get("pair_cost_hist") or []:
        hist_lines.append(f"| {label} | {n} |")
    daily_lines = ["| day | windows | total_pnl | pair_pnl |", "|---|---:|---:|---:|"]
    for row in stats.get("daily") or []:
        daily_lines.append(
            f"| {row['day']} | {row['windows']} | {_fmt(row['pnl'], 2)} | {_fmt(row['pair_pnl'], 2)} |"
        )
    tests = [
        ("T1 complete-set", stats["t1"], "median pair_cost < 1.00 AND pair_pnl > 0"),
        ("T2 residual", stats["t2"], "residual WR ≥ 55% on resolved leftover inventory"),
        ("T3 late", stats["t3"], f"t > {LATE_T_SECONDS}s fill markout > 0 (n≥20)"),
        ("T4 buy-only", stats["t4"], "SELL rate < 1% on btc-updown-5m"),
        ("T5 clip/burst", stats["t5"], "median BUY clip in 5–50 and some windows with ≥4 fills"),
    ]
    test_lines = ["| test | result | rule |", "|---|---|---|"]
    for name, ok, rule in tests:
        test_lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {rule} |")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""# PHASE1 — Whiskas BTC 5m reconstruction

Generated: {now}

Do not start the bot loop from this file. Config below is quantile-fitted, not a live go.

## Identity

- Username: `{stats['username']}`
- Profile: {stats['profile']}
- Proxy wallet: `{stats['wallet']}`
- Scope: `btc-updown-5m-*` only

## Dump

- Activity rows: {extra.get('n_activity', 'n/a')}
- Closed-position rows: {extra.get('n_closed', 'n/a')}
- Winner sources: {extra.get('winners', 'n/a')}

## Coverage

- Windows: **{stats['n_windows']}**
- Resolved: **{stats['n_resolved']}**
- Unresolved: {stats['n_unresolved']}
- Windows with both legs (pair_cost defined): **{stats['n_paired']}**
- Residual windows: {stats['n_residual']}
- Fills: {stats['n_fills']} (BUY {stats['n_buy']} / SELL {stats['n_sell']}, sell_rate={_fmt(stats['sell_rate'], 4)})

## Pair-cost distribution

| q | pair_cost |
|---|---:|
| p10 | {_fmt(stats['pair_cost_p10'])} |
| p25 | {_fmt(stats['pair_cost_p25'])} |
| p50 | {_fmt(stats['pair_cost_p50'])} |
| p75 | {_fmt(stats['pair_cost_p75'])} |
| p90 | {_fmt(stats['pair_cost_p90'])} |
| p95 | {_fmt(stats['pair_cost_p95'])} |

{chr(10).join(hist_lines)}

## PnL decomposition (resolved windows)

| component | USDC |
|---|---:|
| pair_pnl (matched × (1 − pair_cost) − allocated fee) | {_fmt(stats['pair_pnl'], 2)} |
| residual_pnl | {_fmt(stats['residual_pnl'], 2)} |
| estimated taker fees | {_fmt(stats['fees'], 2)} |
| rebates observed | {_fmt(stats['rebates'], 2)} |
| total_pnl (payout − cost − fee + rebate) | {_fmt(stats['total_pnl'], 2)} |

- Window win rate (total_pnl > 0): {_fmt(stats['window_wr'], 3)}
- Residual win rate: {_fmt(stats['residual_wr'], 3)}
- Late fills: {stats['late_n']} ; late markout {_fmt(stats['late_markout'], 2)} ; late price p50/p90 {_fmt(stats['late_price_p50'])} / {_fmt(stats['late_price_p90'])}

Fees use the official crypto curve `fee = C × 0.07 × p × (1−p)` ([docs](https://docs.polymarket.com/trading/fees)). Activity does not mark maker vs taker; Phase 1 treats BUY fills as taker (conservative).

## T1–T5

{chr(10).join(test_lines)}

## Daily resolved PnL

{chr(10).join(daily_lines) if stats.get('daily') else '_no resolved daily rows_'}

## Quantiles used for config

| field | source | value |
|---|---|---:|
| pair_max | min(0.97, pair_cost p25) if p25 else 0.97 | see `configs/whiskas.yaml` |
| clip | BUY size p50 | {_fmt(stats['clip_p50'], 2)} |
| max_residual | residual_ratio p75 | {_fmt(stats['max_residual_p75'], 3)} |
| burst_windows | n_fills p90 | {_fmt(stats['burst_p90'], 1)} |
| late_max_price | late fill price p50 | {_fmt(stats['late_price_p50'])} |
| fee.rate | official crypto taker | {CRYPTO_TAKER_FEE_RATE} |

## Stop

Phase 1 only. Policy / replay / paper loop are later steps.
"""


def fitted_config(stats: dict[str, Any]) -> dict[str, Any]:
    p25 = stats.get("pair_cost_p25")
    pair_max = 0.97
    if p25 is not None:
        pair_max = float(min(0.97, max(0.90, p25)))
    clip = stats.get("clip_p50") or 10.0
    clip = float(min(50.0, max(5.0, clip)))
    max_residual = stats.get("max_residual_p75") or 0.20
    late_max = stats.get("late_price_p50") or 0.35
    burst = stats.get("burst_p90") or 8
    return {
        "wallet": WHISKAS_WALLET,
        "username": WHISKAS_USERNAME,
        "profile": WHISKAS_PROFILE,
        "market": "btc-updown-5m",
        "pair_max": round(float(pair_max), 4),
        "min_edge": 0.04,
        "clip": round(float(clip), 2),
        "max_residual": round(float(max_residual), 4),
        "burst_windows": int(round(float(burst))),
        "late_max_price": round(float(late_max), 4),
        "late_t_seconds": LATE_T_SECONDS,
        "fee": {"rate": CRYPTO_TAKER_FEE_RATE, "category": "crypto", "assume_taker": True},
        "slippage_ticks": 1,
        "notes": "Fitted from PHASE1 quantiles. Tune ONLY after Phase 1. Not a live enable.",
    }


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
