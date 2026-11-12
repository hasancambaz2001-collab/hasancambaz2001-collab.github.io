"""Round 2: literature-based betting hypotheses, same blind protocol.

H1  Consensus gap (Kaunitz, Zhong & Kreiner 2017): bet at the best market
    price when it beats the Bet365 margin-free (Shin) probability.
H2  Favourite-longshot bias (Thaler & Ziemba 1988; Cain, Law & Peel 2000):
    back favourites at the best price.
H3  Model + market pool at the best price (pool refitted on validation).
H4  H1 restricted to short odds (H1 x H2).

Protocol
  validation 2005-07-01 .. 2019-07-01 : choose parameters per hypothesis
  gate        a hypothesis goes to the test only if its validation 95% CI
              (day-block bootstrap) is entirely above 0
  freeze      config/strategies_frozen.json is committed BEFORE `--test`
  test        2019-07-01 .. end, run once; Bonferroni over every strategy
              tested in this project (5 in round 1 + the gated ones here)

Usage: python3 strategies.py --tune ; git commit ; python3 strategies.py --test
"""
import iddaa  # noqa: F401
import argparse
import itertools
import json
import os

import numpy as np
import pandas as pd

from iddaa.backtest import Config, walk_forward
from iddaa.data import load
from iddaa.evaluate import all_probs, apply_pool, fit_pool, group_matrix, market_probs, outcomes

VAL = ("2005-07-01", "2019-07-01")
TEST = ("2019-07-01", "2026-12-31")
MAX_RATIO = 1.35   # fixed a priori: a best price >35% above Bet365 is treated as a stale/erroneous quote
ROUND1_TESTS = 5
FROZEN = "config/strategies_frozen.json"


def block_boot(profit, dates, n=2000, seed=1):
    """Bootstrap ROI resampling whole days (bets on one day are correlated)."""
    if len(profit) == 0:
        return np.nan, np.nan, np.nan
    df = pd.DataFrame({"d": dates, "p": profit}).groupby("d").p.agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), (n, len(s)))
    roi = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(roi, 2.5)), float(np.percentile(roi, 97.5)), float((roi <= 0).mean())


def candidates(D, p_fair, p_model):
    """Per match & outcome: best odds, b365 odds, fair prob, model prob, won flag."""
    res = np.stack([(D.FTHome > D.FTAway).to_numpy(), (D.FTHome == D.FTAway).to_numpy(), (D.FTHome < D.FTAway).to_numpy()], 1)
    tot = (D.FTHome + D.FTAway).to_numpy()
    rows = []
    for k, (mx, b3, lab) in enumerate((("MaxHome", "OddHome", "1"), ("MaxDraw", "OddDraw", "X"), ("MaxAway", "OddAway", "2"))):
        rows.append(pd.DataFrame({"i": np.arange(len(D)), "market": "1x2", "pick": lab,
                                  "o_max": D[mx].to_numpy(float), "o_b365": D[b3].to_numpy(float),
                                  "p_fair": p_fair[lab], "p_model": p_model[lab], "won": res[:, k]}))
    for mx, b3, lab, w in (("MaxOver25", "Over25", "O2.5", tot > 2.5), ("MaxUnder25", "Under25", "U2.5", tot < 2.5)):
        rows.append(pd.DataFrame({"i": np.arange(len(D)), "market": "ou25", "pick": lab,
                                  "o_max": D[mx].to_numpy(float), "o_b365": D[b3].to_numpy(float),
                                  "p_fair": p_fair[lab], "p_model": p_model[lab], "won": w}))
    C = pd.concat(rows, ignore_index=True)
    C["date"] = D.date.to_numpy()[C.i]
    C["div"] = D["div"].to_numpy()[C.i]
    C = C[np.isfinite(C.o_max) & np.isfinite(C.o_b365) & np.isfinite(C.p_fair)]
    C = C[C.o_max / C.o_b365 <= MAX_RATIO]
    C["profit"] = np.where(C.won, C.o_max - 1, -1.0)
    return C


def select(C, h, prm):
    if h == "H1":
        m = (C.market == prm["market"]) & (C.o_max * C.p_fair - 1 > prm["tau"]) & (C.o_max <= prm["omax"])
    elif h == "H2":
        m = (C.market == "1x2") & (C.p_fair >= prm["pmin"]) & (C.pick != "X")
    elif h == "H3":
        m = (C.market == prm["market"]) & (C.o_max * C.p_model - 1 > prm["tau"]) & (C.o_max <= prm["omax"])
    elif h == "H4":
        m = (C.market == "1x2") & (C.o_max * C.p_fair - 1 > prm["tau"]) & (C.p_fair >= prm["pmin"])
    S = C[m]
    # at most one bet per match and market: the highest-edge selection
    ev = S.o_max * (S.p_model if h == "H3" else S.p_fair) - 1
    S = S.assign(ev=ev).sort_values("ev", ascending=False).drop_duplicates(["i", "market"])
    return S


GRID = {
    "H1": [dict(market=m, tau=t, omax=o) for m, t, o in itertools.product(("1x2", "ou25"), (0.0, 0.01, 0.02, 0.03, 0.05), (2.5, 4.0, 10.0))],
    "H2": [dict(pmin=p) for p in (0.5, 0.6, 0.7, 0.8)],
    "H3": [dict(market=m, tau=t, omax=o) for m, t, o in itertools.product(("1x2", "ou25"), (0.0, 0.02, 0.04, 0.06), (2.5, 4.0))],
    "H4": [dict(tau=t, pmin=p) for t, p in itertools.product((0.0, 0.01, 0.02, 0.03), (0.4, 0.5, 0.6))],
}


def summarize(S):
    lo, hi, p = block_boot(S.profit.to_numpy(), S.date.to_numpy())
    return {"bets": int(len(S)), "roi": float(S.profit.mean()) if len(S) else np.nan, "ci_lo": lo, "ci_hi": hi,
            "p_val": p, "avg_odds": float(S.o_max.mean()) if len(S) else np.nan}


def build(df, start, end, pool=None):
    cfg = Config(**json.load(open("config/frozen_params.json"))["config"])
    cfg.side_markets = False
    P = walk_forward(df, start, end, cfg)
    D = df.loc[P.index]
    p = all_probs(P)
    q = market_probs(D, "b365")
    O = outcomes(D)
    if pool is None:
        pool = {k: fit_pool(group_matrix(p, ks), group_matrix(q, ks), group_matrix(O, ks)).tolist()
                for k, ks in (("1x2", ["1", "X", "2"]), ("ou25", ["O2.5", "U2.5"]))}
    b3 = apply_pool(group_matrix(p, ["1", "X", "2"]), group_matrix(q, ["1", "X", "2"]), pool["1x2"])
    b2 = apply_pool(group_matrix(p, ["O2.5", "U2.5"]), group_matrix(q, ["O2.5", "U2.5"]), pool["ou25"])
    pm = {"1": b3[:, 0], "X": b3[:, 1], "2": b3[:, 2], "O2.5": b2[:, 0], "U2.5": b2[:, 1]}
    return candidates(D, q, pm), pool


def tune():
    df = load()
    C, pool = build(df, *VAL)
    print("pool (validation 2005-2019):", pool)
    rows, chosen = [], {}
    for h, grid in GRID.items():
        best = None
        for prm in grid:
            s = summarize(select(C, h, prm))
            rows.append({"h": h, **prm, **s})
            if s["bets"] >= 500 and (best is None or s["roi"] > best[1]["roi"]):
                best = (prm, s)
        gate = best is not None and best[1]["ci_lo"] > 0
        chosen[h] = {"params": best[0] if best else None, "validation": best[1] if best else None, "passes_gate": bool(gate)}
        print(h, chosen[h], flush=True)
    pd.DataFrame(rows).to_csv("results/strategies_validation_grid.csv", index=False)
    n_new = sum(v["passes_gate"] for v in chosen.values())
    frozen = {"validation": VAL, "test": TEST, "max_ratio": MAX_RATIO, "pool_val": pool, "hypotheses": chosen,
              "bonferroni_k": ROUND1_TESTS + n_new,
              "note": "Only hypotheses with passes_gate=true are evaluated in the test; alpha = 0.05 / bonferroni_k."}
    json.dump(frozen, open(FROZEN, "w"), indent=2, default=float)
    print(json.dumps(frozen, indent=2, default=float))


def test():
    fz = json.load(open(FROZEN))
    df = load()
    C, _ = build(df, *TEST, pool=fz["pool_val"])
    alpha = 0.05 / fz["bonferroni_k"]
    out = {}
    for h, v in fz["hypotheses"].items():
        if not v["passes_gate"]:
            out[h] = {"status": "validation'da elendi, test edilmedi"}
            continue
        S = select(C, h, v["params"])
        s = summarize(S)
        s["season_roi"] = {int(k): float(g.profit.mean()) for k, g in
                           S.groupby(np.where(S.date.dt.month >= 7, S.date.dt.year, S.date.dt.year - 1))}
        s["significant_after_bonferroni"] = bool(s["p_val"] < alpha and s["roi"] > 0)
        out[h] = s
        S.to_csv(f"results/strategy_{h}_test_bets.csv.gz", index=False)
        print(h, s, flush=True)
    out["alpha_bonferroni"] = alpha
    json.dump(out, open("results/strategies_test_results.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--tune", action="store_true")
    a.add_argument("--test", action="store_true")
    x = a.parse_args()
    if x.tune:
        tune()
    if x.test:
        test()
