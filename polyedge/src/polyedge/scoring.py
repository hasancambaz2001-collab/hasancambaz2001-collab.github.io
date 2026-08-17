"""Market attractiveness: reward density + rebate pool − extremity/spread."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MarketScore:
    condition_id: str
    reward_density: float
    rebate_pool: float
    spread: float
    extremity: float
    score: float
    skip_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mid(best_bid: float | None, best_ask: float | None) -> float:
    if best_bid and best_ask:
        return (best_bid + best_ask) / 2.0
    return best_bid or best_ask or 0.5


def rebate_pool(volume_24h: float, fee_rate: float, rebate_rate: float, mid: float) -> float:
    """Whole-market daily maker-rebate pool (trailing volume)."""
    if volume_24h <= 0 or fee_rate <= 0 or rebate_rate <= 0:
        return 0.0
    mid = min(max(mid, 0.01), 0.99)
    daily_fees = volume_24h * fee_rate * (1.0 - mid)
    return daily_fees * rebate_rate


def score_market(
    *,
    condition_id: str,
    daily_rate: float,
    liquidity: float,
    volume_24h: float,
    best_bid: float | None,
    best_ask: float | None,
    fee_rate: float,
    rebate_rate: float,
    quote_size_usdc: float = 100.0,
) -> MarketScore:
    mid = _mid(best_bid, best_ask)
    liq = max(liquidity, quote_size_usdc)
    our_share = min(1.0, quote_size_usdc / liq)
    rd = daily_rate * our_share if daily_rate > 0 else 0.0
    rp = rebate_pool(volume_24h, fee_rate, rebate_rate, mid)
    ext = min(1.0, abs(mid - 0.5) / 0.5)
    spread = max(0.0, (best_ask - best_bid)) if (best_bid and best_ask) else 1.0
    fill_share = min(0.5, quote_size_usdc / max(liquidity, quote_size_usdc))
    income = rd + rp * fill_share
    penalty = (1.0 - 0.5 * ext) * (1.0 / (1.0 + spread * 20.0))
    viability = min(1.0, liquidity / 2500.0) if liquidity > 0 else 0.0
    return MarketScore(
        condition_id=condition_id,
        reward_density=round(rd, 4),
        rebate_pool=round(rp, 4),
        spread=round(spread, 4),
        extremity=round(ext, 4),
        score=round(income * penalty * viability, 4),
    )
