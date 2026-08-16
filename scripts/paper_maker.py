#!/usr/bin/env python3
"""Third paper: rest both bids on 5m/15m updown. GET only. Never posts.

Do not edit paper_whiskas.py or paper_06dc.py.
Do not write data/paper/intended.jsonl or data/paper06dc/intended.jsonl.
No live. No pair>1. Clip 10 on this book only.
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

from whiskas.paper import (
    append_jsonl,
    asset_window_slug,
    best_ask,
    best_bid,
    book_key,
    current_t0,
    discover_tokens,
    fetch_book,
    load_jsonl,
    normalize_tf,
)

CLIP_DEFAULT = 10.0
INTERVAL_DEFAULT = 2.0
REST_MAX = 0.90
CANCEL_RICH = 0.92
MAX_AGE_SEC = 45.0
MAKER_ASSETS = ("btc", "eth", "sol", "xrp", "doge")
MAKER_TFS = ("5m", "15m")
DEFAULT_OUT = ROOT / "data" / "paper_maker" / "intended.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "paper_maker" / "overnight_summary.json"
FIVE_M_JSONL = ROOT / "data" / "paper" / "intended.jsonl"
DC06_JSONL = ROOT / "data" / "paper06dc" / "intended.jsonl"


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


def _parse_since(text: str | None) -> datetime | None:
    if not text:
        return None
    return _parse_ts(text.strip())


def level_eaten(rest_px: float | None, best_bid_px: float | None, best_ask_px: float | None) -> bool:
    """True if our join-best bid was hit or the level disappeared below us."""
    if rest_px is None:
        return False
    if best_ask_px is not None and float(best_ask_px) <= float(rest_px) + 1e-12:
        return True
    if best_bid_px is None:
        return True
    return float(best_bid_px) + 1e-12 < float(rest_px)


def decide_maker(
    *,
    bid_up: float | None,
    bid_down: float | None,
    bid_sz_up: float,
    bid_sz_down: float,
    ask_up: float | None,
    ask_down: float | None,
    state: dict[str, Any] | None,
    now: float,
    t0: int,
    clip: float = CLIP_DEFAULT,
    rest_max: float = REST_MAX,
    cancel_rich: float = CANCEL_RICH,
    max_age: float = MAX_AGE_SEC,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Measure-only rest/requote/cancel. Never live. Never pair>1 complete."""
    bid_sum = None if bid_up is None or bid_down is None else float(bid_up) + float(bid_down)
    ask_sum = None if ask_up is None or ask_down is None else float(ask_up) + float(ask_down)
    min_bid = min(float(bid_sz_up), float(bid_sz_down)) if bid_up is not None and bid_down is not None else 0.0
    rec: dict[str, Any] = {
        "book": "maker",
        "live_order": False,
        "pair_gt_1": False,
        "clip": float(clip),
        "bid_up": bid_up,
        "bid_down": bid_down,
        "bid_sum": bid_sum,
        "bid_depth_up": float(bid_sz_up),
        "bid_depth_down": float(bid_sz_down),
        "min_bid_size": min_bid,
        "ask_up": ask_up,
        "ask_down": ask_down,
        "ask_sum": ask_sum,
        "rest": False,
        "requote": False,
        "cancel": False,
        "complete": False,
        "eaten_up": False,
        "eaten_down": False,
        "orders": [],
        "reason": "watch",
        "age_sec": None,
    }

    resting = None
    if state and int(state.get("t0") or 0) == int(t0) and state.get("px_up") is not None:
        resting = state

    if state and int(state.get("t0") or 0) != int(t0) and state.get("px_up") is not None:
        rec["cancel"] = True
        rec["reason"] = "cancel_window"
        rec["orders"] = []
        resting = None

    if resting is not None:
        age = float(now) - float(resting.get("rest_ts") or now)
        rec["age_sec"] = age
        rec["rest_px_up"] = resting.get("px_up")
        rec["rest_px_down"] = resting.get("px_down")
        eaten_up = level_eaten(resting.get("px_up"), bid_up, ask_up)
        eaten_down = level_eaten(resting.get("px_down"), bid_down, ask_down)
        rec["eaten_up"] = eaten_up
        rec["eaten_down"] = eaten_down

        if age > float(max_age) + 1e-12:
            rec["cancel"] = True
            rec["reason"] = "cancel_age"
            return rec, None

        if bid_sum is not None and bid_sum > float(cancel_rich) + 1e-12:
            rec["cancel"] = True
            rec["reason"] = "rich_cancel"
            return rec, None

        if eaten_up and eaten_down:
            rec["reason"] = "filled_both"
            rec["fill_up"] = resting.get("px_up")
            rec["fill_down"] = resting.get("px_down")
            return rec, None

        if eaten_up ^ eaten_down:
            fill_px = float(resting["px_up"] if eaten_up else resting["px_down"])
            opp = "Down" if eaten_up else "Up"
            opp_ask = ask_down if eaten_up else ask_up
            rec["fill_px"] = fill_px
            rec["opp"] = opp
            rec["opp_ask"] = opp_ask
            pair = None if opp_ask is None else float(fill_px) + float(opp_ask)
            rec["complete_pair"] = pair
            if pair is not None and pair > 1.0 + 1e-12:
                rec["cancel"] = True
                rec["reason"] = "pair_gt_1"
                rec["pair_gt_1"] = False
                return rec, None
            if pair is not None and pair <= float(rest_max) + 1e-12:
                rec["complete"] = True
                rec["reason"] = "complete"
                rec["orders"] = [
                    {
                        "side": "BUY",
                        "outcome": opp,
                        "type": "FOK",
                        "price": float(opp_ask),
                        "size": float(clip),
                        "complete": True,
                    }
                ]
                return rec, None
            rec["cancel"] = True
            rec["reason"] = "rich_complete"
            return rec, None

        moved = (
            bid_up is not None
            and bid_down is not None
            and (
                abs(float(bid_up) - float(resting["px_up"])) > 1e-12
                or abs(float(bid_down) - float(resting["px_down"])) > 1e-12
            )
        )
        can_join = (
            bid_sum is not None
            and bid_sum <= float(rest_max) + 1e-12
            and min_bid + 1e-12 >= float(clip)
        )
        if moved and can_join:
            rec["requote"] = True
            rec["rest"] = True
            rec["reason"] = "requote"
            rec["orders"] = _rest_orders(float(bid_up), float(bid_down), clip)
            return rec, _new_state(t0, now, float(bid_up), float(bid_down), clip)
        rec["reason"] = "hold"
        rec["rest"] = True
        return rec, resting

    if bid_sum is None:
        rec["reason"] = "missing_bid"
        return rec, None
    if bid_sum > 1.0 + 1e-12:
        rec["reason"] = "rich_bid_sum"
        rec["pair_gt_1"] = False
        return rec, None
    if bid_sum > float(rest_max) + 1e-12:
        rec["reason"] = "rich_bid_sum"
        return rec, None
    if min_bid + 1e-12 < float(clip):
        rec["reason"] = "thin_bid"
        return rec, None
    rec["rest"] = True
    rec["reason"] = "rest"
    rec["orders"] = _rest_orders(float(bid_up), float(bid_down), clip)
    return rec, _new_state(t0, now, float(bid_up), float(bid_down), clip)


def _rest_orders(px_up: float, px_down: float, clip: float) -> list[dict[str, Any]]:
    return [
        {"side": "BUY", "outcome": "Up", "type": "GTC", "price": float(px_up), "size": float(clip), "maker_bid": True},
        {"side": "BUY", "outcome": "Down", "type": "GTC", "price": float(px_down), "size": float(clip), "maker_bid": True},
    ]


def _new_state(t0: int, now: float, px_up: float, px_down: float, clip: float) -> dict[str, Any]:
    return {"t0": int(t0), "rest_ts": float(now), "px_up": float(px_up), "px_down": float(px_down), "clip": float(clip)}


def snapshot_maker(
    *,
    asset: str,
    tf: str,
    clip: float = CLIP_DEFAULT,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
    now: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    tf_key = normalize_tf(tf)
    ts_now = time.time() if now is None else float(now)
    t0 = current_t0(ts_now, tf=tf_key)
    slug = asset_window_slug(asset, t0, tf_key)
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "book": "maker",
        "asset": str(asset).strip().lower(),
        "tf": tf_key,
        "t0": t0,
        "slug": slug,
        "live_order": False,
        "clip": float(clip),
    }
    try:
        tok = tokens if tokens is not None else discover_tokens(slug)
    except Exception as exc:
        rec["error"] = f"gamma:{exc}"
        rec["reason"] = "gamma_error"
        rec["orders"] = []
        return rec, state
    if "Up" not in tok or "Down" not in tok:
        rec["error"] = "missing_tokens"
        rec["reason"] = "missing_tokens"
        rec["orders"] = []
        return rec, state
    rec["token_up"] = tok["Up"]
    rec["token_down"] = tok["Down"]
    try:
        if books is not None:
            book_up = books.get("Up") or {}
            book_down = books.get("Down") or {}
        else:
            book_up = fetch_book(tok["Up"])
            book_down = fetch_book(tok["Down"])
    except Exception as exc:
        rec["error"] = f"clob:{exc}"
        rec["reason"] = "clob_error"
        rec["orders"] = []
        return rec, state
    bid_up, sz_up = best_bid(book_up)
    bid_down, sz_down = best_bid(book_down)
    ask_up, _ = best_ask(book_up)
    ask_down, _ = best_ask(book_down)
    decision, new_state = decide_maker(
        bid_up=bid_up,
        bid_down=bid_down,
        bid_sz_up=sz_up,
        bid_sz_down=sz_down,
        ask_up=ask_up,
        ask_down=ask_down,
        state=state,
        now=ts_now,
        t0=t0,
        clip=clip,
    )
    rec.update(decision)
    rec["live_order"] = False
    rec["pair_gt_1"] = False
    return rec, new_state


def _interesting(rec: dict[str, Any]) -> bool:
    reason = str(rec.get("reason") or "")
    return reason == "rest" or reason.startswith("rich_") or reason in {
        "requote",
        "complete",
        "filled_both",
        "cancel_age",
        "cancel_window",
        "pair_gt_1",
    }


def print_line(rec: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "book": "maker",
                "ts": rec.get("ts"),
                "asset": rec.get("asset"),
                "tf": rec.get("tf"),
                "slug": rec.get("slug"),
                "action": rec.get("reason"),
                "reason": rec.get("reason"),
                "bid_up": rec.get("bid_up"),
                "bid_down": rec.get("bid_down"),
                "bid_sum": rec.get("bid_sum"),
                "min_bid_size": rec.get("min_bid_size"),
                "ask_sum": rec.get("ask_sum"),
                "rest": rec.get("rest"),
                "requote": rec.get("requote"),
                "cancel": rec.get("cancel"),
                "complete": rec.get("complete"),
                "age_sec": rec.get("age_sec"),
                "fill_px": rec.get("fill_px"),
                "opp_ask": rec.get("opp_ask"),
                "complete_pair": rec.get("complete_pair"),
                "live_order": False,
                "pair_gt_1": False,
            }
        ),
        flush=True,
    )


def summarize_maker(rows: list[dict[str, Any]], *, since: datetime | None = None) -> dict[str, Any]:
    counts = {
        "rows": 0,
        "rest": 0,
        "requote": 0,
        "rich_bid_sum": 0,
        "rich_cancel": 0,
        "rich_complete": 0,
        "complete": 0,
        "cancel_age": 0,
        "thin_bid": 0,
        "hold": 0,
    }
    first_ts = None
    last_ts = None
    for rec in rows:
        if rec.get("book") and rec.get("book") != "maker":
            continue
        ts = _parse_ts(rec.get("ts"))
        if since is not None and ts is not None and ts < since:
            continue
        counts["rows"] += 1
        if first_ts is None or (ts is not None and ts < first_ts):
            first_ts = ts
        if last_ts is None or (ts is not None and ts > last_ts):
            last_ts = ts
        reason = str(rec.get("reason") or "")
        if reason in counts:
            counts[reason] += 1
    counts["first_ts"] = first_ts.isoformat() if first_ts else None
    counts["last_ts"] = last_ts.isoformat() if last_ts else None
    counts["live_order"] = False
    counts["clip"] = CLIP_DEFAULT
    counts["note"] = "maker paper. GET only. No live. Separate from 5m and 06dc jsonl."
    return counts


def run_loop(
    *,
    out_path: Path,
    interval: float,
    clip: float,
    assets: tuple[str, ...],
    tfs: tuple[str, ...],
    once: bool,
    seconds: float,
    stop_after_print: bool = False,
) -> list[dict[str, Any]]:
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    keys = [book_key(a, t) for a in assets for t in tfs]
    states: dict[str, dict[str, Any] | None] = {k: None for k in keys}
    token_cache: dict[str, dict[str, str]] = {}
    rows: list[dict[str, Any]] = []
    n_cycles = 0
    n_lines = 0
    printed_stop = False
    next_tick = time.time()
    while True:
        for asset in assets:
            for tf in tfs:
                t0 = current_t0(tf=tf)
                key = book_key(asset, tf)
                slug = asset_window_slug(asset, t0, tf)
                tokens = token_cache.get(slug)
                if tokens is None:
                    try:
                        tokens = discover_tokens(slug)
                    except Exception:
                        tokens = {}
                    if tokens:
                        stale = [k for k in token_cache if k.startswith(f"{asset}-updown-{tf}-") and k != slug]
                        for old in stale:
                            token_cache.pop(old, None)
                        token_cache[slug] = tokens
                rec, new_state = snapshot_maker(
                    asset=asset,
                    tf=tf,
                    clip=clip,
                    tokens=tokens or None,
                    state=states.get(key),
                )
                rec["live_order"] = False
                states[key] = new_state
                append_jsonl(out_path, rec)
                n_lines += 1
                rows.append(rec)
                if _interesting(rec):
                    print_line(rec)
                    if stop_after_print and (
                        rec.get("reason") == "rest" or str(rec.get("reason") or "").startswith("rich_")
                    ):
                        printed_stop = True
        n_cycles += 1
        if n_cycles % 15 == 0:
            print(
                json.dumps(
                    {
                        "book": "maker",
                        "heartbeat_cycles": n_cycles,
                        "lines": n_lines,
                        "live_order": False,
                    }
                ),
                flush=True,
            )
        if once or printed_stop or (deadline is not None and time.time() >= deadline):
            break
        next_tick += max(0.2, float(interval))
        sleep_for = next_tick - time.time()
        if sleep_for < 0:
            next_tick = time.time()
            sleep_for = 0.2
        time.sleep(sleep_for)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Maker rest paper. Never sends orders.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seconds", type=float, default=0.0)
    parser.add_argument("--interval", type=float, default=INTERVAL_DEFAULT)
    parser.add_argument("--clip", type=float, default=CLIP_DEFAULT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--assets", type=str, default=",".join(MAKER_ASSETS))
    parser.add_argument("--tfs", type=str, default=",".join(MAKER_TFS))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--since-file", type=Path, default=None)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--stop-after-print",
        action="store_true",
        help="exit after the first rest or rich_* line (default: leave up)",
    )
    args = parser.parse_args()
    if args.out.resolve() in {FIVE_M_JSONL.resolve(), DC06_JSONL.resolve()}:
        print("refusing to write the 5m or 06dc jsonl", file=sys.stderr)
        return 2
    assets = tuple(a.strip().lower() for a in args.assets.split(",") if a.strip())
    tfs = tuple(normalize_tf(t) for t in args.tfs.split(",") if t.strip())
    tfs = tuple(t for t in tfs if t in {"5m", "15m"})
    since = _parse_since(args.since)
    if args.since_file and args.since_file.is_file():
        since = _parse_since(args.since_file.read_text(encoding="utf-8").splitlines()[0])
    if args.summary:
        stats = summarize_maker(load_jsonl(args.out), since=since)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(stats, indent=2))
        return 0
    rows = run_loop(
        out_path=args.out,
        interval=float(args.interval),
        clip=float(args.clip),
        assets=assets,
        tfs=tfs,
        once=bool(args.once),
        seconds=float(args.seconds),
        stop_after_print=bool(args.stop_after_print),
    )
    print(
        f"appended to {args.out} book=maker clip={args.clip} assets={','.join(assets)} "
        f"tfs={','.join(tfs)} rows={len(rows)} (GET only, no orders)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
