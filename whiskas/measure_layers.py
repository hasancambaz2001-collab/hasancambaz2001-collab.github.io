"""Three measurement layers. Never merge sim_fill and real_fill.

A) INTENT — rest decision (bid_sum<=0.90, min_size>=clip)
B) still250 — cheap+deep still true ~250ms later
C) REAL FILL — only after an order was sent; null on paper
"""

from __future__ import annotations

from typing import Any

PAIR_MAX = 0.90
CLIP_DEFAULT = 10.0
SKIP_REASONS = {
    "rich_bid_sum",
    "thin_bid",
    "missing_bid",
    "gamma_error",
    "clob_error",
    "missing_tokens",
}


def still250_ok(
    bid_sum: float | None,
    min_size: float | None,
    *,
    clip: float,
    pair_max: float = PAIR_MAX,
) -> bool:
    if bid_sum is None or min_size is None:
        return False
    return float(bid_sum) <= float(pair_max) + 1e-12 and float(min_size) + 1e-12 >= float(clip)


def stamp_null_real_fill(rec: dict[str, Any]) -> dict[str, Any]:
    rec["real_fill"] = None
    rec["real_fill_rate"] = None
    rec["pair_gt_1_trade"] = False
    rec["live_order"] = False
    return rec


def attach_layers(
    rec: dict[str, Any],
    *,
    still: dict[str, Any] | None = None,
    clip: float = CLIP_DEFAULT,
    pair_max: float = PAIR_MAX,
    real_fill: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp INTENT / still250 / real_fill. Never writes a merged fill rate."""
    stamp_null_real_fill(rec)
    if real_fill is not None:
        rec["real_fill"] = real_fill
        rested = float(real_fill.get("rested_size") or 0.0)
        filled = float(real_fill.get("filled_size") or 0.0)
        rec["real_fill_rate"] = (filled / rested) if rested > 0 else None
        rec["live_order"] = True
    rec["sim_fill"] = None
    rec["sim_fill_label"] = "SIM"
    reason = str(rec.get("reason") or "")
    bid_sum_0 = rec.get("bid_sum")
    min_size_0 = rec.get("min_bid_size")
    rec["bid_sum_0"] = bid_sum_0
    rec["min_size_0"] = min_size_0
    if reason == "rest":
        rec["intent"] = True
        rec["skip_reason"] = None
        rec["intent_bid_sum"] = bid_sum_0
        rec["intent_min_size"] = min_size_0
        rec["intent_slug"] = rec.get("slug")
        rec["intent_asset"] = rec.get("asset")
        rec["intent_tf"] = rec.get("tf")
        rec["intent_ts"] = rec.get("ts")
    else:
        rec["intent"] = False
        rec["skip_reason"] = reason or rec.get("skip_reason")
    if still is None:
        rec["still250"] = None
        rec["still_there_250ms"] = None
        rec["bid_sum_250"] = None
        rec["min_size_250"] = None
        rec["still250_absent"] = True
    else:
        rec["bid_sum_250"] = still.get("bid_sum_250")
        rec["min_size_250"] = still.get("min_size_250")
        ok = still.get("still_there_250ms")
        if ok is None:
            ok = still250_ok(
                still.get("bid_sum_250"),
                still.get("min_size_250"),
                clip=float(rec.get("clip") or clip),
                pair_max=float(rec.get("pair_max") or pair_max),
            )
        rec["still250"] = bool(ok)
        rec["still_there_250ms"] = bool(ok)
        rec["still250_absent"] = False
    if reason in {"complete", "filled_both"}:
        rec["sim_fill"] = True
    return rec
