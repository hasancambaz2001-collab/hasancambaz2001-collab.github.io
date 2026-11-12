"""Build the feature store (cache/features.pkl) from 2009/10 onward."""
import iddaa  # noqa: F401
import json
import os
import time

import pandas as pd

from iddaa.backtest import Config, walk_forward
from iddaa.data import load
from iddaa.features import build, targets
from iddaa.injuries import availability

os.makedirs("cache", exist_ok=True)
t0 = time.time()
df = load()
if not os.path.exists("cache/dc_preds.pkl"):
    cfg = Config(**json.load(open("config/frozen_params.json"))["config"])
    walk_forward(df, "2009-07-01", "2026-12-31", cfg).to_pickle("cache/dc_preds.pkl")
P = pd.read_pickle("cache/dc_preds.pkl")
if os.path.exists("cache/availability.pkl"):
    A = pd.read_pickle("cache/availability.pkl")
else:
    A, tm = availability(df)
    A.to_pickle("cache/availability.pkl")
X = build(df, P, A)
T = targets(df)
keep = df.date >= "2010-07-01"
meta = df.loc[keep, ["date", "season", "div", "country", "HomeTeam", "AwayTeam", "FTHome", "FTAway",
                     "OddHome", "OddDraw", "OddAway", "MaxHome", "MaxDraw", "MaxAway", "Over25", "Under25",
                     "MaxOver25", "MaxUnder25", "AHLine", "HandiHome", "HandiAway"]]
pd.to_pickle({"X": X[keep], "T": T[keep], "meta": meta}, "cache/features.pkl")
print("features", X[keep].shape, f"{time.time() - t0:.0f}s")
print(X[keep].notna().mean().round(2).to_string())
