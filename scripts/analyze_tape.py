#!/usr/bin/env python3
"""Join Binance 1s + Chainlink strike/TWAP for T6–T9. No bot."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.constants import GAMMA_API
from whiskas.http import get_json

PROC = ROOT / "data" / "processed"
BINANCE_DIR = ROOT / "data" / "raw" / "binance_btcusdt_1s"
AUG1 = 1785542400
AUG7 = 1786060800
AUG14 = 1786665600
MAKER_EPS = 0.02


def _sec(ts: int) -> int:
    x = int(ts)
    if x >= 10**15:  # microseconds
        return x // 1_000_000
    if x >= 10**12:  # milliseconds
        return x // 1000
    return x


def load_binance_closes() -> pd.Series:
    frames = []
    for path in sorted(BINANCE_DIR.glob("BTCUSDT-1s-2026-08-*.csv")):
        df = pd.read_csv(path, header=None, usecols=[0, 4], names=["ts", "close"])
        df["ts"] = df["ts"].map(_sec)
        df["close"] = df["close"].astype(float)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no 1s csv in {BINANCE_DIR}")
    out = pd.concat(frames, ignore_index=True).drop_duplicates("ts").sort_values("ts")
    return out.set_index("ts")["close"]


def fetch_strikes(slugs: list[str], cache_path: Path) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    missing = [s for s in slugs if s not in cache]
    print(f"gamma cache={len(cache)} missing={len(missing)}", flush=True)

    def one(slug: str) -> tuple[str, dict]:
        rec: dict = {"ok": False}
        try:
            ev = get_json(f"{GAMMA_API}/events", {"slug": slug}, timeout=25, retries=3, pause=0.02)
            if ev:
                e = ev[0]
                meta = e.get("eventMetadata") or {}
                m0 = (e.get("markets") or [{}])[0]
                cfg = m0.get("cryptoMarketConfig") or {}
                rec = {
                    "ok": True,
                    "priceToBeat": float(meta["priceToBeat"]) if meta.get("priceToBeat") is not None else None,
                    "finalPrice": float(meta["finalPrice"]) if meta.get("finalPrice") is not None else None,
                    "twapLookbackSeconds": cfg.get("twapLookbackSeconds"),
                    "twapEnabled": cfg.get("twapEnabled"),
                    "resolutionSource": e.get("resolutionSource") or m0.get("resolutionSource"),
                }
        except Exception as exc:
            rec = {"ok": False, "error": str(exc)[:200]}
        return slug, rec

    if missing:
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(one, s) for s in missing]
            for fut in as_completed(futs):
                slug, rec = fut.result()
                cache[slug] = rec
                done += 1
                if done % 100 == 0:
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")
                    print(f"  gamma {done}/{len(missing)}", flush=True)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def agree_rate(side_up: pd.Series, signal_up: pd.Series) -> dict:
    sig = pd.to_numeric(signal_up, errors="coerce")
    side = side_up.astype(float)
    mask = side.notna() & sig.notna()
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "agree": None, "se": None}
    hit = float((side[mask] == sig[mask]).mean())
    return {"n": n, "agree": hit, "se": float(np.sqrt(hit * (1 - hit) / n))}


def main() -> int:
    win = pd.read_parquet(PROC / "whiskas_windows.parquet")
    fills = pd.read_parquet(PROC / "whiskas_fills.parquet")
    fills = fills.copy()
    fills["role"] = np.where((fills["usdc"] - fills["size"] * fills["price"]).abs() <= MAKER_EPS, "maker", "taker")
    fills.loc[(fills["usdc"] - fills["size"] * fills["price"]) < -MAKER_EPS, "role"] = "other"

    since = win[win["t0"] >= AUG1].copy()
    slugs = since["slug"].tolist()
    print(f"windows since Aug1={len(since)}", flush=True)
    strikes = fetch_strikes(slugs, PROC / "gamma_strikes.json")

    print("loading binance 1s...", flush=True)
    px = load_binance_closes()
    print(f"binance seconds={len(px)} {int(px.index.min())}->{int(px.index.max())}", flush=True)
    # rolling TWAPs on the 1s close (proxy for Chainlink TWAP)
    twap30 = px.rolling(30, min_periods=30).mean()
    twap60 = px.rolling(60, min_periods=60).mean()

    f = fills[fills["slug"].isin(slugs)].copy()
    f["strike"] = f["slug"].map(lambda s: (strikes.get(s) or {}).get("priceToBeat"))
    f["final"] = f["slug"].map(lambda s: (strikes.get(s) or {}).get("finalPrice"))
    f["spot"] = f["timestamp"].map(px)
    f["twap30"] = f["timestamp"].map(twap30)
    f["twap60"] = f["timestamp"].map(twap60)
    f["spot5"] = (f["timestamp"] + 5).map(px)
    f["spot30"] = (f["timestamp"] + 30).map(px)
    f["side_up"] = f["leg"] == "Up"

    def _dir(level: pd.Series, strike: pd.Series) -> pd.Series:
        out = pd.Series(np.nan, index=level.index, dtype="float")
        ok = level.notna() & strike.notna() & (level != strike)
        out.loc[ok] = (level[ok] > strike[ok]).astype(float)
        return out

    f["spot_up"] = _dir(f["spot"], f["strike"])
    f["twap30_up"] = _dir(f["twap30"], f["strike"])
    f["twap60_up"] = _dir(f["twap60"], f["strike"])
    f["official_up"] = _dir(f["final"], f["strike"])
    f["twap_live"] = np.where(f["t0"] >= AUG14, f["twap60"], np.where(f["t0"] >= AUG7, f["twap30"], f["spot"]))
    f["twap_live"] = pd.to_numeric(f["twap_live"], errors="coerce")
    f["twap_live_up"] = _dir(f["twap_live"], f["strike"])

    taker = f[f["role"] == "taker"]
    maker = f[f["role"] == "maker"]

    t6 = {
        "all": agree_rate(taker["side_up"], taker["spot_up"]),
        "pre_aug14": agree_rate(taker.loc[taker["t0"] < AUG14, "side_up"], taker.loc[taker["t0"] < AUG14, "spot_up"]),
        "post_aug14": agree_rate(taker.loc[taker["t0"] >= AUG14, "side_up"], taker.loc[taker["t0"] >= AUG14, "spot_up"]),
    }
    t7 = {
        "live_twap_all": agree_rate(taker["side_up"], taker["twap_live_up"]),
        "pre_aug14_twap30_or_spot": agree_rate(
            taker.loc[taker["t0"] < AUG14, "side_up"], taker.loc[taker["t0"] < AUG14, "twap_live_up"]
        ),
        "post_aug14_twap60": agree_rate(
            taker.loc[taker["t0"] >= AUG14, "side_up"], taker.loc[taker["t0"] >= AUG14, "twap_live_up"]
        ),
        "official_final_minus_strike": agree_rate(taker["side_up"], taker["official_up"]),
        "aug1_6_snapshot": agree_rate(
            taker.loc[taker["t0"] < AUG7, "side_up"], taker.loc[taker["t0"] < AUG7, "spot_up"]
        ),
        "aug7_13_twap30": agree_rate(
            taker.loc[(taker["t0"] >= AUG7) & (taker["t0"] < AUG14), "side_up"],
            taker.loc[(taker["t0"] >= AUG7) & (taker["t0"] < AUG14), "twap30_up"],
        ),
    }
    print("T6", t6, flush=True)
    print("T7", t7, flush=True)

    # T8 maker adverse selection
    maker = maker.copy()
    maker["ret5"] = (maker["spot5"] - maker["spot"]) / maker["spot"]
    maker["ret30"] = (maker["spot30"] - maker["spot"]) / maker["spot"]
    sign = np.where(maker["side_up"], 1.0, -1.0)
    maker["markout5"] = maker["ret5"] * sign
    maker["markout30"] = maker["ret30"] * sign
    maker["lost"] = maker["leg"] != maker["winner"]
    t8 = {
        "n": int(len(maker)),
        "p_side_is_loser": float(maker["lost"].mean()) if len(maker) else None,
        "markout5_mean_bps": float(maker["markout5"].mean() * 1e4) if maker["markout5"].notna().any() else None,
        "markout30_mean_bps": float(maker["markout30"].mean() * 1e4) if maker["markout30"].notna().any() else None,
        "p_adverse_5s": float((maker["markout5"] < 0).mean()) if maker["markout5"].notna().any() else None,
        "p_adverse_30s": float((maker["markout30"] < 0).mean()) if maker["markout30"].notna().any() else None,
        "n_markout": int(maker["markout5"].notna().sum()),
    }
    # taker markout for contrast
    taker2 = taker.copy()
    taker2["ret5"] = (taker2["spot5"] - taker2["spot"]) / taker2["spot"]
    taker2["markout5"] = taker2["ret5"] * np.where(taker2["side_up"], 1.0, -1.0)
    t8["taker_p_side_is_loser"] = float((taker2["leg"] != taker2["winner"]).mean()) if len(taker2) else None
    t8["taker_markout5_mean_bps"] = float(taker2["markout5"].mean() * 1e4) if taker2["markout5"].notna().any() else None
    print("T8", t8, flush=True)

    # T9 daily
    since = since.copy()
    since["day"] = pd.to_datetime(since["t0"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    payout = since.apply(lambda r: r["q_up"] if r["winner"] == "Up" else r["q_down"], axis=1)
    since["fee0_usdc"] = payout - since["cost_up"] - since["cost_down"]
    since["cheap97"] = since["pair_cost"].notna() & (since["pair_cost"] < 0.97)
    since["cheap96"] = since["pair_cost"].notna() & (since["pair_cost"] < 0.96)

    def bucket(name: str, mask: pd.Series) -> dict:
        sub = since[mask]
        return {
            "name": name,
            "n": int(len(sub)),
            "fee0_usdc": float(sub["fee0_usdc"].sum()),
            "per_window": float(sub["fee0_usdc"].mean()) if len(sub) else None,
            "cheap97_n": int(sub["cheap97"].sum()),
            "cheap97_pct": float(sub["cheap97"].mean()) if len(sub) else None,
            "cheap96_n": int(sub["cheap96"].sum()),
            "cheap96_pct": float(sub["cheap96"].mean()) if len(sub) else None,
            "cheap97_fee0": float(sub.loc[sub["cheap97"], "fee0_usdc"].sum()),
        }

    t9 = {
        "aug1_6_snapshot": bucket("aug1_6", since["t0"] < AUG7),
        "aug7_13_twap30": bucket("aug7_13", (since["t0"] >= AUG7) & (since["t0"] < AUG14)),
        "pre_aug14": bucket("pre_aug14", since["t0"] < AUG14),
        "post_aug14_twap60": bucket("post_aug14", since["t0"] >= AUG14),
        "daily": since.groupby("day")
        .agg(n=("slug", "size"), fee0=("fee0_usdc", "sum"), cheap97=("cheap97", "sum"), cheap96=("cheap96", "sum"))
        .reset_index()
        .to_dict(orient="records"),
    }
    print("T9 pre", t9["pre_aug14"], flush=True)
    print("T9 post", t9["post_aug14_twap60"], flush=True)

    n_strike = sum(1 for s in slugs if (strikes.get(s) or {}).get("priceToBeat") is not None)
    out = {
        "n_windows_aug": int(len(since)),
        "n_fills_aug": int(len(f)),
        "n_gamma_strike": n_strike,
        "binance_seconds": int(len(px)),
        "binance_span": [int(px.index.min()), int(px.index.max())],
        "note": "strike/finalPrice = Gamma eventMetadata (Chainlink). Intra-window spot/TWAP = Binance 1s close proxy. Aug 16 1s not on data.binance.vision (REST 451).",
        "t6": t6,
        "t7": t7,
        "t8": t8,
        "t9": t9,
    }
    dest = PROC / "tape_stats.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
