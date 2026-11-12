"""Live data adapters.

API-Football (v3.football.api-sports.io): fixtures, injuries, lineups, odds.
The Odds API (api.the-odds-api.com): prices from many bookmakers incl. sharp ones.

Keys: in a Claude cloud session the network proxy injects the saved key, so
the env vars may hold any placeholder. Locally, export API_FOOTBALL_KEY and
ODDS_API_KEY.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

AF_HOST = "https://v3.football.api-sports.io"
ODDS_HOST = "https://api.the-odds-api.com/v4"

# API-Football league ids for the leagues the model covers
AF_LEAGUES = {"E0": 39, "E1": 40, "E2": 41, "E3": 42, "EC": 43, "SC0": 179, "SC1": 180, "SC2": 183, "SC3": 184,
              "D1": 78, "D2": 79, "I1": 135, "I2": 136, "SP1": 140, "SP2": 141, "F1": 61, "F2": 62,
              "N1": 88, "B1": 144, "P1": 94, "T1": 203, "G1": 197}
ODDS_SPORTS = {"E0": "soccer_epl", "E1": "soccer_efl_champ", "E2": "soccer_england_league1",
               "E3": "soccer_england_league2", "D1": "soccer_germany_bundesliga", "D2": "soccer_germany_bundesliga2",
               "I1": "soccer_italy_serie_a", "I2": "soccer_italy_serie_b", "SP1": "soccer_spain_la_liga",
               "SP2": "soccer_spain_segunda_division", "F1": "soccer_france_ligue_one", "F2": "soccer_france_ligue_two",
               "N1": "soccer_netherlands_eredivisie", "P1": "soccer_portugal_primeira_liga",
               "T1": "soccer_turkey_super_league", "SC0": "soccer_spl", "B1": "soccer_belgium_first_div",
               "G1": "soccer_greece_super_league"}


def _get(url: str, headers: dict, retries: int = 3) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise RuntimeError(f"{url}: {e}") from e
            time.sleep(2 ** i)
    return {}


class APIFootball:
    def __init__(self, key: str | None = None):
        self.h = {"x-apisports-key": key or os.environ.get("API_FOOTBALL_KEY", "proxy-injected")}

    def _q(self, path, **params):
        return _get(f"{AF_HOST}/{path}?{urllib.parse.urlencode(params)}", self.h).get("response", [])

    def fixtures(self, date: str, league: int, season: int):
        return self._q("fixtures", date=date, league=league, season=season)

    def injuries(self, fixture: int):
        """Players listed as missing / questionable for a fixture."""
        return self._q("injuries", fixture=fixture)

    def lineups(self, fixture: int):
        return self._q("fixtures/lineups", fixture=fixture)

    def odds(self, fixture: int):
        return self._q("odds", fixture=fixture)

    def statistics(self, fixture: int):
        return self._q("fixtures/statistics", fixture=fixture)


class OddsAPI:
    def __init__(self, key: str | None = None):
        self.key = key or os.environ.get("ODDS_API_KEY", "proxy-injected")

    def odds(self, sport: str, markets="h2h,totals", regions="eu,uk"):
        q = urllib.parse.urlencode({"apiKey": self.key, "regions": regions, "markets": markets, "oddsFormat": "decimal"})
        return _get(f"{ODDS_HOST}/sports/{sport}/odds?{q}", {})


def best_prices(event: dict) -> dict:
    """Best price and Pinnacle price per outcome from one Odds API event."""
    out: dict = {}
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            for o in mk.get("outcomes", []):
                key = (mk["key"], o["name"], o.get("point"))
                rec = out.setdefault(key, {"best": 0.0, "best_book": None, "pinnacle": None})
                if o["price"] > rec["best"]:
                    rec["best"], rec["best_book"] = o["price"], bk["key"]
                if bk["key"] == "pinnacle":
                    rec["pinnacle"] = o["price"]
    return out
