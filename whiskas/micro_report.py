"""MICRO LIVE 24h measurement. Layers stay unmixed. Never invent real_fill."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from whiskas.paper import load_jsonl

ROOT = Path(__file__).resolve().parents[1]
PAPER_MAKER = ROOT / "data" / "paper_maker" / "intended.jsonl"
MICRO_LIVE = ROOT / "data" / "micro_live" / "intended.jsonl"
INTENT_LOG = ROOT / "data" / "micro_live" / "intent.jsonl"
STILL_LOG = ROOT / "data" / "micro_live" / "still250.jsonl"
FILL_LOG = ROOT / "data" / "micro_live" / "real_fill.jsonl"
REPORT = ROOT / "data" / "reports" / "MICRO_LIVE_24H.md"
PROC = ROOT / "data" / "processed" / "micro_live_24h.json"

TAKER_FEE_K = 0.07
PAIR_MAX = 0.90
SKIP_OK = {"rich_bid_sum", "missing_bid", "thin_bid", "hold", "gamma_error", "clob_error"}


def signal_health(
    *,
    live_cheap_intent: int,
    live_order_id: int,
    paper_btc5_rest: int,
    hours_up: float | None = None,
) -> dict[str, Any]:
    """Judge by signal, not clock. Silence + only rich skips is OK."""
    if live_cheap_intent > 0 and live_order_id == 0:
        verdict = "ALARM_intent_no_order_id"
        note = "cheap intent logged + no order_id. Auth/API problem. Do not wait."
    elif paper_btc5_rest >= 5 and live_cheap_intent == 0 and (hours_up or 0) >= 12:
        verdict = "WATCH_paper_rest_live_zero_intent"
        note = "paper BTC 5m rested a lot; live has zero cheap intent for many hours."
    else:
        verdict = "OK_rich_skips_only"
        note = "long time + only rich/missing skips is not a fault. Hole seen and not posted is the fault."
    return {
        "verdict": verdict,
        "live_cheap_intent": int(live_cheap_intent),
        "live_order_id": int(live_order_id),
        "paper_btc5_rest": int(paper_btc5_rest),
        "hours_up": hours_up,
        "note": note,
    }


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _in_window(rec: dict[str, Any], *, since: datetime | None) -> bool:
    if since is None:
        return True
    ts = _parse_ts(rec.get("ts") or rec.get("generated"))
    if ts is None:
        return True
    return ts >= since


def _is_btc_5m(rec: dict[str, Any]) -> bool:
    return str(rec.get("asset") or "").strip().lower() == "btc" and str(rec.get("tf") or "") == "5m"


def _is_rest_intent(rec: dict[str, Any]) -> bool:
    return str(rec.get("reason") or "") == "rest" or rec.get("intent") is True


def taker_fee_usd(price: float, size: float) -> float:
    p = float(price)
    return float(TAKER_FEE_K) * p * (1.0 - p) * float(size)


def adverse_action(fill_px: float | None, opp_ask: float | None) -> str:
    """one leg filled → complete only if fill_px+opp<=0.90 else cancel leftover."""
    if fill_px is None or opp_ask is None:
        return "cancel_missing_opp"
    pair = float(fill_px) + float(opp_ask)
    if pair > 1.0 + 1e-12:
        return "pair_gt_1_refused"
    if pair > PAIR_MAX + 1e-12:
        return "rich_complete"
    return "complete"


def fee_estimated_net_pnl(orders: list[dict[str, Any]]) -> float | None:
    """Maker fee 0. Taker only on FOK complete. None if nothing was sent."""
    sent = [o for o in orders if o.get("order_id")]
    if not sent:
        return None
    pnl = 0.0
    seen_complete = False
    for order in sent:
        filled = float(order.get("filled_size") or 0.0)
        if filled <= 0:
            continue
        px = float(order.get("price") or 0.0)
        kind = str(order.get("type") or "GTC").upper()
        if kind == "FOK":
            pnl -= taker_fee_usd(px, filled)
            seen_complete = True
        # complete-set redeem ~ $1 vs pair cost is only known after both legs
    both = [o for o in sent if float(o.get("filled_size") or 0.0) > 0]
    if len(both) >= 2:
        cost = sum(float(o.get("price") or 0.0) * float(o.get("filled_size") or 0.0) for o in both[:2])
        size = min(float(both[0].get("filled_size") or 0.0), float(both[1].get("filled_size") or 0.0))
        pnl += size - cost
        return pnl
    if seen_complete:
        return pnl
    return 0.0


def _still_rate(rows: list[dict[str, Any]]) -> float | None:
    probed = [r for r in rows if r.get("still_there_250ms") is not None]
    if not probed:
        return None
    return sum(1 for r in probed if r.get("still_there_250ms") is True) / len(probed)


def _scan_paper(*, since: datetime | None) -> dict[str, Any]:
    rows = load_jsonl(PAPER_MAKER) if PAPER_MAKER.is_file() else []
    win = [r for r in rows if _in_window(r, since=since)]
    btc5 = [r for r in win if _is_btc_5m(r)]
    rests_all = [r for r in win if str(r.get("reason") or "") == "rest"]
    rests_btc5 = [r for r in btc5 if str(r.get("reason") or "") == "rest"]
    pair_gt1_trade = sum(1 for r in win if r.get("pair_gt_1_trade") is True)
    return {
        "paper_rows_24h": len(win),
        "n_rest_intent_btc5_paper": len(rests_btc5),
        "n_rest_intent_paper_all_books": len(rests_all),
        "still250_rate_btc5_paper": _still_rate(rests_btc5),
        "still250_rate_paper_all_books": _still_rate(rests_all),
        "still250_field_on_all_paper_rests": (
            all("still_there_250ms" in r and r.get("still_there_250ms") is not None for r in rests_all[-80:])
            if rests_all
            else None
        ),
        "pair_gt_1_trade_paper": pair_gt1_trade,
        "paper_real_fill_nonnull": sum(1 for r in win if r.get("real_fill") is not None),
    }


def _scan_micro(*, since: datetime | None) -> dict[str, Any]:
    rows = load_jsonl(MICRO_LIVE) if MICRO_LIVE.is_file() else []
    win = [r for r in rows if _in_window(r, since=since)]
    intents = [r for r in win if _is_rest_intent(r)]
    fills: list[dict[str, Any]] = []
    n_partial = 0
    n_cancel = 0
    n_pair_gt1_trade = 0
    for rec in win:
        if rec.get("pair_gt_1_trade") is True:
            n_pair_gt1_trade += 1
        rf = rec.get("real_fill")
        if not isinstance(rf, dict):
            continue
        orders = list(rf.get("orders") or [])
        fills.extend(o for o in orders if o.get("order_id"))
        for order in orders:
            st = str(order.get("status") or "")
            if st == "partial":
                n_partial += 1
            if st in {"cancelled", "canceled"} or rec.get("cancel_reason"):
                n_cancel += 1
    extra_fills = load_jsonl(FILL_LOG) if FILL_LOG.is_file() else []
    extra_fills = [r for r in extra_fills if _in_window(r, since=since) and r.get("order_id")]
    if extra_fills and not fills:
        fills = extra_fills
        n_partial = sum(1 for o in fills if str(o.get("status") or "") == "partial")
        n_cancel = sum(1 for o in fills if str(o.get("status") or "") in {"cancelled", "canceled"})
    sent = [o for o in fills if o.get("order_id")]
    filled = sum(float(o.get("filled_size") or 0.0) for o in sent)
    rested = sum(float(o.get("rested_size") or o.get("size") or 0.0) for o in sent)
    real_rate = (filled / rested) if sent and rested > 0 else None
    return {
        "n_rest_intent_micro": len(intents),
        "still250_rate_micro": _still_rate(intents),
        "n_real_orders": len(sent),
        "real_fill_rate": real_rate,
        "n_partial": n_partial,
        "n_cancel": n_cancel,
        "n_pair_gt_1_trade": n_pair_gt1_trade,
        "net_pnl_usd": fee_estimated_net_pnl(sent),
    }


def build_24h(
    *,
    auth_reason: str,
    sent: bool,
    halted_on_loss: bool,
    clip: float = 5.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    paper = _scan_paper(since=since)
    micro = _scan_micro(since=since)
    n_rest = int(micro["n_rest_intent_micro"] or 0) + int(paper["n_rest_intent_btc5_paper"] or 0)
    still = micro["still250_rate_micro"]
    if still is None:
        still = paper["still250_rate_btc5_paper"]
    pair_gt1 = int(micro["n_pair_gt_1_trade"] or 0) + int(paper["pair_gt_1_trade_paper"] or 0)
    real_rate = micro["real_fill_rate"] if sent else None
    if not sent:
        real_rate = None
    pnl = micro["net_pnl_usd"] if sent else None
    health = signal_health(
        live_cheap_intent=int(micro["n_rest_intent_micro"] or 0),
        live_order_id=int(micro["n_real_orders"] or 0),
        paper_btc5_rest=int(paper["n_rest_intent_btc5_paper"] or 0),
        hours_up=None,
    )
    return {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "universe": "btc 5m only",
        "clip": float(clip),
        "auth_reason": auth_reason,
        "sent": bool(sent),
        "n_rest_intent": n_rest,
        "still250_rate": still,
        "still250_rate_paper_all_books": paper["still250_rate_paper_all_books"],
        "still250_logging_on_paper_maker": paper["still250_field_on_all_paper_rests"],
        "real_fill_rate": real_rate,
        "n_partial": 0 if not sent else int(micro["n_partial"] or 0),
        "n_cancel": 0 if not sent else int(micro["n_cancel"] or 0),
        "net_pnl_usd": pnl,
        "hit_max_daily_loss": bool(halted_on_loss),
        "pair_gt_1_trade": pair_gt1,
        "paper": paper,
        "micro": micro,
        "signal_health": health,
        "note": (
            "real_fill_rate is null until an order is sent. "
            "Do not invent real_fill. micro trial ≠ full live. No size bump."
        ),
    }


def render_24h_md(payload: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, float):
            return f"{v:.6g}"
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    lines = [
        "# MICRO_LIVE_24H",
        "",
        f"Generated: {payload.get('generated')}",
        "BTC 5m only. clip 5. No pair>1 trade. No clip 10/67. No multi-asset live.",
        "No Whiskas live. No 06dc live. No full LIVE_READY.",
        "Layers unmixed: INTENT / still_there_250ms / REAL FILL.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| n_rest_intent | {fmt(payload.get('n_rest_intent'))} |",
        f"| still250_rate | {fmt(payload.get('still250_rate'))} |",
        f"| real_fill_rate | {fmt(payload.get('real_fill_rate'))} |",
        f"| n_partial | {fmt(payload.get('n_partial'))} |",
        f"| n_cancel | {fmt(payload.get('n_cancel'))} |",
        f"| fee-estimated net PnL | {fmt(payload.get('net_pnl_usd'))} |",
        f"| hit max_daily_loss? | {fmt(payload.get('hit_max_daily_loss'))} |",
        f"| any pair>1 trade? | {fmt(payload.get('pair_gt_1_trade'))} |",
        f"| AUTH | {fmt(payload.get('auth_reason'))} |",
        f"| sent | {fmt(payload.get('sent'))} |",
        f"| signal_health | {fmt((payload.get('signal_health') or {}).get('verdict'))} |",
        f"| clip | {fmt(payload.get('clip'))} |",
        "",
        f"- paper_maker still250 logging (all books, diagnostic): {fmt(payload.get('still250_logging_on_paper_maker'))}",
        f"- paper_maker still250_rate all books (not BTC-5m trial): {fmt(payload.get('still250_rate_paper_all_books'))}",
        "- BTC 5m still250_rate is null when n_rest_intent=0 (book has been rich).",
        "- Judge by signal, not clock: 2–6h with only rich skips is OK. Alarm = cheap intent + no order_id.",
        "- real_fill is null unless an order_id was returned. Not invented.",
        "- micro trial ≠ full live; next step only if real_fill>0 and loss cap OK",
        "",
    ]
    return "\n".join(lines)


def write_24h(payload: dict[str, Any]) -> Path:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    PROC.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_24h_md(payload), encoding="utf-8")
    PROC.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return REPORT


def layer_records(rec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split one snapshot into three layer dicts. REAL FILL omitted unless order_id exists."""
    base = {
        "ts": rec.get("ts"),
        "slug": rec.get("slug"),
        "asset": rec.get("asset") or "btc",
        "tf": rec.get("tf") or "5m",
        "t0": rec.get("t0"),
        "clip": rec.get("clip"),
        "bid_sum": rec.get("bid_sum"),
        "pair_gt_1_trade": False,
    }
    intent = {
        **base,
        "layer": "INTENT",
        "intent": bool(rec.get("intent")),
        "reason": rec.get("reason"),
        "bid_sum_0": rec.get("bid_sum_0", rec.get("bid_sum")),
        "min_size_0": rec.get("min_size_0", rec.get("min_bid_size")),
    }
    still = {
        **base,
        "layer": "still_there_250ms",
        "still_there_250ms": rec.get("still_there_250ms"),
        "still250": rec.get("still250"),
        "bid_sum_250": rec.get("bid_sum_250"),
        "min_size_250": rec.get("min_size_250"),
    }
    out: dict[str, dict[str, Any]] = {"INTENT": intent, "still_there_250ms": still}
    rf = rec.get("real_fill")
    orders = []
    if isinstance(rf, dict):
        orders = [o for o in (rf.get("orders") or []) if o.get("order_id")]
    if orders:
        out["REAL FILL"] = {
            **base,
            "layer": "REAL FILL",
            "orders": [
                {
                    "order_id": o.get("order_id"),
                    "status": o.get("status"),
                    "filled_size": o.get("filled_size"),
                    "trader_side": o.get("trader_side"),
                    "fill_role": o.get("fill_role"),
                }
                for o in orders
            ],
            "real_fill_rate": rec.get("real_fill_rate"),
            "lag_ms": rec.get("lag_ms"),
            "adverse_action": rec.get("adverse_action", rec.get("adverse")),
            "residual": rec.get("residual"),
            "fill_role": rec.get("fill_role"),
            "s1_edge": rec.get("s1_edge"),
            "both_fill": rec.get("both_fill"),
            "one_leg": rec.get("one_leg"),
        }
    return out
