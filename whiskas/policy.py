"""Taker complete-set policy. BUY both asks FOK. No SELL, no residual, no maker."""

from __future__ import annotations

from dataclasses import dataclass

from whiskas.constants import CLIP, PAIR_MAX, PAIR_MAX_CAP
from whiskas.fees import taker_fee_usdc

FORBIDDEN_PAIR_MAX = 0.9513


def assert_pair_max_legal(pair_max: float, pair_max_cap: float = PAIR_MAX_CAP) -> None:
    if abs(float(pair_max) - FORBIDDEN_PAIR_MAX) < 1e-9:
        raise ValueError("pair_max 0.9513 is forbidden (broken PHASE1 p25, not a gate)")
    if float(pair_max) > float(pair_max_cap) + 1e-12:
        raise ValueError(f"pair_max {pair_max} exceeds cap {pair_max_cap}")
    if float(pair_max_cap) > 0.97 + 1e-12:
        raise ValueError("pair_max_cap above 0.97 is forbidden")


@dataclass(frozen=True)
class IntendedFOK:
    side: str
    outcome: str
    order_type: str
    price: float
    size: float

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "outcome": self.outcome,
            "type": self.order_type,
            "price": self.price,
            "size": self.size,
        }


@dataclass(frozen=True)
class PolicyDecision:
    intend: bool
    reason: str
    ask_up: float | None
    ask_down: float | None
    ask_sum: float | None
    clip: float
    orders: tuple[IntendedFOK, ...] = ()

    def to_dict(self) -> dict:
        return {
            "intend": self.intend,
            "reason": self.reason,
            "ask_up": self.ask_up,
            "ask_down": self.ask_down,
            "ask_sum": self.ask_sum,
            "clip": self.clip,
            "orders": [o.to_dict() for o in self.orders],
        }


def complete_set_pnl(
    ask_up: float,
    ask_down: float,
    clip: float = CLIP,
    *,
    diamond_rebate: bool = False,
) -> float:
    """Winner-independent: redeem clip after resolve. No rebate unless Diamond (we are not)."""
    if diamond_rebate:
        raise ValueError("Diamond rebate is their edge, not ours")
    ask_sum = float(ask_up) + float(ask_down)
    gross = float(clip) * (1.0 - ask_sum)
    fees = taker_fee_usdc(clip, ask_up) + taker_fee_usdc(clip, ask_down)
    return gross - fees


def decide(
    ask_up: float | None,
    ask_down: float | None,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
) -> PolicyDecision:
    """Intend two BUY FOKs iff both asks exist and ask_sum ≤ pair_max. Never SELL."""
    assert_pair_max_legal(pair_max, pair_max_cap)
    if ask_up is None or ask_down is None:
        return PolicyDecision(False, "missing_ask", ask_up, ask_down, None, clip)
    try:
        up = float(ask_up)
        down = float(ask_down)
    except (TypeError, ValueError):
        return PolicyDecision(False, "invalid_ask", None, None, None, clip)
    if not (0.0 < up < 1.0 and 0.0 < down < 1.0):
        return PolicyDecision(False, "invalid_ask", up, down, up + down, clip)
    ask_sum = up + down
    if ask_sum > float(pair_max) + 1e-12:
        return PolicyDecision(False, "ask_sum_above_pair_max", up, down, ask_sum, clip)
    orders = (
        IntendedFOK("BUY", "Up", "FOK", up, float(clip)),
        IntendedFOK("BUY", "Down", "FOK", down, float(clip)),
    )
    return PolicyDecision(True, "complete_set_fok", up, down, ask_sum, float(clip), orders)
