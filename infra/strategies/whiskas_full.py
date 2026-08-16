"""Whiskas ask-FOK (legacy) + full measure (pair>1 ATTR only). trade=false."""

from __future__ import annotations

from typing import Any

from infra.strategies.base import Decision, Strategy
from whiskas.fees import taker_fee_usdc
from whiskas.kasa import is_s3, s3_pnl
from whiskas.l2 import BookTick
from whiskas.policy import decide


class WhiskasAskFok(Strategy):
    """Legacy ask-FOK. Never primary 5m PnL."""

    name = "whiskas"
    trade = False

    def __init__(self, *, clip: float = 21.0) -> None:
        self.clip = float(clip)

    def on_window(self, window: dict[str, Any]) -> Decision:
        if is_s3(window):
            usd = s3_pnl(window)
            return Decision(self.name, True, False, "s3_taker_le_096", edge=0.0, measure_edge=usd, pair=float(window["taker_pair"]))
        pair = window.get("taker_pair") or window.get("pair")
        return Decision(self.name, False, False, "legacy_ask_fok_skip", pair=None if pair is None else float(pair))

    def on_tick(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        d = decide(tick.au, tick.ad, pair_max=0.96, clip=self.clip)
        edge = 0.0
        if d.intend and d.ask_sum is not None:
            edge = self.clip * (1.0 - float(d.ask_sum)) - (
                taker_fee_usdc(self.clip, float(tick.au or 0)) + taker_fee_usdc(self.clip, float(tick.ad or 0))
            )
        return Decision(self.name, d.intend, False, d.reason, edge=0.0, measure_edge=edge, pair=d.ask_sum), state


class WhiskasFullMeasure(Strategy):
    """Attribution including pair>1. trade=false. Not a license to trade pair>1."""

    name = "whiskas_full_measure"
    trade = False

    def __init__(self, *, clip: float = 21.0, allow_pair_gt1: bool = True) -> None:
        self.clip = float(clip)
        self.allow_pair_gt1 = bool(allow_pair_gt1)

    def on_window(self, window: dict[str, Any]) -> Decision:
        pair = window.get("taker_pair")
        if pair is None:
            pair = window.get("pair")
        if pair is None:
            return Decision(self.name, False, False, "no_pair")
        pair_f = float(pair)
        size = float(window.get("taker_matched") or window.get("matched") or 0.0)
        fee = float(window.get("taker_fee") or 0.0)
        usd = size * (1.0 - pair_f) - fee
        if pair_f + 1e-12 >= 1.0:
            if not self.allow_pair_gt1:
                return Decision(self.name, False, False, "pair_gt_1_skipped", pair=pair_f)
            return Decision(
                self.name,
                False,
                False,
                "pair_gt_1_attr",
                edge=0.0,
                measure_edge=usd,
                pair=pair_f,
                extra={"allow_pair_gt1": True, "trade": False},
            )
        return Decision(self.name, False, False, "pair_lt_1_attr", edge=0.0, measure_edge=usd, pair=pair_f)

    def on_tick(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        pair = tick.ask_sum
        if pair is None:
            return Decision(self.name, False, False, "missing_ask"), state
        usd = self.clip * (1.0 - float(pair))
        if float(pair) + 1e-12 >= 1.0:
            return (
                Decision(self.name, False, False, "pair_gt_1_attr", edge=0.0, measure_edge=usd, pair=float(pair)),
                state,
            )
        return Decision(self.name, False, False, "pair_lt_1_attr", edge=0.0, measure_edge=usd, pair=float(pair)), state
