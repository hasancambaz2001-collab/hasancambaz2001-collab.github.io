"""Taker complete-set (A) + leftover complete (A2). No SELL, no maker, no live."""

from __future__ import annotations

from dataclasses import dataclass

from whiskas.constants import CLIP, PAIR_MAX, PAIR_MAX_CAP
from whiskas.fees import taker_fee_usdc

FORBIDDEN_PAIR_MAX = 0.9513
CHEAP_ASK_MAX = 0.45


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


@dataclass
class BookInventory:
    """Per-asset leftover. Never net BTC against ETH."""

    q_up: float = 0.0
    q_down: float = 0.0
    cost_up: float = 0.0
    cost_down: float = 0.0
    fee_up: float = 0.0
    fee_down: float = 0.0
    t0: int | None = None

    def is_flat(self) -> bool:
        return abs(self.q_up - self.q_down) <= 1e-12

    def residual_qty(self) -> float:
        return abs(self.q_up - self.q_down)

    def residual_leg(self) -> str | None:
        if self.q_up > self.q_down + 1e-12:
            return "Up"
        if self.q_down > self.q_up + 1e-12:
            return "Down"
        return None

    def avg(self, leg: str) -> float | None:
        if leg == "Up":
            return (self.cost_up / self.q_up) if self.q_up > 0 else None
        return (self.cost_down / self.q_down) if self.q_down > 0 else None

    def matched(self) -> float:
        return min(self.q_up, self.q_down)

    def traded(self) -> bool:
        return (self.q_up + self.q_down) > 1e-12

    def apply_buy(self, leg: str, size: float, price: float) -> None:
        qty = float(size)
        px = float(price)
        if qty <= 0 or not (0.0 < px < 1.0):
            return
        fee = taker_fee_usdc(qty, px)
        if leg == "Up":
            self.q_up += qty
            self.cost_up += qty * px
            self.fee_up += fee
        elif leg == "Down":
            self.q_down += qty
            self.cost_down += qty * px
            self.fee_down += fee

    def apply_orders(self, orders: tuple[IntendedFOK, ...] | list[IntendedFOK]) -> None:
        for order in orders:
            self.apply_buy(order.outcome, order.size, order.price)

    def pnl_at_resolve(self, winner: str | None) -> float | None:
        if winner not in {"Up", "Down"}:
            return None
        payout = self.q_up if winner == "Up" else self.q_down
        return float(payout) - self.cost_up - self.cost_down - self.fee_up - self.fee_down


def decide_a(
    ask_up: float | None,
    ask_down: float | None,
    size_up: float = 0.0,
    size_down: float = 0.0,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
) -> PolicyDecision:
    """A: flat complete-set. Both asks, sum≤pair_max, min size≥clip. FOK both clip."""
    d = decide(ask_up, ask_down, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    if not d.intend:
        return d
    if min(float(size_up or 0.0), float(size_down or 0.0)) + 1e-12 < float(clip):
        return PolicyDecision(False, "depth_short", d.ask_up, d.ask_down, d.ask_sum, clip)
    return d


def decide_a2(
    ask_up: float | None,
    ask_down: float | None,
    size_up: float = 0.0,
    size_down: float = 0.0,
    inventory: BookInventory | None = None,
    *,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    cheap_max: float = CHEAP_ASK_MAX,
) -> PolicyDecision:
    """A plus first-leg leftover of a valid pair, then complete. Never pair>pair_max."""
    assert_pair_max_legal(pair_max, pair_max_cap)
    inv = inventory or BookInventory()
    su = float(size_up or 0.0)
    sd = float(size_down or 0.0)
    try:
        up = float(ask_up) if ask_up is not None else None
        down = float(ask_down) if ask_down is not None else None
    except (TypeError, ValueError):
        return PolicyDecision(False, "invalid_ask", None, None, None, clip)
    ask_sum = (up + down) if up is not None and down is not None else None

    if inv.is_flat() and inv.traded():
        return PolicyDecision(False, "a2_window_done", up, down, ask_sum, clip)

    if not inv.is_flat():
        held = inv.residual_leg()
        qty = inv.residual_qty()
        avg = inv.avg(held) if held else None
        if held == "Down":
            if up is None or not (0.0 < up < 1.0) or avg is None:
                return PolicyDecision(False, "a2_complete_missing_ask", up, down, ask_sum, clip)
            if avg + up > float(pair_max) + 1e-12:
                return PolicyDecision(False, "a2_complete_above_pair_max", up, down, ask_sum, clip)
            size = min(qty, float(clip), su)
            if size <= 0:
                return PolicyDecision(False, "a2_complete_no_size", up, down, ask_sum, clip)
            return PolicyDecision(
                True,
                "a2_complete",
                up,
                down,
                ask_sum,
                float(clip),
                (IntendedFOK("BUY", "Up", "FOK", up, size),),
            )
        if held == "Up":
            if down is None or not (0.0 < down < 1.0) or avg is None:
                return PolicyDecision(False, "a2_complete_missing_ask", up, down, ask_sum, clip)
            if avg + down > float(pair_max) + 1e-12:
                return PolicyDecision(False, "a2_complete_above_pair_max", up, down, ask_sum, clip)
            size = min(qty, float(clip), sd)
            if size <= 0:
                return PolicyDecision(False, "a2_complete_no_size", up, down, ask_sum, clip)
            return PolicyDecision(
                True,
                "a2_complete",
                up,
                down,
                ask_sum,
                float(clip),
                (IntendedFOK("BUY", "Down", "FOK", down, size),),
            )
        return PolicyDecision(False, "a2_holding", up, down, ask_sum, clip)

    a = decide_a(up, down, su, sd, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    if a.intend:
        return a
    if a.reason != "depth_short":
        return a
    if up is None or down is None:
        return a
    if up <= down:
        cheap_leg, cheap_px, cheap_sz = "Up", up, su
    else:
        cheap_leg, cheap_px, cheap_sz = "Down", down, sd
    if cheap_px > float(cheap_max) + 1e-12:
        return PolicyDecision(False, "a2_cheap_above_045", up, down, ask_sum, clip)
    if cheap_sz <= 0:
        return PolicyDecision(False, "a2_cheap_no_size", up, down, ask_sum, clip)
    size = min(float(clip), cheap_sz)
    return PolicyDecision(
        True,
        "a2_first_leg",
        up,
        down,
        ask_sum,
        float(clip),
        (IntendedFOK("BUY", cheap_leg, "FOK", cheap_px, size),),
    )
