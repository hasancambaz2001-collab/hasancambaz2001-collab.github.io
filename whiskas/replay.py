"""Replay taker complete-set on windows where their taker ask_sum ≤ pair_max.

Ask proxy = size-weighted VWAP of THEIR taker BUY prices (CLOB p, not usdc).
Conservative: that is what they paid lifting the ask. Our fee is 0.07*p*(1-p)
on clip=21. We are not Diamond. Both-or-nothing FOK (no residual).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd

from whiskas.constants import (
    CLIP,
    DAY_DD_PRODUCT,
    FILL_PROB_STRESS,
    MAKER_EPS,
    PAIR_MAX,
    PAIR_MAX_CAP,
    REPLAY_SEED,
    START_EQUITY,
)
from whiskas.fees import looks_like_taker, taker_fee_usdc
from whiskas.killswitch import day_pnl_halt
from whiskas.policy import assert_pair_max_legal, complete_set_pnl, decide
from whiskas.slug import parse_btc_5m_slug


def tag_taker_buy(fills: pd.DataFrame, *, eps: float = MAKER_EPS) -> pd.DataFrame:
    out = fills.copy()
    side = out["side"].astype(str).str.upper()
    out["is_taker"] = [
        bool(looks_like_taker(float(u), float(s), float(p), eps=eps))
        for u, s, p in zip(out["usdc"], out["size"], out["price"])
    ]
    out["taker_buy"] = out["is_taker"] & (side == "BUY")
    return out


def taker_ask_vwap(fills: pd.DataFrame) -> pd.DataFrame:
    """Per-window, per-leg size*price VWAP from taker BUY fills. Both legs required later."""
    tagged = tag_taker_buy(fills)
    taker = tagged[tagged["taker_buy"]].copy()
    if taker.empty:
        return pd.DataFrame(columns=["slug", "t0", "ask_up", "ask_down", "ask_sum", "q_up", "q_down"])
    taker["notional"] = taker["size"] * taker["price"]
    grouped = taker.groupby(["slug", "leg"], sort=False).agg(
        q=("size", "sum"),
        notional=("notional", "sum"),
        n=("size", "size"),
    )
    rows: list[dict[str, Any]] = []
    slugs = grouped.index.get_level_values(0).unique()
    for slug in slugs:
        t0 = parse_btc_5m_slug(str(slug))
        rec: dict[str, Any] = {"slug": str(slug), "t0": t0, "ask_up": None, "ask_down": None, "q_up": 0.0, "q_down": 0.0}
        for leg in ("Up", "Down"):
            try:
                g = grouped.loc[(slug, leg)]
                q = float(g["q"])
                px = float(g["notional"]) / q if q > 0 else None
            except KeyError:
                q, px = 0.0, None
            if leg == "Up":
                rec["ask_up"] = px
                rec["q_up"] = q
            else:
                rec["ask_down"] = px
                rec["q_down"] = q
        if rec["ask_up"] is not None and rec["ask_down"] is not None:
            rec["ask_sum"] = float(rec["ask_up"]) + float(rec["ask_down"])
        else:
            rec["ask_sum"] = None
        rows.append(rec)
    return pd.DataFrame(rows)


def eligible_windows(
    asks: pd.DataFrame,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
) -> pd.DataFrame:
    assert_pair_max_legal(pair_max, pair_max_cap)
    both = asks[asks["ask_sum"].notna()].copy()
    both["decision"] = [
        decide(u, d, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip).intend
        for u, d in zip(both["ask_up"], both["ask_down"])
    ]
    elig = both[both["decision"]].copy()
    if elig.empty:
        elig["pnl_fill1"] = pd.Series(dtype=float)
        elig["fee_up"] = pd.Series(dtype=float)
        elig["fee_down"] = pd.Series(dtype=float)
        elig["residual"] = pd.Series(dtype=float)
        return elig
    elig["fee_up"] = [taker_fee_usdc(clip, float(p)) for p in elig["ask_up"]]
    elig["fee_down"] = [taker_fee_usdc(clip, float(p)) for p in elig["ask_down"]]
    elig["pnl_fill1"] = [
        complete_set_pnl(float(u), float(d), clip, diamond_rebate=False)
        for u, d in zip(elig["ask_up"], elig["ask_down"])
    ]
    elig["residual"] = 0.0
    elig["clip"] = float(clip)
    elig.sort_values("t0", inplace=True)
    elig.reset_index(drop=True, inplace=True)
    return elig


@dataclass
class DayPath:
    day: str
    n: int
    pnl: float
    start_equity: float
    end_equity: float
    day_pct: float
    halt: bool


@dataclass
class ReplayResult:
    n_windows: int
    n_both_legs: int
    n_eligible: int
    n_excluded_cap: int
    median_pair: float | None
    pair_p10: float | None
    pair_p90: float | None
    pnl_fill1: float
    pnl_fill30_ev: float
    pnl_fill30_mc: float
    n_fill30_mc: int
    fees_fill1: float
    worst_day_pct_fill1: float | None
    worst_day_pct_fill30_ev: float | None
    worst_day_pct_fill30_mc: float | None
    days_fill1: list[DayPath] = field(default_factory=list)
    days_fill30_ev: list[DayPath] = field(default_factory=list)
    days_fill30_mc: list[DayPath] = field(default_factory=list)
    pass_n: bool = False
    pass_pnl30: bool = False
    pass_median: bool = False
    pass_day: bool = False
    passed: bool = False
    fail_reasons: list[str] = field(default_factory=list)


def _quantile(series: pd.Series, q: float) -> float | None:
    s = series.dropna()
    if s.empty:
        return None
    return float(s.quantile(q))


def daily_paths(
    elig: pd.DataFrame,
    pnl_col: str,
    *,
    start_equity: float = START_EQUITY,
    day_dd: float = DAY_DD_PRODUCT,
) -> list[DayPath]:
    if elig.empty:
        return []
    tmp = elig.copy()
    tmp["day"] = pd.to_datetime(tmp["t0"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    grouped = tmp.groupby("day", sort=True).agg(n=(pnl_col, "size"), pnl=(pnl_col, "sum"))
    equity = float(start_equity)
    out: list[DayPath] = []
    for day, row in grouped.iterrows():
        start = equity
        pnl = float(row["pnl"])
        halt = day_pnl_halt(pnl, start, day_dd)
        equity = start + pnl
        pct = (pnl / start) if start > 0 else (0.0 if pnl == 0 else float("-inf"))
        out.append(
            DayPath(
                day=str(day),
                n=int(row["n"]),
                pnl=pnl,
                start_equity=start,
                end_equity=equity,
                day_pct=pct,
                halt=halt,
            )
        )
    return out


def _worst_day_pct(days: list[DayPath]) -> float | None:
    if not days:
        return None
    return float(min(d.day_pct for d in days))


def simulate_fill30(
    elig: pd.DataFrame,
    *,
    fill_prob: float = FILL_PROB_STRESS,
    seed: int = REPLAY_SEED,
) -> pd.DataFrame:
    """Both-or-nothing FOK: one Bernoulli per window. Independent per-leg would create residual."""
    out = elig.copy()
    if out.empty:
        out["filled"] = pd.Series(dtype=bool)
        out["pnl_fill30_mc"] = pd.Series(dtype=float)
        return out
    rng = np.random.default_rng(seed)
    filled = rng.random(len(out)) < float(fill_prob)
    out["filled"] = filled
    out["pnl_fill30_mc"] = out["pnl_fill1"] * filled.astype(float)
    return out


def run_replay(
    fills: pd.DataFrame,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    fill_prob: float = FILL_PROB_STRESS,
    start_equity: float = START_EQUITY,
    day_dd: float = DAY_DD_PRODUCT,
    seed: int = REPLAY_SEED,
) -> tuple[ReplayResult, pd.DataFrame, pd.DataFrame]:
    assert_pair_max_legal(pair_max, pair_max_cap)
    if fill_prob <= 0 or fill_prob > 1:
        raise ValueError("fill_prob must be in (0, 1]")
    asks = taker_ask_vwap(fills)
    both = asks[asks["ask_sum"].notna()]
    cap_band = both[(both["ask_sum"] > pair_max + 1e-12) & (both["ask_sum"] <= pair_max_cap + 1e-12)]
    elig = eligible_windows(asks, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    elig = elig.copy()
    if not elig.empty:
        elig["pnl_fill30_ev"] = elig["pnl_fill1"] * float(fill_prob)
    else:
        elig["pnl_fill30_ev"] = pd.Series(dtype=float)
    elig = simulate_fill30(elig, fill_prob=fill_prob, seed=seed)

    days1 = daily_paths(elig, "pnl_fill1", start_equity=start_equity, day_dd=day_dd)
    days30e = daily_paths(elig, "pnl_fill30_ev", start_equity=start_equity, day_dd=day_dd)
    days30m = daily_paths(elig, "pnl_fill30_mc", start_equity=start_equity, day_dd=day_dd)

    n_elig = int(len(elig))
    median_pair = _quantile(elig["ask_sum"], 0.50) if n_elig else None
    pnl1 = float(elig["pnl_fill1"].sum()) if n_elig else 0.0
    pnl30e = float(elig["pnl_fill30_ev"].sum()) if n_elig else 0.0
    pnl30m = float(elig["pnl_fill30_mc"].sum()) if n_elig else 0.0
    fees1 = float((elig["fee_up"] + elig["fee_down"]).sum()) if n_elig else 0.0
    worst1 = _worst_day_pct(days1)
    worst30e = _worst_day_pct(days30e)
    worst30m = _worst_day_pct(days30m)

    halt_any = any(d.halt for d in days1 + days30e + days30m)
    pass_n = n_elig > 400
    pass_pnl30 = pnl30e > 0
    pass_median = median_pair is not None and median_pair <= pair_max + 1e-12
    pass_day = (not halt_any) and n_elig > 0
    fails: list[str] = []
    if not pass_n:
        fails.append(f"n_eligible={n_elig} <= 400")
    if not pass_pnl30:
        fails.append(f"pnl_fill30_ev={pnl30e:.4f} <= 0")
    if not pass_median:
        fails.append(f"median_pair={median_pair} > {pair_max}")
    if not pass_day:
        fails.append("day_dd_halt or empty")

    result = ReplayResult(
        n_windows=int(fills["slug"].nunique()) if not fills.empty and "slug" in fills.columns else 0,
        n_both_legs=int(len(both)),
        n_eligible=n_elig,
        n_excluded_cap=int(len(cap_band)),
        median_pair=median_pair,
        pair_p10=_quantile(elig["ask_sum"], 0.10) if n_elig else None,
        pair_p90=_quantile(elig["ask_sum"], 0.90) if n_elig else None,
        pnl_fill1=pnl1,
        pnl_fill30_ev=pnl30e,
        pnl_fill30_mc=pnl30m,
        n_fill30_mc=int(elig["filled"].sum()) if n_elig else 0,
        fees_fill1=fees1,
        worst_day_pct_fill1=worst1,
        worst_day_pct_fill30_ev=worst30e,
        worst_day_pct_fill30_mc=worst30m,
        days_fill1=days1,
        days_fill30_ev=days30e,
        days_fill30_mc=days30m,
        pass_n=pass_n,
        pass_pnl30=pass_pnl30,
        pass_median=pass_median,
        pass_day=pass_day,
        passed=pass_n and pass_pnl30 and pass_median and pass_day,
        fail_reasons=fails,
    )
    return result, elig, asks


def result_to_dict(result: ReplayResult) -> dict[str, Any]:
    def _days(rows: list[DayPath]) -> list[dict[str, Any]]:
        return [
            {
                "day": d.day,
                "n": d.n,
                "pnl": d.pnl,
                "start_equity": d.start_equity,
                "end_equity": d.end_equity,
                "day_pct": d.day_pct,
                "halt": d.halt,
            }
            for d in rows
        ]

    return {
        "product": "taker_complete_set",
        "pair_max": PAIR_MAX,
        "pair_max_cap": PAIR_MAX_CAP,
        "clip": CLIP,
        "fee": "0.07*p*(1-p)",
        "diamond_rebate": False,
        "fill_prob_stress": FILL_PROB_STRESS,
        "start_equity": START_EQUITY,
        "day_dd": DAY_DD_PRODUCT,
        "seed": REPLAY_SEED,
        "n_windows": result.n_windows,
        "n_both_legs": result.n_both_legs,
        "n_eligible": result.n_eligible,
        "n_excluded_cap": result.n_excluded_cap,
        "median_pair": result.median_pair,
        "pair_p10": result.pair_p10,
        "pair_p90": result.pair_p90,
        "pnl_fill1": result.pnl_fill1,
        "pnl_fill30_ev": result.pnl_fill30_ev,
        "pnl_fill30_mc": result.pnl_fill30_mc,
        "n_fill30_mc": result.n_fill30_mc,
        "fees_fill1": result.fees_fill1,
        "worst_day_pct_fill1": result.worst_day_pct_fill1,
        "worst_day_pct_fill30_ev": result.worst_day_pct_fill30_ev,
        "worst_day_pct_fill30_mc": result.worst_day_pct_fill30_mc,
        "pass_n": result.pass_n,
        "pass_pnl30": result.pass_pnl30,
        "pass_median": result.pass_median,
        "pass_day": result.pass_day,
        "passed": result.passed,
        "fail_reasons": result.fail_reasons,
        "days_fill1": _days(result.days_fill1),
        "days_fill30_ev": _days(result.days_fill30_ev),
        "days_fill30_mc": _days(result.days_fill30_mc),
    }


def synthetic_taker_fills(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Test helper: rows with slug, leg, size, price. Embeds official taker fee into usdc."""
    recs = []
    for i, r in enumerate(rows):
        size = float(r["size"])
        price = float(r["price"])
        fee = taker_fee_usdc(size, price)
        slug = str(r["slug"])
        t0 = parse_btc_5m_slug(slug)
        recs.append(
            {
                "t0": t0,
                "slug": slug,
                "timestamp": int(r.get("timestamp") or (t0 or 0) + 10),
                "t_in_window": 10,
                "late": False,
                "leg": r["leg"],
                "side": str(r.get("side") or "BUY"),
                "size": size,
                "price": price,
                "usdc": size * price + fee,
                "fee": fee,
                "tx": r.get("tx") or f"0x{i}",
                "winner": r.get("winner"),
            }
        )
    return pd.DataFrame(recs)
