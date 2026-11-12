"""Factor lab: which inputs (puzzle pieces) improve out-of-sample prediction
of corners, cards, red cards, goals, BTTS, 1X2 ... beyond what the market and
the Dixon-Coles model already know?

1. Group ablation (walk-forward LightGBM, season folds):
     base  = market + model
     base + G for every other group G, and full (all groups)
   Gain = loss(base) - loss(base+G) per match, day-block bootstrap CI.
   Discovery folds 2015-2018, confirmation folds 2019-2026.
2. Effect direction: SHAP contributions of the full model on confirmation
   folds, summarised as "high X -> target +y%".
3. Human-readable rules ("home unbeaten in last 3 home H2H", "top scorer
   injured", top/bottom decile of every feature ...). For each rule the
   observed outcome rate is compared with the base model's expectation on the
   same matches. Benjamini-Hochberg FDR on discovery, survivors re-tested on
   confirmation.
"""
import iddaa  # noqa: F401
import json
import os
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import stats

from iddaa.features import GROUPS

R = "results/factor_lab"
os.makedirs(R, exist_ok=True)
FOLDS = [(2015, 2016), (2017, 2018), (2019, 2020), (2021, 2022), (2023, 2024), (2025, 2026)]
DISC = {2015, 2016, 2017, 2018}
TARGETS = {  # name: (objective, base groups)
    "corners": ("poisson", ["piyasa", "model"]),
    "cards": ("poisson", ["piyasa", "model"]),
    "red_any": ("binary", ["piyasa", "model"]),
    "goals": ("poisson", ["piyasa", "model"]),
    "over25": ("binary", ["piyasa", "model"]),
    "btts": ("binary", ["piyasa", "model"]),
    "result": ("multiclass", ["piyasa", "model"]),
    "ht_goal": ("binary", ["piyasa", "model"]),
}
TR_NAMES = {"corners": "Toplam korner", "cards": "Toplam kart", "red_any": "Kırmızı kart çıkması", "goals": "Toplam gol",
            "over25": "2.5 Üst", "btts": "KG Var", "result": "MS 1X2", "ht_goal": "İlk yarı gol"}
PARAMS = dict(learning_rate=0.06, num_leaves=15, min_data_in_leaf=300, feature_fraction=0.8, bagging_fraction=0.8,
              bagging_freq=1, lambda_l2=10.0, verbose=-1, num_threads=4, seed=7)
ROUNDS = 250


def loss(obj, y, p):
    if obj == "binary":
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    if obj == "multiclass":
        return -np.log(np.clip(p[np.arange(len(y)), y.astype(int)], 1e-9, 1))
    mu = np.clip(p, 1e-6, None)  # Poisson deviance / 2
    return mu - y * np.log(mu) + np.where(y > 0, y * np.log(np.maximum(y, 1)) - y, 0)


def fit_predict(obj, Xtr, ytr, Xte):
    prm = dict(PARAMS, objective=obj)
    if obj == "multiclass":
        prm["num_class"] = 3
    m = lgb.train(prm, lgb.Dataset(Xtr, ytr), ROUNDS)
    return m.predict(Xte), m


def block_ci(diff, dates, n=1000, seed=0):
    s = pd.DataFrame({"d": dates, "x": diff}).groupby("d").x.agg(["sum", "count"])
    a, c = s["sum"].to_numpy(), s["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), (n, len(a)))
    b = a[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    t0 = time.time()
    d = pd.read_pickle("cache/features.pkl")
    X, T, M = d["X"], d["T"], d["meta"]
    X = X.copy()
    X["rest_h"] = X.rest_h.clip(upper=30)
    X["rest_a"] = X.rest_a.clip(upper=30)
    season = M.season.to_numpy()
    feats = {g: [c for c in cols if c in X] for g, cols in GROUPS.items()}
    allf = sorted({c for v in feats.values() for c in v} | {"div_code"})
    ablation, oos_base = [], {}
    shap_rows = []
    for tname, (obj, base_groups) in TARGETS.items():
        y_all = T[tname]
        ok = y_all.notna().to_numpy().copy()
        if tname in ("corners", "cards"):
            ok &= X.dc_corner_h.notna().to_numpy()
        base_cols = sorted({c for g in base_groups for c in feats[g]} | {"div_code"})
        configs = {"base": base_cols}
        for g in feats:
            if g not in base_groups:
                configs[f"+{g}"] = sorted(set(base_cols) | set(feats[g]))
        configs["full"] = allf
        preds = {k: [] for k in configs}
        rows_idx = []
        for f0, f1 in FOLDS:
            tr = ok & (season < f0)
            te = ok & (season >= f0) & (season <= f1)
            if te.sum() == 0 or tr.sum() < 5000:
                continue
            rows_idx.append(np.where(te)[0])
            for k, cols in configs.items():
                p, m = fit_predict(obj, X.loc[tr, cols], y_all[tr], X.loc[te, cols])
                preds[k].append(p)
                if k == "full" and f0 >= 2019:
                    c = m.predict(X.loc[te, cols], pred_contrib=True)
                    if obj == "multiclass":
                        c = c[:, :len(cols) + 1]  # home-win class contributions
                    C = pd.DataFrame(c[:, :-1], columns=cols, index=X.index[te])
                    shap_rows.append((tname, C, X.loc[te, cols]))
        idx = np.concatenate(rows_idx)
        y = y_all.to_numpy()[idx]
        dates = M.date.to_numpy()[idx]
        disc = np.isin(season[idx], list(DISC))
        L = {k: loss(obj, y, np.concatenate(v)) for k, v in preds.items()}
        oos_base[tname] = (idx, np.concatenate(preds["base"]))
        for k in configs:
            if k == "base":
                continue
            diff = L["base"] - L[k]
            for part, msk in (("kesif_2015_18", disc), ("teyit_2019_26", ~disc)):
                lo, hi = block_ci(diff[msk], dates[msk])
                ablation.append({"target": tname, "hedef": TR_NAMES[tname], "piece": k, "period": part,
                                 "n": int(msk.sum()), "gain_pct": 100 * diff[msk].mean() / L["base"][msk].mean(),
                                 "gain": diff[msk].mean(), "ci_lo": lo, "ci_hi": hi})
        print(f"{tname}: done {time.time() - t0:.0f}s", flush=True)

    A = pd.DataFrame(ablation)
    A["verdict"] = np.select([A.ci_lo > 0, A.ci_hi < 0], ["POZİTİF", "NEGATİF"], "etkisiz")
    A.to_csv(f"{R}/ablation.csv", index=False)

    # ---- effect directions (confirmation folds, full model) -----------------
    eff = []
    for tname, C, Xv in shap_rows:
        for c in C.columns:
            x = Xv[c]
            if x.notna().sum() < 500 or x.nunique() < 2:
                continue
            q_hi, q_lo = x.quantile(0.9), x.quantile(0.1)
            hi_m = (x >= q_hi) if x.nunique() > 10 else (x == x.max())
            lo_m = (x <= q_lo) if x.nunique() > 10 else (x == x.min())
            eff.append({"target": tname, "feature": c, "mean_abs": float(C[c].abs().mean()),
                        "contrib_high": float(C.loc[hi_m, c].mean()), "contrib_low": float(C.loc[lo_m, c].mean()),
                        "x_high": float(q_hi), "x_low": float(q_lo)})
    E = pd.DataFrame(eff).groupby(["target", "feature"]).mean().reset_index()
    E.to_csv(f"{R}/effects.csv", index=False)

    # ---- human-readable rules ----------------------------------------------
    rules = rule_mine(X, T, M, oos_base)
    rules.to_csv(f"{R}/rules.csv", index=False)
    print(f"done {time.time() - t0:.0f}s")


def rule_conditions(X):
    c = {
        "Ev sahibi bu rakibe karşı son 3 iç saha maçında yenilmedi": X.h2h_home_unbeaten3 == 1,
        "Ev sahibi 3+ maçtır kazanıyor": X.wstreak_h >= 3,
        "Deplasman 3+ maçtır kaybediyor": X.lstreak_a >= 3,
        "Ev sahibi 8+ maçtır yenilmiyor": X.unbeaten_h >= 8,
        "Deplasman 8+ maçtır yenilmiyor": X.unbeaten_a >= 8,
        "Ev sahibi 3 gün veya daha az dinlendi": X.rest_h <= 3,
        "Deplasman 3 gün veya daha az dinlendi": X.rest_a <= 3,
        "Ev sahibinin en değerli oyuncusu sakat": X.inj_top1_home == 1,
        "Deplasmanın en değerli oyuncusu sakat": X.inj_top1_away == 1,
        "Ev sahibinin kadro değerinin %20+'si sakat": X.inj_value_share_home >= 0.2,
        "Deplasmanın kadro değerinin %20+'si sakat": X.inj_value_share_away >= 0.2,
        "Ev sahibinde ilk 5 değerliden 2+ sakat": X.inj_top5_home >= 2,
        "Sezonun son %15'i": X.late_season == 1,
        "Sezonun ilk 5 haftası": X.round_frac <= 0.13,
        "Lider/ilk 3 vs son 3 (puan tablosu)": (X.pos_h <= 3) & (X.pos_a >= X.pos_a.groupby(X.div_code).transform("max") - 2),
        "Hakemin maç başı kart ortalaması üst %25'te (PL)": X.ref_cards_ewm >= X.ref_cards_ewm.quantile(0.75),
        "Hakemin kırmızı kart oranı üst %25'te (PL)": X.ref_red_rate >= X.ref_red_rate.quantile(0.75),
        "H2H maçlarında ortalama kart üst %25'te": X.h2h_cards >= X.h2h_cards.quantile(0.75),
        "H2H maçlarında ortalama korner üst %25'te": X.h2h_corners >= X.h2h_corners.quantile(0.75),
        "H2H maçlarında ortalama 3.5+ gol": X.h2h_goals >= 3.5,
        "İki takımın da son maçlarda korner ortalaması üst %25'te": (X.co_ewm_h + X.co_ewm_a) >= (X.co_ewm_h + X.co_ewm_a).quantile(0.75),
        "İki takımın da faul ortalaması üst %25'te": (X.fo_ewm_h + X.fo_ewm_a) >= (X.fo_ewm_h + X.fo_ewm_a).quantile(0.75),
        "Ev sahibi son 5 maçta gol yemedi (seri 3+)": X.cs_h >= 3,
        "Deplasman 5+ maçtır gol atıyor": X.scoring_a >= 5,
        "Hafta içi maçı": X.weekday.isin([1, 2, 3]),
        "Akşam maçı (19:00 ve sonrası)": X.hour >= 19,
    }
    # automatic decile rules for every numeric feature
    for col in X.columns:
        if col in ("div_code",) or X[col].nunique() < 15:
            continue
        hi, lo = X[col].quantile(0.9), X[col].quantile(0.1)
        c[f"[oto] {col} üst %10"] = X[col] >= hi
        c[f"[oto] {col} alt %10"] = X[col] <= lo
    return {k: v.fillna(False).to_numpy() for k, v in c.items()}


def rule_mine(X, T, M, oos_base):
    conds = rule_conditions(X)
    season = M.season.to_numpy()
    out = []
    for tname, (idx, pb) in oos_base.items():
        obj = TARGETS[tname][0]
        y = T[tname].to_numpy()[idx]
        if obj == "multiclass":
            outcomes = {"ev sahibi kazanır": (y == 0, pb[:, 0]), "beraberlik": (y == 1, pb[:, 1]), "deplasman kazanır": (y == 2, pb[:, 2])}
        elif obj == "binary":
            outcomes = {"evet": (y == 1, pb)}
        else:
            outcomes = {"ortalama": (y, pb)}
        disc = np.isin(season[idx], list(DISC))
        for rname, cm in conds.items():
            cmask = cm[idx]
            for oname, (yy, pp) in outcomes.items():
                rec = {"target": tname, "hedef": TR_NAMES[tname], "outcome": oname, "rule": rname}
                for part, pm in (("kesif", disc), ("teyit", ~disc)):
                    m = cmask & pm
                    n = int(m.sum())
                    rec[f"n_{part}"] = n
                    if n < 100:
                        rec[f"obs_{part}"] = rec[f"exp_{part}"] = rec[f"p_{part}"] = np.nan
                        continue
                    obs, exp = float(np.mean(yy[m])), float(np.mean(pp[m]))
                    base_rate = float(np.mean(yy[pm]))
                    if obj == "poisson":
                        z = (np.sum(yy[m]) - np.sum(pp[m])) / np.sqrt(np.sum(pp[m]))
                    else:
                        z = (np.sum(yy[m]) - np.sum(pp[m])) / np.sqrt(np.sum(pp[m] * (1 - pp[m])))
                    rec.update({f"obs_{part}": obs, f"exp_{part}": exp, f"raw_{part}": base_rate,
                                f"p_{part}": float(2 * stats.norm.sf(abs(z))), f"z_{part}": float(z)})
                out.append(rec)
    D = pd.DataFrame(out)
    # Benjamini-Hochberg on discovery
    p = D.p_kesif.fillna(1).to_numpy()
    order = np.argsort(p)
    k = np.arange(1, len(p) + 1)
    bh = np.minimum.accumulate((p[order] * len(p) / k)[::-1])[::-1]
    q = np.empty_like(p)
    q[order] = np.minimum(bh, 1)
    D["q_kesif"] = q
    D["survives_discovery"] = D.q_kesif < 0.05
    n_conf = max(1, int(D.survives_discovery.sum()))
    D["confirmed"] = D.survives_discovery & (D.p_teyit < 0.05 / n_conf) & (np.sign(D.z_teyit) == np.sign(D.z_kesif))
    D["raw_lift_teyit_%"] = 100 * (D.obs_teyit / D.raw_teyit - 1)
    D["lift_vs_market_teyit_%"] = 100 * (D.obs_teyit / D.exp_teyit - 1)
    return D


if __name__ == "__main__":
    main()
