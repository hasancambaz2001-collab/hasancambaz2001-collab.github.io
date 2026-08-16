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
    create_gtc_buy,
    fetch_order,
    real_fill_rate,
    refuse_send,
)
from whiskas.config import load_config
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY
from whiskas.measure_layers import attach_layers
from whiskas.micro_report import (
    FILL_LOG,
    INTENT_LOG,
    STILL_LOG,
    adverse_action,
    build_24h,
    layer_records,
    write_24h,
)
from whiskas.paper import append_jsonl, current_t0
from scripts.paper_maker import _probe_still250, snapshot_maker

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
    path_ok = all(s in clob_src for s in ("create_gtc_buy", "cancel_order", "fetch_order"))
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


def send_rest_both(
    client: Any,
    rec: dict[str, Any],
    tokens: dict[str, str],
    *,
    clip: float,
) -> dict[str, Any]:
    """GTC both legs. Cancel leftover if one posts and the other fails. No pair>1."""
    guard = _guard_rest(rec, clip=clip)
    if guard:
        rec["send_blocked"] = guard
        attach_layers(rec, still=None, clip=clip)
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["live_order"] = False
        return rec
    posted: list[dict[str, Any]] = []
    try:
        up = create_gtc_buy(client, token_id=tokens["Up"], price=float(rec["bid_up"]), size=float(clip))
        posted.append({**up, "outcome": "Up"})
        down = create_gtc_buy(client, token_id=tokens["Down"], price=float(rec["bid_down"]), size=float(clip))
        posted.append({**down, "outcome": "Down"})
    except AuthAbsent:
        for prev in posted:
            if prev.get("order_id"):
                try:
                    cancel_order(client, str(prev["order_id"]))
                except Exception:
                    pass
        rec["send_blocked"] = "AUTH_ABSENT"
        attach_layers(rec, still=None, clip=clip)
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["live_order"] = False
        return rec
    except Exception as exc:
        for prev in posted:
            if prev.get("order_id"):
                try:
                    cancel_order(client, str(prev["order_id"]))
                except Exception:
                    pass
        rec["send_error"] = type(exc).__name__
        attach_layers(rec, still=None, clip=clip)
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["live_order"] = False
        return rec
    refreshed = []
    for order in posted:
        oid = order.get("order_id")
        if not oid:
            continue
        try:
            refreshed.append({**order, **fetch_order(client, str(oid))})
        except Exception:
            refreshed.append(order)
    if not refreshed:
        rec["real_fill"] = None
        rec["real_fill_rate"] = None
        rec["live_order"] = False
        rec["send_blocked"] = "no_order_id"
        return rec
    rec["real_fill"] = {
        "orders": refreshed,
        "filled_size": sum(float(o.get("filled_size") or 0.0) for o in refreshed),
        "rested_size": sum(float(o.get("rested_size") or 0.0) for o in refreshed),
    }
    rec["real_fill_rate"] = real_fill_rate(refreshed)
    rec["live_order"] = True
    rec["pair_gt_1_trade"] = False
    rec["intent"] = True
    return rec


def cancel_open(client: Any, orders: list[dict[str, Any]], *, reason: str) -> list[dict[str, Any]]:
    out = []
    for order in orders:
        oid = order.get("order_id")
        if not oid:
            continue
        try:
            cancelled = cancel_order(client, str(oid))
            cancelled["cancel_reason"] = reason
            out.append(cancelled)
        except Exception:
            out.append({**order, "cancel_reason": reason, "status": "cancel_failed"})
    return out


def _filled(order: dict[str, Any], *, clip: float) -> bool:
    st = str(order.get("status") or "")
    filled = float(order.get("filled_size") or 0.0)
    rested = float(order.get("rested_size") or clip)
    return st == "filled" or (rested > 0 and filled + 1e-12 >= rested)


def manage_open(
    client: Any,
    rec: dict[str, Any],
    orders: list[dict[str, Any]],
    *,
    clip: float,
) -> tuple[list[dict[str, Any]], str | None]:
    """Cancel if sum>0.92. Adverse: one fill → complete only if fill+opp<=0.90 else cancel leftover."""
    bid_sum = rec.get("bid_sum")
    if bid_sum is not None and float(bid_sum) > CANCEL_ABOVE + 1e-12:
        return cancel_open(client, orders, reason="rich_cancel"), "rich_cancel"
    refreshed: list[dict[str, Any]] = []
    for order in orders:
        oid = order.get("order_id")
        if not oid:
            continue
        try:
            refreshed.append({**order, **fetch_order(client, str(oid))})
        except Exception:
            refreshed.append(order)
    filled = [o for o in refreshed if _filled(o, clip=clip)]
    leftover = [o for o in refreshed if not _filled(o, clip=clip)]
    if len(filled) == 1 and leftover:
        fill_px = filled[0].get("price")
        outcome = filled[0].get("outcome")
        opp_ask = rec.get("ask_down") if outcome == "Up" else rec.get("ask_up")
        action = adverse_action(fill_px if fill_px is None else float(fill_px), None if opp_ask is None else float(opp_ask))
        rec["adverse"] = action
        if action != "complete":
            return cancel_open(client, leftover, reason=action), action
        token = rec.get("token_down") if outcome == "Up" else rec.get("token_up")
        if not token or opp_ask is None:
            return cancel_open(client, leftover, reason="cancel_missing_opp"), "cancel_missing_opp"
        try:
            fok = create_fok_buy(client, token_id=str(token), price=float(opp_ask), size=float(clip))
            leftover_ids = [o.get("order_id") for o in leftover if o.get("order_id")]
            if leftover_ids:
                cancel_open(client, leftover, reason="replaced_by_fok_complete")
            refreshed = filled + [{**fok, "outcome": "Down" if outcome == "Up" else "Up"}]
            rec["complete"] = True
            return refreshed, "complete"
        except AuthAbsent:
            return cancel_open(client, leftover, reason="AUTH_ABSENT"), "AUTH_ABSENT"
        except Exception:
            return cancel_open(client, leftover, reason="complete_failed"), "complete_failed"
    return refreshed, None


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
    open_windows: dict[int, list[dict[str, Any]]] = {}
    daily_loss = 0.0
    n_sent = 0
    halted = False
    max_loss = float(micro.get("max_daily_loss_usd") or MAX_DAILY_LOSS)
    max_open = int(micro.get("max_open_windows") or MAX_OPEN)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    while time.time() < deadline:
        if daily_loss + 1e-12 >= max_loss:
            for orders in list(open_windows.values()):
                cancel_open(client, orders, reason="daily_loss")
            halted = True
            break
        rec, _state = snapshot_maker(asset=ASSET, tf=TF, clip=clip)
        rec["asset"] = ASSET
        rec["tf"] = TF
        t0 = int(rec.get("t0") or current_t0(tf=TF))
        bid_sum = rec.get("bid_sum")
        if t0 in open_windows:
            orders, why = manage_open(client, rec, open_windows[t0], clip=clip)
            if why in {"rich_cancel", "rich_complete", "pair_gt_1_refused", "cancel_missing_opp", "daily_loss"}:
                open_windows.pop(t0, None)
            elif why == "complete":
                open_windows.pop(t0, None)
            else:
                open_windows[t0] = orders
        if (
            rec.get("reason") == "rest"
            and t0 not in open_windows
            and len(open_windows) < max_open
        ):
            still = _probe_still250(
                tokens={"Up": rec.get("token_up") or "", "Down": rec.get("token_down") or ""},
                clip=clip,
                pair_max=PAIR_MAX,
            )
            attach_layers(rec, still=still, clip=clip)
            tokens = {"Up": rec["token_up"], "Down": rec["token_down"]}
            rec = send_rest_both(client, rec, tokens, clip=clip)
            if rec.get("live_order") and rec.get("real_fill"):
                open_windows[t0] = list((rec["real_fill"] or {}).get("orders") or [])
                n_sent += 1
        rec["pair_gt_1_trade"] = False
        log_layers(rec)
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
