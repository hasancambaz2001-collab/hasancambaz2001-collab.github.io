"""PMData slug downloads. Key from env only. Never write the key. No live.

Post-08-14 5m/15m updown only. Not 06dc daily/monthly. No Mar–May bulk.
NautilusTrader has no historical L2 (orderbook-history is dead). PMData is the L2 source.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pandas as pd

PMDATA_KEYS = ("PMDATA_API_KEY", "PM_DATA_API_KEY", "PMDATA_KEY")
PMDATA_BASE = "https://api.pmdata.dev/download"
REGIME_CUTOFF = datetime(2026, 8, 14, tzinfo=timezone.utc)
CACHE = Path("data/parquet/pmdata")
TICK = 0.01


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


def is_pmdata_slug(slug: str) -> bool:
    text = str(slug or "").lower()
    if "updown-4h" in text:
        return False
    return "updown-5m-" in text or "updown-15m-" in text


def download(dtype: str, slug: str, *, dest_dir: Path | None = None) -> Path | None:
    """GET /download/{dtype}/{slug}.parquet. Cache under data/parquet/pmdata. 404 → None."""
    dest_dir = dest_dir or (CACHE / dtype)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slug}.parquet"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    url = f"{PMDATA_BASE}/{dtype}/{slug}.parquet"
    tmp = dest.with_suffix(dest.suffix + ".part")
    key = api_key()
    req = Request(url, headers={"api_key": key, "User-Agent": "Mozilla/5.0"})
    try:
        from urllib.request import urlopen

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


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


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
