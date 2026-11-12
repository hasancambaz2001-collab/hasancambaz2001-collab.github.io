"""Exploratory robustness checks of H7 (NOT pre-registered; read as diagnostics).

A  same rule priced at Bet365 instead of the best price
B  best price but only where it is within 10% of Bet365 (no outlier quotes)
C  ablation: identical LightGBM WITHOUT injuries (market + model only)
D  injuries counted only if they started >= 3 days before the match
E  stability by season, league and pick
"""
import iddaa  # noqa: F401
import json

import numpy as np
import pandas as pd

import iddaa.injuries as inj_mod
from betting_ml import candidates, select, summ
from factor_lab import FOLDS, fit_predict
from iddaa.data import load
from iddaa.features import GROUPS, build

fz = json.load(open("config/ml_frozen.json"))["hypotheses"]["H7"]["params"]
tau, omax = fz["tau"], fz["omax"]
out = {}


def run_preds(X, T, M, cols):
    season = M.season.to_numpy()
    p = np.full((len(X), 3), np.nan)
    for f0, f1 in FOLDS:
        tr = (season < f0) & T.result.notna().to_numpy()
        te = (season >= f0) & (season <= f1)
        pr, _ = fit_predict("multiclass", X.loc[tr, cols], T.result[tr], X.loc[te, cols])
        p[te] = pr
    return p


def cand_from(p, M, odds_cols=("MaxHome", "MaxDraw", "MaxAway")):
    res = np.stack([(M.FTHome > M.FTAway).to_numpy(), (M.FTHome == M.FTAway).to_numpy(), (M.FTHome < M.FTAway).to_numpy()], 1)
    rows = []
    for k, (c, b3) in enumerate(zip(odds_cols, ("OddHome", "OddDraw", "OddAway"))):
        rows.append(pd.DataFrame({"i": np.arange(len(M)), "o": M[c].to_numpy(float), "o_b365": M[b3].to_numpy(float),
                                  "p": p[:, k], "won": res[:, k], "pick": "1X2"[k]}))
    C = pd.concat(rows, ignore_index=True)
    C["date"], C["season"], C["div"] = M.date.to_numpy()[C.i], M.season.to_numpy()[C.i], M["div"].to_numpy()[C.i]
    C = C[np.isfinite(C.o) & np.isfinite(C.p) & np.isfinite(C.o_b365) & (C.o / C.o_b365 <= 1.35)]
    C["ev"] = C.p * C.o - 1
    C["profit"] = np.where(C.won, C.o - 1, -1.0)
    return C


d = pd.read_pickle("cache/features.pkl")
X, T, M = d["X"].copy(), d["T"], d["meta"]
P = pd.read_pickle("cache/ml_preds.pkl")
p7 = P[["inj_p1", "inj_px", "inj_p2"]].to_numpy()
test = lambda C: C[C.season >= 2019]

base = select(test(cand_from(p7, M)), tau, omax)
out["H7 (as frozen)"] = summ(base)
out["A at Bet365"] = summ(select(test(cand_from(p7, M, ("OddHome", "OddDraw", "OddAway"))), tau, omax))
Cb = test(cand_from(p7, M))
out["B best within 10% of B365"] = summ(select(Cb[Cb.o / Cb.o_b365 <= 1.10], tau, omax))

f = {g: [c for c in cols if c in X] for g, cols in GROUPS.items()}
cols_base = sorted(set(f["piyasa"]) | set(f["model"]) | {"div_code"})
pb = run_preds(X, T, M, cols_base)
out["C no injuries (market+model LGBM)"] = summ(select(test(cand_from(pb, M)), tau, omax))
out["C' no injuries at Bet365"] = summ(select(test(cand_from(pb, M, ("OddHome", "OddDraw", "OddAway"))), tau, omax))

# D: injuries that started >= 3 days before the match
orig = inj_mod.availability
df = load()
src = open(inj_mod.__file__).read()
assert "(f[None, :] < D[:, None])" in src
code = src.replace("(f[None, :] < D[:, None])", "(f[None, :] <= D[:, None] - np.timedelta64(3, 'D'))")
ns = {}
exec(compile(code, "injuries_lag3", "exec"), ns)
A3, _ = ns["availability"](df)
X3 = build(df, pd.read_pickle("cache/dc_preds.pkl"), A3).loc[X.index]
X3["rest_h"], X3["rest_a"] = X3.rest_h.clip(upper=30), X3.rest_a.clip(upper=30)
cols_inj = sorted(set(f["piyasa"]) | set(f["model"]) | set(f["sakatlik"]) | {"div_code"})
p3 = run_preds(X3, T, M, cols_inj)
out["D injuries started >=3 days before"] = summ(select(test(cand_from(p3, M)), tau, omax))
out["D' same, at Bet365"] = summ(select(test(cand_from(p3, M, ("OddHome", "OddDraw", "OddAway"))), tau, omax))

# E: stability
out["E by season"] = {int(k): {"bets": int(len(g)), "roi": float(g.profit.mean())} for k, g in base.groupby("season")}
out["E by pick"] = {k: {"bets": int(len(g)), "roi": float(g.profit.mean()), "avg_odds": float(g.o.mean())} for k, g in base.groupby("pick")}
out["E by league"] = {k: {"bets": int(len(g)), "roi": float(g.profit.mean())} for k, g in base.groupby("div")}
json.dump(out, open("results/h7_robustness.json", "w"), indent=1, default=float)
for k, v in out.items():
    print(k, v)
