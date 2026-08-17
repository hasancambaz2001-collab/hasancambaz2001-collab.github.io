"""Optional historical loaders: warproxxx/poly_data and Jon-Becker PMA."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any


def poly_data_trades_path() -> Path | None:
    raw = os.environ.get("POLY_DATA_DIR") or os.environ.get("POLYEDGE_POLY_DATA")
    if not raw:
        return None
    p = Path(raw)
    for cand in (p / "processed" / "trades.csv", p / "trades.csv"):
        if cand.is_file():
            return cand
    return None


def pma_data_dir() -> Path | None:
    raw = os.environ.get("PMA_DATA_DIR") or os.environ.get("PREDICTION_MARKET_ANALYSIS_DIR")
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else None


def recent_volume_hint(condition_id: str, limit: int = 200) -> dict[str, Any] | None:
    """If poly_data trades.csv exists, return a cheap maker-flow hint."""
    path = poly_data_trades_path()
    if not path:
        return None
    matched = 0
    usd = 0.0
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mid = row.get("market_id") or row.get("condition_id") or ""
            if mid.lower() != condition_id.lower():
                continue
            matched += 1
            try:
                usd += float(row.get("usd_amount") or 0)
            except ValueError:
                pass
            if matched >= limit:
                break
    if not matched:
        return None
    return {"trades": matched, "usd": round(usd, 2), "source": str(path)}
