"""Constant-product math for the pump.fun bonding curve and AMM pools."""
from __future__ import annotations

from .events import TOTAL_SUPPLY

# pump.fun launch reserves (virtual)
INITIAL_V_SOL = 30.0
INITIAL_V_TOKENS = 1_073_000_000.0


def mcap_sol(v_sol: float, v_tokens: float) -> float:
    return v_sol / v_tokens * TOTAL_SUPPLY


def buy_tokens_out(v_sol: float, v_tokens: float, sol_in: float) -> float:
    if sol_in <= 0:
        return 0.0
    k = v_sol * v_tokens
    return v_tokens - k / (v_sol + sol_in)


def sell_sol_out(v_sol: float, v_tokens: float, tokens_in: float) -> float:
    if tokens_in <= 0:
        return 0.0
    k = v_sol * v_tokens
    return v_sol - k / (v_tokens + tokens_in)


def apply_buy(v_sol: float, v_tokens: float, sol_in: float):
    out = buy_tokens_out(v_sol, v_tokens, sol_in)
    return v_sol + sol_in, v_tokens - out, out


def apply_sell(v_sol: float, v_tokens: float, tokens_in: float):
    out = sell_sol_out(v_sol, v_tokens, tokens_in)
    return v_sol - out, v_tokens + tokens_in, out
