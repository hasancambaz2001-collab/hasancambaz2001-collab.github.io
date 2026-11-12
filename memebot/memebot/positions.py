"""Open positions and the exit policy (incl. 'take principal out at 3x')."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import ExitCfg
from .features import TokenState


@dataclass
class Fill:
    ts: float
    side: str
    sol: float      # buy: SOL spent (all-in); sell: SOL received (net)
    tokens: float
    reason: str = ""

    @property
    def price(self) -> float:
        return self.sol / self.tokens if self.tokens else 0.0


@dataclass
class Position:
    mint: str
    symbol: str
    opened_ts: float
    cost_sol: float
    tokens: float
    entry_signals: dict = field(default_factory=dict)
    realized_sol: float = 0.0
    recovered: bool = False
    recovered_ts: Optional[float] = None
    peak_price: float = 0.0
    peak_net_multiple: float = 0.0
    ladder_idx: int = 0
    dev_sold_at_entry: float = 0.0
    fills: list = field(default_factory=list)
    closed_ts: Optional[float] = None
    exit_reasons: list = field(default_factory=list)

    @property
    def entry_price(self) -> float:
        return self.cost_sol / self.tokens if self.tokens else 0.0

    @property
    def closed(self) -> bool:
        return self.closed_ts is not None

    @property
    def pnl_sol(self) -> float:
        return self.realized_sol - self.cost_sol

    def apply_sell(self, f: Fill) -> None:
        self.tokens = max(0.0, self.tokens - f.tokens)
        self.realized_sol += f.sol
        self.fills.append(f)
        self.exit_reasons.append(f.reason)
        if self.tokens <= 1e-6:
            self.tokens = 0.0
            self.closed_ts = f.ts


@dataclass
class SellOrder:
    tokens: float
    reason: str
    kind: str  # recover | ladder | full


Quote = Callable[[TokenState, float], float]  # (state, tokens) -> net SOL


def tokens_to_recover(pos: Position, st: TokenState, quote: Quote, target_sol: float) -> float:
    """Smallest token amount whose net sale proceeds >= target_sol (binary search)."""
    lo, hi = 0.0, pos.tokens
    if quote(st, hi) < target_sol:
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if quote(st, mid) >= target_sol:
            hi = mid
        else:
            lo = mid
    return hi


def decide_exit(pos: Position, st: TokenState, now: float, cfg: ExitCfg, quote: Quote,
                entry_initial_tokens: float) -> Optional[SellOrder]:
    if pos.closed or pos.tokens <= 0:
        return None
    price = st.price
    pos.peak_price = max(pos.peak_price, price)
    net_all = quote(st, pos.tokens)
    # multiple of *original* cost that the remaining bag + realised cash represents
    net_mult = (net_all + pos.realized_sol) / pos.cost_sol if pos.cost_sol else 0.0
    pos.peak_net_multiple = max(pos.peak_net_multiple, net_mult)

    # --- rug detection: always first ---
    if st.dev_initial_tokens > 0:
        dev_sold_since = (st.dev_sold_tokens - pos.dev_sold_at_entry) / st.dev_initial_tokens * 100
        if dev_sold_since >= cfg.rug_dev_sell_pct:
            return SellOrder(pos.tokens, f"rug:dev_sold_{dev_sold_since:.0f}%", "full")
    if st.last_drop_ts > pos.opened_ts and st.last_drop_ts >= now - 1e-9 and st.last_drop_pct >= cfg.rug_single_drop_pct:
        return SellOrder(pos.tokens, f"rug:drop_{st.last_drop_pct:.0f}%", "full")

    if now - pos.opened_ts >= cfg.max_hold_s:
        return SellOrder(pos.tokens, "max_hold", "full")

    if not pos.recovered:
        if net_mult <= 1 - cfg.stop_loss_pct / 100:
            return SellOrder(pos.tokens, f"stop_loss {net_mult:.2f}x", "full")
        if cfg.breakeven_arm_multiple and pos.peak_net_multiple >= cfg.breakeven_arm_multiple and net_mult <= 1.0:
            return SellOrder(pos.tokens, "breakeven_stop", "full")
        if net_mult >= cfg.recover_at_multiple:
            need = pos.cost_sol - pos.realized_sol
            amt = tokens_to_recover(pos, st, quote, need)
            if amt >= pos.tokens * 0.999:
                return SellOrder(pos.tokens, "recover_all", "full")
            return SellOrder(amt, f"recover_principal@{net_mult:.2f}x", "recover")
        if now - pos.opened_ts >= cfg.max_hold_before_recovery_s:
            return SellOrder(pos.tokens, "time_stop", "full")
        return None

    # --- house money: ladder + trailing ---
    mult = price / pos.entry_price if pos.entry_price else 0.0
    if pos.ladder_idx < len(cfg.ladder):
        lvl, frac = cfg.ladder[pos.ladder_idx]
        if mult >= lvl:
            amt = min(pos.tokens, entry_initial_tokens * frac)
            return SellOrder(amt, f"ladder@{lvl:g}x", "ladder")
    if pos.peak_price > 0 and price <= pos.peak_price * (1 - cfg.trailing_drawdown_pct / 100):
        return SellOrder(pos.tokens, f"trailing_stop peak={pos.peak_price / pos.entry_price:.1f}x", "full")
    return None
