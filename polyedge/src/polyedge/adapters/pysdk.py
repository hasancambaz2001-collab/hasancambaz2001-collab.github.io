"""Official Polymarket/py-sdk (polymarket-client) adapter."""

from __future__ import annotations

from typing import Any


def available() -> bool:
    try:
        import polymarket  # noqa: F401

        return True
    except ImportError:
        return False


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def iter_reward_configs(limit: int = 2500) -> list[dict[str, Any]]:
    from polymarket import PublicClient

    rows: list[dict[str, Any]] = []
    with PublicClient() as client:
        for item in client.list_current_rewards().iter_items():
            rows.append(
                {
                    "condition_id": str(item.condition_id),
                    "daily_rate": _f(item.total_daily_rate),
                    "min_size": _f(item.rewards_min_size),
                    "max_spread": _f(item.rewards_max_spread),
                }
            )
            if len(rows) >= limit:
                break
    return rows


def fetch_markets(condition_ids: list[str]) -> list[dict[str, Any]]:
    from polymarket import PublicClient

    if not condition_ids:
        return []
    out: list[dict[str, Any]] = []
    with PublicClient() as client:
        # SDK page_size caps; chunk ids.
        for i in range(0, len(condition_ids), 40):
            chunk = condition_ids[i : i + 40]
            page = client.list_markets(
                condition_ids=chunk, closed=False, page_size=50
            ).first_page()
            for market in page.items:
                out.append(normalize_market(market))
    return out


def normalize_market(market: Any) -> dict[str, Any]:
    outcomes = getattr(market, "outcomes", None)
    yes = getattr(outcomes, "yes", None) if outcomes else None
    no = getattr(outcomes, "no", None) if outcomes else None
    prices = getattr(market, "prices", None)
    metrics = getattr(market, "metrics", None)
    trading = getattr(market, "trading", None)
    rewards = getattr(market, "rewards", None)
    state = getattr(market, "state", None)
    fee_sched = getattr(trading, "fee_schedule", None) if trading else None
    clob = None
    if rewards and getattr(rewards, "clob_rewards", None):
        clob = rewards.clob_rewards[0]
    return {
        "condition_id": str(getattr(market, "condition_id", "") or ""),
        "slug": str(getattr(market, "slug", "") or ""),
        "question": str(getattr(market, "question", "") or ""),
        "yes_token": str(getattr(yes, "token_id", "") or ""),
        "no_token": str(getattr(no, "token_id", "") or ""),
        "best_bid": _f(getattr(prices, "best_bid", None), default=0.0) or None,
        "best_ask": _f(getattr(prices, "best_ask", None), default=0.0) or None,
        "liquidity": _f(getattr(metrics, "liquidity_num", None) or getattr(metrics, "liquidity", None)),
        "volume_24h": _f(getattr(metrics, "volume_24hr", None)),
        "min_order_size": _f(getattr(trading, "minimum_order_size", None), 5.0),
        "tick_size": _f(getattr(trading, "minimum_tick_size", None), 0.01),
        "fees_enabled": bool(getattr(trading, "fees_enabled", False)) if trading else False,
        "fee_rate": _f(getattr(fee_sched, "rate", None)),
        "rebate_rate": _f(getattr(fee_sched, "rebate_rate", None)),
        "fee_type": str(getattr(trading, "fee_type", "") or ""),
        "rewards_daily_rate": _f(getattr(clob, "rewards_daily_rate", None)),
        "rewards_min_size": _f(getattr(rewards, "rewards_min_size", None)),
        "rewards_max_spread": _f(getattr(rewards, "rewards_max_spread", None)),
        "holding": bool(getattr(rewards, "holding_rewards_enabled", False)) if rewards else False,
        "accepting_orders": bool(getattr(state, "accepting_orders", False)) if state else False,
        "enable_order_book": bool(getattr(state, "enable_order_book", False)) if state else False,
        "end_date": str(getattr(state, "end_date", "") or ""),
        "source": "polymarket-client",
    }


def fetch_prices(token_ids: list[str]) -> dict[str, dict[str, float]]:
    from polymarket import PublicClient
    from polymarket.models.clob.requests import PriceRequest

    unique = [str(t) for t in dict.fromkeys(token_ids) if t]
    if not unique:
        return {}
    reqs = []
    for tid in unique:
        reqs.append(PriceRequest(token_id=tid, side="BUY"))
        reqs.append(PriceRequest(token_id=tid, side="SELL"))
    out: dict[str, dict[str, float]] = {}
    with PublicClient() as client:
        raw = client.get_prices(requests=reqs)
    for tid, sides in (raw or {}).items():
        parsed: dict[str, float] = {}
        for side in ("BUY", "SELL"):
            val = (sides or {}).get(side)
            if val is None:
                continue
            parsed[side] = float(val)
        if parsed:
            out[str(tid)] = parsed
    return out
