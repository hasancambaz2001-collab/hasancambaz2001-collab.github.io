"""Walk-forward (blind) backtest engine.

Every Monday the models are refitted using ONLY matches played strictly
before that Monday; the fitted models then predict every match in the
following 7 days. No information from the predicted week ever reaches a fit.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from multiprocessing import Pool

import numpy as np
import pandas as pd

from .model import fit_counts, half_shares


@dataclass
class Config:
    xi: float = 0.0018          # time decay per day (half-life ~ 385 d, Ley et al. 2019)
    ridge: float = 2.0          # L2 prior on team effects
    w_sot: float = 0.0          # weight of shots-on-target pseudo goals
    window_days: int = 1460
    c_xi: float = 0.003         # corners
    c_ridge: float = 2.0
    k_xi: float = 0.003         # cards
    k_ridge: float = 5.0
    side_markets: bool = True   # fit corners/cards/half shares


def _remap(prev_fit, teams_new):
    if prev_fit is None:
        return None
    x = prev_fit.extra["x"]
    n_old = len(prev_fit.teams)
    n = len(teams_new)
    x0 = np.zeros(2 + 2 * n)
    x0[:2] = x[:2]
    for t, i in teams_new.items():
        j = prev_fit.teams.get(t)
        if j is not None:
            x0[2 + i] = x[2 + j]
            x0[2 + n + i] = x[2 + n_old + j]
    return x0


def run_country(args):
    df, country, start, end, cfg = args
    cfg = Config(**cfg)
    d = df[df.country == country]
    targets = d[(d.date >= start) & (d.date < end)]
    if targets.empty:
        return pd.DataFrame()
    first = targets.date.min()
    monday = first - pd.Timedelta(days=first.weekday())
    rows = []
    prev = None
    while monday <= targets.date.max():
        wk = targets[(targets.date >= monday) & (targets.date < monday + pd.Timedelta(days=7))]
        if not wk.empty:
            hist = d[d.date < monday]
            # warm start: fit once quickly to get team set, then remap
            teams_now = sorted(set(hist[hist.date >= monday - pd.Timedelta(days=cfg.window_days)].HomeTeam)
                               | set(hist[hist.date >= monday - pd.Timedelta(days=cfg.window_days)].AwayTeam))
            x0 = _remap(prev, {t: i for i, t in enumerate(teams_now)})
            g = fit_counts(hist, "FTHome", "FTAway", monday, cfg.xi, cfg.ridge, cfg.window_days,
                           pseudo=("HomeTarget", "AwayTarget", cfg.w_sot), dc=True, x0=x0)
            prev = g
            out = {"idx": wk.index.to_numpy()}
            r = [g.rates(h, a, dv) for h, a, dv in zip(wk.HomeTeam, wk.AwayTeam, wk["div"])]
            out["lh"], out["la"], out["nh"], out["na"] = map(np.array, zip(*r))
            out["rho"] = np.full(len(wk), g.rho)
            if cfg.side_markets:
                fh, fa = half_shares(hist, monday, cfg.xi, cfg.window_days)
                out["fh"], out["fa"] = np.full(len(wk), fh), np.full(len(wk), fa)
                for pre, hc, ac, xi, rg in (("c", "HomeCorners", "AwayCorners", cfg.c_xi, cfg.c_ridge),
                                            ("k", "HomeCards", "AwayCards", cfg.k_xi, cfg.k_ridge)):
                    hh = hist.dropna(subset=[hc, ac])
                    hh = hh[hh.date >= monday - pd.Timedelta(days=cfg.window_days)]
                    if len(hh) < 300:
                        for s in ("lh", "la", "disp", "nh", "na"):
                            out[f"{pre}{s}"] = np.full(len(wk), np.nan)
                        continue
                    f = fit_counts(hh, hc, ac, monday, xi, rg, cfg.window_days, nb=True)
                    r = [f.rates(h, a, dv) for h, a, dv in zip(wk.HomeTeam, wk.AwayTeam, wk["div"])]
                    out[f"{pre}lh"], out[f"{pre}la"], out[f"{pre}nh"], out[f"{pre}na"] = map(np.array, zip(*r))
                    out[f"{pre}disp"] = np.full(len(wk), f.disp)
            rows.append(pd.DataFrame(out))
        monday += pd.Timedelta(days=7)
    return pd.concat(rows) if rows else pd.DataFrame()


def walk_forward(df, start, end, cfg: Config, countries=None, procs=4, verbose=True):
    countries = countries or sorted(df.country.unique())
    t0 = time.time()
    jobs = [(df[df.country == c], c, pd.Timestamp(start), pd.Timestamp(end), asdict(cfg)) for c in countries]
    # biggest countries first for better load balance
    jobs.sort(key=lambda j: -(df.country == j[1]).sum())
    with Pool(procs) as pool:
        parts = pool.map(run_country, jobs, chunksize=1)
    pred = pd.concat([p for p in parts if len(p)]).set_index("idx").sort_index()
    if verbose:
        print(f"walk-forward {start}..{end} {len(pred)} matches in {time.time() - t0:.0f}s  cfg={json.dumps(asdict(cfg))}")
    return pred
