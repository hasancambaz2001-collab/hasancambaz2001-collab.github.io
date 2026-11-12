"""Step 1 — tune every free parameter on the VALIDATION window only
(2016/17-2018/19) and freeze them in config/frozen_params.json.

The holdout window (2019/20 onward) is never touched here.
"""
import iddaa  # noqa: F401  (sets BLAS threads before numpy)
import itertools
import json
import os
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

from iddaa import markets as mk
from iddaa.backtest import Config, walk_forward
from iddaa.data import load
from iddaa.evaluate import (EPS, all_probs, bets_1x2, bets_ah, bets_ou, fit_pool, group_matrix,
                            implied_rates, logloss, market_probs, outcomes, summarize_bets, apply_pool)

VAL_START, VAL_END = "2016-07-01", "2019-07-01"
os.makedirs("results", exist_ok=True)


def score_ll(P, D):
    M = mk.score_matrix(P.lh.to_numpy(), P.la.to_numpy(), P.rho.to_numpy())
    h = np.clip(D.FTHome.to_numpy().astype(int), 0, mk.G - 1)
    a = np.clip(D.FTAway.to_numpy().astype(int), 0, mk.G - 1)
    return -np.log(np.clip(M[np.arange(len(h)), h, a], EPS, 1)).mean()


def count_ll(P, D, pre, hc, ac):
    ok = P[f"{pre}lh"].notna().to_numpy() & D[hc].notna().to_numpy() & D[ac].notna().to_numpy()
    pm = mk.count_pmf((P[f"{pre}lh"] + P[f"{pre}la"]).to_numpy()[ok], P[f"{pre}disp"].to_numpy()[ok], 60)
    y = (D[hc] + D[ac]).to_numpy()[ok].astype(int)
    return -np.log(np.clip(pm[np.arange(len(y)), np.clip(y, 0, 59)], EPS, 1)).mean(), ok.sum()


def main():
    df = load()
    D_val = df[(df.date >= VAL_START) & (df.date < VAL_END)]
    O = outcomes(D_val)

    # ---- 1. goal model grid ------------------------------------------------
    rows = []
    best = None
    for xi, ridge, w in itertools.product((0.001, 0.0018, 0.003), (1.0, 3.0, 8.0), (0.0, 0.3, 0.6)):
        cfg = Config(xi=xi, ridge=ridge, w_sot=w, side_markets=False)
        P = walk_forward(df, VAL_START, VAL_END, cfg)
        D = D_val.loc[P.index]
        p = all_probs(P)
        Oi = {k: v[D_val.index.get_indexer(P.index)] for k, v in O.items()}
        r = {"xi": xi, "ridge": ridge, "w_sot": w, "n": len(P), "score_ll": score_ll(P, D)}
        for g, keys in (("ll_1x2", ["1", "X", "2"]), ("ll_ou25", ["O2.5", "U2.5"]), ("ll_kg", ["KG_VAR", "KG_YOK"])):
            r[g] = logloss(group_matrix(p, keys), group_matrix(Oi, keys))[0]
        rows.append(r)
        print(r, flush=True)
        if best is None or r["score_ll"] < best["score_ll"]:
            best = r
    pd.DataFrame(rows).to_csv("results/validation_goal_grid.csv", index=False)
    cfg = Config(xi=best["xi"], ridge=best["ridge"], w_sot=best["w_sot"])

    # ---- 2. corners / cards grid ------------------------------------------
    rows = []
    bc = bk = None
    for cx, cr in itertools.product((0.0015, 0.003, 0.006), (1.0, 3.0, 8.0, 20.0, 50.0, 120.0, 300.0)):
        c2 = replace(cfg, c_xi=cx, c_ridge=cr, k_xi=cx, k_ridge=cr)
        P = walk_forward(df, VAL_START, VAL_END, c2)
        D = D_val.loc[P.index]
        lc, nc = count_ll(P, D, "c", "HomeCorners", "AwayCorners")
        lk, nk = count_ll(P, D, "k", "HomeCards", "AwayCards")
        r = {"xi": cx, "ridge": cr, "ll_corners": lc, "n_c": nc, "ll_cards": lk, "n_k": nk}
        rows.append(r)
        print(r, flush=True)
        if bc is None or lc < bc["ll_corners"]:
            bc = r
        if bk is None or lk < bk["ll_cards"]:
            bk = r
    pd.DataFrame(rows).to_csv("results/validation_side_grid.csv", index=False)
    cfg = replace(cfg, c_xi=bc["xi"], c_ridge=bc["ridge"], k_xi=bk["xi"], k_ridge=bk["ridge"])

    # ---- 3. final validation run, market pool + betting rules --------------
    P = walk_forward(df, VAL_START, VAL_END, cfg)
    P.to_pickle("results/pred_validation.pkl")
    D = D_val.loc[P.index]
    p = all_probs(P)
    Oi = {k: v[D_val.index.get_indexer(P.index)] for k, v in O.items()}
    q = market_probs(D, "b365")
    pool = {}
    for name, keys in (("1x2", ["1", "X", "2"]), ("ou25", ["O2.5", "U2.5"])):
        pool[name] = fit_pool(group_matrix(p, keys), group_matrix(q, keys), group_matrix(Oi, keys)).tolist()
    print("pool weights", pool)

    blend = {}
    b = apply_pool(group_matrix(p, ["1", "X", "2"]), group_matrix(q, ["1", "X", "2"]), pool["1x2"])
    blend.update({"1": b[:, 0], "X": b[:, 1], "2": b[:, 2]})
    b = apply_pool(group_matrix(p, ["O2.5", "U2.5"]), group_matrix(q, ["O2.5", "U2.5"]), pool["ou25"])
    blend.update({"O2.5": b[:, 0], "U2.5": b[:, 1]})
    ok = np.isfinite(blend["1"]) & np.isfinite(blend["O2.5"])
    tgt = {k: np.where(ok, v, np.nan) for k, v in blend.items()}
    lh2, la2 = implied_rates(P.lh.to_numpy(), P.la.to_numpy(), P.rho.to_numpy(), tgt)
    pb = all_probs(P, lh2, la2)
    min_n = ((P.nh >= 10) & (P.na >= 10)).to_numpy()

    rules = {}
    rows = []
    for market in ("1x2", "ou25", "ah"):
        best_r = None
        for src, tau, omax in itertools.product(("model", "blend"), (0.02, 0.04, 0.06, 0.08, 0.1, 0.15), (3.0, 5.0)):
            pp = p if src == "model" else pb
            if market == "1x2":
                B = bets_1x2(pp, D, ["OddHome", "OddDraw", "OddAway"], tau, omax, min_n)
            elif market == "ou25":
                B = bets_ou(pp, D, ["Over25", "Under25"], tau, omax, min_n)
            else:
                B = bets_ah(pp["_dpmf"], D, tau, omax, min_n)
            s = summarize_bets(B)
            s.update({"market": market, "src": src, "tau": tau, "omax": omax})
            rows.append(s)
            if s["bets"] >= 300 and (best_r is None or s["roi"] > best_r["roi"]):
                best_r = s
        rules[market] = {k: best_r[k] for k in ("src", "tau", "omax")}
        print(market, best_r, flush=True)
    pd.DataFrame(rows).to_csv("results/validation_betting_grid.csv", index=False)

    frozen = {"config": asdict(cfg), "pool_b365": pool, "rules": rules, "min_team_obs": 10,
              "validation_window": [VAL_START, VAL_END],
              "note": "Tuned on validation only. Holdout (2019-07-01 onward) not used."}
    with open("config/frozen_params.json", "w") as f:
        json.dump(frozen, f, indent=2)
    print(json.dumps(frozen, indent=2))


if __name__ == "__main__":
    main()
