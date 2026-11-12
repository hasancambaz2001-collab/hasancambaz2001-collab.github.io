"""Squad availability features from Transfermarkt (salimt/football-datasets).

For every (team, match date):
  squad_value     sum of latest market values (<= date) of players at the club
  inj_n           players at the club whose injury interval covers the date
  inj_value_share injured value / squad value
  inj_top5        how many of the club's 5 most valuable players are injured
  inj_top1        1 if the most valuable player is injured

A player's club on a date = destination of their last transfer/loan before
that date. Market values use only valuations published before the date.
Caveat: an injury interval's end date is known only afterwards; on match day
the absence itself is public (team news), so "injured on date" is treated as
pre-match information.
"""
from __future__ import annotations

import difflib
import os
import re
import unicodedata

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

TM_DIR = os.environ.get("TM_DIR", "/home/user/salimt/football-datasets/datalake/transfermarkt")
TM_EXTRA = os.environ.get("TM_EXTRA", "/tmp/claude-0/tm")  # LFS files fetched separately

DIV2COMP = {"E0": "GB1", "E1": "GB2", "E2": "GB3", "E3": "GB4", "D1": "L1", "D2": "L2", "F1": "FR1",
            "F2": "FR2", "I1": "IT1", "I2": "IT2", "SP1": "ES1", "SP2": "ES2", "SC0": "SC1",
            "B1": "BE1", "G1": "GR1", "N1": "NL1", "P1": "PO1", "T1": "TR1"}

_STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "sv", "vfl", "vfb", "tsg", "fk", "sk", "cd", "ud",
         "rcd", "rc", "real", "club", "de", "del", "la", "1", "calcio", "football", "sporting", "sl", "sad",
         "kv", "krc", "rsc", "kas", "pfc", "bk", "if", "aj", "ogc", "sco", "stade", "olympique", "town", "city",
         "united", "utd", "athletic", "atletico", "1899", "1846", "1860", "04", "05", "09", "96", "98", "07"}
_ALIAS = {"man": "manchester", "nott'm": "nottingham", "nottm": "nottingham", "wolves": "wolverhampton",
          "spurs": "tottenham", "sheffield": "sheffield", "qpr": "queens park rangers", "mgladbach": "monchengladbach",
          "m'gladbach": "monchengladbach", "ein": "eintracht", "psg": "paris", "sociedad": "sociedad",
          "ath": "athletic", "espanol": "espanyol", "inter": "inter internazionale", "milan": "milan",
          "fortuna": "fortuna", "dusseldorf": "dusseldorf", "bayern": "bayern munchen munich",
          "leverkusen": "leverkusen bayer", "dortmund": "dortmund borussia", "betis": "betis",
          "celta": "celta vigo", "gijon": "gijon sporting", "ad.": "", "buyuksehyr": "buyuksehir basaksehir",
          "basaksehir": "basaksehir buyuksehir"}


def _norm(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    toks = []
    for t in s.split():
        toks += _ALIAS.get(t, t).split()
    return {t for t in toks if t not in _STOP} or set(s.split())


def _sim(a: str, b: str) -> float:
    A, B = _norm(a), _norm(b)
    j = len(A & B) / max(1, len(A | B))
    pre = max((1.0 for x in A for y in B if len(x) >= 4 and len(y) >= 4 and (x.startswith(y) or y.startswith(x))), default=0)
    r = difflib.SequenceMatcher(None, " ".join(sorted(A)), " ".join(sorted(B))).ratio()
    return max(j, 0.8 * pre, r * 0.9)


def team_map(matches: pd.DataFrame) -> pd.DataFrame:
    """Map football-data (div, team) -> Transfermarkt club_id by per-season assignment + majority vote."""
    tcs = pd.read_csv(f"{TM_DIR}/team_competitions_seasons/team_competitions_seasons.csv",
                      usecols=["club_id", "competition_id", "season_id", "team_name"])
    votes = []
    for (dv, season), g in matches.groupby(["div", "season"]):
        comp = DIV2COMP.get(dv)
        if comp is None:
            continue
        fd = sorted(set(g.HomeTeam) | set(g.AwayTeam))
        tm = tcs[(tcs.competition_id == comp) & (tcs.season_id == season)].drop_duplicates("club_id")
        if len(tm) < 0.6 * len(fd):
            continue
        S = np.array([[_sim(a, b) for b in tm.team_name] for a in fd])
        r, c = linear_sum_assignment(-S)
        for i, j in zip(r, c):
            if S[i, j] >= 0.5:
                votes.append((dv, fd[i], int(tm.club_id.iloc[j]), tm.team_name.iloc[j], S[i, j]))
    v = pd.DataFrame(votes, columns=["div", "team", "club_id", "tm_name", "sim"])
    m = (v.groupby(["team", "club_id", "tm_name"]).agg(n=("sim", "size"), sim=("sim", "mean"))
         .reset_index().sort_values("n", ascending=False).drop_duplicates("team")
         .drop_duplicates("club_id"))  # one club per FD name and vice versa (keeps most-voted)
    return m


def _stints(tr: pd.DataFrame) -> pd.DataFrame:
    tr = tr.dropna(subset=["transfer_date"]).sort_values(["player_id", "transfer_date"])
    tr["end"] = tr.groupby("player_id").transfer_date.shift(-1).fillna(pd.Timestamp("2100-01-01"))
    return tr.rename(columns={"to_team_id": "club_id", "transfer_date": "start"})[["player_id", "club_id", "start", "end"]]


def availability(matches: pd.DataFrame, min_date="2009-07-01") -> pd.DataFrame:
    """Return one row per (match index, side) with availability features."""
    tmap = team_map(matches)
    name2club = dict(zip(tmap.team, tmap.club_id))
    tr = pd.read_csv(f"{TM_EXTRA}/transfer_history.csv", usecols=["player_id", "transfer_date", "to_team_id"],
                     parse_dates=["transfer_date"])
    st = _stints(tr)
    inj = pd.read_csv(f"{TM_DIR}/player_injuries/player_injuries_updated_20260929.csv",
                      parse_dates=["from_date", "end_date"]).dropna(subset=["from_date", "end_date"])
    mv = pd.read_csv(f"{TM_DIR}/player_market_value/player_market_value.csv").rename(columns={"date_unix": "date"})
    mv["date"] = pd.to_datetime(mv.date, errors="coerce")
    mv = mv.dropna().sort_values(["player_id", "date"])
    mv_g = {p: (g.date.to_numpy(), g.value.to_numpy()) for p, g in mv.groupby("player_id")}
    inj_g = {p: (g.from_date.to_numpy(), g.end_date.to_numpy() + np.timedelta64(1, "D")) for p, g in inj.groupby("player_id")}

    m = matches[matches.date >= min_date]
    side = pd.concat([pd.DataFrame({"idx": m.index, "date": m.date, "team": m.HomeTeam, "side": "home"}),
                      pd.DataFrame({"idx": m.index, "date": m.date, "team": m.AwayTeam, "side": "away"})])
    side["club_id"] = side.team.map(name2club)
    side = side.dropna(subset=["club_id"])
    out = []
    for cid, g in side.groupby("club_id"):
        S = st[st.club_id == cid]
        if S.empty:
            continue
        D = g.date.to_numpy()
        players = S.player_id.to_numpy()
        on = (S.start.to_numpy()[None, :] <= D[:, None]) & (S.end.to_numpy()[None, :] > D[:, None])
        val = np.zeros(on.shape)
        injm = np.zeros(on.shape, bool)
        for j, p in enumerate(players):
            if not on[:, j].any():
                continue
            if p in mv_g:
                dts, vs = mv_g[p]
                k = np.searchsorted(dts, D, side="right") - 1
                val[:, j] = np.where(k >= 0, vs[np.clip(k, 0, None)], 0.0)
            if p in inj_g:
                f, e = inj_g[p]
                injm[:, j] = ((f[None, :] <= D[:, None]) & (e[None, :] > D[:, None])).any(1)
        val = np.where(on, val, 0.0)
        injm &= on
        sq = val.sum(1)
        iv = (val * injm).sum(1)
        # top-5 by value at date
        order = np.argsort(-val, 1)[:, :5]
        top_inj = np.take_along_axis(injm, order, 1) & (np.take_along_axis(val, order, 1) > 0)
        out.append(pd.DataFrame({"idx": g.idx.to_numpy(), "side": g.side.to_numpy(),
                                 "squad_value": sq, "squad_n": on.sum(1), "inj_n": injm.sum(1),
                                 "inj_value_share": np.where(sq > 0, iv / np.maximum(sq, 1), np.nan),
                                 "inj_top5": top_inj.sum(1), "inj_top1": top_inj[:, 0].astype(int)}))
    A = pd.concat(out)
    A = A.pivot_table(index="idx", columns="side",
                      values=["squad_value", "squad_n", "inj_n", "inj_value_share", "inj_top5", "inj_top1"])
    A.columns = [f"{a}_{b}" for a, b in A.columns]
    return A, tmap
