#!/usr/bin/env python3
"""MICRO CLOB path: GTC / cancel / status. Not LIVE_READY.

Default: measurement + yaml only. Does not send.

Send is refused unless ALL of:
  1) user passes --send-live-orders-now  (explicit "send live orders now")
  2) configs/generated/MICRO_LIVE_TRIAL.yaml exists
  3) data/ops/G6_fill_calibrated.flag exists
  4) --i-accept-micro-risk
  5) local CLOB keys present

--send alone is not enough. Keys from env / configs/.env.clob. Never print.
pair_gt_1_trade=false. No clip 67. micro trial ≠ full solve.
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
    create_gtc_buy,
    fetch_order,
    real_fill_rate,
    refuse_send,
)
from whiskas.config import load_config
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY
from whiskas.measure_layers import attach_layers
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


def load_micro() -> dict[str, Any] | None:
    if not MICRO.is_file():
        return None
    return load_config(MICRO)


def clip_cap(*, g5: bool, yaml_clip: float | None) -> float:
    hard = CLIP_WITH_G5 if g5 else CLIP_NO_G5
    want = float(yaml_clip) if yaml_clip is not None else hard
    return min(want, hard)


def write_report(payload: dict[str, Any]) -> None:
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
        "- MICRO ≠ LIVE_READY. No clip 67. pair_gt_1_trade=false.",
        f"- {still}",
        f"- live_ready_exists: {payload.get('live_ready_exists')}",
        f"- g5: {payload.get('g5')}",
        "",
    ]
    (REPORTS / "MICRO_CLOB.md").write_text("\n".join(lines), encoding="utf-8")


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
        "clip_cap": clip_cap(g5=g5, yaml_clip=(micro or {}).get("clip")),
        "note": "AUTH_ABSENT => do not send, do not fake real_fill. micro trial ≠ full solve.",
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


def run_send(*, seconds: float, interval: float) -> dict[str, Any]:
    if not (ROOT / G6_FLAG).is_file():
        return {"ok": False, "reason": "G6 flag missing; refuse send", "sent": False, "real_fill_rate": None}
    micro = load_micro()
    if not micro:
        return {"ok": False, "reason": "MICRO yaml missing", "sent": False, "real_fill_rate": None}
    g5 = (ROOT / G5_FLAG).is_file()
    clip = clip_cap(g5=g5, yaml_clip=micro.get("clip"))
    client = connect(derive_l2=False)
    if client is None:
        payload = probe()
        payload["ok"] = True
        payload["sent"] = False
        payload["real_fill_rate"] = None
        payload["block"] = "AUTH_ABSENT"
        return payload
    deadline = time.time() + max(0.0, float(seconds))
    open_windows: dict[int, list[dict[str, Any]]] = {}
    daily_loss = 0.0
    n_sent = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    while time.time() < deadline:
        if daily_loss + 1e-12 >= float(micro.get("max_daily_loss_usd") or 25.0):
            for orders in list(open_windows.values()):
                cancel_open(client, orders, reason="daily_loss")
            break
        rec, _state = snapshot_maker(asset="btc", tf="5m", clip=clip)
        t0 = int(rec.get("t0") or current_t0(tf="5m"))
        bid_sum = rec.get("bid_sum")
        if t0 in open_windows and bid_sum is not None and float(bid_sum) > CANCEL_ABOVE + 1e-12:
            cancel_open(client, open_windows.pop(t0), reason="rich_cancel")
        if (
            rec.get("reason") == "rest"
            and t0 not in open_windows
            and len(open_windows) < int(micro.get("max_open_windows") or 2)
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
        append_jsonl(OUT, rec)
        time.sleep(max(0.5, float(interval)))
    payload = probe()
    payload["sent"] = n_sent > 0
    payload["n_sent_windows"] = n_sent
    payload["real_fill_rate"] = None if n_sent == 0 else payload.get("real_fill_rate")
    payload["clip"] = clip
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="MICRO CLOB path. Default: measurement only. No send.")
    parser.add_argument("--send", action="store_true", help="ignored unless --send-live-orders-now")
    parser.add_argument(
        "--send-live-orders-now",
        action="store_true",
        dest="send_now",
        help="required explicit phrase. Still needs MICRO yaml + G6 flag + keys.",
    )
    parser.add_argument("--i-accept-micro-risk", action="store_true", dest="accept")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.send and not args.send_now:
        print(json.dumps({
            "ok": False,
            "sent": False,
            "real_fill_rate": None,
            "reason": "refused: --send alone is not enough; need --send-live-orders-now + MICRO yaml + G6 flag",
        }))
        return 2
    if args.send_now:
        if not args.accept:
            print(json.dumps({"ok": False, "sent": False, "reason": "pass --i-accept-micro-risk"}))
            return 2
        if not (ROOT / G6_FLAG).is_file() or load_micro() is None:
            print(json.dumps({
                "ok": False,
                "sent": False,
                "real_fill_rate": None,
                "reason": "need MICRO_LIVE_TRIAL.yaml and G6_fill_calibrated.flag",
            }))
            return 2
        payload = run_send(seconds=float(args.seconds), interval=float(args.interval))
    else:
        payload = probe()
    write_report(payload)
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
        "note": payload.get("note"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
