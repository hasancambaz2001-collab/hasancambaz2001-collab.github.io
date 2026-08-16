"""PMData Day API + Slug API. Key from env only. Never write the key. No live.

Day:  GET https://api.pmdata.dev/polymarket/{series}/{data_type}/{series}_{data_type}_{date}.zip
Slug: GET https://api.pmdata.dev/download/{data_type}/{slug}.parquet
      pandas.read_parquet(..., storage_options={api_key, User-Agent})

Post-08-14 5m/15m updown only. Not 06dc daily/monthly. No Mar–May bulk.
2026-08-01 example dates are pre-regime DEBUG.
NautilusTrader has no historical L2. Chainlink/TWAP is not the S1 edge.
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd
import requests

PMDATA_KEYS = ("PMDATA_API_KEY", "PM_DATA_API_KEY", "PMDATA_KEY")
PMDATA_HOST = "https://api.pmdata.dev"
REGIME_CUTOFF = datetime(2026, 8, 14, tzinfo=timezone.utc)
CACHE = Path("data/parquet/pmdata")
TICK = 0.01
DAY_TYPES = ("l2", "trades", "onchain_fills")
# 5m/15m only. 1h exists at PMData but is not the 5m primary signal.
SERIES_5M_15M = (
    "btc-5m",
    "btc-15m",
    "eth-5m",
    "eth-15m",
    "sol-5m",
    "sol-15m",
    "xrp-5m",
    "xrp-15m",
    "doge-5m",
    "doge-15m",
)


def api_key_name() -> str | None:
    for name in PMDATA_KEYS:
        if os.environ.get(name):
            return name
    return None


def api_key() -> str:
    name = api_key_name()
    if not name:
        raise RuntimeError("set PMDATA_API_KEY (not committed). Post-08-14 only. No Mar–May bulk.")
    return os.environ[name]


def auth_headers() -> dict[str, str]:
    return {"api_key": api_key(), "User-Agent": "Mozilla/5.0"}


def is_pmdata_slug(slug: str) -> bool:
    text = str(slug or "").lower()
    if "updown-4h" in text:
        return False
    return "updown-5m-" in text or "updown-15m-" in text


def regime_for_date(data_date: str) -> str:
    day = datetime.fromisoformat(str(data_date)).replace(tzinfo=timezone.utc)
    if day < REGIME_CUTOFF:
        return "pre_2026_08_14_DEBUG"
    return "post_2026_08_14"


def slug_url(data_type: str, slug: str) -> str:
    return f"{PMDATA_HOST}/download/{data_type}/{slug}.parquet"


def day_file_name(series: str, data_type: str, data_date: str) -> str:
    return f"{series}_{data_type}_{data_date}.zip"


def day_url(series: str, data_type: str, data_date: str) -> str:
    name = day_file_name(series, data_type, data_date)
    return f"{PMDATA_HOST}/polymarket/{series}/{data_type}/{name}"


def chainlink_url(symbol: str, kind: str, data_date: str) -> str:
    """Paid Day API shape. Not used for S1 (not residual/TWAP directional)."""
    if kind == "streams":
        return f"{PMDATA_HOST}/chainlink/{symbol}/streams/{symbol}_streams_{data_date}.parquet"
    return f"{PMDATA_HOST}/chainlink/{symbol}/{kind}/{symbol}_{kind}_{data_date}.parquet"


def read_slug(data_type: str, slug: str) -> pd.DataFrame:
    """Slug API via pandas + storage_options, same shape as PMData docs."""
    url = slug_url(data_type, slug)
    headers = auth_headers()
    try:
        return pd.read_parquet(
            url,
            storage_options={"api_key": headers["api_key"], "User-Agent": headers["User-Agent"]},
        )
    except Exception:
        return pd.read_parquet(url, storage_options={"headers": headers})


def download_slug(data_type: str, slug: str, *, dest_dir: Path | None = None) -> Path | None:
    """curl-equivalent: GET slug parquet with api_key header. Cache. 404 → None."""
    dest_dir = dest_dir or (CACHE / "slug" / data_type)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slug}.parquet"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    req = Request(slug_url(data_type, slug), headers=auth_headers())
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urlopen(req, timeout=90) as resp, tmp.open("wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
    except HTTPError as exc:
        if tmp.exists():
            tmp.unlink()
        if exc.code == 404:
            return None
        raise
    tmp.replace(dest)
    return dest


def download_day(
    series: str,
    data_type: str,
    data_date: str,
    *,
    dest_dir: Path | None = None,
    timeout: int = 300,
) -> Path:
    """Day API: requests.get zip with api_key header. Same shape as PMData docs."""
    if data_type not in DAY_TYPES:
        raise ValueError(f"data_type must be one of {DAY_TYPES}")
    dest_dir = dest_dir or (CACHE / "day")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / day_file_name(series, data_type, data_date)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    url = day_url(series, data_type, data_date)
    resp = requests.get(url, headers=auth_headers(), timeout=timeout)
    if resp.status_code == 404:
        raise FileNotFoundError(url)
    resp.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)
    return dest


def list_day_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.namelist()


def read_day_member(zip_path: Path, name: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(name) as fh:
            return pd.read_parquet(io.BytesIO(fh.read()))


def iter_day_parquets(zip_path: Path):
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.endswith(".parquet"):
                continue
            with zf.open(name) as fh:
                yield name, pd.read_parquet(io.BytesIO(fh.read()))


# Back-compat names used by scripts/pmdata_wallet_config.py
download = download_slug
read_parquet = pd.read_parquet


def bbo_timeline(l2: pd.DataFrame) -> pd.DataFrame:
    """Yes-token BBO from book snapshots + price_change. Single-token file — not both legs."""
    rows: list[tuple[Any, float, float]] = []
    for rec in l2.itertuples(index=False):
        et = str(getattr(rec, "event_type", "") or "")
        ts = getattr(rec, "timestamp", None)
        if et == "book":
            bp = getattr(rec, "bid_prices", None)
            ap = getattr(rec, "ask_prices", None)
            try:
                bids = list(bp) if bp is not None else []
                asks = list(ap) if ap is not None else []
            except TypeError:
                continue
            if not bids or not asks:
                continue
            rows.append((ts, float(bids[0]), float(asks[0])))
        elif et == "price_change":
            bb = getattr(rec, "best_bid", None)
            aa = getattr(rec, "best_ask", None)
            if bb is None or aa is None or pd.isna(bb) or pd.isna(aa):
                continue
            rows.append((ts, float(bb), float(aa)))
    out = pd.DataFrame(rows, columns=["timestamp", "best_bid", "best_ask"])
    if out.empty:
        return out
    return out.sort_values("timestamp").reset_index(drop=True)


def bbo_at(bbo: pd.DataFrame, ts: Any) -> tuple[float, float] | None:
    if bbo.empty or ts is None:
        return None
    sub = bbo[bbo["timestamp"] <= ts]
    if sub.empty:
        return None
    row = sub.iloc[-1]
    return float(row.best_bid), float(row.best_ask)


def join_best(*, price: float, outcome: str, best_bid: float, best_ask: float, tick: float = TICK) -> dict[str, bool]:
    """Yes book only. No-leg uses complementary ask (1-best_ask). Not a second L2."""
    oc = str(outcome or "").strip().lower()
    yes = oc in {"yes", "up"}
    return {
        "yes_leg": yes,
        "join_best_yes": bool(yes and abs(float(price) - float(best_bid)) <= tick + 1e-12),
        "join_best_no_comp": bool((not yes) and abs(float(price) - (1.0 - float(best_ask))) <= tick + 1e-12),
    }
