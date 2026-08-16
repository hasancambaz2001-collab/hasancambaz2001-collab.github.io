"""Nautilus-shaped paper engine for S1. Reads PAPER_ONLY. Never posts.

Uses nautilus_trader core QuoteTick/InstrumentId only.
Does NOT import adapters.polymarket (that pulls a live CLOB client).
Does NOT set size_ok. Does NOT write G5/G6 flags. Does NOT write LIVE_READY.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from whiskas.l2 import BookTick, PolicyMaker
from whiskas.live_config import PAPER_ONLY, paper_only_payload
from whiskas.config import load_config


def probe_nautilus() -> dict[str, Any]:
    try:
        import nautilus_trader
    except ImportError:
        return {"installed": False, "historical_l2": False, "live": False}
    version = getattr(nautilus_trader, "__version__", "unknown")
    return {
        "installed": True,
        "version": version,
        "polymarket_extra": False,
        "historical_l2": False,
        "live": False,
        "note": "core QuoteTick only. No execution client. No historical L2.",
    }


def _paper_cfg() -> dict[str, Any]:
    if PAPER_ONLY.is_file():
        cfg = load_config(PAPER_ONLY)
    else:
        cfg = paper_only_payload()
    return {
        "pair_max": float(cfg.get("pair_max", 0.90)),
        "cancel_above": float(cfg.get("cancel_above", 0.92)),
        "clip": float(cfg.get("clip", 10)),
        "live_orders": False,
        "pair_gt_1_trade": False,
        "size_ok": False,
        "shadow_only": True,
    }


def booktick_to_quotes(tick: BookTick) -> list[Any]:
    """Map one complete-set BookTick to two Nautilus QuoteTicks (Up/Down)."""
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.objects import Price, Quantity

    venue = Venue("PAPER")
    ts = int(max(float(tick.t), 0.0) * 1_000_000_000)
    out: list[Any] = []
    legs = (
        ("UP", tick.bu, tick.au, tick.su, tick.sau),
        ("DOWN", tick.bd, tick.ad, tick.sd, tick.sad),
    )
    for name, bid, ask, bsz, asz in legs:
        if bid is None or ask is None:
            continue
        iid = InstrumentId(Symbol(f"{tick.asset.upper()}-{tick.tf.upper()}-{name}"), venue)
        out.append(
            QuoteTick(
                iid,
                Price.from_str(f"{float(bid):.2f}"),
                Price.from_str(f"{float(ask):.2f}"),
                Quantity.from_str(f"{max(float(bsz or 0.0), 0.01):.2f}"),
                Quantity.from_str(f"{max(float(asz or 0.0), 0.01):.2f}"),
                ts,
                ts,
            )
        )
    return out


class NautilusPaperEngine:
    """Drive PolicyMaker from BookTicks, keep Nautilus quotes as the data bus."""

    def __init__(self) -> None:
        self.cfg = _paper_cfg()
        self.policy = PolicyMaker(
            pair_max=self.cfg["pair_max"],
            cancel_above=self.cfg["cancel_above"],
            clip=self.cfg["clip"],
            fill="residual",
        )
        self.probe = probe_nautilus()

    def run(self, ticks: Iterable[BookTick], *, max_ticks: int = 0) -> dict[str, Any]:
        if not self.probe.get("installed"):
            raise RuntimeError("nautilus_trader not installed")
        states: dict[str, dict[str, Any] | None] = {}
        reasons: Counter[str] = Counter()
        n = 0
        n_quotes = 0
        n_rest = 0
        for tick in ticks:
            quotes = booktick_to_quotes(tick)
            n_quotes += len(quotes)
            rec, states[tick.slug] = self.policy.step(tick, states.get(tick.slug))
            reasons[str(rec.get("reason") or "none")] += 1
            if rec.get("reason") == "rest":
                n_rest += 1
            if rec.get("live_order"):
                raise RuntimeError("nautilus paper produced live_order")
            n += 1
            if max_ticks and n >= int(max_ticks):
                break
        return {
            "engine": "nautilus_paper",
            "nautilus": self.probe,
            "n_ticks": n,
            "n_quotes": n_quotes,
            "n_rest": n_rest,
            "reasons": dict(reasons),
            "live_orders": False,
            "size_ok": False,
            "pair_gt_1_trade": False,
            "g5_g6_unlocked": False,
            "clip": self.cfg["clip"],
            "pair_max": self.cfg["pair_max"],
            "shadow_only": True,
            "note": "paper bus only. do not live without G5 G6",
        }
