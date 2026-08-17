"""Maker-only two-sided quotes (poly-maker model, paper-safe).

reservation r = FV - skew(inventory)
half-spread δ = max(min_ticks * tick, clamped into the reward band)
BUY YES at r - δ
BUY NO at (1 - r) - δ

Both legs are bids. If both fill, merge back to $1 at locked edge 1 - p - q.
Never cross the ask (post-only).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


def clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def round_to_tick(price: float, tick: float, *, up: bool) -> float:
    if tick <= 0:
        tick = 0.01
    n = price / tick
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    p = round(n * tick, decimals + 2)
    return clamp(p, tick, 1.0 - tick)


def order_score(spread_from_mid: float, max_spread: float) -> float:
    """Official quadratic S(v,s) = ((v-s)/v)^2. Zero outside the band."""
    if max_spread <= 0 or spread_from_mid < 0:
        return 0.0
    if spread_from_mid > max_spread:
        return 0.0
    return ((max_spread - spread_from_mid) / max_spread) ** 2


@dataclass(frozen=True)
class BookTouch:
    best_bid: float | None
    best_ask: float | None


@dataclass(frozen=True)
class Quote:
    token: str
    side: str  # BUY or SELL
    outcome: str  # YES or NO
    price: float
    size: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuoteSet:
    yes: Quote | None
    no: Quote | None
    fair_value: float
    half_spread: float
    locked_edge: float
    capital_usdc: float
    reward_score: float
    two_sided: bool
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "yes": self.yes.as_dict() if self.yes else None,
            "no": self.no.as_dict() if self.no else None,
            "fair_value": self.fair_value,
            "half_spread": self.half_spread,
            "locked_edge": self.locked_edge,
            "capital_usdc": self.capital_usdc,
            "reward_score": self.reward_score,
            "two_sided": self.two_sided,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class QuoteParams:
    gamma: float = 0.6
    delta_min_ticks: int = 2
    min_edge_ticks: int = 1
    reward_size_mult: float = 1.25
    inventory_yes: float = 0.0
    inventory_no: float = 0.0
    q_max_usdc: float = 150.0


def _place_bid(
    target: float,
    touch: BookTouch,
    tick: float,
    fv: float,
    min_edge_ticks: int,
) -> float | None:
    price = target
    price = min(price, fv - min_edge_ticks * tick)
    if touch.best_bid is not None and price >= touch.best_bid:
        price = touch.best_bid
    if touch.best_ask is not None and price >= touch.best_ask:
        price = touch.best_ask - tick
    p = round_to_tick(price, tick, up=False)
    if p <= 0 or p >= 1:
        return None
    if touch.best_ask is not None and p >= touch.best_ask:
        return None
    return p


def construct_quotes(
    *,
    yes_token: str,
    no_token: str,
    yes_touch: BookTouch,
    no_touch: BookTouch,
    tick: float,
    min_size: float,
    max_spread_cents: float,
    params: QuoteParams | None = None,
    size_shares: float | None = None,
) -> QuoteSet:
    params = params or QuoteParams()
    tick = tick if tick > 0 else 0.01
    notes: list[str] = []

    y_bid, y_ask = yes_touch.best_bid, yes_touch.best_ask
    if y_bid and y_ask and y_ask > y_bid:
        fv = (y_bid + y_ask) / 2.0
    elif y_bid:
        fv = y_bid
    elif y_ask:
        fv = y_ask
    else:
        fv = 0.5
        notes.append("no-yes-touch-default-fv")
    fv = clamp(fv, tick, 1.0 - tick)

    net = params.inventory_yes - params.inventory_no
    q_max_shares = params.q_max_usdc / max(fv, tick)
    u = clamp(net / q_max_shares, -1.0, 1.0) if q_max_shares > 0 else 0.0
    skew = params.gamma * 0.01 * u  # quiet-tape default vol ~1c

    base = params.delta_min_ticks * tick
    reward_band = max(max_spread_cents / 100.0, 0.0)
    delta = base
    if reward_band > 0:
        delta = clamp(delta, tick, max(tick, reward_band * 0.45))
    else:
        delta = max(base, tick)

    r = fv - skew
    yes_px = _place_bid(r - delta, yes_touch, tick, fv, params.min_edge_ticks)
    no_px = _place_bid((1.0 - r) - delta, no_touch, tick, 1.0 - fv, params.min_edge_ticks)

    size = size_shares if size_shares is not None else max(min_size * params.reward_size_mult, min_size)
    size = round(max(size, min_size), 2)

    yes_q = Quote(yes_token, "BUY", "YES", yes_px, size) if yes_px else None
    no_q = Quote(no_token, "BUY", "NO", no_px, size) if no_px else None

    mid = fv
    band = max_spread_cents
    s_yes = abs((yes_px - mid) * 100.0) if yes_px else 999.0
    s_no = abs((no_px - (1.0 - mid)) * 100.0) if no_px else 999.0
    q_one = order_score(s_yes, band) * size if yes_q else 0.0
    q_two = order_score(s_no, band) * size if no_q else 0.0
    two_sided = bool(yes_q and no_q)
    if 0.10 <= mid <= 0.90:
        reward = max(min(q_one, q_two), max(q_one, q_two) / 3.0)
    else:
        reward = min(q_one, q_two) if two_sided else 0.0
        if not two_sided:
            notes.append("extreme-mid-requires-two-sided")

    locked = 0.0
    capital = 0.0
    if yes_q:
        capital += yes_q.price * yes_q.size
    if no_q:
        capital += no_q.price * no_q.size
    if yes_q and no_q:
        locked = max(0.0, 1.0 - yes_q.price - no_q.price)
        if locked <= 0:
            notes.append("bids-sum-not-below-1")

    return QuoteSet(
        yes=yes_q,
        no=no_q,
        fair_value=round(fv, 6),
        half_spread=round(delta, 6),
        locked_edge=round(locked, 6),
        capital_usdc=round(capital, 4),
        reward_score=round(reward, 4),
        two_sided=two_sided,
        notes=tuple(notes),
    )
