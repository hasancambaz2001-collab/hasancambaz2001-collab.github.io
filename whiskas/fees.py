from __future__ import annotations

from whiskas.constants import CRYPTO_TAKER_FEE_RATE


def taker_fee_usdc(shares: float, price: float, fee_rate: float = CRYPTO_TAKER_FEE_RATE) -> float:
    """Official formula: fee = C × feeRate × p × (1 − p), rounded to 5 decimals."""
    if shares <= 0 or price <= 0 or price >= 1:
        return 0.0
    fee = shares * fee_rate * price * (1.0 - price)
    return round(fee, 5)


def notional_usdc(shares: float, price: float) -> float:
    return float(shares) * float(price)


def embedded_fee_usdc(usdc: float, shares: float, price: float) -> float:
    """Cash paid minus CLOB price notional. Taker BUY: equals taker_fee_usdc. Maker BUY: ~0."""
    return float(usdc) - notional_usdc(shares, price)


def looks_like_taker(usdc: float, shares: float, price: float, *, eps: float = 0.02) -> bool:
    """BUY ≠ taker. Bid fill (maker) has usdc ≈ size×price; ask take has usdc = notional + fee."""
    return embedded_fee_usdc(usdc, shares, price) > eps
