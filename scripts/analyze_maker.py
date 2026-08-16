#!/usr/bin/env python3
"""Maker/taker role-split + rebate. No bot. Does not redo tie-out."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.fees import looks_like_taker, taker_fee_usdc

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
MAKER_EPS = 0.02


def load_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def hist_edges(series: pd.Series, edges: list[float]) -> list[dict]:
    s = series.dropna()
    rows = []
    for i, lo in enumerate(edges[:-1]):
        hi = edges[i + 1]
        last = i == len(edges) - 2
        n = int(((s >= lo) & (s <= hi)).sum()) if last else int(((s >= lo) & (s < hi)).sum())
        label = f"[{lo:.2f}, {hi:.2f}]" if last else f"[{lo:.2f}, {hi:.2f})"
        rows.append({"bin": label, "n": n})
    return rows


def pair_cost(q_up: float, c_up: float, q_down: float, c_down: float) -> float | None:
    if q_up <= 0 or q_down <= 0:
        return None
    return (c_up / q_up) + (c_down / q_down)


def main() -> int:
    fills = pd.read_parquet(PROC / "whiskas_fills.parquet")
    win = pd.read_parquet(PROC / "whiskas_windows.parquet")
    fills = fills.copy()
    fills["implied"] = fills["size"] * fills["price"]
    fills["embed"] = fills["usdc"] - fills["implied"]
    fills["role"] = "taker"
    fills.loc[fills["embed"].abs() <= MAKER_EPS, "role"] = "maker"
    fills.loc[fills["embed"] < -MAKER_EPS, "role"] = "other"
    fills["formula"] = [taker_fee_usdc(s, p) for s, p in zip(fills["size"], fills["price"])]

    role_n = fills["role"].value_counts().to_dict()
    print("role n", role_n, flush=True)
    print("maker pct", float((fills["role"] == "maker").mean()), flush=True)

    # fill-level fee-correct pnl: winner share pays $1, loser $0; cost = usdc
    fills["fill_pnl_usdc"] = 0.0
    won = fills["leg"] == fills["winner"]
    fills.loc[won, "fill_pnl_usdc"] = fills.loc[won, "size"] - fills.loc[won, "usdc"]
    fills.loc[~won, "fill_pnl_usdc"] = -fills.loc[~won, "usdc"]
    fills["fill_pnl_px"] = 0.0
    fills.loc[won, "fill_pnl_px"] = fills.loc[won, "size"] - fills.loc[won, "implied"]
    fills.loc[~won, "fill_pnl_px"] = -fills.loc[~won, "implied"]

    by_role = {}
    for role in ("maker", "taker", "other"):
        sub = fills[fills["role"] == role]
        by_role[role] = {
            "n": int(len(sub)),
            "pct_fills": float(len(sub) / len(fills)) if len(fills) else 0,
            "shares": float(sub["size"].sum()),
            "usdc": float(sub["usdc"].sum()),
            "implied": float(sub["implied"].sum()),
            "embed": float(sub["embed"].sum()),
            "formula": float(sub["formula"].sum()),
            "pnl_usdc": float(sub["fill_pnl_usdc"].sum()),
            "pnl_px": float(sub["fill_pnl_px"].sum()),
            "t_p10": float(sub["t_in_window"].quantile(0.10)) if len(sub) else None,
            "t_p25": float(sub["t_in_window"].quantile(0.25)) if len(sub) else None,
            "t_p50": float(sub["t_in_window"].quantile(0.50)) if len(sub) else None,
            "t_p75": float(sub["t_in_window"].quantile(0.75)) if len(sub) else None,
            "t_p90": float(sub["t_in_window"].quantile(0.90)) if len(sub) else None,
            "late_n": int((sub["t_in_window"] > 240).sum()),
            "late_pct": float((sub["t_in_window"] > 240).mean()) if len(sub) else 0,
        }
        print(role, by_role[role], flush=True)

    t_bins = list(range(0, 301, 30))
    t_hist = {}
    for role in ("maker", "taker"):
        sub = fills[fills["role"] == role]["t_in_window"]
        rows = []
        for i, lo in enumerate(t_bins[:-1]):
            hi = t_bins[i + 1]
            n = int(((sub >= lo) & (sub < hi)).sum())
            rows.append({"t": f"{lo}-{hi}", "n": n, "pct": float(n / len(sub)) if len(sub) else 0})
        t_hist[role] = rows

    # per-window role pair_costs (price book = size*price; usdc book = cash)
    recs = []
    grouped = fills.groupby(["slug", "role", "leg"], sort=False).agg(
        q=("size", "sum"), implied=("implied", "sum"), usdc=("usdc", "sum")
    )
    win_idx = win.set_index("slug")
    slugs = win["slug"].tolist()
    for slug in slugs:
        w = win_idx.loc[slug]
        row: dict = {
            "slug": slug,
            "t0": int(w["t0"]),
            "winner": w["winner"],
            "pair_cost_usdc": w["pair_cost"],
            "pair_pnl_broken": w["pair_pnl"],
            "q_up": float(w["q_up"]),
            "q_down": float(w["q_down"]),
        }
        for role in ("maker", "taker"):
            qu = qd = iu = idn = uu = ud = 0.0
            for leg, qk, ik, uk in (
                ("Up", "q_up", "imp_up", "usdc_up"),
                ("Down", "q_down", "imp_dn", "usdc_dn"),
            ):
                try:
                    g = grouped.loc[(slug, role, leg)]
                    q = float(g["q"])
                    imp = float(g["implied"])
                    u = float(g["usdc"])
                except KeyError:
                    q = imp = u = 0.0
                if leg == "Up":
                    qu, iu, uu = q, imp, u
                else:
                    qd, idn, ud = q, imp, u
            row[f"{role}_q_up"] = qu
            row[f"{role}_q_down"] = qd
            row[f"{role}_pair_px"] = pair_cost(qu, iu, qd, idn)
            row[f"{role}_pair_usdc"] = pair_cost(qu, uu, qd, ud)
            row[f"{role}_shares"] = qu + qd
            row[f"{role}_usdc"] = uu + ud
        recs.append(row)
    role_win = pd.DataFrame(recs)
    role_win["taker_share"] = role_win["taker_shares"] / (role_win["taker_shares"] + role_win["maker_shares"]).replace(0, pd.NA)
    role_win["maker_share"] = 1.0 - role_win["taker_share"]

    cheap = role_win[role_win["pair_cost_usdc"].notna() & (role_win["pair_cost_usdc"] < 0.97)]
    mid = role_win[role_win["pair_cost_usdc"].notna() & (role_win["pair_cost_usdc"] >= 0.97) & (role_win["pair_cost_usdc"] < 1.00)]
    exp = role_win[role_win["pair_cost_usdc"].notna() & (role_win["pair_cost_usdc"] > 1.00)]
    hyp = {
        "cheap_n": int(len(cheap)),
        "cheap_taker_share_mean": float(cheap["taker_share"].mean()) if len(cheap) else None,
        "cheap_taker_share_median": float(cheap["taker_share"].median()) if len(cheap) else None,
        "cheap_taker_notional_frac": float(cheap["taker_usdc"].sum() / (cheap["taker_usdc"].sum() + cheap["maker_usdc"].sum())) if len(cheap) else None,
        "exp_n": int(len(exp)),
        "exp_taker_share_mean": float(exp["taker_share"].mean()) if len(exp) else None,
        "exp_taker_share_median": float(exp["taker_share"].median()) if len(exp) else None,
        "exp_maker_share_mean": float(exp["maker_share"].mean()) if len(exp) else None,
        "exp_maker_notional_frac": float(exp["maker_usdc"].sum() / (exp["taker_usdc"].sum() + exp["maker_usdc"].sum())) if len(exp) else None,
        "mid_n": int(len(mid)),
        "mid_taker_share_mean": float(mid["taker_share"].mean()) if len(mid) else None,
    }
    # accept if cheap taker_share > 0.60 and exp maker_share > 0.60
    hyp["accept_cheap_mostly_taker"] = bool(hyp["cheap_taker_share_mean"] and hyp["cheap_taker_share_mean"] >= 0.60)
    hyp["accept_exp_mostly_maker"] = bool(hyp["exp_maker_share_mean"] and hyp["exp_maker_share_mean"] >= 0.60)
    print("HYPOTHESIS", hyp, flush=True)

    pair_hists = {
        "taker_px": hist_edges(role_win["taker_pair_px"], [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 1.00, 1.02, 1.10, 1.50]),
        "maker_px": hist_edges(role_win["maker_pair_px"], [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 1.00, 1.02, 1.10, 1.50]),
        "taker_usdc": hist_edges(role_win["taker_pair_usdc"], [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 1.00, 1.02, 1.10, 1.50]),
        "maker_usdc": hist_edges(role_win["maker_pair_usdc"], [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 1.00, 1.02, 1.10, 1.50]),
        "all_usdc": hist_edges(role_win["pair_cost_usdc"], [0.80, 0.90, 0.94, 0.96, 0.97, 0.98, 1.00, 1.02, 1.10, 1.50]),
    }
    pair_q = {}
    for col in ("taker_pair_px", "maker_pair_px", "taker_pair_usdc", "maker_pair_usdc", "pair_cost_usdc"):
        s = role_win[col].dropna()
        pair_q[col] = {
            "n": int(len(s)),
            "p10": float(s.quantile(0.10)) if len(s) else None,
            "p25": float(s.quantile(0.25)) if len(s) else None,
            "p50": float(s.quantile(0.50)) if len(s) else None,
            "p75": float(s.quantile(0.75)) if len(s) else None,
            "p90": float(s.quantile(0.90)) if len(s) else None,
        }
        print(col, pair_q[col], flush=True)

    # rebates from activity
    reb: dict[str, dict] = defaultdict(lambda: {"n": 0, "usdc": 0.0, "rows": []})
    for r in load_jsonl(RAW / "whiskas_activity.jsonl"):
        t = r.get("type")
        if t not in {"MAKER_REBATE", "TAKER_REBATE", "REWARD"}:
            continue
        usdc = float(r.get("usdcSize") or r.get("size") or 0.0)
        ts = int(r.get("timestamp") or 0)
        reb[t]["n"] += 1
        reb[t]["usdc"] += usdc
        reb[t]["rows"].append(
            {
                "ts": ts,
                "iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                "usdc": usdc,
                "slug": r.get("eventSlug") or r.get("slug") or "",
                "title": r.get("title") or "",
            }
        )
    for t, rec in reb.items():
        rec["rows"].sort(key=lambda x: x["ts"])
        print(t, rec["n"], rec["usdc"], "first", rec["rows"][0]["iso"] if rec["rows"] else None, "last", rec["rows"][-1]["iso"] if rec["rows"] else None, flush=True)

    maker_n = by_role["maker"]["n"]
    taker_n = by_role["taker"]["n"]
    maker_reb = reb["MAKER_REBATE"]["usdc"]
    taker_reb = reb["TAKER_REBATE"]["usdc"]
    reward = reb["REWARD"]["usdc"]
    # theoretical: crypto maker rebate = 20% of fee-curve on maker fills (if 100% of pool)
    maker_fee_eq = float(fills.loc[fills["role"] == "maker", "formula"].sum())
    theo_maker_if_full_pool = 0.20 * maker_fee_eq
    # diamond taker rebate 44% of actual taker fees (embed)
    taker_fees = float(fills.loc[fills["role"] == "taker", "embed"].sum())
    theo_taker_diamond = 0.44 * taker_fees

    cents_maker = (100.0 * maker_reb / maker_n) if maker_n else None
    cents_taker = (100.0 * taker_reb / taker_n) if taker_n else None
    maker_reb_per_share = maker_reb / by_role["maker"]["shares"] if by_role["maker"]["shares"] else None
    maker_reb_bps_notional = 1e4 * maker_reb / by_role["maker"]["implied"] if by_role["maker"]["implied"] else None

    # pair>1.00 net-flat test: allocate maker rebate by maker implied notional
    exp_maker_imp = float(
        fills.merge(exp[["slug"]], on="slug", how="inner")
        .query("role=='maker'")["implied"]
        .sum()
    ) if len(exp) else 0.0
    all_maker_imp = by_role["maker"]["implied"]
    exp_reb_alloc = maker_reb * (exp_maker_imp / all_maker_imp) if all_maker_imp else 0.0
    # pair loss on expensive windows using usdc fee0 (window total, not just pair)
    exp_slugs = set(exp["slug"])
    exp_win = win[win["slug"].isin(exp_slugs)].copy()
    payout = exp_win.apply(lambda r: r["q_up"] if r["winner"] == "Up" else r["q_down"], axis=1)
    exp_fee0_usdc = float((payout - exp_win["cost_up"] - exp_win["cost_down"]).sum())
    # matched pair component: matched * (1 - pair_cost) on usdc book (no extra fee)
    exp_pair_edge = float((exp_win["matched"] * (1.0 - exp_win["pair_cost"])).sum()) if len(exp_win) else 0.0
    flat = {
        "exp_n": int(len(exp)),
        "exp_fee0_usdc": exp_fee0_usdc,
        "exp_pair_edge_usdc": exp_pair_edge,
        "exp_maker_implied": exp_maker_imp,
        "maker_rebate_alloc": exp_reb_alloc,
        "pair_edge_plus_rebate": exp_pair_edge + exp_reb_alloc,
        "fee0_plus_rebate": exp_fee0_usdc + exp_reb_alloc,
        "net_flat_pair": abs(exp_pair_edge + exp_reb_alloc) < 5000 and (exp_pair_edge + exp_reb_alloc) > -abs(exp_pair_edge) * 0.15,
    }
    print("PAIR>1 NET-FLAT", flat, flush=True)
    print(f"cents/maker fill={cents_maker} cents/taker fill={cents_taker}", flush=True)
    print(f"theo maker 20% pool={theo_maker_if_full_pool:.2f} actual={maker_reb:.2f}", flush=True)
    print(f"theo diamond 44% taker fees={theo_taker_diamond:.2f} actual={taker_reb:.2f}", flush=True)

    out = {
        "maker_eps": MAKER_EPS,
        "role": by_role,
        "t_hist": t_hist,
        "pair_quantiles": pair_q,
        "pair_hists": pair_hists,
        "hypothesis": hyp,
        "rebate": {
            "maker_usdc": maker_reb,
            "taker_usdc": taker_reb,
            "reward_usdc": reward,
            "total": maker_reb + taker_reb + reward,
            "maker_n_payouts": reb["MAKER_REBATE"]["n"],
            "taker_n_payouts": reb["TAKER_REBATE"]["n"],
            "reward_n": reb["REWARD"]["n"],
            "cents_per_maker_fill": cents_maker,
            "cents_per_taker_fill": cents_taker,
            "maker_rebate_per_share": maker_reb_per_share,
            "maker_rebate_bps_notional": maker_reb_bps_notional,
            "theo_maker_20pct_fee_eq": theo_maker_if_full_pool,
            "maker_fee_eq": maker_fee_eq,
            "actual_over_theo_maker": (maker_reb / theo_maker_if_full_pool) if theo_maker_if_full_pool else None,
            "theo_taker_diamond_44pct": theo_taker_diamond,
            "taker_fees_embed": taker_fees,
            "actual_over_theo_taker": (taker_reb / theo_taker_diamond) if theo_taker_diamond else None,
            "payouts": {k: {"n": v["n"], "usdc": v["usdc"], "rows": v["rows"]} for k, v in reb.items()},
        },
        "pair_gt_1_flat": flat,
        "n_role_windows": {
            "taker_pair_defined": int(role_win["taker_pair_px"].notna().sum()),
            "maker_pair_defined": int(role_win["maker_pair_px"].notna().sum()),
        },
    }
    dest = PROC / "maker_stats.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    role_win.to_parquet(PROC / "whiskas_role_windows.parquet", index=False)
    print(f"wrote {dest} and role windows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
