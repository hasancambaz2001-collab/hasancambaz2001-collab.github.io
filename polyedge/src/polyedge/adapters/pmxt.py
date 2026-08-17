"""pmxt-dev/pmxt — optional Kalshi/cross-venue complement check."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from ..http import request_json


def available() -> bool:
    return bool(os.environ.get("PMXT_API_KEY"))


def kalshi_complements(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """If PMXT_API_KEY is set, search the hosted catalog. Else Kalshi public API."""
    key = os.environ.get("PMXT_API_KEY")
    if key:
        try:
            url = f"https://api.pmxt.dev/v0/markets?query={quote(query)}&limit={limit}&exchange=kalshi"
            data = request_json(
                url,
                retries=2,
                extra_headers={"Authorization": f"Bearer {key}"},
            )
            if isinstance(data, dict):
                return list(data.get("markets") or data.get("data") or [])[:limit]
            if isinstance(data, list):
                return data[:limit]
        except Exception:
            pass
    # Public Kalshi (no key). Best-effort title search.
    try:
        url = (
            "https://api.elections.kalshi.com/trade-api/v2/markets"
            f"?limit={limit}&status=open"
        )
        data = request_json(url, retries=2) or {}
        markets = data.get("markets") or []
        q = query.lower()
        words = [w for w in q.replace("?", "").split() if len(w) > 3][:4]
        hits = []
        for m in markets:
            title = str(m.get("title") or m.get("ticker") or "").lower()
            if words and sum(1 for w in words if w in title) >= 2:
                hits.append(
                    {
                        "venue": "kalshi",
                        "ticker": m.get("ticker"),
                        "title": m.get("title"),
                        "yes_ask": m.get("yes_ask"),
                        "yes_bid": m.get("yes_bid"),
                    }
                )
            if len(hits) >= limit:
                break
        return hits
    except Exception:
        return []
