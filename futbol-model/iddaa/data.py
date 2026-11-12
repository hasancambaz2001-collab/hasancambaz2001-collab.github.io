"""Data loading and cleaning.

Source: Football-Data.co.uk results + odds, mirrored with ClubElo in
github.com/xgabora/Club-Football-Match-Data-2000-2025 (data/Matches.csv).
"""
from __future__ import annotations

import os
import urllib.request

import numpy as np
import pandas as pd

URL = ("https://raw.githubusercontent.com/xgabora/"
       "Club-Football-Match-Data-2000-2025/main/data/Matches.csv")
DEFAULT_PATH = os.environ.get(
    "IDDAA_DATA", os.path.join(os.path.dirname(__file__), "..", "data", "Matches.csv"))

# Divisions are fitted jointly per country so promoted/relegated teams keep
# their history and all teams share one strength scale.
COUNTRY = {
    "E0": "ENG", "E1": "ENG", "E2": "ENG", "E3": "ENG", "EC": "ENG",
    "D1": "GER", "D2": "GER", "F1": "FRA", "F2": "FRA", "I1": "ITA", "I2": "ITA",
    "SP1": "ESP", "SP2": "ESP", "SC0": "SCO", "SC1": "SCO", "SC2": "SCO", "SC3": "SCO",
    "B1": "BEL", "G1": "GRE", "N1": "NED", "P1": "POR", "T1": "TUR",
}

LEAGUE_NAMES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "EC": "National League", "D1": "Bundesliga", "D2": "2. Bundesliga", "F1": "Ligue 1",
    "F2": "Ligue 2", "I1": "Serie A", "I2": "Serie B", "SP1": "La Liga", "SP2": "La Liga 2",
    "SC0": "Scottish Prem", "SC1": "Scottish Champ", "SC2": "Scottish L1", "SC3": "Scottish L2",
    "B1": "Belçika Pro Lig", "G1": "Yunanistan SL", "N1": "Eredivisie", "P1": "Portekiz Liga",
    "T1": "Süper Lig",
}


def download(path: str = DEFAULT_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        urllib.request.urlretrieve(URL, path)
    return path


def _clean_odds(df: pd.DataFrame, cols: list[str], lo: float, hi: float) -> None:
    """Null out odds sets whose overround is implausible (data errors)."""
    ok = df[cols].notna().all(axis=1) & (df[cols] > 1.0).all(axis=1)
    over = (1.0 / df[cols]).sum(axis=1)
    bad = ~ok | (over < lo) | (over > hi)
    df.loc[bad, cols] = np.nan


def load(path: str = DEFAULT_PATH) -> pd.DataFrame:
    path = download(path)
    d = pd.read_csv(path, low_memory=False, parse_dates=["MatchDate"])
    d = d[d.Division.isin(COUNTRY)].copy()  # leagues with full market coverage
    d = d.dropna(subset=["FTHome", "FTAway"])
    d["country"] = d.Division.map(COUNTRY)
    d = d.rename(columns={"MatchDate": "date", "Division": "div"})
    for c in ["FTHome", "FTAway", "HTHome", "HTAway"]:
        d[c] = d[c].astype("float")
    # Cards = yellow + red (each card counted once)
    d["HomeCards"] = d.HomeYellow + d.HomeRed
    d["AwayCards"] = d.AwayYellow + d.AwayRed

    _clean_odds(d, ["OddHome", "OddDraw", "OddAway"], 1.0, 1.25)
    _clean_odds(d, ["MaxHome", "MaxDraw", "MaxAway"], 0.97, 1.20)
    _clean_odds(d, ["Over25", "Under25"], 1.0, 1.20)
    _clean_odds(d, ["MaxOver25", "MaxUnder25"], 0.97, 1.15)
    _clean_odds(d, ["HandiHome", "HandiAway"], 1.0, 1.20)
    # AH lines are stored rounded (-0.3 == -0.25, -0.8 == -0.75); snap to quarters.
    d["AHLine"] = np.round(d.HandiSize * 4) / 4
    d.loc[d.HandiHome.isna(), "AHLine"] = np.nan

    d = d.sort_values(["date", "div", "HomeTeam"]).reset_index(drop=True)
    d["season"] = np.where(d.date.dt.month >= 7, d.date.dt.year, d.date.dt.year - 1)
    return d
