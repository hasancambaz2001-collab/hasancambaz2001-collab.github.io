"""Settle the paper ledger: result from API-Football, closing price = the last
Pinnacle price this system logged for the same match and pick before kickoff
(run live.run_today again ~30 min before kickoff to capture it).

  python3 -m live.settle
Prints ROI and average CLV per strategy. CLV = taken odds / closing odds - 1.
"""
import iddaa  # noqa: F401

import pandas as pd

from iddaa.injuries import _sim
from live.coupon import LEDGER
from live.sources import APIFootball


def main():
    L = pd.read_csv(LEDGER)
    af = APIFootball()
    L["kickoff"] = pd.to_datetime(L.kickoff, utc=True)
    L["logged_at"] = pd.to_datetime(L.logged_at, utc=True)
    pre = L[L.logged_at < L.kickoff]
    close = pre.sort_values("logged_at").groupby(["match_id", "market", "pick"]).pinnacle.last()
    L["closing_odds"] = [close.get((m, mk, p)) for m, mk, p in zip(L.match_id, L.market, L.pick)]
    first = L.sort_values("logged_at").drop_duplicates(["match_id", "market", "pick", "strategy"])
    cache = {}
    for i, r in first.iterrows():
        if pd.notna(r.result) and r.result != "":
            continue
        if r.kickoff > pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=3):
            continue
        day = r.kickoff.strftime("%Y-%m-%d")
        if day not in cache:
            cache[day] = af._q("fixtures", date=day)
        h, a = r.match.split(" - ")
        fx = next((f for f in cache[day] if _sim(f["teams"]["home"]["name"], h) >= 0.5 and _sim(f["teams"]["away"]["name"], a) >= 0.5
                   and f["fixture"]["status"]["short"] in ("FT", "AET", "PEN")), None)
        if fx is None:
            continue
        gh, ga = fx["goals"]["home"], fx["goals"]["away"]
        res = "1" if gh > ga else ("X" if gh == ga else "2")
        first.loc[i, "result"] = res
        first.loc[i, "profit"] = r.odds - 1 if res == r.pick else -1.0
    first["clv"] = first.odds / first.closing_odds - 1
    first.to_csv(LEDGER.replace(".csv", "_settled.csv"), index=False)
    done = first[pd.to_numeric(first.profit, errors="coerce").notna()]
    print(done.groupby("strategy").agg(n=("profit", "size"), roi=("profit", lambda x: pd.to_numeric(x).mean()),
                                       clv=("clv", "mean")).round(4))


if __name__ == "__main__":
    main()
