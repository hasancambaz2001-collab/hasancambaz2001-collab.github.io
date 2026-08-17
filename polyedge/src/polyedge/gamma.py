"""Polymarket Gamma API (market + event discovery)."""

from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.parse import urlencode

from .http import request_json

GAMMA = "https://gamma-api.polymarket.com"


def _as_list(raw: Any) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def parse_token_ids(market: dict) -> list[str]:
    return [str(x) for x in _as_list(market.get("clobTokenIds")) if x]


def parse_outcomes(market: dict) -> list[str]:
    return [str(x) for x in _as_list(market.get("outcomes"))]


def iter_markets(
    *,
    limit_per_page: int = 100,
    max_markets: int = 1500,
    extra_params: dict | None = None,
) -> Iterator[dict]:
    fetched = 0
    offset = 0
    while fetched < max_markets:
        page = min(limit_per_page, max_markets - fetched)
        params = {
            "closed": "false",
            "active": "true",
            "limit": page,
            "offset": offset,
        }
        if extra_params:
            params.update(extra_params)
        url = f"{GAMMA}/markets?{urlencode(params)}"
        batch = request_json(url) or []
        if not isinstance(batch, list) or not batch:
            break
        for market in batch:
            yield market
            fetched += 1
            if fetched >= max_markets:
                break
        if len(batch) < page:
            break
        offset += len(batch)


def iter_events(
    *,
    limit_per_page: int = 50,
    max_events: int = 80,
    extra_params: dict | None = None,
) -> Iterator[dict]:
    fetched = 0
    offset = 0
    while fetched < max_events:
        page = min(limit_per_page, max_events - fetched)
        params = {
            "closed": "false",
            "active": "true",
            "limit": page,
            "offset": offset,
            "order": "volume24hr",
            "ascending": "false",
        }
        if extra_params:
            params.update(extra_params)
        url = f"{GAMMA}/events?{urlencode(params)}"
        batch = request_json(url) or []
        if not isinstance(batch, list) or not batch:
            break
        for event in batch:
            yield event
            fetched += 1
            if fetched >= max_events:
                break
        if len(batch) < page:
            break
        offset += len(batch)


def daily_reward(market: dict) -> float:
    rewards = market.get("clobRewards") or []
    if not rewards:
        return 0.0
    first = rewards[0] if isinstance(rewards, list) else rewards
    try:
        return float(first.get("rewardsDailyRate") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
