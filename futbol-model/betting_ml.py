"""Round 3: do the factor-lab models make money against the market?

H5  LightGBM, all puzzle pieces, MS 1X2, best price
H6  LightGBM, all puzzle pieces, Alt/Üst 2.5, best price
H7  LightGBM, market + model + injuries only, MS 1X2, best price

Same protocol: LightGBM hyper-parameters fixed a priori (factor_lab.PARAMS),
walk-forward season folds; edge threshold and odds cap chosen on folds
2015-2018, gate = validation CI > 0, frozen in config/ml_frozen.json and
committed BEFORE `--test`, Bonferroni over every strategy tested so far.

  python3 betting_ml.py --predict   # all fold predictions -> cache
  python3 betting_ml.py --tune      # uses only seasons <= 2018
  git commit config/ml_frozen.json
  python3 betting_ml.py --test
"""
import iddaa  # noqa: F401
import argparse
import itertools
import json

import numpy as np
import pandas as pd

from factor_lab import FOLDS, fit_predict
from iddaa.features import GROUPS
from strategies import block_boot

PRIOR_TESTS = 8  # round 1 (5) + round 2 (3)
FROZEN = "config/ml_frozen.json"
CACHE = "cache/ml_preds.pkl"


def feature_sets(X):
    f = {g: [c for c in cols if c in X] for g, cols in GROUPS.items()}
    full = sorted({c for v in f.values() for c in v} | {"div_code"})
    inj = sorted(set(f["piyasa"]) | set(f["model"]) | set(f["sakatlik"]) | {"div_code"})
    return {"full": full, "inj": inj}


def predict():
    d = pd.read_pickle("cache/features.pkl")
    X, T, M = d["X"].copy(), d["T"], d["meta"]
    X["rest_h"], X["rest_a"] = X.rest_h.clip(upper=30), X.rest_a.clip(upper=30)
    sets = feature_sets(X)
    season = M.season.to_numpy()
    out = pd.DataFrame(index=X.index)
    for name, cols in sets.items():
        for tgt, obj in (("result", "multiclass"), ("over25", "binary")):
            if name == "inj" and tgt == "over25":
                continue
            p = np.full((len(X), 3 if obj == "multiclass" else 1), np.nan)
            for f0, f1 in FOLDS:
                tr = (season < f0) & T[tgt].notna().to_numpy()
                te = (season >= f0) & (season <= f1)
                if te.sum() == 0:
                    continue
                pr, _ = fit_predict(obj, X.loc[tr, cols], T[tgt][tr], X.loc[te, cols])
                p[te] = pr if pr.ndim == 2 else pr[:, None]
            if obj == "multiclass":
                out[f"{name}_p1"], out[f"{name}_px"], out[f"{name}_p2"] = p[:, 0], p[:, 1], p[:, 2]
            else:
                out[f"{name}_pover"] = p[:, 0]
            print(name, tgt, "done", flush=True)
    out.to_pickle(CACHE)


def candidates(src, market):
    d = pd.read_pickle("cache/features.pkl")
    M = d["meta"]
    P = pd.read_pickle(CACHE)
    res = np.stack([(M.FTHome > M.FTAway).to_numpy(), (M.FTHome == M.FTAway).to_numpy(), (M.FTHome < M.FTAway).to_numpy()], 1)
    tot = (M.FTHome + M.FTAway).to_numpy()
    rows = []
    if market == "1x2":
        for k, (c, b3, lab) in enumerate((("MaxHome", "OddHome", "p1"), ("MaxDraw", "OddDraw", "px"), ("MaxAway", "OddAway", "p2"))):
            rows.append(pd.DataFrame({"i": np.arange(len(M)), "o": M[c].to_numpy(float), "o_b365": M[b3].to_numpy(float),
                                      "p": P[f"{src}_{lab}"].to_numpy(), "won": res[:, k]}))
    else:
        po = P[f"{src}_pover"].to_numpy()
        rows.append(pd.DataFrame({"i": np.arange(len(M)), "o": M.MaxOver25.to_numpy(float), "o_b365": M.Over25.to_numpy(float), "p": po, "won": tot > 2.5}))
        rows.append(pd.DataFrame({"i": np.arange(len(M)), "o": M.MaxUnder25.to_numpy(float), "o_b365": M.Under25.to_numpy(float), "p": 1 - po, "won": tot < 2.5}))
    C = pd.concat(rows, ignore_index=True)
    C["date"] = M.date.to_numpy()[C.i]
    C["season"] = M.season.to_numpy()[C.i]
    C = C[np.isfinite(C.o) & np.isfinite(C.p) & np.isfinite(C.o_b365) & (C.o / C.o_b365 <= 1.35)]
    C["ev"] = C.p * C.o - 1
    C["profit"] = np.where(C.won, C.o - 1, -1.0)
    return C


HYP = {"H5": ("full", "1x2"), "H6": ("full", "ou25"), "H7": ("inj", "1x2")}


def select(C, tau, omax):
    S = C[(C.ev > tau) & (C.o <= omax)]
    return S.sort_values("ev", ascending=False).drop_duplicates("i")


def summ(S):
    lo, hi, p = block_boot(S.profit.to_numpy(), S.date.to_numpy())
    return {"bets": int(len(S)), "roi": float(S.profit.mean()) if len(S) else float("nan"), "ci_lo": lo, "ci_hi": hi, "p_val": p}


def tune():
    chosen = {}
    for h, (src, mkt) in HYP.items():
        C = candidates(src, mkt)
        V = C[C.season <= 2018]
        best = None
        for tau, omax in itertools.product((0.0, 0.02, 0.04, 0.06, 0.08, 0.1), (2.5, 4.0)):
            s = summ(select(V, tau, omax))
            if s["bets"] >= 300 and (best is None or s["roi"] > best[1]["roi"]):
                best = ({"tau": tau, "omax": omax}, s)
        chosen[h] = {"src": src, "market": mkt, "params": best[0] if best else None,
                     "validation": best[1] if best else None, "passes_gate": bool(best and best[1]["ci_lo"] > 0)}
        print(h, chosen[h], flush=True)
    n_new = sum(v["passes_gate"] for v in chosen.values())
    json.dump({"hypotheses": chosen, "bonferroni_k": PRIOR_TESTS + n_new, "validation_seasons": "2015-2018",
               "test_seasons": "2019-2026"}, open(FROZEN, "w"), indent=2, default=float)


def test():
    fz = json.load(open(FROZEN))
    alpha = 0.05 / fz["bonferroni_k"]
    out = {"alpha_bonferroni": alpha}
    for h, v in fz["hypotheses"].items():
        C = candidates(v["src"], v["market"])
        Tt = C[C.season >= 2019]
        if not v["passes_gate"]:
            # reported for transparency only, not counted as a test
            s = summ(select(Tt, 0.02, 4.0))
            out[h] = {"status": "validation'da elendi", "info_only_tau0.02": s}
        else:
            S = select(Tt, v["params"]["tau"], v["params"]["omax"])
            s = summ(S)
            s["significant_after_bonferroni"] = bool(s["p_val"] < alpha and s["roi"] > 0)
            out[h] = s
        print(h, out[h], flush=True)
    json.dump(out, open("results/ml_betting_test.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    for f in ("predict", "tune", "test"):
        a.add_argument(f"--{f}", action="store_true")
    x = a.parse_args()
    if x.predict:
        predict()
    if x.tune:
        tune()
    if x.test:
        test()
