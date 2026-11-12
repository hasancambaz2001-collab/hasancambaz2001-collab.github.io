"""Team-strength count models.

Goals: Dixon & Coles (1997) with exponential time decay, ridge shrinkage on
team effects (Bayesian-style prior, cf. Baio & Blangiardo 2010; Egidi et al.
2018) and an optional shots-on-target "pseudo-xG" target in the spirit of
Wheatcroft's GAP ratings (2020): strengths are learned from
(1-w)*goals + w*k*shots_on_target, where k = goals per shot on target.

Corners and cards use the same log-linear attack/defence structure with a
negative-binomial dispersion estimated on the training window.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize, minimize_scalar


@dataclass
class TeamFit:
    teams: dict           # team -> index
    mu: float
    home: float
    att: np.ndarray
    dfn: np.ndarray
    n_obs: np.ndarray     # weighted matches per team in window
    rho: float = 0.0
    disp: float = 0.0     # NB overdispersion for totals (Var = m + disp*m^2)
    extra: dict | None = None

    def rates(self, home_team: str, away_team: str, div: str | None = None):
        h = self.teams.get(home_team)
        a = self.teams.get(away_team)
        # Unseen team (e.g. promoted from a league not in the data): use a
        # weak-team prior for that division instead of the pool average.
        pa, pd_ = (self.extra or {}).get("prior", {}).get(div, (0.0, 0.0))
        ah = self.att[h] if h is not None else pa
        dh = self.dfn[h] if h is not None else pd_
        aa = self.att[a] if a is not None else pa
        da = self.dfn[a] if a is not None else pd_
        lh = np.exp(self.mu + self.home + ah + da)
        la = np.exp(self.mu + aa + dh)
        nh = self.n_obs[h] if h is not None else 0.0
        na = self.n_obs[a] if a is not None else 0.0
        return lh, la, nh, na


def _fit_poisson(hi, ai, yh, ya, w, n, ridge, x0=None):
    def f(p):
        mu, ha, att, dfn = p[0], p[1], p[2:2 + n], p[2 + n:]
        eh = mu + ha + att[hi] + dfn[ai]
        ea = mu + att[ai] + dfn[hi]
        lh, la = np.exp(eh), np.exp(ea)
        nll = np.sum(w * (lh - yh * eh)) + np.sum(w * (la - ya * ea))
        nll += 0.5 * ridge * (att @ att + dfn @ dfn)
        rh, ra = w * (lh - yh), w * (la - ya)
        g = np.empty_like(p)
        g[0] = rh.sum() + ra.sum()
        g[1] = rh.sum()
        g[2:2 + n] = np.bincount(hi, rh, n) + np.bincount(ai, ra, n) + ridge * att
        g[2 + n:] = np.bincount(ai, rh, n) + np.bincount(hi, ra, n) + ridge * dfn
        return nll, g

    if x0 is None or len(x0) != 2 + 2 * n:
        x0 = np.zeros(2 + 2 * n)
        x0[0] = np.log(max(np.average(np.r_[yh, ya], weights=np.r_[w, w]), 1e-3))
    r = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
    return r.x


def _dc_tau_loglik(rho, x, y, lh, la, w):
    t = np.ones_like(lh)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t[m00] = 1 - lh[m00] * la[m00] * rho
    t[m01] = 1 + lh[m01] * rho
    t[m10] = 1 + la[m10] * rho
    t[m11] = 1 - rho
    if np.any(t <= 0):
        return 1e12
    return -np.sum(w * np.log(t))


def fit_counts(df, home_col, away_col, ref_date, xi, ridge, window_days=4 * 365,
               pseudo=None, dc=False, nb=False, x0=None):
    """Fit attack/defence model on matches strictly before ref_date.

    pseudo: optional (home_aux_col, away_aux_col, weight) to blend an auxiliary
    count (shots on target) into the target, rescaled to the goal scale.
    """
    m = df[(df.date < ref_date) & (df.date >= ref_date - np.timedelta64(window_days, "D"))]
    m = m.dropna(subset=[home_col, away_col])
    yh = m[home_col].to_numpy(float)
    ya = m[away_col].to_numpy(float)
    gh, ga = yh.copy(), ya.copy()
    age = (ref_date - m.date).dt.days.to_numpy(float)
    w = np.exp(-xi * age)

    if pseudo is not None and pseudo[2] > 0:
        hc, ac, wt = pseudo
        ok = m[hc].notna().to_numpy() & m[ac].notna().to_numpy()
        if ok.sum() > 50:
            sh, sa = m[hc].to_numpy(float), m[ac].to_numpy(float)
            k = (np.sum(w[ok] * (yh[ok] + ya[ok])) / np.sum(w[ok] * (sh[ok] + sa[ok])))
            yh = np.where(ok, (1 - wt) * yh + wt * k * np.nan_to_num(sh), yh)
            ya = np.where(ok, (1 - wt) * ya + wt * k * np.nan_to_num(sa), ya)

    teams = {t: i for i, t in enumerate(sorted(set(m.HomeTeam) | set(m.AwayTeam)))}
    n = len(teams)
    hi = m.HomeTeam.map(teams).to_numpy()
    ai = m.AwayTeam.map(teams).to_numpy()
    p = _fit_poisson(hi, ai, yh, ya, w, n, ridge, x0)
    mu, ha, att, dfn = p[0], p[1], p[2:2 + n], p[2 + n:]
    n_obs = np.bincount(hi, w, n) + np.bincount(ai, w, n)
    # Division priors for unseen teams: 25th pct attack / 75th pct defence of
    # teams that played in that division in the last year of the window.
    prior = {}
    recent = m[m.date >= ref_date - np.timedelta64(365, "D")]
    for dv, g in recent.groupby("div"):
        idx = np.unique(np.r_[g.HomeTeam.map(teams).to_numpy(), g.AwayTeam.map(teams).to_numpy()])
        prior[dv] = (float(np.percentile(att[idx], 25)), float(np.percentile(dfn[idx], 75)))
    fit = TeamFit(teams, mu, ha, att, dfn, n_obs, extra={"x": p, "prior": prior})

    lh = np.exp(mu + ha + att[hi] + dfn[ai])
    la = np.exp(mu + att[ai] + dfn[hi])
    if dc:
        r = minimize_scalar(_dc_tau_loglik, bounds=(-0.25, 0.25), method="bounded",
                            args=(gh, ga, lh, la, w))
        fit.rho = float(r.x)
    if nb:
        # method-of-moments overdispersion on match totals
        mt = lh + la
        yt = gh + ga
        fit.disp = float(max(0.0, np.sum(w * ((yt - mt) ** 2 - mt)) / np.sum(w * mt ** 2)))
    return fit


def half_shares(df, ref_date, xi, window_days=4 * 365):
    """Weighted share of goals scored in the first half, home and away."""
    m = df[(df.date < ref_date) & (df.date >= ref_date - np.timedelta64(window_days, "D"))]
    m = m.dropna(subset=["HTHome", "HTAway"])
    if len(m) < 100:
        return 0.44, 0.44
    w = np.exp(-xi * (ref_date - m.date).dt.days.to_numpy(float))
    fh = np.sum(w * m.HTHome) / max(np.sum(w * m.FTHome), 1e-9)
    fa = np.sum(w * m.HTAway) / max(np.sum(w * m.FTAway), 1e-9)
    return float(fh), float(fa)
