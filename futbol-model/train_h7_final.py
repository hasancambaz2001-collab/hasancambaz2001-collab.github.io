"""Train the H7 model (market + model + injuries, MS 1X2) on every season
for live use. Hyper-parameters are the a-priori ones from factor_lab."""
import iddaa  # noqa: F401
import json
import os

import lightgbm as lgb
import pandas as pd

from betting_ml import feature_sets
from factor_lab import PARAMS, ROUNDS

d = pd.read_pickle("cache/features.pkl")
X, T, M = d["X"].copy(), d["T"], d["meta"]
cols = feature_sets(X)["inj"]
ok = T.result.notna()
m = lgb.train(dict(PARAMS, objective="multiclass", num_class=3), lgb.Dataset(X.loc[ok, cols], T.result[ok]), ROUNDS)
os.makedirs("models", exist_ok=True)
m.save_model("models/h7_lgbm.txt")
divs = sorted(M["div"].unique())
json.dump({"columns": cols, "div_codes": {dv: i for i, dv in enumerate(sorted(pd.read_pickle("cache/features.pkl")["meta"]["div"].astype("category").cat.categories))},
           "trained_on": [str(M.date.min().date()), str(M.date.max().date())],
           "rule": json.load(open("config/ml_frozen.json"))["hypotheses"]["H7"]["params"]},
          open("models/h7_meta.json", "w"), indent=1)
print("saved", len(cols), "features")
