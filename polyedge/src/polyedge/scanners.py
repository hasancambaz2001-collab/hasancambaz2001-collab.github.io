"""Paper-only scanners. No order placement, no private keys."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import clob, gamma
from .fees import (
    FeeSchedule,
    completeness_net_edge,
    dutch_book_net_edge,
    reverse_completeness_net_edge,
)


@dataclass
class CompletenessHit:
    kind: str
    question: str
    slug: str
    yes_px: float
    no_px: float
    raw_gap: float
    net_edge: float
    fee_rate: float
    fees_enabled: bool
    fee_type: str
    volume_24h: float
    url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DutchHit:
    title: str
    slug: str
    n_outcomes: int
    sum_asks: float
    net_edge: float
    fee_rate: float
    outcomes: list[str]
    url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RewardRow:
    question: str
    slug: str
    daily_rate: float
    min_size: float
    max_spread: float
    liquidity: float
    volume_24h: float
    farm_score: float
    fee_type: str
    holding: bool
    url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HoldingRow:
    question: str
    slug: str
    best_bid: float | None
    best_ask: float | None
    volume_24h: float
    liquidity: float
    end_date: str
    url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    completeness: list[CompletenessHit] = field(default_factory=list)
    dutch: list[DutchHit] = field(default_factory=list)
    rewards: list[RewardRow] = field(default_factory=list)
    holding: list[HoldingRow] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "completeness": [x.as_dict() for x in self.completeness],
            "dutch": [x.as_dict() for x in self.dutch],
            "rewards": [x.as_dict() for x in self.rewards],
            "holding": [x.as_dict() for x in self.holding],
            "stats": self.stats,
        }


def _market_url(slug: str) -> str:
    return f"https://polymarket.com/market/{slug}" if slug else "https://polymarket.com"


def _event_url(slug: str) -> str:
    return f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def scan_rewards(markets: list[dict], *, min_daily: float = 1.0, top: int = 25) -> list[RewardRow]:
    rows: list[RewardRow] = []
    for market in markets:
        daily = gamma.daily_reward(market)
        if daily < min_daily:
            continue
        liq = _f(market.get("liquidityNum") or market.get("liquidity"))
        vol = _f(market.get("volume24hr"))
        # Higher daily pool and thinner book => less crowded farm (heuristic).
        farm_score = daily / (1.0 + liq / 25_000.0 + vol / 50_000.0)
        slug = str(market.get("slug") or "")
        rows.append(
            RewardRow(
                question=str(market.get("question") or ""),
                slug=slug,
                daily_rate=daily,
                min_size=_f(market.get("rewardsMinSize")),
                max_spread=_f(market.get("rewardsMaxSpread")),
                liquidity=liq,
                volume_24h=vol,
                farm_score=round(farm_score, 4),
                fee_type=str(market.get("feeType") or "none"),
                holding=bool(market.get("holdingRewardsEnabled")),
                url=_market_url(slug),
            )
        )
    rows.sort(key=lambda r: r.farm_score, reverse=True)
    return rows[:top]


def scan_holding(markets: list[dict], *, top: int = 40) -> list[HoldingRow]:
    rows: list[HoldingRow] = []
    for market in markets:
        if not market.get("holdingRewardsEnabled"):
            continue
        slug = str(market.get("slug") or "")
        rows.append(
            HoldingRow(
                question=str(market.get("question") or ""),
                slug=slug,
                best_bid=_f(market.get("bestBid")) if market.get("bestBid") is not None else None,
                best_ask=_f(market.get("bestAsk")) if market.get("bestAsk") is not None else None,
                volume_24h=_f(market.get("volume24hr")),
                liquidity=_f(market.get("liquidityNum") or market.get("liquidity")),
                end_date=str(market.get("endDate") or market.get("endDateIso") or ""),
                url=_market_url(slug),
            )
        )
    rows.sort(key=lambda r: r.volume_24h, reverse=True)
    return rows[:top]


def scan_completeness(
    markets: list[dict],
    *,
    min_net_edge: float = 0.004,
    max_books: int = 400,
) -> list[CompletenessHit]:
    binary: list[dict] = []
    token_ids: list[str] = []
    for market in markets:
        if not market.get("enableOrderBook"):
            continue
        ids = gamma.parse_token_ids(market)
        outcomes = gamma.parse_outcomes(market)
        if len(ids) < 2 or len(outcomes) < 2:
            continue
        binary.append(market)
        token_ids.extend(ids[:2])
        if len(binary) >= max_books:
            break
    prices = clob.fetch_prices(token_ids)
    hits: list[CompletenessHit] = []
    for market in binary:
        ids = gamma.parse_token_ids(market)
        yes_id, no_id = ids[0], ids[1]
        yes = prices.get(yes_id) or {}
        no = prices.get(no_id) or {}
        y_ask, n_ask = yes.get("SELL"), no.get("SELL")
        y_bid, n_bid = yes.get("BUY"), no.get("BUY")
        slug = str(market.get("slug") or "")
        schedule = FeeSchedule.from_market(market)
        fee_type = str(market.get("feeType") or "none")
        vol = _f(market.get("volume24hr"))
        q = str(market.get("question") or "")
        if y_ask and n_ask:
            raw = 1.0 - (y_ask + n_ask)
            net = completeness_net_edge(y_ask, n_ask, market)
            if net >= min_net_edge:
                hits.append(
                    CompletenessHit(
                        kind="buy_both",
                        question=q,
                        slug=slug,
                        yes_px=y_ask,
                        no_px=n_ask,
                        raw_gap=round(raw, 6),
                        net_edge=round(net, 6),
                        fee_rate=schedule.rate,
                        fees_enabled=schedule.enabled,
                        fee_type=fee_type,
                        volume_24h=vol,
                        url=_market_url(slug),
                    )
                )
        if y_bid and n_bid:
            raw = (y_bid + n_bid) - 1.0
            net = reverse_completeness_net_edge(y_bid, n_bid, market)
            if net >= min_net_edge:
                hits.append(
                    CompletenessHit(
                        kind="sell_both_after_split",
                        question=q,
                        slug=slug,
                        yes_px=y_bid,
                        no_px=n_bid,
                        raw_gap=round(raw, 6),
                        net_edge=round(net, 6),
                        fee_rate=schedule.rate,
                        fees_enabled=schedule.enabled,
                        fee_type=fee_type,
                        volume_24h=vol,
                        url=_market_url(slug),
                    )
                )
    hits.sort(key=lambda h: h.net_edge, reverse=True)
    return hits


def scan_dutch(
    events: list[dict],
    *,
    min_net_edge: float = 0.008,
    min_outcomes: int = 3,
    max_outcomes: int = 24,
) -> list[DutchHit]:
    """Neg-risk events: one winner. Buying every YES should pay $1 if exhaustive."""
    wanted: list[tuple[dict, list[dict], list[str]]] = []
    token_ids: list[str] = []
    for event in events:
        if not event.get("negRisk") and not event.get("enableNegRisk"):
            continue
        markets = [m for m in (event.get("markets") or []) if m.get("enableOrderBook") and not m.get("closed")]
        if not (min_outcomes <= len(markets) <= max_outcomes):
            continue
        yes_tokens: list[str] = []
        usable: list[dict] = []
        for market in markets:
            ids = gamma.parse_token_ids(market)
            if not ids:
                continue
            yes_tokens.append(ids[0])
            usable.append(market)
        if not (min_outcomes <= len(usable) <= max_outcomes):
            continue
        wanted.append((event, usable, yes_tokens))
        token_ids.extend(yes_tokens)
    prices = clob.fetch_prices(token_ids)
    hits: list[DutchHit] = []
    for event, markets, yes_tokens in wanted:
        asks: list[float] = []
        labels: list[str] = []
        missing = False
        for market, tid in zip(markets, yes_tokens):
            ask = (prices.get(tid) or {}).get("SELL")
            if not ask:
                missing = True
                break
            asks.append(ask)
            labels.append(str(market.get("groupItemTitle") or market.get("question") or tid)[:48])
        if missing or not asks:
            continue
        # Use the fattest fee schedule among legs (conservative).
        fee_market = max(markets, key=lambda m: FeeSchedule.from_market(m).rate)
        net = dutch_book_net_edge(asks, fee_market)
        if net < min_net_edge:
            continue
        slug = str(event.get("slug") or "")
        hits.append(
            DutchHit(
                title=str(event.get("title") or ""),
                slug=slug,
                n_outcomes=len(asks),
                sum_asks=round(sum(asks), 6),
                net_edge=round(net, 6),
                fee_rate=FeeSchedule.from_market(fee_market).rate,
                outcomes=labels,
                url=_event_url(slug),
            )
        )
    hits.sort(key=lambda h: h.net_edge, reverse=True)
    return hits


def run_scan(
    *,
    max_markets: int = 1200,
    max_events: int = 40,
    max_books: int = 350,
    min_arb_edge: float = 0.004,
) -> ScanResult:
    markets = list(gamma.iter_markets(max_markets=max_markets))
    events = list(gamma.iter_events(max_events=max_events))
    rewards = scan_rewards(markets)
    holding = scan_holding(markets)
    completeness = scan_completeness(markets, min_net_edge=min_arb_edge, max_books=max_books)
    dutch = scan_dutch(events, min_net_edge=max(min_arb_edge, 0.008))
    rewarded = sum(1 for m in markets if gamma.daily_reward(m) >= 1.0)
    hold_n = sum(1 for m in markets if m.get("holdingRewardsEnabled"))
    return ScanResult(
        completeness=completeness,
        dutch=dutch,
        rewards=rewards,
        holding=holding,
        stats={
            "markets_scanned": len(markets),
            "events_scanned": len(events),
            "markets_with_daily_reward_ge_1": rewarded,
            "holding_reward_markets": hold_n,
            "completeness_hits": len(completeness),
            "dutch_hits": len(dutch),
            "note": (
                "Paper scan only. Completeness/dutch use live CLOB /prices. "
                "Net edge subtracts official taker fees. Depth is not walked; "
                "size at the touch may be tiny."
            ),
        },
    )
