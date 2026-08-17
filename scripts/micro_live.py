#!/usr/bin/env python3
"""MICRO CLOB path: GTC / cancel / status. BTC 5m clip 5. Not LIVE_READY.

Default: measurement + yaml only. Does not send.

Send is refused unless ALL of:
  1) --send --i-accept-micro-risk  (or --send-live-orders-now --i-accept-micro-risk)
  2) configs/generated/MICRO_LIVE_TRIAL.yaml exists
  3) data/ops/G6_fill_calibrated.flag exists
  4) local CLOB keys present (env / configs/.env.clob)

--send alone is not enough. Keys never printed.
pair_gt_1_trade=false. No clip 10/67 this trial. micro trial ≠ full live.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.clob_auth import auth_status, load_env_file
from whiskas.clob_orders import (
    AuthAbsent,
    cancel_order,
    connect,
    create_fok_buy,
    create_gtc_buy_pair,
    fetch_order,
    real_fill_rate,
    refuse_send,
    stamp_trader_side,
)
from whiskas.config import load_config
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY
from whiskas.measure_layers import (
    MIN_SPREAD,
    REQUOTE_MAX,
    apply_still250_send_gate,
    attach_layers,
    guard_maker_join,
    guard_min_spread,
    guard_still250_send,
    join_bbo,
)
from whiskas.micro_report import (
    FILL_LOG,
    INTENT_LOG,
    STILL_LOG,
    adverse_action,
    build_24h,
    layer_records,
    write_24h,
)
from whiskas.latency_grid import V2, BookAgeCache, current_variant
from whiskas.paper import append_jsonl, current_t0, fetch_books_parallel
from scripts.paper_maker import snapshot_maker

MICRO = ROOT / "configs" / "generated" / "MICRO_LIVE_TRIAL.yaml"
OUT = ROOT / "data" / "micro_live" / "intended.jsonl"
REPORTS = ROOT / "data" / "reports"
PROC = ROOT / "data" / "processed"
PAIR_MAX = 0.90
CANCEL_ABOVE = 0.92
CLIP_NO_G5 = 5.0
CLIP_WITH_G5 = 10.0
MICRO_TRIAL_CLIP = 5.0
MAX_DAILY_LOSS = 25.0
MAX_OPEN = 2
UNPAIRED_TIMEOUT_SEC = 45.0
POST_ACK_SEC = 0.25
REQUOTE_MIN_GAP_SEC = 0.10
SIT_WAKE_SEC = 0.20
ASSET = "btc"
TF = "5m"


def load_micro() -> dict[str, Any] | None:
    if not MICRO.is_file():
        return None
    return load_config(MICRO)


def clip_cap(*, g5: bool, yaml_clip: float | None) -> float:
    hard = CLIP_WITH_G5 if g5 else CLIP_NO_G5
    want = float(yaml_clip) if yaml_clip is not None else hard
    return min(want, hard)


def trial_clip(*, g5: bool, yaml_clip: float | None) -> float:
    """This MICRO trial is clip 5 only. No clip 10/67. No size bump."""
    return min(clip_cap(g5=g5, yaml_clip=yaml_clip), MICRO_TRIAL_CLIP)


def print_preconditions() -> dict[str, Any]:
    load_env_file()
    auth = auth_status()
    micro = load_micro()
    g6 = (ROOT / G6_FLAG).is_file()
    yaml_ok = bool(micro)
    clip = float((micro or {}).get("clip") or 0)
    assets = list((micro or {}).get("assets") or [])
    tfs = list((micro or {}).get("tfs") or [])
    yaml_shape = yaml_ok and clip <= MICRO_TRIAL_CLIP + 1e-12 and assets == ["btc"] and tfs == ["5m"]
    paper_src = (ROOT / "scripts" / "paper_maker.py").read_text(encoding="utf-8")
    still_ok = "still_there_250ms" in paper_src and "_probe_still250" in paper_src
    clob_src = (ROOT / "scripts" / "micro_live.py").read_text(encoding="utf-8")
    path_ok = all(
        s in clob_src
        for s in (
            "create_gtc_buy_pair",
            "cancel_order",
            "fetch_order",
            "still250_false",
            "guard_still250_send",
            "still_ms",
            "post_ack_ms",
        )
    )
    pre = {
        "1_g6_flag": g6,
        "2_micro_yaml": yaml_ok,
        "2_micro_clip5_btc_5m": yaml_shape,
        "3_still250_on_paper_maker": still_ok,
        "4_micro_live_gtc_cancel_status": path_ok,
        "5_auth": auth["reason"],
        "auth_available": bool(auth["auth_available"]),
    }
    print(json.dumps({"preconditions": pre}, indent=2))
    return pre


def write_clob_report(payload: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    (PROC / "micro_clob.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    still = payload.get("still250_note") or "paper still250 continues"
    lines = [
        "# MICRO_CLOB",
        "",
        f"Generated: {payload.get('generated')}",
        f"auth: **{payload.get('auth_reason')}**",
        f"sent: **{payload.get('sent')}**",
        f"real_fill_rate: **{payload.get('real_fill_rate')}**",
        "",
        "- Keys from env / configs/.env.clob only. Never printed.",
        "- AUTH_ABSENT => stop at MICRO yaml + paper still250. Do not fake real_fill.",
        "- MICRO ≠ LIVE_READY. No clip 10/67 this trial. pair_gt_1_trade=false.",
        f"- {still}",
        f"- live_ready_exists: {payload.get('live_ready_exists')}",
        f"- g5: {payload.get('g5')}",
        "",
    ]
    (REPORTS / "MICRO_CLOB.md").write_text("\n".join(lines), encoding="utf-8")


def log_layers(rec: dict[str, Any]) -> None:
    """Write INTENT / still_there_250ms / REAL FILL to separate files. No invented fills."""
    append_jsonl(OUT, rec)
    layers = layer_records(rec)
    append_jsonl(INTENT_LOG, layers["INTENT"])
    append_jsonl(STILL_LOG, layers["still_there_250ms"])
    if "REAL FILL" in layers:
        append_jsonl(FILL_LOG, layers["REAL FILL"])


def probe() -> dict[str, Any]:
    load_env_file()
    auth = auth_status()
    micro = load_micro()
    g5 = (ROOT / G5_FLAG).is_file()
    g6 = (ROOT / G6_FLAG).is_file()
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "micro_yaml": bool(micro),
        "micro_path": str(MICRO) if micro else None,
        "auth_available": bool(auth["auth_available"]),
        "auth_reason": auth["reason"],
        "private_key_env": auth.get("private_key_env"),
        "api_key_env": auth.get("api_key_env"),
        "sent": False,
        "real_fill": None,
        "real_fill_rate": None,
        "live_order": False,
        "pair_gt_1_trade": False,
        "g5": g5,
        "g6": g6,
        "live_ready_exists": (ROOT / LIVE_READY).is_file(),
        "still250_note": "paper_maker still250 continues; real_fill=null until an order is sent",
        "clip_cap": trial_clip(g5=g5, yaml_clip=(micro or {}).get("clip")),
        "asset": ASSET,
        "tf": TF,
        "halted_on_loss": False,
        "note": "AUTH_ABSENT => do not send, do not fake real_fill. micro trial ≠ full live.",
    }
    if not micro:
        payload["ok"] = False
        payload["block"] = "MICRO yaml missing"
    elif not auth["auth_available"]:
        payload["ok"] = True
        payload["block"] = "AUTH_ABSENT"
        payload.update(refuse_send())
        payload["auth_reason"] = auth["reason"]
    else:
        payload["ok"] = True
        payload["block"] = None
        payload["wired"] = True
    return payload


def _guard_rest(rec: dict[str, Any], *, clip: float) -> str | None:
    if rec.get("reason") != "rest":
        return str(rec.get("reason") or "no_rest")
    bid_sum = rec.get("bid_sum")
    if bid_sum is None:
        return "missing_bid"
    if float(bid_sum) > 1.0 + 1e-12:
        return "pair_gt_1_refused"
    if float(bid_sum) > PAIR_MAX + 1e-12:
        return "bid_sum_gt_pair_max"
    min_sz = rec.get("min_bid_size")
    if min_sz is None or float(min_sz) + 1e-12 < float(clip):
        return "thin_bid"
    return None


def _best_bid_join_prices(rec: dict[str, Any]) -> tuple[float, float] | None:
    """Join live best bids. still250 is hole-stayed only — never post bid_*_250 when live exists."""
    up, down, _ask_up, _ask_down = join_bbo(rec)
    if up is None or down is None:
        return None
    if float(up) + float(down) > PAIR_MAX + 1e-12:
        return None
    if guard_maker_join(rec) == "would_be_taker_blocked":
        return None
    if guard_min_spread(rec) == "thin_spread":
        return None
    rec["join_source"] = "live" if rec.get("bid_up") is not None and rec.get("bid_down") is not None else "still250_fallback"
    return float(up), float(down)


def inventory_flat(inv: dict[str, float] | None) -> bool:
    if not inv:
        return True
    return abs(float(inv.get("Up") or 0.0) - float(inv.get("Down") or 0.0)) <= 1e-12


def residual_of(orders: list[dict[str, Any]], *, clip: float) -> dict[str, float]:
    out = {"Up": 0.0, "Down": 0.0}
    for order in orders:
        outcome = str(order.get("outcome") or "")
        if outcome not in out:
            continue
        rested = float(order.get("rested_size") or order.get("size") or clip)
        filled = float(order.get("filled_size") or 0.0)
        out[outcome] += max(0.0, rested - filled)
    return out


def _inv_from_orders(orders: list[dict[str, Any]]) -> dict[str, float]:
    inv = {"Up": 0.0, "Down": 0.0}
    for order in orders:
        outcome = str(order.get("outcome") or "")
        if outcome in inv:
            inv[outcome] += float(order.get("filled_size") or 0.0)
    return inv


def _block_send(rec: dict[str, Any], reason: str, *, clip: float) -> dict[str, Any]:
    rec["send_blocked"] = reason
    rec["would_send"] = False
    rec["live_order"] = False
    rec["real_fill"] = None
    rec["real_fill_rate"] = None
    rec["pair_gt_1_trade"] = False
    rec.setdefault("lag_ms", None)
    rec.setdefault("sign_ms", None)
    rec.setdefault("post_ack_ms", None)
    rec.setdefault("still_ms", rec.get("still_ms"))
    rec.setdefault("adverse_action", rec.get("adverse"))
    rec.setdefault("residual", None)
    rec.setdefault("fill_role", None)
    rec.setdefault("s1_edge", rec.get("bid_sum") or rec.get("intent_bid_sum"))
    rec["would_be_taker_blocked"] = reason == "would_be_taker_blocked"
    rec.setdefault("both_fill", None)
    rec.setdefault("one_leg_taker", None)
    rec.setdefault("off_touch", None)
    return rec


def _fill_px(order: dict[str, Any]) -> float | None:
    for key in ("trade_price", "fill_px", "price"):
        val = order.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _buy_off_touch(px: Any, best_bid: Any) -> bool:
    if px is None or best_bid is None:
        return False
    return float(px) + 1e-12 < float(best_bid)


def _book_from_ws(book_cache: Any, token_up: Any, token_down: Any) -> dict[str, Any]:
    if book_cache is None or not token_up or not token_down:
        return {}
    try:
        got = book_cache.bbo(str(token_up), str(token_down))
    except Exception:
        return {}
    return got or {}


def _reread_book_rest(rec: dict[str, Any]) -> dict[str, Any]:
    """REST BBO for first-send join. Do not use WS cache here — 12:07 WS 250 was 0.01/0.83."""
    from whiskas.paper import best_ask, best_bid

    out: dict[str, Any] = {}
    if not rec.get("token_up") or not rec.get("token_down"):
        return out
    try:
        book_up, book_down = fetch_books_parallel(str(rec["token_up"]), str(rec["token_down"]))
        bu, su = best_bid(book_up)
        au, _ = best_ask(book_up)
        bd, sd = best_bid(book_down)
        ad, _ = best_ask(book_down)
        out["bid_up"] = bu
        out["ask_up"] = au
        out["bid_down"] = bd
        out["ask_down"] = ad
        if su is not None and sd is not None:
            out["min_bid_size"] = min(float(su), float(sd))
    except Exception:
        return out
    if out.get("bid_up") is not None and out.get("bid_down") is not None:
        out["bid_sum"] = float(out["bid_up"]) + float(out["bid_down"])
    out["source"] = "rest"
    return out


def _reread_book(rec: dict[str, Any], book_cache: Any = None) -> dict[str, Any]:
    """Sit/requote may use WS. First send uses _reread_book_rest."""
    ws = _book_from_ws(book_cache, rec.get("token_up"), rec.get("token_down"))
    if ws:
        return ws
    return _reread_book_rest(rec)


def _overlay_live_book(rec: dict[str, Any], book: dict[str, Any]) -> None:
    if not book:
        return
    for key in ("bid_up", "bid_down", "ask_up", "ask_down", "bid_sum", "min_bid_size"):
        if book.get(key) is not None:
            rec[key] = book[key]
    if rec.get("bid_up") is not None and rec.get("bid_down") is not None:
        rec["bid_sum"] = float(rec["bid_up"]) + float(rec["bid_down"])
    rec["join_book_source"] = book.get("source") or "reread"


def _refresh_orders(client: Any, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for order in orders:
        oid = order.get("order_id")
        if not oid:
            continue
        try:
            got = fetch_order(client, str(oid))
            merged = {**order, **got}
            if float(merged.get("filled_size") or 0.0) > 0:
                try:
                    stamp_trader_side(client, merged)
                except Exception:
                    pass
            refreshed.append(merged)
        except Exception:
            refreshed.append(order)
    return refreshed


def _stamp_fill_fields(rec: dict[str, Any], orders: list[dict[str, Any]], *, clip: float) -> None:
    rec["s1_edge"] = rec.get("intent_bid_sum", rec.get("bid_sum"))
    rec["residual"] = residual_of(orders, clip=clip)
    roles = [o.get("trader_side") or o.get("fill_role") for o in orders if o.get("trader_side") or o.get("fill_role")]
    rec["fill_role"] = roles[0] if len(set(roles)) == 1 else (roles or None)
    rec["adverse_action"] = rec.get("adverse_action", rec.get("adverse"))
    filled_n = sum(1 for o in orders if float(o.get("filled_size") or 0.0) > 0)
    rec["both_fill"] = filled_n >= 2
    rec["one_leg"] = filled_n == 1
    rec["one_leg_taker"] = bool(
        rec["one_leg"]
        and any(str(o.get("trader_side") or o.get("fill_role") or "").lower() == "taker" for o in orders)
    )
    if rec.get("adverse_action") == "off_touch" or rec.get("adverse") == "off_touch":
        rec["off_touch"] = True
    rec.setdefault("off_touch", False)
    rec.setdefault("would_be_taker_blocked", rec.get("send_blocked") == "would_be_taker_blocked")
    rec["pair_gt_1_trade"] = False


def send_rest_both(
    client: Any,
    rec: dict[str, Any],
    tokens: dict[str, str],
    *,
    clip: float,
) -> dict[str, Any]:
    """GTC both legs at live best bid. still250 = hole stayed, not the join price. No pair>1."""
    rec["s1_edge"] = rec.get("intent_bid_sum", rec.get("bid_sum"))
    still_block = guard_still250_send(rec)
    if still_block:
        return _block_send(rec, still_block, clip=clip)
    _overlay_live_book(rec, _reread_book_rest(rec))
    book_block = _guard_rest(rec, clip=clip)
    maker_block = guard_maker_join(rec, require_ask=True)
    spread_block = guard_min_spread(rec, require_ask=True)
    guard = book_block or maker_block or spread_block
    if guard:
        return _block_send(rec, guard, clip=clip)
    prices = _best_bid_join_prices(rec)
    if prices is None:
        return _block_send(rec, "not_best_bid", clip=clip)
    px_up, px_down = prices
    rec["join_bid_up"] = px_up
    rec["join_bid_down"] = px_down
    t_intent = rec.get("t_intent")
    t0_send = time.time()
    posted: list[dict[str, Any]] = []
    timings: dict[str, Any] = {}
    try:
        posted = create_gtc_buy_pair(
            client,
            token_up=tokens["Up"],
            price_up=px_up,
            token_down=tokens["Down"],
            price_down=px_down,
            size=float(clip),
            timings=timings,
        )
    except AuthAbsent:
        rec["send_blocked"] = "AUTH_ABSENT"
        rec["live_order"] = False
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["would_send"] = False
        rec["sign_ms"] = timings.get("sign_ms")
        rec["post_ack_ms"] = timings.get("post_ack_ms")
        rec["lag_ms"] = (time.time() - float(t_intent or t0_send)) * 1000.0
        return rec
    except Exception as exc:
        for prev in posted:
            if prev.get("order_id"):
                try:
                    cancel_order(client, str(prev["order_id"]))
                except Exception:
                    pass
        rec["send_error"] = type(exc).__name__
        rec["live_order"] = False
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["would_send"] = False
        rec["sign_ms"] = timings.get("sign_ms")
        rec["post_ack_ms"] = timings.get("post_ack_ms")
        rec["lag_ms"] = (time.time() - float(t_intent or t0_send)) * 1000.0
        return rec
    rec["sign_ms"] = timings.get("sign_ms")
    rec["post_ack_ms"] = timings.get("post_ack_ms", (time.time() - t0_send) * 1000.0)
    rec["lag_ms"] = (time.time() - float(t_intent or t0_send)) * 1000.0
    rec["lag_primary"] = "t_intent_to_ack"
    refreshed = _refresh_orders(client, posted)
    if not refreshed:
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["live_order"] = False
        rec["send_blocked"] = "no_order_id"
        rec["would_send"] = False
        return rec
    rec["real_fill"] = {
        "orders": refreshed,
        "filled_size": sum(float(o.get("filled_size") or 0.0) for o in refreshed),
        "rested_size": sum(float(o.get("rested_size") or o.get("size") or 0.0) for o in refreshed),
    }
    rec["real_fill_rate"] = real_fill_rate(refreshed)
    rec["live_order"] = True
    rec["pair_gt_1_trade"] = False
    rec["intent"] = True
    rec["would_send"] = True
    created = [o.get("created_at") for o in refreshed if o.get("created_at") is not None]
    rec["clob_created_at"] = min(created) if created else None
    _stamp_fill_fields(rec, refreshed, clip=clip)
    return rec


def cancel_open(client: Any, orders: list[dict[str, Any]], *, reason: str) -> list[dict[str, Any]]:
    out = []
    for order in orders:
        oid = order.get("order_id")
        if not oid:
            continue
        if _filled(order, clip=float(order.get("rested_size") or order.get("size") or 0.0) or 5.0):
            out.append({**order, "cancel_reason": reason})
            continue
        try:
            cancelled = cancel_order(client, str(oid))
            cancelled["cancel_reason"] = reason
            cancelled["outcome"] = order.get("outcome")
            out.append({**order, **cancelled, "cancel_reason": reason})
        except Exception:
            out.append({**order, "cancel_reason": reason, "status": "cancel_failed"})
    return out


def _filled(order: dict[str, Any], *, clip: float) -> bool:
    st = str(order.get("status") or "")
    filled = float(order.get("filled_size") or 0.0)
    rested = float(order.get("rested_size") or clip)
    return st == "filled" or (rested > 0 and filled + 1e-12 >= rested)


def _unpaired_notional(orders: list[dict[str, Any]], *, clip: float) -> float:
    filled = [o for o in orders if float(o.get("filled_size") or 0.0) > 0]
    leftover = [o for o in orders if not _filled(o, clip=clip)]
    if len(filled) != 1:
        return 0.0
    px = _fill_px(filled[0])
    if px is None:
        return 0.0
    return float(px) * float(filled[0].get("filled_size") or 0.0)


def _requote_block(
    book: dict[str, Any],
    *,
    clip: float,
    n_requote: int,
    last_requote_ts: float | None = None,
) -> str | None:
    """Requote only while maker-only, bid_sum<=0.90, 1-tick spread, depth>=clip, n<8."""
    if int(n_requote) >= int(REQUOTE_MAX):
        return "requote_max"
    if last_requote_ts is not None and (time.time() - float(last_requote_ts)) < REQUOTE_MIN_GAP_SEC:
        return "requote_gap"
    bid_sum = book.get("bid_sum")
    if bid_sum is None or float(bid_sum) > PAIR_MAX + 1e-12:
        return "requote_rich"
    min_sz = book.get("min_bid_size")
    if min_sz is not None and float(min_sz) + 1e-12 < float(clip):
        return "thin_bid"
    probe = {
        "bid_up": book.get("bid_up"),
        "bid_down": book.get("bid_down"),
        "ask_up": book.get("ask_up"),
        "ask_down": book.get("ask_down"),
    }
    return guard_maker_join(probe, require_ask=True) or guard_min_spread(probe, require_ask=True)


def _try_requote(
    client: Any,
    rec: dict[str, Any],
    leftover: list[dict[str, Any]],
    book: dict[str, Any],
    *,
    clip: float,
    n_requote: int,
    last_requote_ts: float | None = None,
) -> tuple[list[dict[str, Any]] | None, str]:
    block = _requote_block(book, clip=clip, n_requote=n_requote, last_requote_ts=last_requote_ts)
    if block:
        return None, block
    token_up = rec.get("token_up")
    token_down = rec.get("token_down")
    px_up = book.get("bid_up")
    px_down = book.get("bid_down")
    if not token_up or not token_down or px_up is None or px_down is None:
        return None, "not_best_bid"
    cancel_open(client, leftover, reason="requote")
    timings: dict[str, Any] = {}
    try:
        posted = create_gtc_buy_pair(
            client,
            token_up=str(token_up),
            price_up=float(px_up),
            token_down=str(token_down),
            price_down=float(px_down),
            size=float(clip),
            timings=timings,
        )
    except Exception:
        rec["adverse_action"] = "requote_failed"
        rec["off_touch"] = True
        rec["n_requote"] = n_requote
        return [], "requote_failed"
    rec["n_requote"] = int(n_requote) + 1
    rec["adverse_action"] = "requote"
    rec["off_touch"] = True
    rec["requote_source"] = book.get("source") or rec.get("requote_source") or "poll"
    rec["join_bid_up"] = float(px_up)
    rec["join_bid_down"] = float(px_down)
    rec["sign_ms"] = timings.get("sign_ms")
    rec["post_ack_ms"] = timings.get("post_ack_ms")
    return posted, "requote"


def manage_open(
    client: Any,
    rec: dict[str, Any],
    orders: list[dict[str, Any]],
    *,
    clip: float,
    book_now: dict[str, Any] | None = None,
    force_flatten: bool = False,
    n_requote: int = 0,
    last_requote_ts: float | None = None,
    book_cache: Any = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """One-leg/adverse FIRST, then off-touch, then rich_cancel. Complete only if fill+opp<=0.90."""
    refreshed = _refresh_orders(client, orders)
    book = book_now if book_now is not None else _reread_book(rec, book_cache)
    if book.get("ask_up") is not None:
        rec["ask_up"] = book.get("ask_up")
    if book.get("ask_down") is not None:
        rec["ask_down"] = book.get("ask_down")
    if book.get("bid_up") is not None:
        rec["live_bid_up"] = book.get("bid_up")
    if book.get("bid_down") is not None:
        rec["live_bid_down"] = book.get("bid_down")
    filled = [o for o in refreshed if _filled(o, clip=clip)]
    leftover = [o for o in refreshed if not _filled(o, clip=clip)]
    if len(filled) == 1 and leftover:
        fill_px = _fill_px(filled[0])
        outcome = filled[0].get("outcome")
        opp_ask = book.get("ask_down") if outcome == "Up" else book.get("ask_up")
        if opp_ask is None:
            opp_ask = rec.get("ask_down") if outcome == "Up" else rec.get("ask_up")
        action = adverse_action(
            fill_px if fill_px is None else float(fill_px),
            None if opp_ask is None else float(opp_ask),
        )
        rec["adverse"] = action
        rec["adverse_action"] = action
        if action != "complete":
            cancelled = cancel_open(client, leftover, reason=action)
            _stamp_fill_fields(rec, filled + cancelled, clip=clip)
            return filled + cancelled, action
        token = rec.get("token_down") if outcome == "Up" else rec.get("token_up")
        if not token or opp_ask is None:
            cancelled = cancel_open(client, leftover, reason="cancel_missing_opp")
            _stamp_fill_fields(rec, filled + cancelled, clip=clip)
            return filled + cancelled, "cancel_missing_opp"
        try:
            fok = create_fok_buy(client, token_id=str(token), price=float(opp_ask), size=float(clip))
            if leftover:
                cancel_open(client, leftover, reason="replaced_by_fok_complete")
            refreshed = filled + [{**fok, "outcome": "Down" if outcome == "Up" else "Up", "fill_role": "fok_complete"}]
            rec["complete"] = True
            rec["adverse_action"] = "complete"
            _stamp_fill_fields(rec, refreshed, clip=clip)
            return refreshed, "complete"
        except AuthAbsent:
            cancelled = cancel_open(client, leftover, reason="AUTH_ABSENT")
            return filled + cancelled, "AUTH_ABSENT"
        except Exception:
            cancelled = cancel_open(client, leftover, reason="complete_failed")
            return filled + cancelled, "complete_failed"
    if filled and not leftover:
        rec["adverse_action"] = rec.get("adverse_action")
        _stamp_fill_fields(rec, refreshed, clip=clip)
        return refreshed, "filled_both"
    if leftover and force_flatten:
        cancelled = cancel_open(client, leftover, reason="unpaired_timeout")
        rec["adverse_action"] = "unpaired_timeout"
        _stamp_fill_fields(rec, filled + cancelled, clip=clip)
        return filled + cancelled, "unpaired_timeout"
    if leftover:
        off = False
        for order in leftover:
            outcome = order.get("outcome")
            best = book.get("bid_up") if outcome == "Up" else book.get("bid_down")
            if best is None:
                best = rec.get("bid_up") if outcome == "Up" else rec.get("bid_down")
            if _buy_off_touch(order.get("price"), best):
                off = True
                break
        if off:
            rec["off_touch"] = True
            if not filled:
                posted, rq = _try_requote(
                    client,
                    rec,
                    leftover,
                    book,
                    clip=clip,
                    n_requote=n_requote,
                    last_requote_ts=last_requote_ts,
                )
                if posted:
                    _stamp_fill_fields(rec, posted, clip=clip)
                    return posted, "requote"
                if rq == "requote_gap":
                    _stamp_fill_fields(rec, refreshed, clip=clip)
                    return refreshed, None
            cancelled = cancel_open(client, leftover, reason="off_touch")
            rec["adverse_action"] = "off_touch"
            _stamp_fill_fields(rec, filled + cancelled, clip=clip)
            return filled + cancelled, "off_touch"
    bid_sum = book.get("bid_sum", rec.get("bid_sum"))
    if leftover and bid_sum is not None and float(bid_sum) > CANCEL_ABOVE + 1e-12:
        cancelled = cancel_open(client, leftover, reason="rich_cancel")
        rec["adverse_action"] = "rich_cancel"
        _stamp_fill_fields(rec, filled + cancelled, clip=clip)
        return filled + cancelled, "rich_cancel"
    _stamp_fill_fields(rec, refreshed, clip=clip)
    return refreshed, None


def _pop_reasons() -> set[str]:
    return {
        "rich_cancel",
        "rich_complete",
        "pair_gt_1_refused",
        "cancel_missing_opp",
        "daily_loss",
        "complete",
        "filled_both",
        "off_touch",
        "unpaired_timeout",
        "AUTH_ABSENT",
        "complete_failed",
    }


def after_send_manage(
    client: Any,
    rec: dict[str, Any],
    orders: list[dict[str, Any]],
    *,
    clip: float,
    sleep_s: float = POST_ACK_SEC,
    n_requote: int = 0,
    book_cache: Any = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Immediate one-leg if MATCHED; then 200–500ms off-touch (requote if still cheap+maker)."""
    why: str | None = None
    filled_n = sum(1 for o in orders if float(o.get("filled_size") or 0.0) > 0)
    if filled_n == 1:
        orders, why = manage_open(client, rec, orders, clip=clip, n_requote=n_requote, book_cache=book_cache)
        if why in _pop_reasons():
            return orders, why
    if sleep_s > 0:
        time.sleep(min(0.5, max(0.2, float(sleep_s))))
    return manage_open(client, rec, orders, clip=clip, n_requote=n_requote, book_cache=book_cache)


def run_send(*, seconds: float, interval: float) -> dict[str, Any]:
    if not (ROOT / G6_FLAG).is_file():
        return {"ok": False, "reason": "G6 flag missing; refuse send", "sent": False, "real_fill_rate": None, "halted_on_loss": False}
    micro = load_micro()
    if not micro:
        return {"ok": False, "reason": "MICRO yaml missing", "sent": False, "real_fill_rate": None, "halted_on_loss": False}
    g5 = (ROOT / G5_FLAG).is_file()
    clip = trial_clip(g5=g5, yaml_clip=micro.get("clip"))
    client = connect(derive_l2=False)
    if client is None:
        payload = probe()
        payload["ok"] = True
        payload["sent"] = False
        payload["real_fill_rate"] = None
        payload["block"] = "AUTH_ABSENT"
        payload["halted_on_loss"] = False
        print("AUTH_ABSENT")
        return payload
    deadline = time.time() + max(0.0, float(seconds))
    token_cache: dict[str, dict[str, str]] = {}
    variant = current_variant()
    book_cache = BookAgeCache()
    book_cache.start()
    max_loss = float(micro.get("max_daily_loss_usd") or MAX_DAILY_LOSS)
    max_open = int(micro.get("max_open_windows") or MAX_OPEN)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _run_send_loop(
            client=client,
            clip=clip,
            deadline=deadline,
            interval=interval,
            token_cache=token_cache,
            variant=variant,
            book_cache=book_cache,
            max_loss=max_loss,
            max_open=max_open,
        )
    finally:
        if book_cache is not None:
            book_cache.stop()


def _tick_open_windows(
    *,
    client: Any,
    rec: dict[str, Any],
    t0: int,
    clip: float,
    open_windows: dict[int, list[dict[str, Any]]],
    open_meta: dict[int, dict[str, Any]],
    inventory: dict[int, dict[str, float]],
    loss_charged: set[int],
    daily_loss: float,
    book_cache: Any,
    log_requote: bool = False,
) -> float:
    """Manage resting orders. WS BBO when cached so off-touch requote is event-driven."""
    for ot0 in list(open_windows):
        meta = open_meta.get(ot0) or {}
        age = time.time() - float(meta.get("rest_ts") or time.time())
        ended = int(ot0) != int(t0)
        one_leg_inv = not inventory_flat(inventory.get(ot0))
        force = ended or (one_leg_inv and age > UNPAIRED_TIMEOUT_SEC + 1e-12)
        rec_use = rec if int(ot0) == int(t0) else {**rec, "token_up": meta.get("token_up"), "token_down": meta.get("token_down")}
        rec_use["token_up"] = rec_use.get("token_up") or meta.get("token_up")
        rec_use["token_down"] = rec_use.get("token_down") or meta.get("token_down")
        book = _book_from_ws(book_cache, rec_use.get("token_up"), rec_use.get("token_down"))
        orders, why = manage_open(
            client,
            rec_use,
            open_windows[ot0],
            clip=clip,
            book_now=book or None,
            force_flatten=force,
            n_requote=int(meta.get("n_requote") or 0),
            last_requote_ts=meta.get("last_requote_ts"),
            book_cache=book_cache,
        )
        inventory[ot0] = _inv_from_orders(orders)
        if why in {"rich_complete", "pair_gt_1_refused", "unpaired_timeout", "cancel_missing_opp"} and ot0 not in loss_charged:
            daily_loss += _unpaired_notional(orders, clip=clip)
            loss_charged.add(ot0)
        if why in _pop_reasons():
            open_windows.pop(ot0, None)
            open_meta.pop(ot0, None)
        else:
            open_windows[ot0] = orders
            if why == "requote":
                meta["n_requote"] = int(rec_use.get("n_requote") or meta.get("n_requote") or 0)
                meta["last_requote_ts"] = time.time()
                open_meta[ot0] = meta
                rec["n_requote"] = meta["n_requote"]
                rec["adverse_action"] = "requote"
                rec["requote_source"] = rec_use.get("requote_source") or book.get("source") or "ws"
                rec["off_touch"] = True
                if log_requote:
                    rec["pair_gt_1_trade"] = False
                    rec["daily_loss_usd"] = daily_loss
                    log_layers(rec)
    return daily_loss


def _run_send_loop(
    *,
    client: Any,
    clip: float,
    deadline: float,
    interval: float,
    token_cache: dict[str, dict[str, str]],
    variant: str,
    book_cache: Any,
    max_loss: float,
    max_open: int,
) -> dict[str, Any]:
    open_windows: dict[int, list[dict[str, Any]]] = {}
    open_meta: dict[int, dict[str, Any]] = {}
    inventory: dict[int, dict[str, float]] = {}
    loss_charged: set[int] = set()
    daily_loss = 0.0
    n_sent = 0
    halted = False
    last_snap = 0.0
    ws_gen = 0
    while time.time() < deadline:
        if daily_loss + 1e-12 >= max_loss:
            for orders in list(open_windows.values()):
                cancel_open(client, orders, reason="daily_loss")
            halted = True
            break
        rec, _state = snapshot_maker(
            asset=ASSET,
            tf=TF,
            clip=clip,
            token_cache=token_cache,
            latency_variant=variant,
            book_cache=book_cache,
        )
        rec["asset"] = ASSET
        rec["tf"] = TF
        rec["latency_variant"] = variant
        t0 = int(rec.get("t0") or current_t0(tf=TF))
        rec["s1_edge"] = rec.get("intent_bid_sum", rec.get("bid_sum"))
        if str(rec.get("reason") or "") == "rest":
            apply_still250_send_gate(rec)
        daily_loss = _tick_open_windows(
            client=client,
            rec=rec,
            t0=t0,
            clip=clip,
            open_windows=open_windows,
            open_meta=open_meta,
            inventory=inventory,
            loss_charged=loss_charged,
            daily_loss=daily_loss,
            book_cache=book_cache,
        )
        can_rest = (
            rec.get("reason") == "rest"
            and rec.get("would_send") is True
            and guard_still250_send(rec) is None
            and t0 not in open_windows
            and inventory_flat(inventory.get(t0))
            and len(open_windows) < max_open
        )
        if can_rest:
            tokens = {"Up": rec["token_up"], "Down": rec["token_down"]}
            rec = send_rest_both(client, rec, tokens, clip=clip)
            if rec.get("live_order") and rec.get("real_fill"):
                orders = list((rec["real_fill"] or {}).get("orders") or [])
                orders, why = after_send_manage(client, rec, orders, clip=clip, n_requote=0, book_cache=book_cache)
                rec["real_fill"] = {
                    "orders": orders,
                    "filled_size": sum(float(o.get("filled_size") or 0.0) for o in orders),
                    "rested_size": sum(float(o.get("rested_size") or o.get("size") or 0.0) for o in orders),
                }
                rec["real_fill_rate"] = real_fill_rate(orders)
                _stamp_fill_fields(rec, orders, clip=clip)
                inventory[t0] = _inv_from_orders(orders)
                if why in {"rich_complete", "pair_gt_1_refused", "unpaired_timeout", "cancel_missing_opp"} and t0 not in loss_charged:
                    daily_loss += _unpaired_notional(orders, clip=clip)
                    loss_charged.add(t0)
                n_sent += 1
                if why not in _pop_reasons():
                    open_windows[t0] = orders
                    open_meta[t0] = {
                        "rest_ts": time.time(),
                        "token_up": rec.get("token_up"),
                        "token_down": rec.get("token_down"),
                        "n_requote": int(rec.get("n_requote") or 0),
                        "last_requote_ts": time.time() if int(rec.get("n_requote") or 0) else None,
                    }
        rec["pair_gt_1_trade"] = False
        rec["daily_loss_usd"] = daily_loss
        log_layers(rec)
        last_snap = time.time()
        if open_windows and book_cache is not None:
            meta0 = next(iter(open_meta.values()), {})
            tu, td = meta0.get("token_up"), meta0.get("token_down")
            sit_until = last_snap + max(0.5, float(interval))
            while time.time() < deadline and time.time() < sit_until and open_windows and tu and td:
                ws_gen = book_cache.wait_change(str(tu), str(td), ws_gen, timeout=SIT_WAKE_SEC)
                t0_now = int(current_t0(tf=TF))
                daily_loss = _tick_open_windows(
                    client=client,
                    rec=rec,
                    t0=t0_now,
                    clip=clip,
                    open_windows=open_windows,
                    open_meta=open_meta,
                    inventory=inventory,
                    loss_charged=loss_charged,
                    daily_loss=daily_loss,
                    book_cache=book_cache,
                    log_requote=True,
                )
        else:
            time.sleep(max(0.5, float(interval)))
    payload = probe()
    payload["sent"] = n_sent > 0
    payload["n_sent_windows"] = n_sent
    payload["real_fill_rate"] = None if n_sent == 0 else payload.get("real_fill_rate")
    payload["clip"] = clip
    payload["halted_on_loss"] = halted
    payload["daily_loss_usd"] = daily_loss
    return payload


def finish(payload: dict[str, Any]) -> dict[str, Any]:
    write_clob_report(payload)
    report = build_24h(
        auth_reason=str(payload.get("auth_reason") or payload.get("block") or "unknown"),
        sent=bool(payload.get("sent")),
        halted_on_loss=bool(payload.get("halted_on_loss")),
        clip=float(payload.get("clip") or payload.get("clip_cap") or MICRO_TRIAL_CLIP),
    )
    write_24h(report)
    payload["micro_live_24h"] = {
        "n_rest_intent": report["n_rest_intent"],
        "still250_rate": report["still250_rate"],
        "real_fill_rate": report["real_fill_rate"],
        "n_partial": report["n_partial"],
        "n_cancel": report["n_cancel"],
        "net_pnl_usd": report["net_pnl_usd"],
        "hit_max_daily_loss": report["hit_max_daily_loss"],
        "pair_gt_1_trade": report["pair_gt_1_trade"],
        "path": str(ROOT / "data" / "reports" / "MICRO_LIVE_24H.md"),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="MICRO CLOB path. Default: measurement only. No send.")
    parser.add_argument("--send", action="store_true", help="requires --i-accept-micro-risk; refused alone")
    parser.add_argument(
        "--send-live-orders-now",
        action="store_true",
        dest="send_now",
        help="alias for explicit phrase. Still needs --i-accept-micro-risk + MICRO yaml + G6 + keys.",
    )
    parser.add_argument("--i-accept-micro-risk", action="store_true", dest="accept")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    pre = print_preconditions()
    if args.send and not args.accept and not args.send_now:
        print(json.dumps({
            "ok": False,
            "sent": False,
            "real_fill_rate": None,
            "reason": "refused: --send alone is not enough; need --send --i-accept-micro-risk + MICRO yaml + G6 flag",
        }))
        return 2
    want_send = bool(args.accept and (args.send or args.send_now))
    if (args.send or args.send_now) and not args.accept:
        print(json.dumps({"ok": False, "sent": False, "reason": "pass --i-accept-micro-risk"}))
        return 2
    if want_send:
        if not pre.get("auth_available"):
            print("AUTH_ABSENT")
            payload = probe()
            payload["sent"] = False
            payload["real_fill_rate"] = None
            payload["block"] = "AUTH_ABSENT"
            payload["halted_on_loss"] = False
        elif not (ROOT / G6_FLAG).is_file() or load_micro() is None:
            print(json.dumps({
                "ok": False,
                "sent": False,
                "real_fill_rate": None,
                "reason": "need MICRO_LIVE_TRIAL.yaml and G6_fill_calibrated.flag",
            }))
            return 2
        else:
            payload = run_send(seconds=float(args.seconds), interval=float(args.interval))
    else:
        payload = probe()
    payload = finish(payload)
    print(json.dumps({
        "ok": payload.get("ok"),
        "auth_reason": payload.get("auth_reason"),
        "auth_available": payload.get("auth_available"),
        "micro_yaml": payload.get("micro_yaml"),
        "sent": payload.get("sent"),
        "real_fill_rate": payload.get("real_fill_rate"),
        "live_ready_exists": payload.get("live_ready_exists"),
        "block": payload.get("block"),
        "clip_cap": payload.get("clip_cap"),
        "pair_gt_1_trade": False,
        "halted_on_loss": payload.get("halted_on_loss"),
        "micro_live_24h": payload.get("micro_live_24h"),
        "note": payload.get("note"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
