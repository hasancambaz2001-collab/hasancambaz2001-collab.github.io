"""06dc R1/R4/R5/R6. R7 gated. 5m ticks = smoke. Real 06dc needs daily + T6."""

from __future__ import annotations

from typing import Any

from infra.strategies.base import Decision, Strategy
from scripts.paper_06dc import decide_06dc
from whiskas.fees import taker_fee_usdc
from whiskas.l2 import BookTick


def _kind(slug: str) -> str:
    text = str(slug or "").lower()
    if "up-or-down-on" in text:
        return "daily_ud"
    if "above" in text or "between" in text or "reach" in text or "what-price" in text:
        return "bracket"
    return "smoke_5m"


class S06dc(Strategy):
    name = "s06dc"
    trade = False

    def __init__(self, *, clip: float = 20.0, r7: bool = False) -> None:
        self.clip = float(clip)
        self.r7 = bool(r7)

    def on_window(self, window: dict[str, Any]) -> Decision:
        slug = str(window.get("slug") or "")
        kind = _kind(slug)
        pair = window.get("pair")
        if pair is None:
            return Decision(self.name, False, False, "no_pair")
        pair_f = float(pair)
        extra = {"kind": kind, "r7": self.r7, "smoke": kind == "smoke_5m"}
        if kind == "smoke_5m":
            return Decision(self.name, False, False, "smoke_5m_not_daily", pair=pair_f, extra=extra)
        if pair_f + 1e-12 >= 1.0:
            return Decision(self.name, False, False, "pair_ge_1", pair=pair_f, extra=extra)
        # R6-style maker both if pair<0.99 on daily
        if kind == "daily_ud" and pair_f <= 0.99 + 1e-12:
            edge = float(window.get("matched") or 0.0) * (1.0 - pair_f)
            return Decision(self.name, True, False, "r6_measure", edge=0.0, measure_edge=edge, pair=pair_f, extra=extra)
        return Decision(self.name, False, False, "watch", pair=pair_f, extra=extra)

    def on_tick(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        kind = _kind(tick.slug)
        if kind == "smoke_5m":
            return (
                Decision(
                    self.name,
                    False,
                    False,
                    "smoke_5m_not_daily",
                    pair=tick.bid_sum,
                    extra={"kind": kind, "r7": self.r7, "smoke": True},
                ),
                state,
            )
        rec = decide_06dc(
            kind="daily_ud" if kind == "daily_ud" else ("bracket" if kind == "bracket" else "daily_ud"),
            yes_ask=tick.au,
            no_ask=tick.ad,
            yes_bid=tick.bu,
            no_bid=tick.bd,
            depth_yes=tick.sau,
            depth_no=tick.sad,
            clip=self.clip,
        )
        if kind == "smoke_5m":
            rec["rule"] = rec.get("rule")
        edge = 0.0
        if rec.get("r3") and rec.get("ask_sum") is not None:
            pair = float(rec["ask_sum"])
            fee = taker_fee_usdc(self.clip, float(tick.au or 0)) + taker_fee_usdc(self.clip, float(tick.ad or 0))
            edge = self.clip * (1.0 - pair) - fee
        elif rec.get("r6") and rec.get("bid_sum") is not None:
            edge = self.clip * (1.0 - float(rec["bid_sum"]))
        return (
            Decision(
                self.name,
                bool(rec.get("taker_intend") or rec.get("maker_intend")),
                False,
                str(rec.get("reason") or "watch"),
                edge=0.0,
                measure_edge=edge,
                pair=rec.get("bid_sum") or rec.get("ask_sum"),
                extra={"rule": rec.get("rule"), "kind": kind, "r7": self.r7, "smoke": kind == "smoke_5m"},
            ),
            state,
        )
