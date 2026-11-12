"""Scoring, market blending and betting simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import markets as mk
from .odds import power, shin

EPS = 1e-12


# ----------------------------------------------------------------------------
# probabilities for every market
# ----------------------------------------------------------------------------
def all_probs(P: pd.DataFrame, lh=None, la=None, chunk=20000) -> dict:
    lh = P.lh.to_numpy() if lh is None else lh
    la = P.la.to_numpy() if la is None else la
    rho = P.rho.to_numpy()
    out: dict = {}
    for s in range(0, len(P), chunk):
        sl = slice(s, s + chunk)
        M = mk.score_matrix(lh[sl], la[sl], rho[sl])
        p = mk.ft_markets(M)
        p["_dpmf"] = mk.diff_pmf(M)
        if "fh" in P:
            fh, fa = P.fh.to_numpy()[sl], P.fa.to_numpy()[sl]
            p.update(mk.half_markets(lh[sl], la[sl], fh, fa, p))
        for pre, lines in (("KOR", (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)), ("KART", (2.5, 3.5, 4.5, 5.5, 6.5))):
            c = "c" if pre == "KOR" else "k"
            if f"{c}lh" in P:
                a, b, d = (P[f"{c}lh"].to_numpy()[sl], P[f"{c}la"].to_numpy()[sl], P[f"{c}disp"].to_numpy()[sl])
                ok = np.isfinite(a)
                q = mk.count_markets(pre, np.where(ok, a, 1), np.where(ok, b, 1), np.where(ok, d, 0), lines)
                p.update({k: np.where(ok, v, np.nan) for k, v in q.items()})
        for k, v in p.items():
            out.setdefault(k, []).append(v)
    return {k: np.concatenate(v) for k, v in out.items()}


def outcomes(D: pd.DataFrame) -> dict:
    h, a = D.FTHome.to_numpy(), D.FTAway.to_numpy()
    t, d = h + a, h - a
    o = {"1": d > 0, "X": d == 0, "2": d < 0}
    for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        o[f"O{L}"], o[f"U{L}"] = t > L, t < L
    o["KG_VAR"] = (h > 0) & (a > 0)
    o["KG_YOK"] = ~o["KG_VAR"]
    o.update({"TG0-1": t <= 1, "TG2-3": (t >= 2) & (t <= 3), "TG4-5": (t >= 4) & (t <= 5), "TG6+": t >= 6})
    o["TEK"], o["CIFT"] = t % 2 == 1, t % 2 == 0
    for L in (0.5, 1.5, 2.5):
        o[f"EV_O{L}"], o[f"DEP_O{L}"] = h > L, a > L
    for r, rm in (("1", d > 0), ("X", d == 0), ("2", d < 0)):
        o[f"{r}&O2.5"], o[f"{r}&U2.5"] = rm & (t > 2.5), rm & (t < 2.5)
    for hh in (-2, -1, 1, 2):
        o[f"HND{hh:+d}_1"], o[f"HND{hh:+d}_X"], o[f"HND{hh:+d}_2"] = d + hh > 0, d + hh == 0, d + hh < 0
    for i in range(6):
        for j in range(6):
            o[f"CS{i}-{j}"] = (h == i) & (a == j)
    o["CS_OTHER"] = (h > 5) | (a > 5)
    o = {k: v.astype(float) for k, v in o.items()}
    hh, ha = D.HTHome.to_numpy(), D.HTAway.to_numpy()
    okh = np.isfinite(hh) & np.isfinite(ha)
    def m(x, ok=okh):
        return np.where(ok, x.astype(float), np.nan)
    d1, t1 = hh - ha, hh + ha
    d2, t2 = d - d1, t - t1
    o.update({"IY1": m(d1 > 0), "IYX": m(d1 == 0), "IY2": m(d1 < 0)})
    for L in (0.5, 1.5, 2.5):
        o[f"IY_O{L}"], o[f"IY_U{L}"] = m(t1 > L), m(t1 < L)
    o["2Y1"], o["2YX"], o["2Y2"] = m(d2 > 0), m(d2 == 0), m(d2 < 0)
    o["YARI_1"], o["YARI_X"], o["YARI_2"] = m(t1 > t2), m(t1 == t2), m(t1 < t2)
    for r1, c1 in (("1", d1 > 0), ("X", d1 == 0), ("2", d1 < 0)):
        for r2, c2 in (("1", d > 0), ("X", d == 0), ("2", d < 0)):
            o[f"IYMS_{r1}/{r2}"] = m(c1 & c2)
    for pre, hc, ac, lines in (("KOR", "HomeCorners", "AwayCorners", (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)),
                               ("KART", "HomeCards", "AwayCards", (2.5, 3.5, 4.5, 5.5, 6.5))):
        x, y = D[hc].to_numpy(float), D[ac].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        for L in lines:
            o[f"{pre}_O{L}"], o[f"{pre}_U{L}"] = m(x + y > L, ok), m(x + y < L, ok)
        o[f"{pre}_1"], o[f"{pre}_X"], o[f"{pre}_2"] = m(x > y, ok), m(x == y, ok), m(x < y, ok)
    return o


GROUPS = {
    "MS 1X2": ["1", "X", "2"],
    **{f"Alt/Üst {L}": [f"O{L}", f"U{L}"] for L in (0.5, 1.5, 2.5, 3.5, 4.5)},
    "KG Var/Yok": ["KG_VAR", "KG_YOK"],
    "Toplam gol aralığı": ["TG0-1", "TG2-3", "TG4-5", "TG6+"],
    "Tek/Çift": ["TEK", "CIFT"],
    "Ev sahibi 1.5 Üst": ["EV_O1.5", "_EV_U1.5"],
    "Deplasman 1.5 Üst": ["DEP_O1.5", "_DEP_U1.5"],
    "MS + A/Ü 2.5": ["1&O2.5", "1&U2.5", "X&O2.5", "X&U2.5", "2&O2.5", "2&U2.5"],
    "Handikaplı MS (-1)": ["HND-1_1", "HND-1_X", "HND-1_2"],
    "Doğru skor": [f"CS{i}-{j}" for i in range(6) for j in range(6)] + ["CS_OTHER"],
    "İY 1X2": ["IY1", "IYX", "IY2"],
    "İY Alt/Üst 0.5": ["IY_O0.5", "IY_U0.5"],
    "İY Alt/Üst 1.5": ["IY_O1.5", "IY_U1.5"],
    "2Y 1X2": ["2Y1", "2YX", "2Y2"],
    "Daha çok gol olan yarı": ["YARI_1", "YARI_X", "YARI_2"],
    "İY/MS": [f"IYMS_{a}/{b}" for a in "1X2" for b in "1X2"],
    "Korner A/Ü 9.5": ["KOR_O9.5", "KOR_U9.5"],
    "Korner A/Ü 10.5": ["KOR_O10.5", "KOR_U10.5"],
    "Korner 1X2": ["KOR_1", "KOR_X", "KOR_2"],
    "Kart A/Ü 3.5": ["KART_O3.5", "KART_U3.5"],
    "Kart A/Ü 4.5": ["KART_O4.5", "KART_U4.5"],
    "Kart 1X2": ["KART_1", "KART_X", "KART_2"],
}


def _complete(p: dict, o: dict):
    for side in ("EV", "DEP"):
        p[f"_{side}_U1.5"] = 1 - p[f"{side}_O1.5"]
        o[f"_{side}_U1.5"] = 1 - o[f"{side}_O1.5"]


def group_matrix(d: dict, keys):
    return np.stack([d[k] for k in keys], 1)


def logloss(P, O):
    ok = np.isfinite(O).all(1) & np.isfinite(P).all(1)
    p = np.clip((P[ok] * O[ok]).sum(1), EPS, 1)
    return -np.log(p).mean(), ok.sum()


def brier(P, O):
    ok = np.isfinite(O).all(1) & np.isfinite(P).all(1)
    return ((P[ok] - O[ok]) ** 2).sum(1).mean()


def rps(P, O):
    ok = np.isfinite(O).all(1) & np.isfinite(P).all(1)
    cp, co = np.cumsum(P[ok], 1)[:, :-1], np.cumsum(O[ok], 1)[:, :-1]
    return ((cp - co) ** 2).sum(1).mean() / (P.shape[1] - 1)


def climatology(D_all: pd.DataFrame, D_eval: pd.DataFrame, before, years=3) -> dict:
    """Per-division outcome frequencies from `years` seasons before `before`."""
    ref = D_all[(D_all.date < before) & (D_all.date >= pd.Timestamp(before) - pd.Timedelta(days=365 * years))]
    o_ref = outcomes(ref)
    _complete({"EV_O1.5": 0, "DEP_O1.5": 0}, o_ref)
    freq = pd.DataFrame(o_ref, index=ref.index).groupby(ref["div"].to_numpy()).mean()
    return {k: freq[k].reindex(D_eval["div"]).to_numpy() for k in freq.columns}


# ----------------------------------------------------------------------------
# market probabilities and blending
# ----------------------------------------------------------------------------
def market_probs(D: pd.DataFrame, book="b365") -> dict:
    c = {"b365": (["OddHome", "OddDraw", "OddAway"], ["Over25", "Under25"]),
         "max": (["MaxHome", "MaxDraw", "MaxAway"], ["MaxOver25", "MaxUnder25"])}[book]
    p1x2 = shin(D[c[0]].to_numpy(float))
    pou = power(D[c[1]].to_numpy(float))
    return {"1": p1x2[:, 0], "X": p1x2[:, 1], "2": p1x2[:, 2], "O2.5": pou[:, 0], "U2.5": pou[:, 1]}


def fit_pool(Pm, Pk, O):
    """Log-linear pool p ∝ Pm^a * Pk^b, fitted by max likelihood."""
    ok = np.isfinite(Pm).all(1) & np.isfinite(Pk).all(1) & np.isfinite(O).all(1)
    lm, lk, Oo = np.log(np.clip(Pm[ok], EPS, 1)), np.log(np.clip(Pk[ok], EPS, 1)), O[ok]

    def nll(ab):
        z = ab[0] * lm + ab[1] * lk
        z -= z.max(1, keepdims=True)
        lp = z - np.log(np.exp(z).sum(1, keepdims=True))
        return -(lp * Oo).sum(1).mean()

    r = minimize(nll, [0.5, 0.5], method="Nelder-Mead")
    return r.x


def apply_pool(Pm, Pk, ab):
    z = ab[0] * np.log(np.clip(Pm, EPS, 1)) + ab[1] * np.log(np.clip(Pk, EPS, 1))
    z -= np.nanmax(z, 1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def implied_rates(lh, la, rho, target):
    """Adjust (lh, la) so the DC model reproduces target 1X2 + O2.5 probs
    (vectorised Gauss-Newton on log rates). Rows w/o target keep model rates."""
    tgt = np.stack([target["1"], target["X"], target["2"], target["O2.5"]], 1)
    ok = np.isfinite(tgt).all(1)
    x = np.log(np.stack([lh, la], 1)).copy()

    def f(xx, idx):
        M = mk.score_matrix(np.exp(xx[:, 0]), np.exp(xx[:, 1]), rho[idx])
        p = mk.ft_markets(M)
        return np.stack([p["1"], p["X"], p["2"], p["O2.5"]], 1)

    idx = np.where(ok)[0]
    for _ in range(8):
        xx = x[idx]
        r = f(xx, idx) - tgt[idx]
        J = np.zeros((len(idx), 4, 2))
        for k in range(2):
            e = np.zeros(2); e[k] = 1e-4
            J[:, :, k] = (f(xx + e, idx) - f(xx, idx)) / 1e-4
        JT = np.transpose(J, (0, 2, 1))
        A = JT @ J + 1e-6 * np.eye(2)
        step = np.linalg.solve(A, (JT @ r[:, :, None]))[:, :, 0]
        x[idx] = xx - np.clip(step, -0.5, 0.5)
    return np.exp(x[:, 0]), np.exp(x[:, 1])


# ----------------------------------------------------------------------------
# betting simulation
# ----------------------------------------------------------------------------
def bets_1x2(p, D, cols, tau, omax, min_n=None):
    O = D[cols].to_numpy(float)
    P = np.stack([p["1"], p["X"], p["2"]], 1)
    ev = P * O - 1
    ev[~np.isfinite(ev)] = -9
    k = ev.argmax(1)
    e = ev[np.arange(len(k)), k]
    o = O[np.arange(len(k)), k]
    pr = P[np.arange(len(k)), k]
    res = np.stack([(D.FTHome > D.FTAway).to_numpy(), (D.FTHome == D.FTAway).to_numpy(), (D.FTHome < D.FTAway).to_numpy()], 1)
    won = res[np.arange(len(k)), k]
    sel = (e > tau) & (o <= omax)
    if min_n is not None:
        sel &= min_n
    profit = np.where(won, o - 1, -1.0)
    return pd.DataFrame({"date": D.date.to_numpy(), "div": D["div"].to_numpy(), "market": "MS 1X2",
                         "pick": np.array(["1", "X", "2"])[k], "odds": o, "p": pr, "ev": e,
                         "profit": profit}, index=D.index)[sel]


def bets_ou(p, D, cols, tau, omax, min_n=None):
    O = D[cols].to_numpy(float)
    P = np.stack([p["O2.5"], p["U2.5"]], 1)
    ev = P * O - 1
    ev[~np.isfinite(ev)] = -9
    k = ev.argmax(1)
    e, o, pr = ev[np.arange(len(k)), k], O[np.arange(len(k)), k], P[np.arange(len(k)), k]
    t = (D.FTHome + D.FTAway).to_numpy()
    won = np.where(k == 0, t > 2.5, t < 2.5)
    sel = (e > tau) & (o <= omax)
    if min_n is not None:
        sel &= min_n
    return pd.DataFrame({"date": D.date.to_numpy(), "div": D["div"].to_numpy(), "market": "Alt/Üst 2.5",
                         "pick": np.array(["Üst", "Alt"])[k], "odds": o, "p": pr, "ev": e,
                         "profit": np.where(won, o - 1, -1.0)}, index=D.index)[sel]


def bets_ah(dpmf, D, tau, omax, min_n=None):
    line = D.AHLine.to_numpy(float)
    oh, oa = D.HandiHome.to_numpy(float), D.HandiAway.to_numpy(float)
    ok = np.isfinite(line) & np.isfinite(oh) & np.isfinite(oa)
    evh = np.full(len(D), -9.0)
    eva = np.full(len(D), -9.0)
    for L in np.unique(line[ok]):
        m = ok & (line == L)
        evh[m] = mk.ah_expected_profit(dpmf[m], L, oh[m])
        # away at +(-L) == mirror: away profit uses reversed diff pmf
        eva[m] = mk.ah_expected_profit(dpmf[m][:, ::-1], -L, oa[m])
    home = evh >= eva
    e = np.where(home, evh, eva)
    o = np.where(home, oh, oa)
    diff = (D.FTHome - D.FTAway).to_numpy()
    prof = np.where(home, mk.ah_profit_realised(diff, line, oh), mk.ah_profit_realised(-diff, -line, oa))
    sel = ok & (e > tau) & (o <= omax)
    if min_n is not None:
        sel &= min_n
    return pd.DataFrame({"date": D.date.to_numpy(), "div": D["div"].to_numpy(), "market": "Asya Handikap",
                         "pick": np.where(home, "Ev " + pd.Series(line).map(lambda x: f"{x:+.2f}").to_numpy(),
                                          "Dep " + pd.Series(-line).map(lambda x: f"{x:+.2f}").to_numpy()),
                         "odds": o, "p": np.nan, "ev": e, "profit": prof}, index=D.index)[sel]


def summarize_bets(B: pd.DataFrame, n_boot=2000, seed=0) -> dict:
    if len(B) == 0:
        return {"bets": 0}
    rng = np.random.default_rng(seed)
    pr = B.profit.to_numpy()
    boots = rng.choice(pr, (n_boot, len(pr))).mean(1)
    cum = np.cumsum(pr)
    dd = (np.maximum.accumulate(cum) - cum).max()
    return {"bets": int(len(B)), "roi": float(pr.mean()), "profit_u": float(pr.sum()),
            "ci_lo": float(np.percentile(boots, 2.5)), "ci_hi": float(np.percentile(boots, 97.5)),
            "p_val": float((boots <= 0).mean()), "avg_odds": float(B.odds.mean()),
            "hit": float((pr > 0).mean()), "max_dd_u": float(dd)}


def kelly_path(B: pd.DataFrame, frac=0.25, cap=0.025):
    """Fractional Kelly bankroll path; bets on the same day share the bankroll."""
    bank = 1.0
    path = []
    for day, g in B.sort_values("date").groupby("date"):
        b = g.odds.to_numpy() - 1
        f = np.clip(frac * g.ev.to_numpy() / b, 0, cap)
        if f.sum() > 0.25:
            f *= 0.25 / f.sum()
        stake = f * bank
        bank += (stake * g.profit.to_numpy()).sum()
        path.append((day, bank))
    return pd.DataFrame(path, columns=["date", "bank"])
