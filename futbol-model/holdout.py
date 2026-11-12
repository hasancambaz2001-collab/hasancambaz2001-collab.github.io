"""Step 2 — the BLIND test. Loads the frozen parameters, runs the
walk-forward on the untouched holdout window and writes every metric.
Run once; do not re-tune on these results.
"""
import iddaa  # noqa: F401
import json
import os
import subprocess

import numpy as np
import pandas as pd

from iddaa.backtest import Config, walk_forward
from iddaa.data import LEAGUE_NAMES, load
from iddaa.evaluate import (GROUPS, _complete, all_probs, apply_pool, bets_1x2, bets_ah, bets_ou,
                            brier, climatology, group_matrix, implied_rates, kelly_path, logloss,
                            market_probs, outcomes, rps, summarize_bets)

HOLD_START = os.environ.get("HOLD_START", "2019-07-01")
HOLD_END = os.environ.get("HOLD_END", "2026-12-31")
R = os.environ.get("RESULTS_DIR", "results")


def calib_table(p, o, bins=10):
    ok = np.isfinite(p) & np.isfinite(o)
    p, o = p[ok], o[ok]
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return [{"pred": float(p[idx == b].mean()), "obs": float(o[idx == b].mean()), "n": int((idx == b).sum())}
            for b in range(bins) if (idx == b).any()]


def main():
    fz = json.load(open("config/frozen_params.json"))
    commit = subprocess.run(["git", "log", "-1", "--format=%H %cI", "--", "config/frozen_params.json"],
                            capture_output=True, text=True).stdout.strip()
    cfg = Config(**fz["config"])
    df = load()
    P = walk_forward(df, HOLD_START, HOLD_END, cfg)
    P.to_pickle(f"{R}/pred_holdout.pkl")
    D = df.loc[P.index]
    p = all_probs(P)
    O = outcomes(D)
    _complete(p, O)
    base = climatology(df, D, HOLD_START)
    _complete(base, {"EV_O1.5": 0, "DEP_O1.5": 0})

    q = market_probs(D, "b365")
    blend = {}
    b = apply_pool(group_matrix(p, ["1", "X", "2"]), group_matrix(q, ["1", "X", "2"]), fz["pool_b365"]["1x2"])
    blend.update({"1": b[:, 0], "X": b[:, 1], "2": b[:, 2]})
    b = apply_pool(group_matrix(p, ["O2.5", "U2.5"]), group_matrix(q, ["O2.5", "U2.5"]), fz["pool_b365"]["ou25"])
    blend.update({"O2.5": b[:, 0], "U2.5": b[:, 1]})
    lh2, la2 = implied_rates(P.lh.to_numpy(), P.la.to_numpy(), P.rho.to_numpy(), blend)
    pb = all_probs(P, lh2, la2)
    _complete(pb, {"EV_O1.5": np.zeros(1), "DEP_O1.5": np.zeros(1)})

    out = {"frozen_commit": commit, "frozen": fz, "n_matches": int(len(P)),
           "window": [str(D.date.min().date()), str(D.date.max().date())]}

    # ---- 1. probabilistic accuracy for every market -------------------------
    rows = []
    for g, keys in GROUPS.items():
        Om = group_matrix(O, keys)
        ll_m, n = logloss(group_matrix(p, keys), Om)
        ll_b, _ = logloss(group_matrix(base, keys), Om)
        ll_x, _ = logloss(group_matrix(pb, keys), Om)
        r = {"market": g, "n": int(n), "ll_model": ll_m, "ll_base": ll_b, "ll_model_mkt": ll_x,
             "skill_vs_base_%": 100 * (1 - ll_m / ll_b), "skill_mkt_vs_base_%": 100 * (1 - ll_x / ll_b),
             "brier_model": brier(group_matrix(p, keys), Om), "brier_base": brier(group_matrix(base, keys), Om)}
        if g in ("MS 1X2", "Alt/Üst 2.5"):
            r["ll_bookmaker"] = logloss(group_matrix(q, keys), Om)[0]
        if g == "MS 1X2":
            r["rps_model"], r["rps_book"], r["rps_base"] = (rps(group_matrix(x, keys), Om) for x in (p, q, base))
            r["rps_model_mkt"] = rps(group_matrix(pb, keys), Om)
        rows.append(r)
    acc = pd.DataFrame(rows)
    acc.to_csv(f"{R}/holdout_accuracy.csv", index=False)
    out["accuracy"] = acc.to_dict("records")

    # same-sample model vs bookmaker (rows where B365 odds exist)
    ok = np.isfinite(q["1"])
    k3 = ["1", "X", "2"]
    out["vs_book_1x2"] = {
        "n": int(ok.sum()),
        "ll_model": logloss(group_matrix(p, k3)[ok], group_matrix(O, k3)[ok])[0],
        "ll_book": logloss(group_matrix(q, k3)[ok], group_matrix(O, k3)[ok])[0],
        "ll_blend": logloss(group_matrix(blend, k3)[ok], group_matrix(O, k3)[ok])[0]}

    # per league
    rows = []
    for dv, idx in pd.Series(np.arange(len(D))).groupby(D["div"].to_numpy()):
        i = idx.to_numpy()
        i2 = i[np.isfinite(q["1"][i])]
        rows.append({"div": dv, "league": LEAGUE_NAMES.get(dv, dv), "n": len(i),
                     "ll_model": logloss(group_matrix(p, k3)[i2], group_matrix(O, k3)[i2])[0],
                     "ll_book": logloss(group_matrix(q, k3)[i2], group_matrix(O, k3)[i2])[0],
                     "ll_base": logloss(group_matrix(base, k3)[i], group_matrix(O, k3)[i])[0]})
    out["per_league"] = rows

    # calibration
    out["calibration"] = {
        "MS 1": calib_table(p["1"], O["1"]), "Beraberlik": calib_table(p["X"], O["X"]),
        "Üst 2.5": calib_table(p["O2.5"], O["O2.5"]), "KG Var": calib_table(p["KG_VAR"], O["KG_VAR"]),
        "İY Üst 0.5": calib_table(p["IY_O0.5"], O["IY_O0.5"]),
        "Korner Üst 9.5": calib_table(p["KOR_O9.5"], O["KOR_O9.5"]),
        "Kart Üst 4.5": calib_table(p["KART_O4.5"], O["KART_O4.5"])}

    # ---- 2. betting with the frozen rules ----------------------------------
    min_n = ((P.nh >= fz["min_team_obs"]) & (P.na >= fz["min_team_obs"])).to_numpy()
    bets = []
    summary = []
    for book, c1, c2 in (("b365", ["OddHome", "OddDraw", "OddAway"], ["Over25", "Under25"]),
                         ("max", ["MaxHome", "MaxDraw", "MaxAway"], ["MaxOver25", "MaxUnder25"])):
        for market, rule in fz["rules"].items():
            if market == "ah" and book == "max":
                continue  # no best-price AH odds in the data
            pp = p if rule["src"] == "model" else pb
            if market == "1x2":
                B = bets_1x2(pp, D, c1, rule["tau"], rule["omax"], min_n)
            elif market == "ou25":
                B = bets_ou(pp, D, c2, rule["tau"], rule["omax"], min_n)
            else:
                B = bets_ah(pp["_dpmf"], D, rule["tau"], rule["omax"], min_n)
            B = B.assign(book=book, season=np.where(B.date.dt.month >= 7, B.date.dt.year, B.date.dt.year - 1))
            bets.append(B)
            s = summarize_bets(B)
            s.update({"book": book, "market": market, **rule})
            s["by_season"] = {int(k): summarize_bets(g, n_boot=500) for k, g in B.groupby("season")}
            kp = kelly_path(B) if len(B) else pd.DataFrame(columns=["date", "bank"])
            s["kelly_final"] = float(kp.bank.iloc[-1]) if len(kp) else 1.0
            s["kelly_min"] = float(kp.bank.min()) if len(kp) else 1.0
            s["curve"] = [[str(d.date()), float(v)] for d, v in
                          zip(B.sort_values("date").date, B.sort_values("date").profit.cumsum())][:: max(1, len(B) // 300)]
            summary.append(s)
            print(book, market, {k: v for k, v in s.items() if k not in ("by_season", "curve")}, flush=True)
    allb = pd.concat(bets)
    allb.to_csv(f"{R}/holdout_bets.csv.gz", index=True)
    out["betting"] = summary

    # sanity reference: betting EVERY outcome blindly = bookmaker margin
    for name, cols in (("1x2_all_b365", ["OddHome", "OddDraw", "OddAway"]),):
        Oo = D[cols].to_numpy(float)
        res = np.stack([(D.FTHome > D.FTAway), (D.FTHome == D.FTAway), (D.FTHome < D.FTAway)], 1)
        pr = np.where(res, Oo - 1, -1.0)
        out[name] = float(np.nanmean(pr))

    with open(f"{R}/holdout_results.json", "w") as f:
        json.dump(out, f, indent=1, default=float)
    print(acc.round(4).to_string())
    print(json.dumps(out["vs_book_1x2"], indent=1))


if __name__ == "__main__":
    main()
