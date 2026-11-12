"""Normalised market events and the PumpPortal message parser."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

TOTAL_SUPPLY = 1_000_000_000.0  # pump.fun tokens always mint 1B (UI units)


@dataclass(frozen=True)
class NewToken:
    ts: float
    mint: str
    creator: str
    name: str
    symbol: str
    initial_buy_tokens: float
    initial_buy_sol: float
    v_sol: Optional[float]
    v_tokens: Optional[float]
    mcap_sol: float
    signature: str = ""


@dataclass(frozen=True)
class Trade:
    ts: float
    mint: str
    trader: str
    side: str  # "buy" | "sell"
    sol: float
    tokens: float
    new_balance: Optional[float]
    v_sol: Optional[float]
    v_tokens: Optional[float]
    mcap_sol: float
    pool: str = "pump"
    signature: str = ""

    @property
    def price(self) -> float:
        """SOL per token (UI units)."""
        return self.mcap_sol / TOTAL_SUPPLY


@dataclass(frozen=True)
class Migration:
    ts: float
    mint: str
    pool: str = "pump-amm"
    signature: str = ""


Event = Union[NewToken, Trade, Migration]


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _mcap(msg: dict) -> float:
    mc = _f(msg.get("marketCapSol"))
    if mc:
        return mc
    vs, vt = _f(msg.get("vSolInBondingCurve")), _f(msg.get("vTokensInBondingCurve"))
    if vs and vt:
        return vs / vt * TOTAL_SUPPLY
    return 0.0


def parse_pumpportal(msg: dict, ts: float) -> Optional[Event]:
    """Turn one PumpPortal websocket JSON message into an Event (or None).

    Field names follow PumpPortal's data API (wss://pumpportal.fun/api/data).
    Unknown / acknowledgement messages return None.
    """
    if not isinstance(msg, dict):
        return None
    tx = str(msg.get("txType") or "").lower()
    mint = msg.get("mint")
    if not mint or not tx:
        return None
    sig = msg.get("signature", "") or ""

    if tx == "create":
        return NewToken(
            ts=ts,
            mint=mint,
            creator=msg.get("traderPublicKey", "") or "",
            name=str(msg.get("name", ""))[:64],
            symbol=str(msg.get("symbol", ""))[:32],
            initial_buy_tokens=_f(msg.get("initialBuy"), 0.0),
            initial_buy_sol=_f(msg.get("solAmount"), 0.0),
            v_sol=_f(msg.get("vSolInBondingCurve")),
            v_tokens=_f(msg.get("vTokensInBondingCurve")),
            mcap_sol=_mcap(msg),
            signature=sig,
        )
    if tx in ("buy", "sell"):
        return Trade(
            ts=ts,
            mint=mint,
            trader=msg.get("traderPublicKey", "") or "",
            side=tx,
            sol=_f(msg.get("solAmount"), 0.0),
            tokens=_f(msg.get("tokenAmount"), 0.0),
            new_balance=_f(msg.get("newTokenBalance")),
            v_sol=_f(msg.get("vSolInBondingCurve")),
            v_tokens=_f(msg.get("vTokensInBondingCurve")),
            mcap_sol=_mcap(msg),
            pool=str(msg.get("pool") or "pump"),
            signature=sig,
        )
    if tx.startswith("migrat"):
        return Migration(ts=ts, mint=mint, pool=str(msg.get("pool") or "pump-amm"), signature=sig)
    return None
