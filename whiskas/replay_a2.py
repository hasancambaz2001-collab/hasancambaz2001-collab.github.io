"""BTC-only A vs A+A2 compare on the Whiskas tape. Does not change A replay."""

from __future__ import annotations

from typing import Any

import pandas as pd

from whiskas.constants import (
    CLIP,
    DAY_DD_PRODUCT,
    FILL_PROB_STRESS,
    PAIR_MAX,
    PAIR_MAX_CAP,
    REPLAY_SEED,
    START_EQUITY,
    WINDOW_SECONDS,
)
from whiskas.fees import looks_like_taker
from whiskas.policy import BookInventory, decide_a2
from whiskas.replay import daily_paths, run_replay, simulate_fill30, _worst_day_pct


def _taker_buys(fills: pd.DataFrame) -> pd.DataFrame:
    tagged = fills.copy()
    side = tagged["side"].astype(str).str.upper()
    tagged["taker_buy"] = [
        bool(looks_like_taker(float(u), float(s), float(p))) and str(sd).upper() == "BUY"
        for u, s, p, sd in zip(tagged["usdc"], tagged["size"], tagged["price"], side)
    ]
    return tagged[tagged["taker_buy"]].copy()


def simulate_a2_window(
    rows: pd.DataFrame,
    *,
    clip: float = CLIP,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
) -> dict[str, Any]:
    inv = BookInventory()
    ask_up = ask_down = None
    sz_up = sz_down = 0.0
    naked_from: int | None = None
    max_naked = 0.0
    n_a = n_first = n_complete = 0
    t0 = int(rows.iloc[0]["t0"]) if len(rows) else 0
    slug = str(rows.iloc[0]["slug"]) if len(rows) else ""
    winner = rows.iloc[0]["winner"] if len(rows) and "winner" in rows.columns else None
    window_end = t0 + WINDOW_SECONDS
    ordered = rows.sort_values("timestamp")
    for r in ordered.itertuples(index=False):
        ts = int(getattr(r, "timestamp") or 0)
        leg = str(getattr(r, "leg"))
        price = float(getattr(r, "price"))
        size = float(getattr(r, "size"))
        if leg == "Up":
            ask_up, sz_up = price, size
        elif leg == "Down":
            ask_down, sz_down = price, size
        else:
            continue
        d = decide_a2(
            ask_up,
            ask_down,
            sz_up,
            sz_down,
            inv,
            pair_max=pair_max,
            pair_max_cap=pair_max_cap,
            clip=clip,
        )
        if d.intend:
            inv.apply_orders(d.orders)
            if d.reason == "complete_set_fok":
                n_a += 1
            elif d.reason == "a2_first_leg":
                n_first += 1
            elif d.reason == "a2_complete":
                n_complete += 1
        if inv.is_flat():
            if naked_from is not None:
                max_naked = max(max_naked, float(ts - naked_from))
                naked_from = None
        elif naked_from is None:
            naked_from = ts
    if not inv.is_flat() and naked_from is not None:
        max_naked = max(max_naked, float(window_end - naked_from))
    pnl = inv.pnl_at_resolve(str(winner) if winner is not None else None)
    if pnl is None:
        pnl = 0.0
    return {
        "slug": slug,
        "t0": t0,
        "pnl_fill1": float(pnl),
        "residual": inv.residual_qty(),
        "residual_leg": inv.residual_leg(),
        "n_a": n_a,
        "n_first": n_first,
        "n_complete": n_complete,
        "max_naked_sec": max_naked,
        "traded": inv.traded(),
        "winner": winner,
        "q_up": inv.q_up,
        "q_down": inv.q_down,
        "kind": "a2_seq",
    }


def run_a2_compare(
    fills: pd.DataFrame,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    fill_prob: float = FILL_PROB_STRESS,
    start_equity: float = START_EQUITY,
    day_dd: float = DAY_DD_PRODUCT,
    seed: int = REPLAY_SEED,
) -> dict[str, Any]:
    a_result, a_elig, _asks = run_replay(
        fills,
        pair_max=pair_max,
        pair_max_cap=pair_max_cap,
        clip=clip,
        fill_prob=fill_prob,
        start_equity=start_equity,
        day_dd=day_dd,
        seed=seed,
    )
    a_slugs = set(a_elig["slug"].astype(str)) if not a_elig.empty else set()
    taker = _taker_buys(fills)
    extras: list[dict[str, Any]] = []
    max_naked = 0.0
    if not taker.empty:
        for slug, group in taker.groupby("slug", sort=False):
            if str(slug) in a_slugs:
                continue
            sim = simulate_a2_window(group, clip=clip, pair_max=pair_max, pair_max_cap=pair_max_cap)
            if sim["traded"]:
                extras.append(sim)
                max_naked = max(max_naked, float(sim["max_naked_sec"]))
    extra_df = pd.DataFrame(extras)
    if extra_df.empty:
        extra_df = pd.DataFrame(columns=["slug", "t0", "pnl_fill1", "max_naked_sec", "residual"])
    extra_df = extra_df.copy()
    if not extra_df.empty:
        extra_df["pnl_fill30_ev"] = extra_df["pnl_fill1"] * float(fill_prob)
        extra_df = simulate_fill30(extra_df, fill_prob=fill_prob, seed=seed + 1)
    else:
        extra_df["pnl_fill30_ev"] = pd.Series(dtype=float)
        extra_df["pnl_fill30_mc"] = pd.Series(dtype=float)
        extra_df["filled"] = pd.Series(dtype=bool)

    a_part = a_elig.copy()
    if not a_part.empty:
        a_part["kind"] = "A"
        a_part["max_naked_sec"] = 0.0
    combined = pd.concat([a_part, extra_df], ignore_index=True, sort=False) if not extra_df.empty else a_part
    if combined.empty:
        combined = pd.DataFrame(columns=["t0", "pnl_fill1", "pnl_fill30_ev", "pnl_fill30_mc"])
    if "pnl_fill30_ev" not in combined.columns and not combined.empty:
        combined["pnl_fill30_ev"] = combined["pnl_fill1"] * float(fill_prob)
    if "pnl_fill30_mc" not in combined.columns and not combined.empty:
        combined = simulate_fill30(combined, fill_prob=fill_prob, seed=seed)

    days1 = daily_paths(combined, "pnl_fill1", start_equity=start_equity, day_dd=day_dd)
    days30e = daily_paths(combined, "pnl_fill30_ev", start_equity=start_equity, day_dd=day_dd)
    days30m = daily_paths(combined, "pnl_fill30_mc", start_equity=start_equity, day_dd=day_dd)
    halt = any(d.halt for d in days1 + days30e + days30m)

    a_pnl1 = float(a_result.pnl_fill1)
    a_pnl30 = float(a_result.pnl_fill30_ev)
    extra_pnl1 = float(extra_df["pnl_fill1"].sum()) if not extra_df.empty else 0.0
    extra_pnl30 = float(extra_df["pnl_fill30_ev"].sum()) if not extra_df.empty else 0.0
    plus_pnl1 = a_pnl1 + extra_pnl1
    plus_pnl30 = a_pnl30 + extra_pnl30
    plus_pnl30_mc = float(combined["pnl_fill30_mc"].sum()) if not combined.empty else 0.0

    pass_ge = plus_pnl30 + 1e-9 >= a_pnl30
    pass_day = (not halt) and (len(combined) > 0)
    passed = pass_ge and pass_day
    fails = []
    if not pass_ge:
        fails.append(f"a2_pnl30={plus_pnl30:.4f} < a_pnl30={a_pnl30:.4f}")
    if not pass_day:
        fails.append("day_dd_halt or empty")

    def _days(rows: list) -> list[dict[str, Any]]:
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
        "a": {
            "n_windows": a_result.n_eligible,
            "pnl_fill1": a_pnl1,
            "pnl_fill30_ev": a_pnl30,
            "pnl_fill30_mc": a_result.pnl_fill30_mc,
            "worst_day_pct_fill1": a_result.worst_day_pct_fill1,
            "worst_day_pct_fill30_ev": a_result.worst_day_pct_fill30_ev,
            "max_naked_sec": 0.0,
        },
        "a2_extra": {
            "n_windows": int(len(extra_df)),
            "pnl_fill1": extra_pnl1,
            "pnl_fill30_ev": extra_pnl30,
            "n_first": int(extra_df["n_first"].sum()) if not extra_df.empty and "n_first" in extra_df else 0,
            "n_complete": int(extra_df["n_complete"].sum()) if not extra_df.empty and "n_complete" in extra_df else 0,
            "n_residual": int((extra_df["residual"] > 1e-12).sum()) if not extra_df.empty else 0,
            "max_naked_sec": max_naked,
        },
        "a_plus_a2": {
            "n_windows": int(len(combined)),
            "pnl_fill1": plus_pnl1,
            "pnl_fill30_ev": plus_pnl30,
            "pnl_fill30_mc": plus_pnl30_mc,
            "worst_day_pct_fill1": _worst_day_pct(days1),
            "worst_day_pct_fill30_ev": _worst_day_pct(days30e),
            "worst_day_pct_fill30_mc": _worst_day_pct(days30m),
            "max_naked_sec": max_naked,
            "days_fill1": _days(days1),
            "days_fill30_ev": _days(days30e),
            "days_fill30_mc": _days(days30m),
        },
        "pass_a2_ge_a": pass_ge,
        "pass_day": pass_day,
        "passed": passed,
        "fail_reasons": fails,
        "clip": clip,
        "pair_max": pair_max,
        "fill_prob": fill_prob,
        "day_dd": day_dd,
        "diamond_rebate": False,
        "start_equity": start_equity,
    }
