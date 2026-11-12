"""Daily live scan: today's fixtures -> fair odds for every market -> signals
from validated strategies -> coupon suggestions -> paper ledger.

  python3 -m live.run_today --date 2026-11-14 --leagues E0 T1 SP1

Needs network access to the two API hosts and their keys (see live/sources.py).
Nothing here places bets; every leg is written to results/paper_ledger.csv
so it can be settled later against the result and the closing price (CLV).
"""
from __future__ import annotations

import iddaa  # noqa: F401
import argparse
import json

import numpy as np
import pandas as pd

from iddaa import markets as mk
from iddaa.backtest import Config
from iddaa.data import COUNTRY, load
from iddaa.evaluate import all_probs, implied_rates
from iddaa.injuries import _sim
from iddaa.model import fit_counts, half_shares
from iddaa.odds import power, shin
from live.coupon import Leg, build_coupons, load_strategies, log_legs
from live.sources import ODDS_SPORTS, OddsAPI, best_prices


def match_team(name, candidates):
    best = max(candidates, key=lambda c: _sim(name, c))
    return best if _sim(name, best) >= 0.5 else None


def scan(date: str, leagues: list[str]):
    fz = json.load(open("config/frozen_params.json"))
    cfg = Config(**fz["config"])
    strategies = load_strategies()
    df = load()
    ref = pd.Timestamp(date)
    oapi = OddsAPI()
    legs, sheets = [], []
    for dv in leagues:
        d = df[df.country == COUNTRY[dv]]
        teams = sorted(set(d[d["div"] == dv].HomeTeam) | set(d[d["div"] == dv].AwayTeam))
        g = fit_counts(d, "FTHome", "FTAway", ref, cfg.xi, cfg.ridge, cfg.window_days,
                       pseudo=("HomeTarget", "AwayTarget", cfg.w_sot), dc=True)
        fh, fa = half_shares(d, ref, cfg.xi, cfg.window_days)
        side = {}
        for pre, hc, ac, xi, rg in (("c", "HomeCorners", "AwayCorners", cfg.c_xi, cfg.c_ridge),
                                    ("k", "HomeCards", "AwayCards", cfg.k_xi, cfg.k_ridge)):
            side[pre] = fit_counts(d.dropna(subset=[hc, ac]), hc, ac, ref, xi, rg, cfg.window_days, nb=True)
        for ev in oapi.odds(ODDS_SPORTS[dv]):
            if not ev["commence_time"].startswith(date):
                continue
            h, a = match_team(ev["home_team"], teams), match_team(ev["away_team"], teams)
            if h is None or a is None:
                continue
            bp = best_prices(ev)
            pin = {k: v["pinnacle"] for k, v in bp.items()}
            o1x2 = [pin.get(("h2h", ev["home_team"], None)), pin.get(("h2h", "Draw", None)), pin.get(("h2h", ev["away_team"], None))]
            oou = [pin.get(("totals", "Over", 2.5)), pin.get(("totals", "Under", 2.5))]
            lh, la, nh, na = g.rates(h, a, dv)
            row = {"lh": [lh], "la": [la], "rho": [g.rho], "fh": [fh], "fa": [fa]}
            for pre, f in side.items():
                r = f.rates(h, a, dv)
                row.update({f"{pre}lh": [r[0]], f"{pre}la": [r[1]], f"{pre}disp": [f.disp]})
            P = pd.DataFrame(row)
            src = "model"
            if all(o1x2) and all(oou):
                q3 = shin(np.array([o1x2]))[0]
                q2 = power(np.array([oou]))[0]
                tgt = {"1": q3[[0]], "X": q3[[1]], "2": q3[[2]], "O2.5": q2[[0]], "U2.5": q2[[1]]}
                lh2, la2 = implied_rates(np.array([lh]), np.array([la]), np.array([g.rho]), tgt)
                p = all_probs(P, lh2, la2)
                src = "Pinnacle-kalibre"
            else:
                p = all_probs(P)
            mid = ev["id"]
            name = f"{h} - {a}"
            sheets.append({"match": name, "src": src, **{k: float(v[0]) for k, v in p.items() if not k.startswith("_")}})
            # H1 consensus gap: best price vs Pinnacle fair
            if all(o1x2):
                fair = shin(np.array([o1x2]))[0]
                for k, lab, nm in ((0, "1", ev["home_team"]), (1, "X", "Draw"), (2, "2", ev["away_team"])):
                    rec = bp.get(("h2h", nm, None))
                    if rec and rec["best"] <= 2.5:
                        st = strategies.get("H1", {})
                        leg = Leg(mid, name, ev["commence_time"], "MS", lab, float(fair[k]), rec["best"], rec["best_book"],
                                  "H1", bool(st.get("approved")), rec["pinnacle"])
                        if leg.ev > st.get("tau", 0.05):
                            legs.append(leg)
    return legs, pd.DataFrame(sheets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--leagues", nargs="+", default=["E0", "SP1", "I1", "D1", "F1", "T1"])
    a = ap.parse_args()
    legs, sheets = scan(a.date, a.leagues)
    sheets.to_csv(f"results/fair_odds_{a.date}.csv", index=False)
    print(f"{len(sheets)} maç fiyatlandı -> results/fair_odds_{a.date}.csv")
    if legs:
        log_legs(legs)
    singles, best_ev, likely = build_coupons(legs)
    print(f"\nSinyal: {len(legs)} (onaylı: {sum(l.approved for l in legs)}) — hepsi kağıt deftere yazıldı")
    for l in legs:
        print(f"  [{'ONAYLI' if l.approved else 'izleme'}] {l.match} {l.market} {l.pick} @ {l.odds} ({l.book}) "
              f"adil p={l.prob:.3f} EV={l.ev:+.1%}")
    if best_ev:
        print(f"\nEn yüksek EV kuponu: oran {best_ev['odds']:.2f}, tutma olasılığı {best_ev['prob']:.1%}, EV {best_ev['ev']:+.1%}")
    if likely:
        print(f"En olası kupon: oran {likely['odds']:.2f}, tutma olasılığı {likely['prob']:.1%}, EV {likely['ev']:+.1%}")
    if not singles:
        print("\nOnaylı strateji yok veya bugün sinyal yok: önerilen kupon YOK.")


if __name__ == "__main__":
    main()
