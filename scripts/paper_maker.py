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

from whiskas.config import load_config
from whiskas.l2 import BookTick, PolicyMaker, decide_maker, level_eaten
from whiskas.measure_layers import apply_still250_send_gate, attach_layers, still250_ok
from whiskas.paper import (
    append_jsonl,
    asset_window_slug,
    best_ask,
    best_bid,
    book_key,
    cached_discover_tokens,
    current_t0,
    fetch_books_parallel,
    load_jsonl,
    normalize_tf,
)

CLIP_DEFAULT = 10.0
INTERVAL_DEFAULT = 1.0
PAPER_POLL_MAX = 1.0
PAIR_MAX = 0.90
CANCEL_ABOVE = 0.92
REQUOTE_MAX = 2.0
STILL_PROBE_SEC = 0.25
REST_MAX = PAIR_MAX
CANCEL_RICH = CANCEL_ABOVE
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


PAPER_ONLY_YAML = ROOT / "configs" / "generated" / "PAPER_ONLY.yaml"


def load_maker_yaml() -> dict[str, Any]:
    """Read PAPER_ONLY.yaml when present, else maker.yaml. Never live. No pair>1."""
    path = PAPER_ONLY_YAML if PAPER_ONLY_YAML.is_file() else (ROOT / "configs" / "maker.yaml")
    cfg = load_config(path)
    paper = cfg
    assets = paper.get("assets") or list(MAKER_ASSETS)
    tfs = paper.get("tfs") or list(MAKER_TFS)
    requote = float(paper.get("requote", paper.get("interval", INTERVAL_DEFAULT)))
    if requote > REQUOTE_MAX + 1e-12:
        requote = REQUOTE_MAX
    smart = paper.get("smart_copy") or {}
    return {
        "path": str(path),
        "pair_max": float(paper.get("pair_max", paper.get("rest_max", PAIR_MAX))),
        "cancel_above": float(paper.get("cancel_above", paper.get("cancel_rich", CANCEL_ABOVE))),
        "clip": float(paper.get("clip", CLIP_DEFAULT)),
        "requote": min(requote, PAPER_POLL_MAX),
        "interval": min(requote, PAPER_POLL_MAX),
        "max_age_sec": float(paper.get("max_age_sec", MAX_AGE_SEC)),
        "assets": tuple(str(a).strip().lower() for a in assets),
        "tfs": tuple(str(t).strip().lower() for t in tfs if str(t).strip().lower() in {"5m", "15m"}),
        "live_order": False,
        "live_orders": False,
        "pair_gt_1": False,
        "pair_gt_1_trade": False,
        "size_ok": False,
        "shadow_only": bool(smart.get("shadow_only", True)),
    }


def _parse_since(text: str | None) -> datetime | None:
    if not text:
        return None
    return _parse_ts(text.strip())


def snapshot_maker(
    *,
    asset: str,
    tf: str,
    clip: float = CLIP_DEFAULT,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
    now: float | None = None,
    pair_max: float = PAIR_MAX,
    cancel_above: float = CANCEL_ABOVE,
    token_cache: dict[str, dict[str, str]] | None = None,
    latency_variant: str | None = None,
    book_cache: Any = None,
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
        "t_intent": None,
        "intent_ts": None,
        "still_ms": None,
        "sign_ms": None,
        "post_ack_ms": None,
        "lag_ms": None,
        "token_cache_hit": None,
        "latency_variant": latency_variant,
        "still250_source": None,
        "book_get_ms": None,
    }
    try:
        if tokens is not None:
            tok = tokens
            rec["token_cache_hit"] = None
        else:
            tok, hit = cached_discover_tokens(slug, token_cache)
            rec["token_cache_hit"] = hit
    except Exception as exc:
        rec["error"] = f"gamma:{exc}"
        rec["reason"] = "gamma_error"
        rec["orders"] = []
        return attach_layers(rec), state
    if "Up" not in tok or "Down" not in tok:
        rec["error"] = "missing_tokens"
        rec["reason"] = "missing_tokens"
        rec["orders"] = []
        if token_cache is not None:
            token_cache.pop(slug, None)
        return attach_layers(rec), state
    rec["token_up"] = tok["Up"]
    rec["token_down"] = tok["Down"]
    try:
        if books is not None:
            book_up = books.get("Up") or {}
            book_down = books.get("Down") or {}
        else:
            t_books = time.time()
            book_up, book_down = fetch_books_parallel(tok["Up"], tok["Down"])
            rec["book_get_ms"] = (time.time() - t_books) * 1000.0
            if book_cache is not None and hasattr(book_cache, "set_tokens"):
                book_cache.set_tokens(tok["Up"], tok["Down"])
    except Exception as exc:
        rec["error"] = f"clob:{exc}"
        rec["reason"] = "clob_error"
        rec["orders"] = []
        if token_cache is not None:
            token_cache.pop(slug, None)
        return attach_layers(rec), state
    bid_up, sz_up = best_bid(book_up)
    bid_down, sz_down = best_bid(book_down)
    ask_up, ask_sz_up = best_ask(book_up)
    ask_down, ask_sz_down = best_ask(book_down)
    tick = BookTick(
        t=ts_now,
        slug=slug,
        asset=str(asset).strip().lower(),
        tf=tf_key,
        t0=t0,
        bu=bid_up,
        bd=bid_down,
        au=ask_up,
        ad=ask_down,
        su=sz_up,
        sd=sz_down,
        sau=ask_sz_up,
        sad=ask_sz_down,
    )
    policy = PolicyMaker(pair_max=float(pair_max), cancel_above=float(cancel_above), clip=float(clip), fill="residual")
    decision, next_state = policy.step(tick, state)
    rec.update(decision)
    rec["live_order"] = False
    rec["pair_gt_1"] = False
    rec["pair_max"] = float(pair_max)
    rec["cancel_above"] = float(cancel_above)
    rec["bid_sum"] = decision.get("bid_sum")
    rec["asset"] = str(asset).strip().lower()
    rec["tf"] = tf_key
    still = None
    if str(decision.get("reason") or "") == "rest":
        rec["t_intent"] = time.time()
        rec["intent_ts"] = datetime.fromtimestamp(float(rec["t_intent"]), tz=timezone.utc).isoformat()
        t_still = time.time()
        still = _probe_still250(
            tokens=tok,
            clip=float(clip),
            pair_max=float(pair_max),
            books=books,
            latency_variant=latency_variant,
            book_cache=book_cache,
        )
        rec["still_ms"] = (time.time() - t_still) * 1000.0
        if still is None:
            still = {
                "still_there_250ms": False,
                "bid_sum_250": None,
                "min_size_250": None,
                "probe_error": True,
            }
        elif still.get("still_ms") is not None:
            rec["still_ms"] = still.get("still_ms")
        rec["still250_source"] = (still or {}).get("still250_source")
        rec["book_age_up_ms"] = (still or {}).get("book_age_up_ms")
        rec["book_age_down_ms"] = (still or {}).get("book_age_down_ms")
    attach_layers(rec, still=still, clip=float(clip), pair_max=float(pair_max))
    if str(rec.get("reason") or "") == "rest":
        if rec.get("still_there_250ms") is None:
            rec["still_there_250ms"] = False
            rec["still250"] = False
        rec["still250_absent"] = False
        apply_still250_send_gate(rec, pair_max=float(pair_max))
        if rec.get("send_blocked"):
            next_state = None
    else:
        rec["would_send"] = False
        rec.setdefault("send_blocked", None)
    return rec, next_state


def _probe_still250(
    *,
    tokens: dict[str, str],
    clip: float,
    pair_max: float,
    books: dict[str, dict[str, Any]] | None = None,
    latency_variant: str | None = None,
    book_cache: Any = None,
) -> dict[str, Any] | None:
    """still250 = bid_sum<=pair_max and min_size>=clip. v2 may use WS age ≤250ms."""
    from whiskas.latency_grid import V2

    t0 = time.time()
    source = "rest_sleep"
    extra: dict[str, Any] = {}
    if books is not None:
        book_up = books.get("Up") or {}
        book_down = books.get("Down") or {}
        source = "injected"
    elif latency_variant == V2 and book_cache is not None:
        fresh = book_cache.fresh_books(tokens["Up"], tokens["Down"], max_age_sec=STILL_PROBE_SEC)
        if fresh:
            book_up = fresh["Up"]
            book_down = fresh["Down"]
            source = "ws_age"
            extra["book_age_up_ms"] = fresh.get("age_up_ms")
            extra["book_age_down_ms"] = fresh.get("age_down_ms")
        else:
            time.sleep(STILL_PROBE_SEC)
            try:
                book_up, book_down = fetch_books_parallel(tokens["Up"], tokens["Down"])
            except Exception:
                return None
            source = "rest_sleep_fallback"
    else:
        time.sleep(STILL_PROBE_SEC)
        try:
            book_up, book_down = fetch_books_parallel(tokens["Up"], tokens["Down"])
        except Exception:
            return None
        source = "rest_sleep"
    still_ms = (time.time() - t0) * 1000.0
    bid_up, sz_up = best_bid(book_up)
    bid_down, sz_down = best_bid(book_down)
    ask_up, _ask_sz_up = best_ask(book_up)
    ask_down, _ask_sz_down = best_ask(book_down)
    if bid_up is None or bid_down is None:
        return {
            "still_there_250ms": False,
            "bid_sum_250": None,
            "min_size_250": 0.0,
            "bid_up_250": bid_up,
            "bid_down_250": bid_down,
            "ask_up_250": ask_up,
            "ask_down_250": ask_down,
            "still_ms": still_ms,
            "still250_source": source,
            **extra,
        }
    bid_sum = float(bid_up) + float(bid_down)
    min_size = min(float(sz_up), float(sz_down))
    return {
        "still_there_250ms": still250_ok(bid_sum, min_size, clip=clip, pair_max=pair_max),
        "bid_sum_250": bid_sum,
        "min_size_250": min_size,
        "bid_up_250": float(bid_up),
        "bid_down_250": float(bid_down),
        "ask_up_250": None if ask_up is None else float(ask_up),
        "ask_down_250": None if ask_down is None else float(ask_down),
        "still_ms": still_ms,
        "still250_source": source,
        **extra,
    }


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
                "intent": rec.get("intent"),
                "skip_reason": rec.get("skip_reason"),
                "still250": rec.get("still250"),
                "still_there_250ms": rec.get("still_there_250ms"),
                "bid_sum_0": rec.get("bid_sum_0"),
                "bid_sum_250": rec.get("bid_sum_250"),
                "real_fill": rec.get("real_fill"),
                "real_fill_rate": rec.get("real_fill_rate"),
                "sim_fill": rec.get("sim_fill"),
                "live_order": False,
                "pair_gt_1": False,
                "pair_gt_1_trade": False,
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
    pair_max: float = PAIR_MAX,
    cancel_above: float = CANCEL_ABOVE,
) -> list[dict[str, Any]]:
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    keys = [book_key(a, t) for a in assets for t in tfs]
    states: dict[str, dict[str, Any] | None] = {k: None for k in keys}
    token_cache: dict[str, dict[str, str]] = {}
    from whiskas.latency_grid import V2, BookAgeCache, current_variant

    variant = current_variant()
    book_cache = None
    if variant == V2:
        book_cache = BookAgeCache()
        book_cache.start()
    rows: list[dict[str, Any]] = []
    n_cycles = 0
    n_lines = 0
    printed_stop = False
    next_tick = time.time()
    while True:
        for asset in assets:
            for tf in tfs:
                key = book_key(asset, tf)
                rec, new_state = snapshot_maker(
                    asset=asset,
                    tf=tf,
                    clip=clip,
                    state=states.get(key),
                    pair_max=pair_max,
                    cancel_above=cancel_above,
                    token_cache=token_cache,
                    latency_variant=variant,
                    book_cache=book_cache,
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
            if book_cache is not None:
                book_cache.stop()
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
    cfg = load_maker_yaml()
    if args.out.resolve() in {FIVE_M_JSONL.resolve(), DC06_JSONL.resolve()}:
        print("refusing to write the 5m or 06dc jsonl", file=sys.stderr)
        return 2
    assets = tuple(a.strip().lower() for a in args.assets.split(",") if a.strip()) or cfg["assets"]
    tfs = tuple(normalize_tf(t) for t in args.tfs.split(",") if t.strip())
    tfs = tuple(t for t in tfs if t in {"5m", "15m"}) or cfg["tfs"]
    interval = min(float(args.interval), float(cfg["requote"]), REQUOTE_MAX, PAPER_POLL_MAX)
    clip = float(args.clip) if args.clip != CLIP_DEFAULT else float(cfg["clip"])
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
        interval=interval,
        clip=clip,
        assets=assets,
        tfs=tfs,
        once=bool(args.once),
        seconds=float(args.seconds),
        stop_after_print=bool(args.stop_after_print),
        pair_max=float(cfg["pair_max"]),
        cancel_above=float(cfg["cancel_above"]),
    )
    print(
        f"appended to {args.out} book=maker clip={clip} pair_max={cfg['pair_max']} "
        f"cancel_above={cfg['cancel_above']} requote={interval} assets={','.join(assets)} "
        f"tfs={','.join(tfs)} rows={len(rows)} (GET only, no orders)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
