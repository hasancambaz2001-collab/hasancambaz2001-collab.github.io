"""Per-token state built purely from the trade stream (no RPC needed)."""
from __future__ import annotations

import heapq
from collections import deque
from typing import Optional

from .events import TOTAL_SUPPLY, Migration, NewToken, Trade


class TokenState:
    HIST_S = 600.0

    def __init__(self, ev: NewToken, snipe_window_s: float = 3.0):
        self._snipe_window = snipe_window_s
        self.mint = ev.mint
        self.symbol = ev.symbol
        self.name = ev.name
        self.creator = ev.creator
        self.created_ts = ev.ts
        self.last_ts = ev.ts
        self.dev_initial_tokens = ev.initial_buy_tokens
        self.dev_sold_tokens = 0.0
        self.balances: dict[str, float] = {}
        if ev.creator and ev.initial_buy_tokens > 0:
            self.balances[ev.creator] = ev.initial_buy_tokens
        self.buyers: set[str] = set()
        self.sniper_tokens = 0.0
        self.n_buys = 0
        self.n_sells = 0
        self.total_buy_sol = 0.0
        self.total_sell_sol = 0.0
        self.max_single_buy_sol = 0.0
        self.mcap = ev.mcap_sol
        self.peak_mcap = ev.mcap_sol
        self.v_sol: Optional[float] = ev.v_sol
        self.v_tokens: Optional[float] = ev.v_tokens
        self.migrated_ts: Optional[float] = None
        self.migration_mcap: Optional[float] = None
        self.last_drop_pct = 0.0
        self.last_drop_ts = 0.0
        # (ts, side, sol, is_new_buyer)
        self.recent: deque = deque()
        # (ts, mcap)
        self.mcap_hist: deque = deque([(ev.ts, ev.mcap_sol)])

    # ---------------- updates ----------------
    def on_trade(self, t: Trade) -> None:
        prev = self.mcap
        self.last_ts = t.ts
        is_new = False
        if t.side == "buy":
            self.n_buys += 1
            self.total_buy_sol += t.sol
            self.max_single_buy_sol = max(self.max_single_buy_sol, t.sol)
            if t.trader not in self.buyers:
                self.buyers.add(t.trader)
                is_new = True
            if t.trader != self.creator and t.ts - self.created_ts <= self._snipe_window:
                self.sniper_tokens += t.tokens
        else:
            self.n_sells += 1
            self.total_sell_sol += t.sol
            if t.trader == self.creator:
                self.dev_sold_tokens += t.tokens
        bal = self.balances.get(t.trader, 0.0)
        if t.new_balance is not None:
            bal = t.new_balance
        else:
            bal = bal + t.tokens if t.side == "buy" else max(0.0, bal - t.tokens)
        if bal > 0:
            self.balances[t.trader] = bal
        else:
            self.balances.pop(t.trader, None)

        if t.mcap_sol > 0:
            self.mcap = t.mcap_sol
            self.peak_mcap = max(self.peak_mcap, t.mcap_sol)
            if t.side == "sell" and prev > 0:
                drop = (1 - t.mcap_sol / prev) * 100
                if drop > 0:
                    self.last_drop_pct, self.last_drop_ts = drop, t.ts
            self.mcap_hist.append((t.ts, t.mcap_sol))
        # bonding-curve reserves are only meaningful while still on the curve
        if t.pool == "pump" and self.migrated_ts is None and t.v_sol and t.v_tokens:
            self.v_sol, self.v_tokens = t.v_sol, t.v_tokens
        self.recent.append((t.ts, t.side, t.sol, is_new))
        self._prune(t.ts)

    def on_migration(self, m: Migration) -> None:
        self.migrated_ts = m.ts
        self.migration_mcap = self.mcap
        self.v_sol = self.v_tokens = None  # switch to AMM pricing model
        self.last_ts = m.ts

    def _prune(self, now: float) -> None:
        while self.recent and now - self.recent[0][0] > self.HIST_S:
            self.recent.popleft()
        while len(self.mcap_hist) > 1 and now - self.mcap_hist[1][0] > self.HIST_S:
            self.mcap_hist.popleft()

    # ---------------- metrics ----------------
    @property
    def price(self) -> float:
        return self.mcap / TOTAL_SUPPLY

    @property
    def on_curve(self) -> bool:
        return self.migrated_ts is None and bool(self.v_sol) and bool(self.v_tokens)

    def age(self, now: float) -> float:
        return now - self.created_ts

    def dev_initial_pct(self) -> float:
        return self.dev_initial_tokens / TOTAL_SUPPLY * 100

    def dev_sold_pct(self) -> float:
        if self.dev_initial_tokens <= 0:
            return 0.0
        return min(100.0, self.dev_sold_tokens / self.dev_initial_tokens * 100)

    def sniper_pct(self) -> float:
        return self.sniper_tokens / TOTAL_SUPPLY * 100

    def top10_pct(self, exclude: set[str] | None = None) -> float:
        vals = (v for k, v in self.balances.items() if not exclude or k not in exclude)
        return sum(heapq.nlargest(10, vals)) / TOTAL_SUPPLY * 100

    def unique_buyers(self) -> int:
        return len(self.buyers)

    def single_buy_share(self) -> float:
        return self.max_single_buy_sol / self.total_buy_sol if self.total_buy_sol > 0 else 1.0

    def window(self, now: float, secs: float = 60.0) -> dict:
        buys = sells = new = 0
        inflow = 0.0
        for ts, side, sol, is_new in reversed(self.recent):
            if now - ts > secs:
                break
            if side == "buy":
                buys += 1
                inflow += sol
                new += is_new
            else:
                sells += 1
                inflow -= sol
        past = self.mcap_at(now - secs)
        return {
            "buys": buys,
            "sells": sells,
            "buy_sell_ratio": buys / sells if sells else float(buys),
            "net_inflow_sol": inflow,
            "new_buyers": new,
            "mcap_momentum": self.mcap / past if past > 0 else 1.0,
        }

    def mcap_at(self, ts: float) -> float:
        best = self.mcap_hist[0][1]
        for t, m in self.mcap_hist:
            if t > ts:
                break
            best = m
        return best

    def snapshot(self, now: float) -> dict:
        w = self.window(now)
        return {
            "age_s": round(self.age(now), 1),
            "mcap_sol": round(self.mcap, 2),
            "dev_initial_pct": round(self.dev_initial_pct(), 2),
            "dev_sold_pct": round(self.dev_sold_pct(), 1),
            "sniper_pct": round(self.sniper_pct(), 2),
            "top10_pct": round(self.top10_pct(), 2),
            "unique_buyers": self.unique_buyers(),
            "single_buy_share": round(self.single_buy_share(), 3),
            "migrated": self.migrated_ts is not None,
            **{f"w60_{k}": round(v, 3) for k, v in w.items()},
        }
