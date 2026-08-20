"""Fee-correct edge. Maker fee0. Taker 0.07*p*(1-p). We are not Diamond."""

from __future__ import annotations

from whiskas.fees import taker_fee_usdc


def maker_fee_usdc(shares: float, price: float) -> float:
    return 0.0


def taker_drag(clip: float, p_up: float, p_down: float) -> float:
    return taker_fee_usdc(clip, p_up) + taker_fee_usdc(clip, p_down)


def complete_set_edge(pair: float, clip: float, *, taker: bool, p_up: float | None = None, p_down: float | None = None) -> float:
    gross = float(clip) * (1.0 - float(pair))
    if not taker:
        return gross
    if p_up is None or p_down is None:
        half = float(pair) / 2.0
        p_up = p_down = half
    return gross - taker_drag(clip, float(p_up), float(p_down))
