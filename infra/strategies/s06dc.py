"""06dc R1/R4/R5/R6. R7 gated.

5m/15m L2 recorder does NOT cover 06dc daily/monthly books.
Those ticks are smoke. 06dc truth = dump + paper_06dc + T6.
"""

from __future__ import annotations

from typing import Any

from infra.strategies.base import Decision, Strategy
from scripts.paper_06dc import decide_06dc
from whiskas.fees import taker_fee_usdc
from whiskas.l2 import BookTick

# l2_recorder TFs only. Daily/monthly 06dc books are not in data/l2.
L2_SHORT_TF = frozenset({"5m", "15m"})
L2_COVERS_06DC = False
TRUTH = "dump + paper_06dc + T6"


def _kind(slug: str) -> str:
    text = str(slug or "").lower()
    if "up-or-down-on" in text:
        return "daily_ud"
    if "above" in text or "between" in text or "reach" in text or "what-price" in text:
        return "bracket"
    return "smoke_5m"


def _l2_short_tf(tf: str | None) -> bool:
    return str(tf or "").strip().lower() in L2_SHORT_TF


def smoke_decision(*, pair: float | None = None, kind: str = "smoke_5m") -> Decision:
    return Decision(
        "s06dc",
        False,
        False,
        "smoke_5m_not_daily",
        pair=pair,
        extra={"kind": kind, "r7": False, "smoke": True, "l2_covers_06dc": False, "truth": TRUTH},
    )


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
        extra = {"kind": kind, "r7": self.r7, "smoke": kind == "smoke_5m", "l2_covers_06dc": False, "truth": TRUTH}
        if kind == "smoke_5m":
            return smoke_decision(pair=pair_f, kind=kind)
        if pair_f + 1e-12 >= 1.0:
            return Decision(self.name, False, False, "pair_ge_1", pair=pair_f, extra=extra)
        # R6-style maker both if pair<0.99 on daily
        if kind == "daily_ud" and pair_f <= 0.99 + 1e-12:
            edge = float(window.get("matched") or 0.0) * (1.0 - pair_f)
            return Decision(self.name, True, False, "r6_measure", edge=0.0, measure_edge=edge, pair=pair_f, extra=extra)
        return Decision(self.name, False, False, "watch", pair=pair_f, extra=extra)

    def on_tick(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        kind = _kind(tick.slug)
        # Recorder ticks are 5m/15m updown. Never 06dc daily/monthly truth.
        if _l2_short_tf(tick.tf) or kind == "smoke_5m":
            return smoke_decision(pair=tick.bid_sum, kind=kind), state
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
                extra={
                    "rule": rec.get("rule"),
                    "kind": kind,
                    "r7": self.r7,
                    "smoke": False,
                    "l2_covers_06dc": False,
                    "truth": TRUTH,
                },
            ),
            state,
        )
