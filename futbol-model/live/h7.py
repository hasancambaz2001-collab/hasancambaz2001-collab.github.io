"""Live H7 features: market (Pinnacle or average price) + Dixon-Coles rates +
squad availability from today's injury list (API-Football) valued with
Transfermarkt market values."""
from __future__ import annotations

import json
import os

import lightgbm as lgb
import numpy as np
import pandas as pd

from iddaa.injuries import TM_DIR, TM_EXTRA, _sim, _stints
from iddaa.odds import power, shin

BASE = os.path.join(os.path.dirname(__file__), "..")


class SquadBook:
    """Players at a Transfermarkt club on a date with their latest value."""

    def __init__(self):
        tr = pd.read_csv(f"{TM_EXTRA}/transfer_history.csv", usecols=["player_id", "transfer_date", "to_team_id"],
                         parse_dates=["transfer_date"])
        self.st = _stints(tr)
        mv = pd.read_csv(f"{TM_DIR}/player_market_value/player_market_value.csv").rename(columns={"date_unix": "date"})
        mv["date"] = pd.to_datetime(mv.date, errors="coerce")
        self.mv = mv.dropna().sort_values("date")
        prof = pd.read_csv(f"{TM_DIR}/player_profiles/player_profiles.csv", usecols=["player_id", "player_name"])
        self.names = dict(zip(prof.player_id, prof.player_name.astype(str).str.replace(r"\s*\(\d+\)$", "", regex=True)))
        tm = pd.read_csv(os.path.join(BASE, "config", "team_map.csv"))
        self.club = dict(zip(tm.team, tm.club_id))

    def squad(self, team: str, date: pd.Timestamp) -> pd.DataFrame:
        cid = self.club.get(team)
        if cid is None:
            return pd.DataFrame(columns=["player_id", "name", "value"])
        s = self.st[(self.st.club_id == cid) & (self.st.start <= date) & (self.st.end > date)]
        v = self.mv[(self.mv.player_id.isin(s.player_id)) & (self.mv.date <= date)].groupby("player_id").value.last()
        out = pd.DataFrame({"player_id": s.player_id.unique()})
        out["value"] = out.player_id.map(v).fillna(0.0)
        out["name"] = out.player_id.map(self.names)
        return out

    def availability(self, team: str, date: pd.Timestamp, injured_names: list[str]) -> dict:
        sq = self.squad(team, date)
        if sq.empty:
            return {}
        hit = set()
        for n in injured_names:
            scores = sq.name.fillna("").map(lambda x: _sim(n, x))
            if len(scores) and scores.max() >= 0.6:
                hit.add(sq.player_id.iloc[int(scores.to_numpy().argmax())])
        sq["inj"] = sq.player_id.isin(hit)
        top = sq.sort_values("value", ascending=False).head(5)
        tot = sq.value.sum()
        return {"inj_n": int(sq.inj.sum()), "inj_value_share": float(sq.loc[sq.inj, "value"].sum() / tot) if tot > 0 else np.nan,
                "inj_top5": int(top.inj.sum()), "inj_top1": int(top.inj.iloc[0]) if len(top) else 0,
                "squad_logv": float(np.log1p(tot))}


class H7:
    def __init__(self):
        self.meta = json.load(open(os.path.join(BASE, "models", "h7_meta.json")))
        self.model = lgb.Booster(model_file=os.path.join(BASE, "models", "h7_lgbm.txt"))
        self.book = SquadBook()

    def predict(self, div, home, away, date, odds_1x2, odds_ou25, ah_line, dc: dict, inj_home: list, inj_away: list):
        q = shin(np.array([odds_1x2], float))[0]
        row = {"mk_p1": q[0], "mk_px": q[1], "mk_p2": q[2],
               "mk_pover": power(np.array([odds_ou25], float))[0][0] if all(odds_ou25) else np.nan,
               "mk_ah_line": ah_line if ah_line is not None else np.nan,
               "mk_overround": float(np.sum(1 / np.array(odds_1x2, float))),
               "div_code": self.meta["div_codes"][div], **dc}
        for side, team, names in (("home", home, inj_home), ("away", away, inj_away)):
            a = self.book.availability(team, pd.Timestamp(date), names)
            s = "h" if side == "home" else "a"
            for k in ("inj_n", "inj_value_share", "inj_top5", "inj_top1"):
                row[f"{k}_{side}"] = a.get(k, np.nan)
            row[f"squad_logv_{s}"] = a.get("squad_logv", np.nan)
        X = pd.DataFrame([row])[self.meta["columns"]]
        return self.model.predict(X)[0], row
