"""Polymarket CLOB V2 taker-fee math.

Official formula (docs.polymarket.com/trading/fees):

    fee = shares * fee_rate * price * (1 - price)

Makers pay 0. Taker fees peak at p=0.50 and vanish at the extremes.
Geopolitics / world-event markets are fee-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Fallback rates when Gamma does not attach a feeSchedule (category docs, Aug 2026).
CATEGORY_TAKER_RATE = {
    "crypto": 0.07,
    "crypto_fees": 0.07,
    "crypto_fees_v2": 0.07,
    "sports": 0.05,
    "sports_fees": 0.05,
    "sports_fees_v2": 0.05,
    "finance": 0.04,
    "finance_fees": 0.04,
    "politics": 0.04,
    "politics_fees": 0.04,
    "economics": 0.05,
    "economics_fees": 0.05,
    "culture": 0.05,
    "culture_fees": 0.05,
    "weather": 0.05,
    "weather_fees": 0.05,
    "other": 0.05,
    "general": 0.05,
    "mentions": 0.04,
    "mentions_fees": 0.04,
    "tech": 0.04,
    "tech_fees": 0.04,
    "geopolitics": 0.0,
    "geopolitics_fees": 0.0,
}

CATEGORY_MAKER_REBATE = {
    "crypto": 0.20,
    "sports": 0.15,
    "finance": 0.25,
    "politics": 0.25,
    "economics": 0.25,
    "culture": 0.25,
    "weather": 0.25,
    "other": 0.25,
    "general": 0.25,
    "mentions": 0.25,
    "tech": 0.25,
    "geopolitics": 0.0,
}


@dataclass(frozen=True)
class FeeSchedule:
    rate: float
    rebate_rate: float = 0.0
    taker_only: bool = True
    enabled: bool = True

    @classmethod
    def from_market(cls, market: dict) -> "FeeSchedule":
        enabled = bool(market.get("feesEnabled"))
        raw = market.get("feeSchedule") or {}
        if isinstance(raw, dict) and raw.get("rate") is not None:
            return cls(
                rate=float(raw.get("rate") or 0.0) if enabled else 0.0,
                rebate_rate=float(raw.get("rebateRate") or 0.0),
                taker_only=bool(raw.get("takerOnly", True)),
                enabled=enabled,
            )
        fee_type = str(market.get("feeType") or "").lower()
        rate = CATEGORY_TAKER_RATE.get(fee_type, 0.0 if not enabled else 0.05)
        if not enabled:
            rate = 0.0
        return cls(rate=rate, rebate_rate=0.0, taker_only=True, enabled=enabled)


def taker_fee(shares: float, price: float, rate: float) -> float:
    """USDC taker fee for `shares` bought/sold at `price`."""
    if shares <= 0 or rate <= 0:
        return 0.0
    if price <= 0 or price >= 1:
        return 0.0
    fee = shares * rate * price * (1.0 - price)
    # Protocol rounds to 5 decimals; sub-0.00001 rounds to zero.
    rounded = round(fee, 5)
    return 0.0 if rounded < 0.00001 else rounded


def taker_fee_from_market(shares: float, price: float, market: dict) -> float:
    schedule = FeeSchedule.from_market(market)
    return taker_fee(shares, price, schedule.rate)


def completeness_net_edge(
    yes_ask: float,
    no_ask: float,
    market: dict,
    shares: float = 1.0,
) -> float:
    """Guaranteed payout is 1.0 per share if both YES and NO are held.

    Net edge per share after lifting both asks as a taker.
    Negative means the 'arb' is a fee illusion.
    """
    if yes_ask <= 0 or no_ask <= 0:
        return float("-inf")
    schedule = FeeSchedule.from_market(market)
    fees = taker_fee(shares, yes_ask, schedule.rate) + taker_fee(
        shares, no_ask, schedule.rate
    )
    cost = shares * (yes_ask + no_ask) + fees
    return (shares - cost) / shares


def reverse_completeness_net_edge(
    yes_bid: float,
    no_bid: float,
    market: dict,
    shares: float = 1.0,
) -> float:
    """Sell both sides (after splitting $1 into YES+NO). Gross proceeds minus $1 and fees."""
    if yes_bid <= 0 or no_bid <= 0:
        return float("-inf")
    schedule = FeeSchedule.from_market(market)
    fees = taker_fee(shares, yes_bid, schedule.rate) + taker_fee(
        shares, no_bid, schedule.rate
    )
    proceeds = shares * (yes_bid + no_bid) - fees
    return (proceeds - shares) / shares


def dutch_book_net_edge(asks: list[float], market: dict, shares: float = 1.0) -> float:
    """Buy every mutually exclusive YES ask. Pays $1 if the set is exhaustive."""
    if not asks or any(a <= 0 for a in asks):
        return float("-inf")
    schedule = FeeSchedule.from_market(market)
    fees = sum(taker_fee(shares, p, schedule.rate) for p in asks)
    cost = shares * sum(asks) + fees
    return (shares - cost) / shares


def category_key(fee_type: Optional[str]) -> str:
    if not fee_type:
        return "unknown"
    key = fee_type.lower()
    for prefix in (
        "crypto",
        "sports",
        "finance",
        "politics",
        "economics",
        "culture",
        "weather",
        "mentions",
        "tech",
        "geopolitics",
    ):
        if key.startswith(prefix):
            return prefix
    return key
