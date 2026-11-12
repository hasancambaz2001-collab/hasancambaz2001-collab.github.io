"""Portfolio-level guard rails. Every entry must pass these."""
from __future__ import annotations

import os
from collections import deque

from .config import RiskCfg


class RiskManager:
    def __init__(self, cfg: RiskCfg, base_dir: str = "."):
        self.cfg = cfg
        self.kill_path = os.path.join(base_dir, cfg.kill_switch_file)
        self.entries: deque = deque()   # ts of entries
        self.closes: deque = deque()    # (ts, pnl_sol)

    def _prune(self, now: float):
        while self.entries and now - self.entries[0] > 3600:
            self.entries.popleft()
        while self.closes and now - self.closes[0][0] > 86400:
            self.closes.popleft()

    def loss_24h(self, now: float) -> float:
        self._prune(now)
        return -sum(p for _, p in self.closes)

    def can_enter(self, now: float, open_count: int, at_risk_sol: float) -> tuple[bool, str]:
        self._prune(now)
        c = self.cfg
        if os.path.exists(self.kill_path):
            return False, "kill_switch"
        if open_count >= c.max_open_positions:
            return False, "max_open_positions"
        if at_risk_sol + c.position_size_sol > c.max_total_exposure_sol + 1e-12:
            return False, "max_exposure"
        if self.loss_24h(now) >= c.max_daily_loss_sol:
            return False, "daily_loss_limit"
        if len(self.entries) >= c.max_entries_per_hour:
            return False, "max_entries_per_hour"
        return True, ""

    def on_entry(self, now: float):
        self.entries.append(now)

    def on_close(self, now: float, pnl_sol: float):
        self.closes.append((now, pnl_sol))
