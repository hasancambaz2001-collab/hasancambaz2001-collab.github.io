"""S1 maker complete-set. Trade candidate. pair<0.90. No pair>1 trade."""

from __future__ import annotations

from typing import Any

from infra.strategies.base import Decision, Strategy
from whiskas.kasa import is_s1, s1_pnl
from whiskas.l2 import BookTick, PolicyMaker


class S1Maker(Strategy):
    name = "s1"
    trade = True

    def __init__(self, *, clip: float = 10.0) -> None:
        self.clip = float(clip)
        self.policy = PolicyMaker(pair_max=0.90, cancel_above=0.92, clip=self.clip, fill="residual")

    def on_window(self, window: dict[str, Any]) -> Decision:
        if not is_s1(window):
            pair = window.get("maker_pair") or window.get("pair")
            return Decision(self.name, False, True, "not_s1", pair=None if pair is None else float(pair))
        usd = s1_pnl(window)
        clip_usd = s1_pnl(window, clip=self.clip)
        return Decision(
            self.name,
            True,
            True,
            "s1_cheap",
            edge=usd,
            measure_edge=usd,
            pair=float(window["maker_pair"]),
            extra={"clip10_edge": clip_usd, "matched": window.get("maker_matched")},
        )

    def on_tick(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        rec, new = self.policy.step(tick, state)
        intend = bool(rec.get("rest") or rec.get("complete"))
        pair = rec.get("bid_sum")
        edge = 0.0
        if rec.get("reason") == "rest" and pair is not None and float(pair) < 0.90:
            edge = float(self.clip) * (1.0 - float(pair))
        if rec.get("complete") and rec.get("complete_pair") is not None:
            edge = float(self.clip) * (1.0 - float(rec["complete_pair"]))
        return (
            Decision(
                self.name,
                intend,
                True,
                str(rec.get("reason") or "watch"),
                edge=edge,
                measure_edge=edge,
                pair=None if pair is None else float(pair),
                extra={"live_order": False, "pair_gt_1": False},
            ),
            new,
        )
