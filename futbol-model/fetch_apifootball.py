"""Download historical API-Football data for the backtest (run on your own computer).

  export API_FOOTBALL_KEY=...           # never commit the key
  python3 fetch_apifootball.py --league 203 --seasons 2021 2022 2023 2024 2025

Writes data/apifootball/<league>_<season>_{fixtures,stats,injuries}.csv.
Respects the plan's per-minute limit (default 10 requests/min, raise with --rpm).
League ids: Süper Lig 203, Premier League 39, La Liga 140, Serie A 135, Bundesliga 78, Ligue 1 61.
"""
import argparse
import csv
import os
import time

from live.sources import APIFootball


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, required=True)
    ap.add_argument("--seasons", type=int, nargs="+", required=True)
    ap.add_argument("--rpm", type=int, default=10)
    a = ap.parse_args()
    if not os.environ.get("API_FOOTBALL_KEY"):
        raise SystemExit("API_FOOTBALL_KEY ortam değişkenini ayarla.")
    api = APIFootball()
    out = os.path.join("data", "apifootball")
    os.makedirs(out, exist_ok=True)
    wait = 60.0 / a.rpm

    def q(path, **p):
        time.sleep(wait)
        return api._q(path, **p)

    for s in a.seasons:
        fx = q("fixtures", league=a.league, season=s)
        fx = [f for f in fx if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN")]
        with open(f"{out}/{a.league}_{s}_fixtures.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["fixture_id", "date", "referee", "home", "away", "home_goals", "away_goals", "ht_home", "ht_away"])
            for x in fx:
                w.writerow([x["fixture"]["id"], x["fixture"]["date"], x["fixture"]["referee"], x["teams"]["home"]["name"],
                            x["teams"]["away"]["name"], x["goals"]["home"], x["goals"]["away"],
                            x["score"]["halftime"]["home"], x["score"]["halftime"]["away"]])
        with open(f"{out}/{a.league}_{s}_stats.csv", "w", newline="") as fs, \
             open(f"{out}/{a.league}_{s}_injuries.csv", "w", newline="") as fi:
            ws, wi = csv.writer(fs), csv.writer(fi)
            ws.writerow(["fixture_id", "team", "stat", "value"])
            wi.writerow(["fixture_id", "team", "player", "type", "reason"])
            for i, x in enumerate(fx):
                fid = x["fixture"]["id"]
                for t in q("fixtures/statistics", fixture=fid):
                    for st in t["statistics"]:
                        ws.writerow([fid, t["team"]["name"], st["type"], st["value"]])
                for it in q("injuries", fixture=fid):
                    wi.writerow([fid, it["team"]["name"], it["player"]["name"], it["player"].get("type"), it["player"].get("reason")])
                if i % 20 == 0:
                    print(f"{s}: {i}/{len(fx)}", flush=True)
        print(f"{s} tamam: {len(fx)} maç")


if __name__ == "__main__":
    main()
