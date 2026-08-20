#!/usr/bin/env python3
"""PnL tie-out: official leaderboard vs reconstructed windows. No bot."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.fees import taker_fee_usdc
from whiskas.slug import is_btc_5m, parse_btc_5m_slug
from whiskas.windows import normalize_leg

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
WALLET = "0x3048d65321be3497164cdfc2996f94f98a2e7537"
OFFICIAL = 211013.5806407136
OFFICIAL_VOL = 12349105.308808003
PROFILE = "https://polymarket.com/@x-moneyforwhiskas"
MAKER_EPS = 0.02


def load_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _f(row: dict, key: str) -> float:
    return float(row.get(key) or 0.0)


def main() -> int:
    print("loading activity...", flush=True)
    activity = list(load_jsonl(RAW / "whiskas_activity.jsonl"))
    print(f"activity={len(activity)}", flush=True)
    print("loading closed...", flush=True)
    closed = list(load_jsonl(RAW / "whiskas_closed_positions.jsonl"))
    print(f"closed={len(closed)}", flush=True)
    win_df = pd.read_parquet(PROC / "whiskas_windows.parquet")
    fills = pd.read_parquet(PROC / "whiskas_fills.parquet")
    fills = fills.copy()
    fills["implied"] = fills["size"] * fills["price"]
    fills["embed"] = fills["usdc"] - fills["implied"]
    fills["formula"] = [taker_fee_usdc(s, p) for s, p in zip(fills["size"], fills["price"])]

    types = Counter(r.get("type") for r in activity)
    print("types", dict(types), flush=True)

    cash: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    sides: Counter[str] = Counter()
    non_btc: Counter[str] = Counter()
    non_btc_rows: list[dict] = []
    size_all = 0.0
    implied_all = 0.0
    first_ts = 10**18
    last_ts = 0
    for r in activity:
        ts = int(r.get("timestamp") or 0)
        if ts:
            first_ts = min(first_ts, ts)
            last_ts = max(last_ts, ts)
        scope = "btc5" if is_btc_5m(r.get("eventSlug"), r.get("slug")) else "other"
        t = r.get("type") or "?"
        side = (r.get("side") or "").upper()
        usdc = _f(r, "usdcSize")
        size = _f(r, "size")
        price = _f(r, "price")
        cash[scope][t] += usdc
        cash["all"][t] += usdc
        if scope == "other":
            non_btc[t] += 1
            slug = (r.get("eventSlug") or r.get("slug") or "")[:60]
            non_btc[f"slug:{slug}"] += 1
            non_btc_rows.append(
                {
                    "type": t,
                    "slug": slug,
                    "side": side,
                    "size": size,
                    "price": price,
                    "usdc": usdc,
                    "outcome": r.get("outcome"),
                }
            )
        if t == "TRADE":
            sides[f"{scope}:{side}"] += 1
            cash[scope][f"TRADE_{side}"] += usdc
            cash["all"][f"TRADE_{side}"] += usdc
            size_all += size
            implied_all += size * price

    def flow(scope: str) -> float:
        c = cash[scope]
        return (
            c.get("REDEEM", 0.0)
            + c.get("TRADE_SELL", 0.0)
            + c.get("MERGE", 0.0)
            + c.get("MAKER_REBATE", 0.0)
            + c.get("TAKER_REBATE", 0.0)
            + c.get("REWARD", 0.0)
            - c.get("TRADE_BUY", 0.0)
            - c.get("SPLIT", 0.0)
        )

    print("\n=== ACTIVITY CASH ===", flush=True)
    for scope in ("all", "btc5", "other"):
        buy = cash[scope].get("TRADE_BUY", 0.0)
        redeem = cash[scope].get("REDEEM", 0.0)
        print(scope, dict(cash[scope]), flush=True)
        print(
            f"  {scope} redeem-buy={redeem-buy:.2f} flow={flow(scope):.2f}",
            flush=True,
        )
    print("sides", dict(sides), flush=True)
    print("non-btc top", non_btc.most_common(20), flush=True)
    print(f"sum TRADE size={size_all:.4f} official_vol={OFFICIAL_VOL:.4f} vol-size={OFFICIAL_VOL-size_all:.4f}", flush=True)

    maker_mask = fills["embed"].abs() <= MAKER_EPS
    taker_mask = fills["embed"] > MAKER_EPS
    neg_mask = fills["embed"] < -MAKER_EPS
    taker_embed = float(fills.loc[taker_mask, "embed"].sum())
    taker_formula = float(fills.loc[taker_mask, "formula"].sum())
    all_formula = float(fills["formula"].sum())
    print("\n=== FEE / MAKER ===", flush=True)
    print(
        f"maker |embed|<={MAKER_EPS} n={int(maker_mask.sum())} "
        f"embed={float(fills.loc[maker_mask, 'embed'].sum()):.4f}",
        flush=True,
    )
    print(
        f"taker embed>eps n={int(taker_mask.sum())} embed={taker_embed:.4f} formula={taker_formula:.4f}",
        flush=True,
    )
    print(f"neg n={int(neg_mask.sum())} embed={float(fills.loc[neg_mask, 'embed'].sum()):.4f}", flush=True)
    print(f"formula on ALL buys={all_formula:.4f} fake_on_makers={all_formula-taker_formula:.4f}", flush=True)

    rp_all = 0.0
    rp_btc = 0.0
    ident_all = 0.0
    ident_mismatch = 0
    by_slug: dict[str, dict[str, float]] = defaultdict(
        lambda: {"up": 0.0, "down": 0.0, "up_cost": 0.0, "down_cost": 0.0, "rp": 0.0}
    )
    closed_btc_n = 0
    closed_other = []
    for r in closed:
        rp = _f(r, "realizedPnl")
        tb = _f(r, "totalBought")
        avg = _f(r, "avgPrice")
        cur = _f(r, "curPrice")
        ident = (cur - avg) * tb
        ident_all += ident
        if abs(ident - rp) > 0.02:
            ident_mismatch += 1
        rp_all += rp
        slug = r.get("eventSlug") or r.get("slug") or ""
        if is_btc_5m(r.get("eventSlug"), r.get("slug")):
            rp_btc += rp
            closed_btc_n += 1
            rec = by_slug[slug]
            rec["rp"] += rp
            leg = normalize_leg(r.get("outcome"), r.get("outcomeIndex"))
            if leg == "Up":
                rec["up"] += tb
                rec["up_cost"] += tb * avg
            elif leg == "Down":
                rec["down"] += tb
                rec["down_cost"] += tb * avg
        else:
            closed_other.append(
                {
                    "slug": slug,
                    "outcome": r.get("outcome"),
                    "avgPrice": avg,
                    "totalBought": tb,
                    "realizedPnl": rp,
                    "curPrice": cur,
                }
            )
    print("\n=== CLOSED POSITIONS ===", flush=True)
    print(f"closed n={len(closed)} btc5 n={closed_btc_n} other n={len(closed_other)}", flush=True)
    print(f"realizedPnl all={rp_all:.4f} btc5={rp_btc:.4f} other={rp_all-rp_btc:.4f}", flush=True)
    print(f"(cur-avg)*tb={ident_all:.4f} mismatch>0.02 n={ident_mismatch}", flush=True)

    resolved = win_df[win_df["winner"].notna()].copy()
    payout = resolved.apply(lambda r: r["q_up"] if r["winner"] == "Up" else r["q_down"], axis=1)
    cost_usdc = resolved["cost_up"] + resolved["cost_down"]
    redeem = resolved["redeem_up"] + resolved["redeem_down"]
    fee0_usdc = float((payout - cost_usdc).sum())
    implied_by_slug = fills.groupby("slug", sort=False)["implied"].sum()
    implied_aligned = resolved["slug"].map(implied_by_slug).fillna(0.0)
    fee0_px = float((payout - implied_aligned).sum())
    embed_windows = float(fills["embed"].sum())
    print("\n=== WINDOW RECON ===", flush=True)
    print(f"windows={len(win_df)} resolved={len(resolved)}", flush=True)
    print(f"fee0_usdc (payout-usdc)={fee0_usdc:.4f}", flush=True)
    print(f"fee0_px (payout-size*price)={fee0_px:.4f}", flush=True)
    print(f"embed usdc-implied={embed_windows:.4f}", flush=True)
    print(f"redeem={float(redeem.sum()):.4f} payout={float(payout.sum()):.4f} d={float((redeem-payout).sum()):.4f}", flush=True)
    print(f"official-fee0_px={OFFICIAL-fee0_px:.4f}", flush=True)

    win_by_slug = {rec["slug"]: rec for rec in resolved.to_dict(orient="records")}
    both = set(win_by_slug) & set(by_slug)
    only_win = set(win_by_slug) - set(by_slug)
    only_cl = set(by_slug) - set(win_by_slug)
    gap_rp = 0.0
    abs_gap = 0.0
    n_big = 0
    for slug in both:
        w = win_by_slug[slug]
        w_fee0 = (w["q_up"] if w["winner"] == "Up" else w["q_down"]) - (w["cost_up"] + w["cost_down"])
        d = by_slug[slug]["rp"] - w_fee0
        gap_rp += d
        abs_gap += abs(d)
        if abs(d) > 20:
            n_big += 1
    only_win_payout = 0.0
    only_win_cost = 0.0
    for slug in only_win:
        w = win_by_slug[slug]
        only_win_payout += w["q_up"] if w["winner"] == "Up" else w["q_down"]
        only_win_cost += w["cost_up"] + w["cost_down"]
    print("\n=== CLOSED vs WINDOW ===", flush=True)
    print(f"both={len(both)} only_window={len(only_win)} only_closed={len(only_cl)}", flush=True)
    print(f"sum(closed_rp-fee0_usdc) both={gap_rp:.2f} abs={abs_gap:.2f} |d|>20 n={n_big}", flush=True)
    print(f"only_window payout={only_win_payout:.2f} cost={only_win_cost:.2f} fee0={only_win_payout-only_win_cost:.2f}", flush=True)

    rng = random.Random(210)
    slugs = sorted(s for s in both if parse_btc_5m_slug(s))
    sample = rng.sample(slugs, 20) if len(slugs) >= 20 else slugs
    print("\n=== 20 WINDOW SAMPLE (seed=210) vs closed-positions / profile Closed tab ===", flush=True)
    samples = []
    for slug in sorted(sample):
        w = win_by_slug[slug]
        c = by_slug[slug]
        w_fee0 = (w["q_up"] if w["winner"] == "Up" else w["q_down"]) - (w["cost_up"] + w["cost_down"])
        sample_row: dict[str, Any] = {
            "slug": slug,
            "profile_event": f"https://polymarket.com/event/{slug}",
            "winner": w["winner"],
            "q_up": w["q_up"],
            "q_down": w["q_down"],
            "avg_up": w["avg_up"],
            "avg_down": w["avg_down"],
            "pair_cost": w["pair_cost"],
            "redeem_up": w["redeem_up"],
            "redeem_down": w["redeem_down"],
            "window_fee0_usdc": w_fee0,
            "ui_closed_up": c["up"],
            "ui_closed_down": c["down"],
            "ui_avg_up": (c["up_cost"] / c["up"]) if c["up"] else None,
            "ui_avg_down": (c["down_cost"] / c["down"]) if c["down"] else None,
            "ui_realizedPnl": c["rp"],
            "diff_ui_minus_window": c["rp"] - w_fee0,
        }
        samples.append(sample_row)
        print(
            f"{slug} win={w['winner']} q={w['q_up']:.2f}/{w['q_down']:.2f} "
            f"avg={w['avg_up']}/{w['avg_down']} pair={w['pair_cost']} "
            f"redeem={w['redeem_up']:.2f}/{w['redeem_down']:.2f} "
            f"win_usdc={w_fee0:.2f} UI_rp={c['rp']:.2f} d={c['rp']-w_fee0:.2f} "
            f"UI_q={c['up']:.2f}/{c['down']:.2f}",
            flush=True,
        )

    up = fills[fills["leg"] == "Up"].groupby("slug").agg(imp_up=("implied", "sum"), q_up_f=("size", "sum"))
    dn = fills[fills["leg"] == "Down"].groupby("slug").agg(imp_dn=("implied", "sum"), q_down_f=("size", "sum"))
    m = resolved.set_index("slug").join(up).join(dn)
    m["payout"] = [row.q_up if row.winner == "Up" else row.q_down for row in m.itertuples()]
    m["fee0_usdc"] = m["payout"] - (m["cost_up"] + m["cost_down"])
    m["fee0_px"] = m["payout"] - (m["imp_up"].fillna(0.0) + m["imp_dn"].fillna(0.0))
    m["pair_px"] = (m["imp_up"] / m["q_up_f"]) + (m["imp_dn"] / m["q_down_f"])
    paired = m[m["pair_cost"].notna() & m["pair_px"].notna()].copy()

    def table_for(col: str) -> list[dict]:
        rows = []
        for thr in (0.94, 0.95, 0.96, 0.97, 0.98):
            sub = paired[paired[col] < thr]
            rows.append(
                {
                    "pair_max": thr,
                    "filter": col,
                    "n": int(len(sub)),
                    "pct_paired": float(len(sub) / len(paired)) if len(paired) else 0.0,
                    "fee0_usdc": float(sub["fee0_usdc"].sum()),
                    "fee0_px": float(sub["fee0_px"].sum()),
                    "per_window_usdc": float(sub["fee0_usdc"].mean()) if len(sub) else 0.0,
                    "pair_pnl_broken_taker": float(sub["pair_pnl"].sum()),
                }
            )
        return rows

    table_usdc = table_for("pair_cost")
    table_px = table_for("pair_px")
    print("\n=== PAIR_MAX usdc pair_cost (fee already in avg) ===", flush=True)
    for row in table_usdc:
        print(row, flush=True)
    print("\n=== PAIR_MAX price pair_cost (size*price avgs, closer to ask_sum) ===", flush=True)
    for row in table_px:
        print(row, flush=True)

    out = {
        "status": "GREEN" if abs(fee0_px - OFFICIAL) < 15000 else "OPEN",
        "gate": 15000.0,
        "official_pnl": OFFICIAL,
        "official_vol": OFFICIAL_VOL,
        "official_source": "data-api /v1/leaderboard timePeriod=ALL + lb-api/profit window=all",
        "profile": PROFILE,
        "wallet": WALLET,
        "n_activity": len(activity),
        "n_closed": len(closed),
        "n_windows": int(len(win_df)),
        "types": dict(types),
        "sides": dict(sides),
        "cash": {k: dict(v) for k, v in cash.items()},
        "activity_redeem_minus_buy_all": cash["all"].get("REDEEM", 0.0) - cash["all"].get("TRADE_BUY", 0.0),
        "activity_flow_all": flow("all"),
        "activity_flow_btc5": flow("btc5"),
        "closed_realized_all": rp_all,
        "closed_realized_btc5": rp_btc,
        "closed_realized_other": rp_all - rp_btc,
        "closed_identity_sum": ident_all,
        "closed_identity_mismatch_n": ident_mismatch,
        "closed_other": closed_other,
        "window_fee0_usdc": fee0_usdc,
        "window_fee0_px": fee0_px,
        "embedded_taker_fees": embed_windows,
        "formula_all_buy_as_taker": all_formula,
        "formula_taker_only": taker_formula,
        "fake_fee_on_makers": all_formula - taker_formula,
        "official_minus_fee0_px": OFFICIAL - fee0_px,
        "official_minus_fee0_usdc": OFFICIAL - fee0_usdc,
        "trade_size_sum": size_all,
        "official_vol_minus_size": OFFICIAL_VOL - size_all,
        "dump_first_ts": first_ts if first_ts < 10**18 else None,
        "dump_last_ts": last_ts,
        "maker_n": int(maker_mask.sum()),
        "taker_n": int(taker_mask.sum()),
        "maker_pct": float(maker_mask.mean()),
        "taker_embed": taker_embed,
        "taker_formula": taker_formula,
        "fee_model": "C * 0.07 * p * (1-p) on taker fills only; not flat 1.5%; BUY is not always taker",
        "non_btc_top": non_btc.most_common(30),
        "non_btc_rows": non_btc_rows,
        "sample20": samples,
        "pair_max_table_usdc_filter": table_usdc,
        "pair_max_table_price_filter": table_px,
        "pair_px_quantiles": {
            "p10": float(paired["pair_px"].quantile(0.10)),
            "p25": float(paired["pair_px"].quantile(0.25)),
            "p50": float(paired["pair_px"].median()),
            "p75": float(paired["pair_px"].quantile(0.75)),
            "p90": float(paired["pair_px"].quantile(0.90)),
        },
        "pair_usdc_quantiles": {
            "p10": float(paired["pair_cost"].quantile(0.10)),
            "p25": float(paired["pair_cost"].quantile(0.25)),
            "p50": float(paired["pair_cost"].median()),
            "p75": float(paired["pair_cost"].quantile(0.75)),
            "p90": float(paired["pair_cost"].quantile(0.90)),
        },
        "slug_overlap": {
            "both": len(both),
            "only_window": len(only_win),
            "only_closed": len(only_cl),
            "gap_rp_minus_fee0_usdc": gap_rp,
            "abs_gap": abs_gap,
            "only_window_payout": only_win_payout,
            "only_window_cost": only_win_cost,
            "only_window_fee0_usdc": only_win_payout - only_win_cost,
        },
        "notes": [
            "PHASE1 'fee0' used usdcSize as cost. usdcSize already includes taker fees.",
            "Official ALL pnl matches payout - size*price (gross, fees not subtracted).",
            "closed-positions.realizedPnl is after-fee (avgPrice ≈ usdc/size, 4 dp) and omits 320 unredeemed loser windows.",
            "pair_max=0.9513 is p25 of fee-inclusive pair_cost. Do not write it into a bot.",
        ],
    }
    dest = PROC / "tieout_stats.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {dest} status={out['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
