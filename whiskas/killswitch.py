from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KillDecision:
    halt: bool
    reason: str


def rolling_win_rate(results: list[bool], window: int = 50) -> float | None:
    if len(results) < window:
        return None
    chunk = results[-window:]
    return sum(1 for x in chunk if x) / float(window)


def day_pnl_halt(day_pnl: float, start_equity: float, threshold: float = -0.08) -> bool:
    if start_equity <= 0:
        return day_pnl < 0
    return (day_pnl / start_equity) <= threshold


def evaluate_kill(
    window_wins: list[bool],
    day_pnl: float,
    start_equity: float,
    *,
    wr_window: int = 50,
    wr_min: float = 0.52,
    day_dd: float = -0.08,
) -> KillDecision:
    wr = rolling_win_rate(window_wins, wr_window)
    if wr is not None and wr < wr_min:
        return KillDecision(True, f"rolling_{wr_window}_wr={wr:.3f}<{wr_min}")
    if day_pnl_halt(day_pnl, start_equity, day_dd):
        return KillDecision(True, f"day_pnl={day_pnl:.4f} <= {day_dd:.0%} of equity")
    return KillDecision(False, "ok")
