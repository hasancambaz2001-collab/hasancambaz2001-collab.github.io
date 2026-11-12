"""Full market sheet for one fixture, using the frozen model.

Examples
  python3 predict.py --div T1 --home Galatasaray --away Fenerbahce
  python3 predict.py --div E0 --home Arsenal --away Chelsea \
      --odds 1=2.10 X=3.50 2=3.60 O2.5=1.85 U2.5=2.00
Passing bookmaker 1X2 / O/U 2.5 odds turns on the market blend (the same
log-linear pool validated in the backtest) and prints EV for offered odds.
"""
import iddaa  # noqa: F401
import argparse
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

from iddaa import markets as mk
from iddaa.backtest import Config
from iddaa.data import COUNTRY, load
from iddaa.evaluate import all_probs, apply_pool, implied_rates
from iddaa.model import fit_counts, half_shares
from iddaa.odds import power, shin

LABELS = {
    "1": "MS 1", "X": "MS X", "2": "MS 2", "1X": "Çifte şans 1X", "12": "Çifte şans 12", "X2": "Çifte şans X2",
    "KG_VAR": "KG Var", "KG_YOK": "KG Yok", "TEK": "Toplam gol Tek", "CIFT": "Toplam gol Çift",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--div", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--date", default=None, help="fit with data before this date (default: today)")
    ap.add_argument("--odds", nargs="*", default=[], help="market=odds pairs, e.g. 1=2.1 O2.5=1.9 KG_VAR=1.8")
    a = ap.parse_args()

    fz = json.load(open("config/frozen_params.json"))
    cfg = Config(**fz["config"])
    df = load()
    ref = pd.Timestamp(a.date) if a.date else pd.Timestamp.today().normalize()
    d = df[df.country == COUNTRY[a.div]]
    teams = set(d.HomeTeam) | set(d.AwayTeam)
    for t in (a.home, a.away):
        if t not in teams:
            close = sorted(x for x in teams if x.lower()[:4] == t.lower()[:4])
            raise SystemExit(f"Takım bulunamadı: {t}. Benzerler: {close}")

    g = fit_counts(d, "FTHome", "FTAway", ref, cfg.xi, cfg.ridge, cfg.window_days,
                   pseudo=("HomeTarget", "AwayTarget", cfg.w_sot), dc=True)
    lh, la, nh, na = g.rates(a.home, a.away, a.div)
    fh, fa = half_shares(d, ref, cfg.xi, cfg.window_days)
    row = {"lh": [lh], "la": [la], "rho": [g.rho], "fh": [fh], "fa": [fa]}
    for pre, hc, ac, xi, rg in (("c", "HomeCorners", "AwayCorners", cfg.c_xi, cfg.c_ridge),
                                ("k", "HomeCards", "AwayCards", cfg.k_xi, cfg.k_ridge)):
        hh = d.dropna(subset=[hc, ac])
        f = fit_counts(hh, hc, ac, ref, xi, rg, cfg.window_days, nb=True)
        r = f.rates(a.home, a.away, a.div)
        row.update({f"{pre}lh": [r[0]], f"{pre}la": [r[1]], f"{pre}disp": [f.disp]})
    P = pd.DataFrame(row)
    p = all_probs(P)

    offered = {k: float(v) for k, v in (s.split("=") for s in a.odds)}
    src = "model"
    if all(k in offered for k in ("1", "X", "2", "O2.5", "U2.5")):
        q3 = shin(np.array([[offered["1"], offered["X"], offered["2"]]]))
        q2 = power(np.array([[offered["O2.5"], offered["U2.5"]]]))
        b3 = apply_pool(np.array([[p["1"][0], p["X"][0], p["2"][0]]]), q3, fz["pool_b365"]["1x2"])
        b2 = apply_pool(np.array([[p["O2.5"][0], p["U2.5"][0]]]), q2, fz["pool_b365"]["ou25"])
        tgt = {"1": b3[:, 0], "X": b3[:, 1], "2": b3[:, 2], "O2.5": b2[:, 0], "U2.5": b2[:, 1]}
        l1, l2 = implied_rates(np.array([lh]), np.array([la]), np.array([g.rho]), tgt)
        p = all_probs(P, l1, l2)
        src = "model+piyasa"
        lh, la = l1[0], l2[0]

    print(f"\n{a.home} - {a.away}  ({a.div}, veri < {ref.date()})   kaynak: {src}")
    print(f"Beklenen gol: {lh:.2f} - {la:.2f}   rho={g.rho:+.3f}   "
          f"veri ağırlığı ev/dep: {nh:.0f}/{na:.0f}" + ("   ⚠ az veri" if min(nh, na) < 10 else ""))
    print(f"Beklenen korner: {row['clh'][0]:.1f} - {row['cla'][0]:.1f}   kart: {row['klh'][0]:.1f} - {row['kla'][0]:.1f}\n")
    print(f"{'Market':28s} {'Olasılık':>9s} {'Adil oran':>9s} {'Teklif':>7s} {'EV':>7s}")
    for k, v in p.items():
        if k.startswith("_"):
            continue
        pr = float(v[0])
        if not np.isfinite(pr):
            continue
        o = offered.get(k)
        ev = f"{pr * o - 1:+.1%}" if o else ""
        print(f"{LABELS.get(k, k):28s} {pr:9.1%} {1 / max(pr, 1e-9):9.2f} {o or '':>7} {ev:>7s}")


if __name__ == "__main__":
    main()
