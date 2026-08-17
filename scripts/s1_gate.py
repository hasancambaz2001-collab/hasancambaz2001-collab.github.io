"""S1 first-send gate for fixture verify only.

Not a sender. Does not post orders. Locks: clip 5, pair_max 0.90, no pair>1,
maker-only (join < ask), still250 on first send.
"""

from __future__ import annotations

from typing import Any

PAIR_MAX = 0.90
CLIP = 5.0
MIN_SPREAD = 0.01  # 1 tick. 2 ticks would have blocked 07:59 (Down spread 0.01).


def _f(rec: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if rec.get(key) is not None:
            return float(rec[key])
    return None


def guard_clip(rec: dict[str, Any]) -> str | None:
    clip = rec.get("clip")
    if clip is None:
        return None
    if abs(float(clip) - CLIP) > 1e-12:
        return "clip_not_5"
    return None


def guard_pair(rec: dict[str, Any]) -> str | None:
    bid_sum = _f(rec, "bid_sum_250", "bid_sum")
    if bid_sum is None:
        return "missing_bid_sum"
    if bid_sum > 1.0 + 1e-12:
        return "pair_gt_1_refused"
    if bid_sum > PAIR_MAX + 1e-12:
        return "bid_sum_gt_pair_max"
    return None


def guard_still250_send(rec: dict[str, Any]) -> str | None:
    if rec.get("still_there_250ms") is not True:
        return "still250_false"
    bid_250 = rec.get("bid_sum_250")
    if bid_250 is None:
        return "still250_false"
    if float(bid_250) > PAIR_MAX + 1e-12:
        return "bid_sum_250_gt_pair_max"
    return None


def guard_maker_join(rec: dict[str, Any]) -> str | None:
    """SEND YOK if a join bid is at or through the ask."""
    up = _f(rec, "bid_up_250", "bid_up")
    down = _f(rec, "bid_down_250", "bid_down")
    ask_up = _f(rec, "ask_up_250", "ask_up")
    ask_down = _f(rec, "ask_down_250", "ask_down")
    if up is None or down is None or ask_up is None or ask_down is None:
        return "missing_book"
    if up + 1e-12 >= ask_up or down + 1e-12 >= ask_down:
        return "would_be_taker_blocked"
    return None


def guard_min_spread(rec: dict[str, Any], *, min_spread: float = MIN_SPREAD) -> str | None:
    up = _f(rec, "bid_up_250", "bid_up")
    down = _f(rec, "bid_down_250", "bid_down")
    ask_up = _f(rec, "ask_up_250", "ask_up")
    ask_down = _f(rec, "ask_down_250", "ask_down")
    if up is None or down is None or ask_up is None or ask_down is None:
        return "missing_book"
    if (ask_up - up) + 1e-12 < min_spread:
        return "thin_spread"
    if (ask_down - down) + 1e-12 < min_spread:
        return "thin_spread"
    return None


def first_send_decision(rec: dict[str, Any]) -> tuple[str, str | None]:
    """Return (ALLOW|BLOCK, reason). Verify-only. Not a sender."""
    for guard in (guard_clip, guard_pair, guard_still250_send, guard_maker_join, guard_min_spread):
        blocked = guard(rec)
        if blocked is not None:
            return "BLOCK", blocked
    if str(rec.get("reason") or "") not in {"", "rest"}:
        return "BLOCK", "not_rest"
    return "ALLOW", None
