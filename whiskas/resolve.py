from __future__ import annotations

import json
from typing import Any, Iterable

from whiskas.constants import GAMMA_API
from whiskas.http import get_json
from whiskas.slug import is_btc_5m, parse_btc_5m_slug
from whiskas.windows import Window, infer_winners_from_redeems, normalize_leg


def winners_from_closed_positions(rows: Iterable[dict[str, Any]]) -> dict[int, str]:
    """curPrice ≈ 1 on a resolved outcome means that leg paid out."""
    scores: dict[int, dict[str, float]] = {}
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug")
        t0 = parse_btc_5m_slug(slug)
        if t0 is None:
            continue
        leg = normalize_leg(row.get("outcome"), row.get("outcomeIndex"))
        if leg is None:
            continue
        price = float(row.get("curPrice") or 0.0)
        scores.setdefault(t0, {})[leg] = price
    out: dict[int, str] = {}
    for t0, legs in scores.items():
        up = legs.get("Up", 0.0)
        down = legs.get("Down", 0.0)
        if up >= 0.99 and down <= 0.01:
            out[t0] = "Up"
        elif down >= 0.99 and up <= 0.01:
            out[t0] = "Down"
        elif up > down and up >= 0.99:
            out[t0] = "Up"
        elif down > up and down >= 0.99:
            out[t0] = "Down"
    return out


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def winner_from_gamma_event(event: dict[str, Any]) -> str | None:
    markets = event.get("markets") or []
    if not markets:
        return None
    market = markets[0]
    outcomes = [str(x) for x in _parse_json_list(market.get("outcomes"))]
    prices = _parse_json_list(market.get("outcomePrices"))
    if len(outcomes) >= 2 and len(prices) >= 2:
        try:
            nums = [float(p) for p in prices]
        except (TypeError, ValueError):
            nums = []
        if nums:
            idx = max(range(len(nums)), key=lambda i: nums[i])
            if nums[idx] >= 0.99:
                return normalize_leg(outcomes[idx], idx)
    return None


def fetch_gamma_winner(slug: str) -> str | None:
    events = get_json(f"{GAMMA_API}/events", {"slug": slug})
    if not isinstance(events, list) or not events:
        return None
    return winner_from_gamma_event(events[0])


def resolve_winners(
    windows: dict[int, Window],
    closed_rows: Iterable[dict[str, Any]],
    *,
    fetch_missing_gamma: bool = True,
    gamma_limit: int | None = None,
) -> dict[str, int]:
    from_redeem = infer_winners_from_redeems(windows)
    from_closed = winners_from_closed_positions(closed_rows)
    merged = dict(from_closed)
    merged.update(from_redeem)

    gamma_n = 0
    missing = [t0 for t0 in windows if t0 not in merged]
    if fetch_missing_gamma:
        if gamma_limit is not None:
            missing = missing[:gamma_limit]
        for i, t0 in enumerate(missing, start=1):
            slug = windows[t0].slug
            if not is_btc_5m(slug):
                continue
            winner = fetch_gamma_winner(slug)
            if winner:
                merged[t0] = winner
                gamma_n += 1
            if i % 25 == 0:
                print(f"  gamma {i}/{len(missing)} resolved_via_gamma={gamma_n}", flush=True)

    for t0, winner in merged.items():
        if t0 in windows:
            windows[t0].winner = winner

    return {
        "from_redeem": len(from_redeem),
        "from_closed": len(from_closed),
        "from_gamma": gamma_n,
        "resolved": sum(1 for w in windows.values() if w.winner),
        "unresolved": sum(1 for w in windows.values() if not w.winner),
    }
