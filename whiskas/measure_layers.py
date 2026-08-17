"""Three measurement layers. Never merge sim_fill and real_fill.

A) INTENT — rest decision (bid_sum<=0.90, min_size>=clip)
B) still250 — cheap+deep still true ~250ms later
C) REAL FILL — only after an order was sent; null on paper
"""

from __future__ import annotations

from typing import Any

PAIR_MAX = 0.90
CLIP_DEFAULT = 10.0
MIN_SPREAD = 0.01  # 1 tick. 2 ticks would have blocked the 07:59 both-maker.
PREFER_BID_SUM = 0.85  # optional preference only; not a send gate
ASK_FAR = 0.05  # optional "asks far" note; not a send gate
REQUOTE_MAX = 8
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
        if not rec.get("intent_ts"):
            rec["intent_ts"] = rec.get("ts")
    else:
        rec["intent"] = False
        rec["skip_reason"] = reason or rec.get("skip_reason")
    if still is None:
        rec["still250"] = None
        rec["still_there_250ms"] = None
        rec["bid_sum_250"] = None
        rec["min_size_250"] = None
        rec["bid_up_250"] = None
        rec["bid_down_250"] = None
        rec["ask_up_250"] = None
        rec["ask_down_250"] = None
        rec["still250_absent"] = True
    else:
        rec["bid_sum_250"] = still.get("bid_sum_250")
        rec["min_size_250"] = still.get("min_size_250")
        rec["bid_up_250"] = still.get("bid_up_250")
        rec["bid_down_250"] = still.get("bid_down_250")
        rec["ask_up_250"] = still.get("ask_up_250")
        rec["ask_down_250"] = still.get("ask_down_250")
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


def guard_still250_send(rec: dict[str, Any], *, pair_max: float = PAIR_MAX) -> str | None:
    """SEND YOK unless still250 is true and bid_sum_250 <= pair_max. Shared by paper + live."""
    if rec.get("still_there_250ms") is not True:
        return "still250_false"
    bid_250 = rec.get("bid_sum_250")
    if bid_250 is None:
        return "still250_false"
    if float(bid_250) > float(pair_max) + 1e-12:
        return "bid_sum_250_gt_pair_max"
    return None


def guard_maker_join(rec: dict[str, Any], *, require_ask: bool = False) -> str | None:
    """SEND YOK if a join bid is at or through the ask. Maker GTC only. No clip/pair change."""
    up = rec.get("bid_up_250", rec.get("bid_up"))
    down = rec.get("bid_down_250", rec.get("bid_down"))
    ask_up = rec.get("ask_up_250", rec.get("ask_up"))
    ask_down = rec.get("ask_down_250", rec.get("ask_down"))
    if up is None or down is None:
        return "not_best_bid" if require_ask else None
    if ask_up is None or ask_down is None:
        return "missing_ask" if require_ask else None
    if float(up) + 1e-12 >= float(ask_up) or float(down) + 1e-12 >= float(ask_down):
        return "would_be_taker_blocked"
    return None


def guard_min_spread(rec: dict[str, Any], *, min_spread: float = MIN_SPREAD, require_ask: bool = False) -> str | None:
    """First send: each leg ask−bid >= 1 tick. Depth stays clip via still250 / thin_bid."""
    up = rec.get("bid_up_250", rec.get("bid_up"))
    down = rec.get("bid_down_250", rec.get("bid_down"))
    ask_up = rec.get("ask_up_250", rec.get("ask_up"))
    ask_down = rec.get("ask_down_250", rec.get("ask_down"))
    if up is None or down is None:
        return "not_best_bid" if require_ask else None
    if ask_up is None or ask_down is None:
        return "missing_ask" if require_ask else None
    if (float(ask_up) - float(up)) + 1e-12 < float(min_spread):
        return "thin_spread"
    if (float(ask_down) - float(down)) + 1e-12 < float(min_spread):
        return "thin_spread"
    return None


def apply_still250_send_gate(rec: dict[str, Any], *, pair_max: float = PAIR_MAX) -> dict[str, Any]:
    blocked = guard_still250_send(rec, pair_max=pair_max)
    if blocked is None:
        blocked = guard_maker_join(rec)
    if blocked is None:
        blocked = guard_min_spread(rec)
    rec["would_be_taker_blocked"] = blocked == "would_be_taker_blocked"
    rec["send_blocked"] = blocked
    rec["would_send"] = blocked is None and str(rec.get("reason") or "") == "rest"
    rec.setdefault("both_fill", None)
    rec.setdefault("one_leg_taker", None)
    rec.setdefault("off_touch", None)
    return rec
