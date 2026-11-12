"""Leakage-free pre-match feature store.

Every feature for a match on date d uses only matches played strictly
before d (team logs are shifted by one match; same-day matches of the same
team do not exist). Feature groups are named so the factor lab can add or
remove whole "puzzle pieces".
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from .odds import power, shin

REF_DIR = "/home/user/datasets/football-datasets/datasets/premier-league"

GROUPS = {
    "piyasa": ["mk_p1", "mk_px", "mk_p2", "mk_pover", "mk_ah_line", "mk_overround"],
    "model": ["dc_lh", "dc_la", "dc_corner_h", "dc_corner_a", "dc_card_h", "dc_card_a"],
    "form": ["pts5_h", "pts5_a", "gf_ewm_h", "ga_ewm_h", "gf_ewm_a", "ga_ewm_a", "ppg_season_h", "ppg_season_a"],
    "sut": ["sh_ewm_h", "sha_ewm_h", "sot_ewm_h", "sota_ewm_h", "sh_ewm_a", "sha_ewm_a", "sot_ewm_a", "sota_ewm_a"],
    "korner_gecmis": ["co_ewm_h", "coa_ewm_h", "co_ewm_a", "coa_ewm_a"],
    "kart_gecmis": ["ca_ewm_h", "caa_ewm_h", "ca_ewm_a", "caa_ewm_a", "fo_ewm_h", "fo_ewm_a", "red_ewm_h", "red_ewm_a"],
    "h2h": ["h2h_n", "h2h_ppg_h", "h2h_goals", "h2h_home_unbeaten3", "h2h_cards", "h2h_corners"],
    "seriler": ["wstreak_h", "lstreak_h", "unbeaten_h", "scoring_h", "cs_h", "wstreak_a", "lstreak_a", "unbeaten_a", "scoring_a", "cs_a"],
    "takvim": ["rest_h", "rest_a", "n14_h", "n14_a", "month", "weekday", "hour", "round_frac"],
    "puan_durumu": ["pos_h", "pos_a", "pts_h", "pts_a", "pos_diff", "late_season"],
    "elo": ["elo_h", "elo_a", "elo_diff"],
    "hakem": ["ref_cards_ewm", "ref_red_rate", "ref_n"],
    "sakatlik": ["inj_n_home", "inj_n_away", "inj_value_share_home", "inj_value_share_away",
                 "inj_top5_home", "inj_top5_away", "inj_top1_home", "inj_top1_away", "squad_logv_h", "squad_logv_a"],
}


def _team_log(df: pd.DataFrame) -> pd.DataFrame:
    cols = {"FT": ("FTHome", "FTAway"), "SH": ("HomeShots", "AwayShots"), "SOT": ("HomeTarget", "AwayTarget"),
            "CO": ("HomeCorners", "AwayCorners"), "CA": ("HomeCards", "AwayCards"), "FO": ("HomeFouls", "AwayFouls"),
            "RED": ("HomeRed", "AwayRed")}
    parts = []
    for side, opp in (("h", "a"), ("a", "h")):
        p = pd.DataFrame({"idx": df.index, "date": df.date, "season": df.season, "div": df["div"],
                          "team": df.HomeTeam if side == "h" else df.AwayTeam, "side": side})
        for k, (hc, ac) in cols.items():
            mine, theirs = (hc, ac) if side == "h" else (ac, hc)
            p[f"{k}_f"] = df[mine].to_numpy()
            p[f"{k}_a"] = df[theirs].to_numpy()
        gf, ga = p["FT_f"], p["FT_a"]
        p["pts"] = np.where(gf > ga, 3, np.where(gf == ga, 1, 0))
        parts.append(p)
    L = pd.concat(parts).sort_values(["team", "date", "idx"]).reset_index(drop=True)
    return L


def _streak(x: pd.Series) -> pd.Series:
    """Length of the run of True values ending at each row (inclusive)."""
    grp = (~x).cumsum()
    return x.groupby(grp).cumsum()


def build(df: pd.DataFrame, preds: pd.DataFrame | None = None, avail: pd.DataFrame | None = None) -> pd.DataFrame:
    L = _team_log(df)
    g = L.groupby("team", sort=False)
    F = pd.DataFrame({"idx": L.idx, "side": L.side})
    span = 10
    for k, short in (("FT_f", "gf"), ("FT_a", "ga"), ("SH_f", "sh"), ("SH_a", "sha"), ("SOT_f", "sot"), ("SOT_a", "sota"),
                     ("CO_f", "co"), ("CO_a", "coa"), ("CA_f", "ca"), ("CA_a", "caa"), ("FO_f", "fo"), ("RED_f", "red")):
        F[f"{short}_ewm"] = g[k].transform(lambda s: s.shift(1).ewm(span=span, min_periods=3, ignore_na=True).mean())
    F["pts5"] = g["pts"].transform(lambda s: s.shift(1).rolling(5, min_periods=3).sum())
    # season-to-date
    gs = L.groupby(["team", "season"], sort=False)
    F["pts_season"] = gs["pts"].transform(lambda s: s.shift(1).fillna(0).cumsum())
    F["n_season"] = gs["pts"].cumcount()
    F["ppg_season"] = np.where(F.n_season > 0, F.pts_season / F.n_season.clip(lower=1), np.nan)
    # streaks (state before the match)
    win, loss = L.pts == 3, L.pts == 0
    for name, cond in (("wstreak", win), ("lstreak", loss), ("unbeaten", ~loss), ("scoring", L.FT_f > 0), ("cs", L.FT_a == 0)):
        s = cond.groupby(L.team, sort=False).transform(lambda c: _streak(c).shift(1))
        F[name] = s
    # schedule
    F["rest"] = g["date"].transform(lambda s: s.diff().dt.days)
    F["n14"] = g["date"].transform(lambda s: pd.Series(
        np.arange(len(s)) - np.searchsorted(s.to_numpy(), s.to_numpy() - np.timedelta64(14, "D"), side="left"),
        index=s.index))
    F["season_key"] = L.season.to_numpy()

    # pivot to match rows
    W = F.set_index(["idx", "side"]).unstack("side")
    W.columns = [f"{a}_{b}" for a, b in W.columns]
    X = pd.DataFrame(index=df.index)
    for c in ["gf_ewm", "ga_ewm", "sh_ewm", "sha_ewm", "sot_ewm", "sota_ewm", "co_ewm", "coa_ewm", "ca_ewm", "caa_ewm",
              "fo_ewm", "red_ewm", "pts5", "ppg_season", "wstreak", "lstreak", "unbeaten", "scoring", "cs", "rest", "n14"]:
        for s in ("h", "a"):
            X[f"{c}_{s}"] = W[f"{c}_{s}"].reindex(df.index)
    X["pts_h"] = W["pts_season_h"].reindex(df.index)
    X["pts_a"] = W["pts_season_a"].reindex(df.index)

    # league table position before the match (by points, then goal diff proxy = ppg)
    X["pos_h"] = np.nan
    X["pos_a"] = np.nan
    tbl = pd.DataFrame({"date": df.date, "div": df["div"], "season": df.season, "h": df.HomeTeam, "a": df.AwayTeam,
                        "ph": X.pts_h, "pa": X.pts_a})
    for (dv, se), m in tbl.groupby(["div", "season"]):
        pts: dict = {}
        ph, pa = [], []
        for _, r in m.sort_values("date").iterrows():
            pts.setdefault(r.h, 0.0)
            pts.setdefault(r.a, 0.0)
            pts[r.h] = r.ph if pd.notna(r.ph) else pts[r.h]
            pts[r.a] = r.pa if pd.notna(r.pa) else pts[r.a]
            ranking = sorted(pts.values(), reverse=True)
            ph.append(1 + ranking.index(pts[r.h]))
            pa.append(1 + ranking.index(pts[r.a]))
        X.loc[m.sort_values("date").index, "pos_h"] = ph
        X.loc[m.sort_values("date").index, "pos_a"] = pa
    X["pos_diff"] = X.pos_h - X.pos_a
    n_teams = df.groupby(["div", "season"]).HomeTeam.transform("nunique")
    games = 2 * (n_teams - 1)
    X["round_frac"] = (W["n_season_h"].reindex(df.index) / games).clip(0, 1)
    X["late_season"] = (X.round_frac > 0.85).astype(float)
    X["month"] = df.date.dt.month
    X["weekday"] = df.date.dt.weekday
    X["hour"] = pd.to_numeric(df.MatchTime.astype(str).str[:2], errors="coerce")

    # head-to-head (any venue, before the match)
    pair = df.apply(lambda r: tuple(sorted((r.HomeTeam, r.AwayTeam))), axis=1)
    H = pd.DataFrame({"pair": pair, "date": df.date, "h": df.HomeTeam, "a": df.AwayTeam, "hg": df.FTHome, "ag": df.FTAway,
                      "cards": df.HomeCards + df.AwayCards, "corners": df.HomeCorners + df.AwayCorners}).sort_values("date")
    h2h = {c: np.full(len(df), np.nan) for c in ("h2h_n", "h2h_ppg_h", "h2h_goals", "h2h_home_unbeaten3", "h2h_cards", "h2h_corners")}
    pos = {ix: i for i, ix in enumerate(df.index)}
    for _, m in H.groupby("pair", sort=False):
        rows = m.to_dict("records")
        idxs = m.index.to_list()
        for k in range(len(rows)):
            past = rows[max(0, k - 6):k]
            i = pos[idxs[k]]
            h2h["h2h_n"][i] = len(past)
            if not past:
                continue
            me = rows[k]["h"]
            pts = [3 if (p["hg"] > p["ag"]) == (p["h"] == me) and p["hg"] != p["ag"] else (1 if p["hg"] == p["ag"] else 0) for p in past]
            h2h["h2h_ppg_h"][i] = np.mean(pts)
            h2h["h2h_goals"][i] = np.mean([p["hg"] + p["ag"] for p in past])
            h2h["h2h_cards"][i] = np.nanmean([p["cards"] for p in past]) if any(pd.notna(p["cards"]) for p in past) else np.nan
            h2h["h2h_corners"][i] = np.nanmean([p["corners"] for p in past]) if any(pd.notna(p["corners"]) for p in past) else np.nan
            home_meet = [p for p in past if p["h"] == me][-3:]
            if len(home_meet) == 3:
                h2h["h2h_home_unbeaten3"][i] = float(all(p["hg"] >= p["ag"] for p in home_meet))
    for c, v in h2h.items():
        X[c] = v

    # market
    q = shin(df[["OddHome", "OddDraw", "OddAway"]].to_numpy(float))
    X["mk_p1"], X["mk_px"], X["mk_p2"] = q[:, 0], q[:, 1], q[:, 2]
    X["mk_pover"] = power(df[["Over25", "Under25"]].to_numpy(float))[:, 0]
    X["mk_ah_line"] = df.AHLine
    X["mk_overround"] = (1 / df[["OddHome", "OddDraw", "OddAway"]]).sum(axis=1).where(df.OddHome.notna())

    # Elo (ClubElo snapshot carried in the source data)
    X["elo_h"], X["elo_a"] = df.HomeElo, df.AwayElo
    X["elo_diff"] = df.HomeElo - df.AwayElo

    # model rates from the walk-forward Dixon-Coles run
    for c, src in (("dc_lh", "lh"), ("dc_la", "la"), ("dc_corner_h", "clh"), ("dc_corner_a", "cla"), ("dc_card_h", "klh"), ("dc_card_a", "kla")):
        X[c] = preds[src].reindex(df.index) if preds is not None and src in preds else np.nan

    # referee (Premier League only)
    X["ref_cards_ewm"], X["ref_red_rate"], X["ref_n"] = np.nan, np.nan, np.nan
    refs = []
    for f in sorted(glob.glob(f"{REF_DIR}/*.csv")):
        r = pd.read_csv(f, usecols=lambda c: c in ("Date", "HomeTeam", "AwayTeam", "Referee"))
        refs.append(r)
    R = pd.concat(refs).dropna(subset=["Referee"])
    R["date"] = pd.to_datetime(R.Date, errors="coerce")
    e0 = df[df["div"] == "E0"].reset_index().merge(R[["date", "HomeTeam", "AwayTeam", "Referee"]], on=["date", "HomeTeam", "AwayTeam"], how="left").set_index("index")
    e0 = e0.dropna(subset=["Referee"]).sort_values("date")
    e0["cards"] = e0.HomeCards + e0.AwayCards
    e0["red"] = (e0.HomeRed + e0.AwayRed > 0).astype(float)
    gr = e0.groupby("Referee", sort=False)
    X.loc[e0.index, "ref_cards_ewm"] = gr.cards.transform(lambda s: s.shift(1).ewm(span=20, min_periods=5).mean())
    X.loc[e0.index, "ref_red_rate"] = gr.red.transform(lambda s: s.shift(1).expanding(min_periods=10).mean())
    X.loc[e0.index, "ref_n"] = gr.cumcount()

    # availability (Transfermarkt)
    if avail is not None:
        for c in avail.columns:
            X[c] = avail[c].reindex(df.index)
        X["squad_logv_h"] = np.log1p(X.get("squad_value_home"))
        X["squad_logv_a"] = np.log1p(X.get("squad_value_away"))
    X["div_code"] = df["div"].astype("category").cat.codes
    return X


def targets(df: pd.DataFrame) -> pd.DataFrame:
    T = pd.DataFrame(index=df.index)
    T["corners"] = df.HomeCorners + df.AwayCorners
    T["cards"] = df.HomeCards + df.AwayCards
    T["red_any"] = (df.HomeRed + df.AwayRed > 0).astype(float).where(df.HomeRed.notna())
    T["goals"] = df.FTHome + df.FTAway
    T["over25"] = (T.goals > 2.5).astype(float)
    T["btts"] = ((df.FTHome > 0) & (df.FTAway > 0)).astype(float)
    T["result"] = np.where(df.FTHome > df.FTAway, 0, np.where(df.FTHome == df.FTAway, 1, 2))
    T["ht_goal"] = ((df.HTHome + df.HTAway) > 0).astype(float).where(df.HTHome.notna())
    return T
