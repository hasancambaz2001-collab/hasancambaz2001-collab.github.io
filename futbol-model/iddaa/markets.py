"""Turn model rates into probabilities for every common betting market.

All functions are vectorised over N matches.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import nbinom, poisson

G = 11  # goals 0..10 per team


def pois_pmf(lam, k=G):
    ks = np.arange(k)
    return poisson.pmf(ks[None, :], np.asarray(lam)[:, None])


def count_pmf(mean, disp, k=40):
    """Poisson (disp=0) or negative binomial with Var = m + disp*m^2."""
    mean = np.asarray(mean, float)
    disp = np.broadcast_to(np.asarray(disp, float), mean.shape)
    ks = np.arange(k)[None, :]
    out = poisson.pmf(ks, mean[:, None])
    nbm = disp > 1e-6
    if nbm.any():
        r = 1.0 / disp[nbm]
        p = r / (r + mean[nbm])
        out[nbm] = nbinom.pmf(ks, r[:, None], p[:, None])
    return out


def score_matrix(lh, la, rho):
    ph, pa = pois_pmf(lh), pois_pmf(la)
    M = ph[:, :, None] * pa[:, None, :]
    lh, la, rho = map(lambda v: np.asarray(v, float), (lh, la, np.broadcast_to(rho, np.shape(lh))))
    M[:, 0, 0] *= 1 - lh * la * rho
    M[:, 0, 1] *= 1 + lh * rho
    M[:, 1, 0] *= 1 + la * rho
    M[:, 1, 1] *= 1 - rho
    M = np.clip(M, 0, None)
    return M / M.sum(axis=(1, 2), keepdims=True)


_I, _J = np.meshgrid(np.arange(G), np.arange(G), indexing="ij")
_TOT = _I + _J
_DIFF = _I - _J


def _sum(M, mask):
    return (M * mask[None]).sum(axis=(1, 2))


def diff_pmf(M):
    """P(home - away = d) for d in -(G-1)..(G-1)."""
    out = np.zeros((M.shape[0], 2 * G - 1))
    for d in range(-(G - 1), G):
        out[:, d + G - 1] = _sum(M, _DIFF == d)
    return out


def ft_markets(M):
    p = {}
    p["1"], p["X"], p["2"] = _sum(M, _DIFF > 0), _sum(M, _DIFF == 0), _sum(M, _DIFF < 0)
    p["1X"], p["12"], p["X2"] = p["1"] + p["X"], p["1"] + p["2"], p["X"] + p["2"]
    p["DNB1"] = p["1"] / (p["1"] + p["2"])
    for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        p[f"U{L}"] = _sum(M, _TOT < L)
        p[f"O{L}"] = 1 - p[f"U{L}"]
    p["KG_VAR"] = _sum(M, (_I > 0) & (_J > 0))
    p["KG_YOK"] = 1 - p["KG_VAR"]
    for a, b, name in ((0, 1, "TG0-1"), (2, 3, "TG2-3"), (4, 5, "TG4-5"), (6, 99, "TG6+")):
        p[name] = _sum(M, (_TOT >= a) & (_TOT <= b))
    p["TEK"] = _sum(M, _TOT % 2 == 1)
    p["CIFT"] = 1 - p["TEK"]
    for L in (0.5, 1.5, 2.5):
        p[f"EV_O{L}"] = _sum(M, _I > L)
        p[f"DEP_O{L}"] = _sum(M, _J > L)
    p["EV_CS"] = _sum(M, _J == 0)   # home clean sheet
    p["DEP_CS"] = _sum(M, _I == 0)
    p["EV_WTN"] = _sum(M, (_DIFF > 0) & (_J == 0))
    p["DEP_WTN"] = _sum(M, (_DIFF < 0) & (_I == 0))
    # MS + Alt/Üst 2.5 combos
    for r, rm in (("1", _DIFF > 0), ("X", _DIFF == 0), ("2", _DIFF < 0)):
        p[f"{r}&O2.5"] = _sum(M, rm & (_TOT > 2.5))
        p[f"{r}&U2.5"] = _sum(M, rm & (_TOT < 2.5))
    p["KG&O2.5"] = _sum(M, (_I > 0) & (_J > 0) & (_TOT > 2.5))
    # European (3-way) handicap, applied to home goals
    for h in (-2, -1, 1, 2):
        d = _DIFF + h
        p[f"HND{h:+d}_1"], p[f"HND{h:+d}_X"], p[f"HND{h:+d}_2"] = _sum(M, d > 0), _sum(M, d == 0), _sum(M, d < 0)
    # Correct score (0..5 x 0..5 + "other")
    for i in range(6):
        for j in range(6):
            p[f"CS{i}-{j}"] = M[:, i, j]
    p["CS_OTHER"] = 1 - M[:, :6, :6].sum(axis=(1, 2))
    return p


def half_markets(lh, la, fh, fa, ft):
    """First half / second half / HT-FT from independent Poisson halves."""
    l1h, l1a = lh * fh, la * fa
    l2h, l2a = lh * (1 - fh), la * (1 - fa)
    H1 = score_matrix(l1h, l1a, 0.0)
    H2 = score_matrix(l2h, l2a, 0.0)
    p = {}
    p["IY1"], p["IYX"], p["IY2"] = _sum(H1, _DIFF > 0), _sum(H1, _DIFF == 0), _sum(H1, _DIFF < 0)
    for L in (0.5, 1.5, 2.5):
        p[f"IY_O{L}"] = _sum(H1, _TOT > L)
        p[f"IY_U{L}"] = 1 - p[f"IY_O{L}"]
    p["IY_KG_VAR"] = _sum(H1, (_I > 0) & (_J > 0))
    p["2Y1"], p["2YX"], p["2Y2"] = _sum(H2, _DIFF > 0), _sum(H2, _DIFF == 0), _sum(H2, _DIFF < 0)
    # More goals in which half
    t1 = np.stack([_sum(H1, _TOT == k) for k in range(2 * G - 1)], 1)
    t2 = np.stack([_sum(H2, _TOT == k) for k in range(2 * G - 1)], 1)
    c2 = np.cumsum(t2, 1)
    p["YARI_1"] = sum(t1[:, k] * (c2[:, k - 1] if k > 0 else 0) for k in range(2 * G - 1))
    p["YARI_X"] = (t1 * t2).sum(1)
    p["YARI_2"] = 1 - p["YARI_1"] - p["YARI_X"]
    # HT/FT
    d1, d2 = diff_pmf(H1), diff_pmf(H2)
    c = np.cumsum(d2, 1)  # P(d2 <= k-(G-1))
    off = G - 1
    def p_ft_given(d):  # returns P(FT>0), P(FT=0), P(FT<0) given HT diff d
        # FT diff = d + d2 ; >0 <=> d2 > -d
        idx_le = -d + off            # index of d2 == -d
        le = c[:, idx_le] if 0 <= idx_le < c.shape[1] else (np.ones(len(c)) if idx_le >= c.shape[1] else np.zeros(len(c)))
        lt = c[:, idx_le - 1] if 0 <= idx_le - 1 < c.shape[1] else (np.ones(len(c)) if idx_le - 1 >= c.shape[1] else np.zeros(len(c)))
        return 1 - le, le - lt, lt
    htft = {k: np.zeros(len(lh)) for k in ("1/1", "1/X", "1/2", "X/1", "X/X", "X/2", "2/1", "2/X", "2/2")}
    for d in range(-off, off + 1):
        w = d1[:, d + off]
        a, b, cc = p_ft_given(d)
        r = "1" if d > 0 else ("X" if d == 0 else "2")
        htft[f"{r}/1"] += w * a
        htft[f"{r}/X"] += w * b
        htft[f"{r}/2"] += w * cc
    # rescale so FT margins match the Dixon-Coles FT matrix
    for r2 in ("1", "X", "2"):
        s = htft[f"1/{r2}"] + htft[f"X/{r2}"] + htft[f"2/{r2}"]
        for r1 in ("1", "X", "2"):
            htft[f"{r1}/{r2}"] = htft[f"{r1}/{r2}"] * ft[r2] / np.maximum(s, 1e-12)
    p.update({f"IYMS_{k}": v for k, v in htft.items()})
    return p


def count_markets(prefix, lh, la, disp, lines):
    """Totals (NB) and 1X2 ("who gets more") for corners / cards."""
    tot = count_pmf(lh + la, disp)
    c = np.cumsum(tot, 1)
    p = {}
    for L in lines:
        p[f"{prefix}_U{L}"] = c[:, int(np.floor(L))]
        p[f"{prefix}_O{L}"] = 1 - p[f"{prefix}_U{L}"]
    # per-team split with same dispersion scaled
    ph, pa = count_pmf(lh, disp, 30), count_pmf(la, disp, 30)
    M = ph[:, :, None] * pa[:, None, :]
    I, J = np.meshgrid(np.arange(30), np.arange(30), indexing="ij")
    p[f"{prefix}_1"] = (M * (I > J)[None]).sum((1, 2))
    p[f"{prefix}_X"] = (M * (I == J)[None]).sum((1, 2))
    p[f"{prefix}_2"] = (M * (I < J)[None]).sum((1, 2))
    return p


def ah_expected_profit(dpmf, line, odds):
    """Expected profit per 1 unit staked on HOME at Asian handicap `line`
    (line applied to home goals); quarter lines split the stake."""
    off = G - 1
    ds = np.arange(-off, off + 1)
    lines = [line] if abs(line * 4) % 2 == 0 else [line - 0.25, line + 0.25]
    ev = 0.0
    for L in lines:
        adj = ds[None, :] + L
        win = (dpmf * (adj > 0)).sum(1)
        lose = (dpmf * (adj < 0)).sum(1)
        ev = ev + 0.5 ** (len(lines) - 1) * (win * (odds - 1) - lose)
    return ev


def ah_profit_realised(diff, line, odds):
    """Realised profit for 1 unit on HOME given actual goal difference
    (vectorised over matches; quarter lines split the stake)."""
    diff, line, odds = (np.asarray(x, float) for x in (diff, line, odds))

    def one(L):
        adj = diff + L
        return np.where(adj > 0, odds - 1, np.where(adj < 0, -1.0, 0.0))

    quarter = np.abs(line * 4) % 2 == 1
    return np.where(quarter, 0.5 * one(line - 0.25) + 0.5 * one(line + 0.25), one(line))
