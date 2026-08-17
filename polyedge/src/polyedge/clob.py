"""Polymarket CLOB public market-data helpers.

Important: `/book` levels are often sorted from the *outside* of the book
inward. Never take asks[0] / bids[0] as best. Use `/prices` or min/max.
"""

from __future__ import annotations

from .http import request_json

CLOB = "https://clob.polymarket.com"
PRICE_BATCH = 120


def fetch_prices(token_ids: list[str]) -> dict[str, dict[str, float]]:
    """Return {token_id: {BUY: best_bid, SELL: best_ask}}."""
    unique = [str(t) for t in dict.fromkeys(token_ids) if t]
    out: dict[str, dict[str, float]] = {}
    for i in range(0, len(unique), PRICE_BATCH):
        chunk = unique[i : i + PRICE_BATCH]
        payload = []
        for tid in chunk:
            payload.append({"token_id": tid, "side": "BUY"})
            payload.append({"token_id": tid, "side": "SELL"})
        raw = request_json(f"{CLOB}/prices", method="POST", payload=payload) or {}
        if not isinstance(raw, dict):
            continue
        for tid, sides in raw.items():
            if not isinstance(sides, dict):
                continue
            parsed: dict[str, float] = {}
            for side in ("BUY", "SELL"):
                val = sides.get(side)
                if val is None or val == "":
                    continue
                try:
                    parsed[side] = float(val)
                except (TypeError, ValueError):
                    continue
            if parsed:
                out[str(tid)] = parsed
    return out


def best_bid_ask(prices: dict[str, dict[str, float]], token_id: str) -> tuple[float | None, float | None]:
    row = prices.get(str(token_id)) or {}
    return row.get("BUY"), row.get("SELL")
