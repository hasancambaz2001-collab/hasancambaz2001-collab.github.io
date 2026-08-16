#!/usr/bin/env python3
"""Second paper process: 0x06dc51826bc524d9a83770e7de9dd7e005b04524. GET only.

Do not edit paper_whiskas.py. Do not write data/paper/intended.jsonl.
No live. No pair>1 taker. No both-taker unless ask_sum<=0.96.

06dc truth = this paper + dump + T6. l2_recorder is 5m/15m only and does not cover daily/monthly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.constants import GAMMA_API
from whiskas.http import get_json
from whiskas.paper import best_ask, fetch_book, load_jsonl, size_at_or_better

WALLET = "0x06dc51826bc524d9a83770e7de9dd7e005b04524"
CLIP_DEFAULT = 20.0
INTERVAL_DEFAULT = 60.0
CONFIRM_DELAY_SEC = 0.25
PAIR_TAKER_MAX = 0.96
PAIR_HARD_CAP = 1.0
R6_BID_MAX = 0.99
DAYS = 5
MONTHLY_HORIZON_D = 40

ASSETS = (
    ("btc", "bitcoin"),
    ("eth", "ethereum"),
    ("sol", "solana"),
    ("xrp", "xrp"),
)
DEFAULT_OUT = ROOT / "data" / "paper06dc" / "intended.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "paper06dc" / "overnight_summary.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "PAPER_06DC.md"
FIVE_M_JSONL = ROOT / "data" / "paper" / "intended.jsonl"


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    return []


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


def daily_slug(full_name: str, day: datetime, kind: str) -> str:
    d = day.astimezone(timezone.utc)
    return f"{full_name}-{kind}-on-{d.strftime('%B').lower()}-{d.day}-{d.year}"


def best_bid(book: dict[str, Any] | None) -> tuple[float | None, float]:
    """Max bid price. Size is at that price only."""
    if not book:
        return None, 0.0
    best_p: float | None = None
    best_sz = 0.0
    for level in book.get("bids") or []:
        try:
            price = float(level.get("price"))
            size = float(level.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or size < 0:
            continue
        if best_p is None or price > best_p:
            best_p = price
            best_sz = size
        elif price == best_p:
            best_sz += size
    return best_p, best_sz


def tokens_yes_no(market: dict[str, Any]) -> dict[str, str]:
    outcomes = [str(x) for x in _parse_json_list(market.get("outcomes"))]
    token_ids = [str(x) for x in _parse_json_list(market.get("clobTokenIds"))]
    out: dict[str, str] = {}
    for outcome, token_id in zip(outcomes, token_ids):
        key = outcome.strip().lower()
        if not token_id:
            continue
        if key in {"yes", "up"}:
            out["Yes"] = token_id
        elif key in {"no", "down"}:
            out["No"] = token_id
    return out


def gamma_yes(market: dict[str, Any]) -> float | None:
    if market.get("bestAsk") is not None:
        try:
            p = float(market["bestAsk"])
            if 0.0 < p <= 1.0:
                return p
        except (TypeError, ValueError):
            pass
    prices = _parse_json_list(market.get("outcomePrices"))
    if prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    return None


def asset_from_text(*parts: str) -> str:
    text = " ".join(p or "" for p in parts).lower()
    if "bitcoin" in text or "btc" in text:
        return "btc"
    if "ethereum" in text or "ether" in text:
        return "eth"
    if "solana" in text or "sol" in text:
        return "sol"
    if "xrp" in text:
        return "xrp"
    return "other"


def keep_monthly_event(event: dict[str, Any], now: datetime) -> bool:
    if event.get("closed") is True:
        return False
    title = str(event.get("title") or "")
    slug = str(event.get("slug") or "")
    blob = f"{title} {slug}".lower()
    if not any(c in blob for c in ("bitcoin", "ethereum", "solana", "xrp", "btc", "eth")):
        return False
    end = _parse_ts(event.get("endDate"))
    if end is not None and end < now - timedelta(hours=6):
        return False
    if "august" in blob:
        return True
    if end is None:
        return True
    return end <= now + timedelta(days=MONTHLY_HORIZON_D)


def in_rule_band(yes: float | None, kind: str) -> bool:
    if kind == "daily_ud":
        return True
    if yes is None:
        return False
    if yes <= 0.01 or yes >= 0.99:
        return False
    if yes <= 0.03 or yes >= 0.97:
        return True
    if 0.03 < yes <= 0.35:
        return True
    if 0.65 <= yes <= 0.93:
        return True
    if 0.35 <= yes <= 0.65:
        return True
    return False


def target_from_market(
    *,
    kind: str,
    asset: str,
    day: str | None,
    event_slug: str,
    market: dict[str, Any],
) -> dict[str, Any] | None:
    tokens = tokens_yes_no(market)
    if "Yes" not in tokens or "No" not in tokens:
        return None
    yes = gamma_yes(market)
    return {
        "kind": kind,
        "asset": asset,
        "day": day,
        "event_slug": event_slug,
        "market_slug": str(market.get("slug") or event_slug),
        "question": str(market.get("question") or market.get("title") or ""),
        "tokens": tokens,
        "gamma_yes": yes,
    }


def discover_daily(now: datetime | None = None, days: int = DAYS) -> list[dict[str, Any]]:
    day0 = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset in range(0, max(1, int(days))):
        day = day0 + timedelta(days=offset)
        day_s = day.date().isoformat()
        for asset, full in ASSETS:
            for kind_slug, kind in (
                ("up-or-down", "daily_ud"),
                ("price", "bracket"),
                ("above", "bracket"),
            ):
                slug = daily_slug(full, day, kind_slug)
                try:
                    events = get_json(f"{GAMMA_API}/events", {"slug": slug}, timeout=20, retries=2, pause=0.04)
                except Exception:
                    continue
                for event in _as_list(events):
                    if not isinstance(event, dict):
                        continue
                    for market in event.get("markets") or []:
                        if not isinstance(market, dict):
                            continue
                        tgt = target_from_market(
                            kind=kind,
                            asset=asset,
                            day=day_s,
                            event_slug=str(event.get("slug") or slug),
                            market=market,
                        )
                        if tgt is None:
                            continue
                        key = tgt["market_slug"]
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(tgt)
    return out


def discover_monthly(now: datetime | None = None) -> list[dict[str, Any]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    queries = []
    for _asset, full in ASSETS:
        queries.append(f"will {full} dip to")
        queries.append(f"will {full} reach")
    for q in queries:
        for page in (1, 2):
            try:
                payload = get_json(
                    f"{GAMMA_API}/public-search",
                    {"q": q, "page": page},
                    timeout=20,
                    retries=2,
                    pause=0.05,
                )
            except Exception:
                continue
            events = payload.get("events") if isinstance(payload, dict) else []
            for event in events or []:
                if not isinstance(event, dict) or not keep_monthly_event(event, now):
                    continue
                event_slug = str(event.get("slug") or "")
                asset = asset_from_text(event.get("title"), event_slug)
                for market in event.get("markets") or []:
                    if not isinstance(market, dict):
                        continue
                    tgt = target_from_market(
                        kind="monthly",
                        asset=asset,
                        day=None,
                        event_slug=event_slug,
                        market=market,
                    )
                    if tgt is None:
                        continue
                    key = tgt["market_slug"]
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(tgt)
    return out


_TARGET_CACHE: dict[str, Any] = {"ts": 0.0, "targets": []}
TARGET_CACHE_SEC = 600.0


def discover_targets(now: datetime | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    if not force and _TARGET_CACHE["targets"] and time.time() - float(_TARGET_CACHE["ts"]) < TARGET_CACHE_SEC:
        return list(_TARGET_CACHE["targets"])
    daily = discover_daily(now)
    monthly = discover_monthly(now)
    targets = daily + monthly
    _TARGET_CACHE["ts"] = time.time()
    _TARGET_CACHE["targets"] = targets
    return targets


def decide_06dc(
    *,
    kind: str,
    yes_ask: float | None,
    no_ask: float | None,
    yes_bid: float | None,
    no_bid: float | None,
    depth_yes: float,
    depth_no: float,
    clip: float = CLIP_DEFAULT,
) -> dict[str, Any]:
    """Measure-only policy. Never live. Never both-taker if pair>0.96."""
    rec: dict[str, Any] = {
        "taker_intend": False,
        "maker_intend": False,
        "rule": None,
        "r1": False,
        "r3": False,
        "r4": False,
        "r5": False,
        "r6": False,
        "atm_watch": False,
        "resolved_lock": False,
        "reason": "watch",
        "orders": [],
        "maker_orders": [],
        "ask_sum": None if yes_ask is None or no_ask is None else float(yes_ask) + float(no_ask),
        "bid_sum": None if yes_bid is None or no_bid is None else float(yes_bid) + float(no_bid),
    }
    if yes_ask is not None and (float(yes_ask) <= 0.01 + 1e-12 or float(yes_ask) >= 0.99 - 1e-12):
        rec["resolved_lock"] = True
        rec["reason"] = "resolved_lock"
        return rec

    ask_sum = rec["ask_sum"]
    if (
        yes_ask is not None
        and no_ask is not None
        and ask_sum is not None
        and ask_sum + 1e-12 <= PAIR_TAKER_MAX
        and min(float(depth_yes), float(depth_no)) + 1e-12 >= float(clip)
    ):
        rec["taker_intend"] = True
        rec["r3"] = True
        rec["rule"] = "R3"
        rec["reason"] = "r3_set"
        rec["orders"] = [
            {"side": "BUY", "outcome": "Yes", "type": "FOK", "price": float(yes_ask), "size": float(clip)},
            {"side": "BUY", "outcome": "No", "type": "FOK", "price": float(no_ask), "size": float(clip)},
        ]
    elif ask_sum is not None and ask_sum + 1e-12 >= PAIR_HARD_CAP:
        rec["reason"] = "pair_ge_1"
    elif yes_ask is not None and no_ask is not None and ask_sum is not None and ask_sum > PAIR_TAKER_MAX:
        rec["reason"] = "pair_gt_096_no_both_taker"

    if not rec["taker_intend"] and yes_ask is not None:
        y = float(yes_ask)
        if y <= 0.03 + 1e-12 and float(depth_no) + 1e-12 >= float(clip) and no_ask is not None:
            rec["taker_intend"] = True
            rec["r1"] = True
            rec["rule"] = "R1"
            rec["reason"] = "r1_tail_buy_no"
            rec["orders"] = [
                {"side": "BUY", "outcome": "No", "type": "FOK", "price": float(no_ask), "size": float(clip)}
            ]
        elif y >= 0.97 - 1e-12 and float(depth_yes) + 1e-12 >= float(clip):
            rec["taker_intend"] = True
            rec["r1"] = True
            rec["rule"] = "R1"
            rec["reason"] = "r1_tail_buy_yes"
            rec["orders"] = [
                {"side": "BUY", "outcome": "Yes", "type": "FOK", "price": y, "size": float(clip)}
            ]
        elif kind in {"bracket", "monthly"} and 0.65 - 1e-12 <= y <= 0.93 + 1e-12 and float(depth_yes) + 1e-12 >= float(clip):
            rec["taker_intend"] = True
            rec["r4"] = True
            rec["rule"] = "R4"
            rec["reason"] = "r4_favorite_buy_yes"
            rec["orders"] = [
                {"side": "BUY", "outcome": "Yes", "type": "FOK", "price": y, "size": float(clip)}
            ]
        elif kind in {"bracket", "monthly"} and 0.03 + 1e-12 < y <= 0.35 + 1e-12 and no_ask is not None and float(depth_no) + 1e-12 >= float(clip):
            rec["taker_intend"] = True
            rec["r5"] = True
            rec["rule"] = "R5"
            rec["reason"] = "r5_fade_buy_no"
            rec["orders"] = [
                {"side": "BUY", "outcome": "No", "type": "FOK", "price": float(no_ask), "size": float(clip)}
            ]

    if rec["orders"] and rec["ask_sum"] is not None and rec["ask_sum"] + 1e-12 >= PAIR_HARD_CAP and rec["r3"]:
        rec["taker_intend"] = False
        rec["r3"] = False
        rec["orders"] = []
        rec["reason"] = "pair_ge_1"

    atm = yes_ask is not None and 0.35 - 1e-12 <= float(yes_ask) <= 0.65 + 1e-12
    r6_ok = kind == "daily_ud" or (kind == "bracket" and atm)
    bid_sum = rec["bid_sum"]
    if r6_ok and yes_bid is not None and no_bid is not None and bid_sum is not None and bid_sum <= R6_BID_MAX + 1e-12:
        rec["maker_intend"] = True
        rec["r6"] = True
        rec["maker_orders"] = [
            {"side": "BUY", "outcome": "Yes", "type": "GTC", "price": float(yes_bid), "size": float(clip), "maker_bid": True},
            {"side": "BUY", "outcome": "No", "type": "GTC", "price": float(no_bid), "size": float(clip), "maker_bid": True},
        ]
        if rec["rule"] is None:
            rec["rule"] = "R6"
            rec["reason"] = "r6_maker_both_bid"

    # ATM is watch only. No directional taker (R4/R5 stay bracket+monthly).
    # daily_ud ATM logs atm_watch even when R6 maker_intend fires.
    if atm and not rec["taker_intend"]:
        rec["atm_watch"] = True
        if rec["reason"] in {"watch", "pair_ge_1", "pair_gt_096_no_both_taker"} and not rec["maker_intend"]:
            rec["reason"] = "atm_watch"

    return rec


def snapshot_market(
    target: dict[str, Any],
    *,
    clip: float,
    books: dict[str, dict[str, Any]] | None = None,
    fetch: bool = True,
) -> dict[str, Any]:
    kind = str(target.get("kind") or "daily_ud")
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "book": "06dc",
        "wallet": WALLET,
        "kind": kind,
        "asset": target.get("asset"),
        "day": target.get("day"),
        "event_slug": target.get("event_slug"),
        "slug": target.get("market_slug"),
        "question": target.get("question"),
        "clip": float(clip),
        "live_order": False,
        "maker_bid": False,
        "taker_intend": False,
        "maker_intend": False,
        "rule": None,
        "r1": False,
        "r3": False,
        "r4": False,
        "r5": False,
        "r6": False,
        "atm_watch": False,
        "orders": [],
        "maker_orders": [],
        "still_there_250ms": None,
        "yes_ask": None,
        "no_ask": None,
        "yes_bid": None,
        "no_bid": None,
        "ask_sum": None,
        "bid_sum": None,
        "gamma_yes": target.get("gamma_yes"),
    }
    tokens = target.get("tokens") or {}
    if "Yes" not in tokens or "No" not in tokens:
        rec["reason"] = "missing_tokens"
        return rec
    rec["token_yes"] = tokens["Yes"]
    rec["token_no"] = tokens["No"]
    if not fetch:
        rec["reason"] = "out_of_band"
        return rec
    try:
        if books is not None:
            book_yes = books.get("Yes") or {}
            book_no = books.get("No") or {}
        else:
            book_yes = fetch_book(tokens["Yes"])
            book_no = fetch_book(tokens["No"])
    except Exception as exc:
        rec["error"] = f"clob:{exc}"
        rec["reason"] = "clob_error"
        return rec
    yes_ask, depth_yes = best_ask(book_yes)
    no_ask, depth_no = best_ask(book_no)
    yes_bid, bid_yes_sz = best_bid(book_yes)
    no_bid, bid_no_sz = best_bid(book_no)
    rec["yes_ask"] = yes_ask
    rec["no_ask"] = no_ask
    rec["yes_bid"] = yes_bid
    rec["no_bid"] = no_bid
    rec["depth_yes"] = depth_yes
    rec["depth_no"] = depth_no
    rec["bid_yes_sz"] = bid_yes_sz
    rec["bid_no_sz"] = bid_no_sz
    rec["min_ask_size"] = min(depth_yes, depth_no) if yes_ask is not None and no_ask is not None else 0.0
    rec["depth_ok"] = rec["min_ask_size"] + 1e-12 >= float(clip)
    d = decide_06dc(
        kind=kind,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_bid=yes_bid,
        no_bid=no_bid,
        depth_yes=depth_yes,
        depth_no=depth_no,
        clip=clip,
    )
    rec.update({k: d[k] for k in (
        "taker_intend", "maker_intend", "rule", "r1", "r3", "r4", "r5", "r6",
        "atm_watch", "resolved_lock", "reason", "orders", "maker_orders", "ask_sum", "bid_sum",
    )})
    rec["maker_bid"] = bool(rec["maker_intend"])
    rec["intend"] = bool(rec["taker_intend"])
    rec["live_order"] = False
    return rec


def append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def _empty_kind() -> dict[str, int]:
    return {
        "rows": 0,
        "taker_intend": 0,
        "maker_intend": 0,
        "R1": 0,
        "R4": 0,
        "R5": 0,
        "R6": 0,
        "atm_watch": 0,
    }


def summarize_06dc(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None = None,
    clip: float = CLIP_DEFAULT,
) -> dict[str, Any]:
    kinds = {k: _empty_kind() for k in ("daily_ud", "bracket", "monthly")}
    first_ts = None
    last_ts = None
    for rec in rows:
        ts = _parse_ts(rec.get("ts"))
        if since is not None and ts is not None and ts < since:
            continue
        kind = str(rec.get("kind") or "daily_ud")
        if kind not in kinds:
            kinds[kind] = _empty_kind()
        cell = kinds[kind]
        cell["rows"] += 1
        if first_ts is None or (ts is not None and ts < first_ts):
            first_ts = ts
        if last_ts is None or (ts is not None and ts > last_ts):
            last_ts = ts
        if rec.get("taker_intend") or rec.get("intend"):
            cell["taker_intend"] += 1
        if rec.get("maker_intend"):
            cell["maker_intend"] += 1
        if rec.get("r1"):
            cell["R1"] += 1
        if rec.get("r4"):
            cell["R4"] += 1
        if rec.get("r5"):
            cell["R5"] += 1
        if rec.get("r6"):
            cell["R6"] += 1
        if rec.get("atm_watch"):
            cell["atm_watch"] += 1
    totals = _empty_kind()
    for cell in kinds.values():
        for key in totals:
            totals[key] += cell[key]
    return {
        "rows": totals["rows"],
        "taker_intend": totals["taker_intend"],
        "maker_intend": totals["maker_intend"],
        "R1": totals["R1"],
        "R4": totals["R4"],
        "R5": totals["R5"],
        "R6": totals["R6"],
        "atm_watch": totals["atm_watch"],
        "kinds": kinds,
        "clip": float(clip),
        "wallet": WALLET,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "note": "06dc measure-only. No live. No pair>1 taker. Separate from 5m jsonl.",
    }


def write_report(stats: dict[str, Any], path: Path) -> str:
    lines = [
        "# paper_06dc",
        "",
        f"Wallet `{WALLET}`. Clip **20**. No live. No pair>1 taker. R3 both-taker only if ask_sum≤0.96.",
        "R1 tail / R4 favorite / R5 fade-wide / R6 maker bids. ATM without R6 = watch.",
        "Second process. Not merged with 5m/15m/4h jsonl.",
        "",
        "| kind | rows | taker_intend | maker_intend | R1 | R4 | R5 | R6 | atm_watch |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    kinds = stats.get("kinds") or {}
    for kind in ("daily_ud", "bracket", "monthly"):
        row = kinds.get(kind) or _empty_kind()
        lines.append(
            f"| {kind} | {row['rows']} | {row['taker_intend']} | {row['maker_intend']} | "
            f"{row['R1']} | {row['R4']} | {row['R5']} | {row['R6']} | {row['atm_watch']} |"
        )
    lines.append(
        f"| **all** | {stats.get('rows', 0)} | {stats.get('taker_intend', 0)} | "
        f"{stats.get('maker_intend', 0)} | {stats.get('R1', 0)} | {stats.get('R4', 0)} | "
        f"{stats.get('R5', 0)} | {stats.get('R6', 0)} | {stats.get('atm_watch', 0)} |"
    )
    lines.extend(
        [
            "",
            f"Window: {stats.get('first_ts')} → {stats.get('last_ts')}",
            "",
            f"{stats.get('note', '')}",
            "",
        ]
    )
    text = "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def run_loop(
    *,
    out_path: Path,
    once: bool,
    seconds: float,
    interval: float,
    clip: float,
    confirm_delay: float = CONFIRM_DELAY_SEC,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    rows: list[dict[str, Any]] = []
    n_cycles = 0
    n_lines = 0
    next_tick = time.time()
    counts = {"monthly": 0, "R4": 0, "R5": 0, "R6": 0, "bracket": 0, "daily_ud": 0}
    while True:
        targets = discover_targets()
        monthly_n = sum(1 for t in targets if t.get("kind") == "monthly")
        cycle_hits = {"R4": 0, "R5": 0, "R6": 0}
        for target in targets:
            kind = str(target.get("kind") or "")
            fetch = in_rule_band(target.get("gamma_yes"), kind)
            if kind != "daily_ud" and not fetch:
                continue
            try:
                rec = snapshot_market(target, clip=clip, fetch=True)
            except Exception as exc:
                rec = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "book": "06dc",
                    "kind": kind,
                    "slug": target.get("market_slug"),
                    "live_order": False,
                    "taker_intend": False,
                    "maker_intend": False,
                    "reason": "poll_error",
                    "error": str(exc),
                }
            if rec.get("taker_intend") and rec.get("token_yes") and rec.get("orders"):
                time.sleep(max(0.0, float(confirm_delay)))
                ok = True
                try:
                    for order in rec["orders"]:
                        tid = rec["token_yes"] if order["outcome"] == "Yes" else rec["token_no"]
                        book = fetch_book(str(tid), pause=0.0)
                        if size_at_or_better(book, float(order["price"])) + 1e-12 < float(order["size"]):
                            ok = False
                            break
                except Exception:
                    ok = False
                rec["still_there_250ms"] = ok
                rec["ts_250ms"] = datetime.now(timezone.utc).isoformat()
            rec["live_order"] = False
            append_jsonl(out_path, rec)
            n_lines += 1
            rows.append(rec)
            if rec.get("kind") in {"daily_ud", "bracket", "monthly"}:
                counts[rec["kind"]] += 1
            if rec.get("r4"):
                counts["R4"] += 1
                cycle_hits["R4"] += 1
            if rec.get("r5"):
                counts["R5"] += 1
                cycle_hits["R5"] += 1
            if rec.get("r6"):
                counts["R6"] += 1
                cycle_hits["R6"] += 1
        n_cycles += 1
        print(
            json.dumps(
                {
                    "book": "06dc",
                    "cycle": n_cycles,
                    "lines": n_lines,
                    "monthly_discovered": monthly_n,
                    "monthly_rows": counts["monthly"],
                    "R4": counts["R4"],
                    "R5": counts["R5"],
                    "R6": counts["R6"],
                    "live_order": False,
                }
            ),
            flush=True,
        )
        if once or (deadline is not None and time.time() >= deadline):
            break
        next_tick += max(1.0, float(interval))
        sleep_for = next_tick - time.time()
        if sleep_for < 0:
            next_tick = time.time()
            sleep_for = 1.0
        time.sleep(sleep_for)
    return rows, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="06dc paper. Never sends orders.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seconds", type=float, default=0.0)
    parser.add_argument("--interval", type=float, default=INTERVAL_DEFAULT)
    parser.add_argument("--clip", type=float, default=CLIP_DEFAULT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--since-file", type=Path, default=None)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.out.resolve() == FIVE_M_JSONL.resolve():
        print("refusing to write the 5m jsonl", file=sys.stderr)
        return 2
    since = _parse_since(args.since)
    if args.since_file and args.since_file.is_file():
        since = _parse_since(args.since_file.read_text(encoding="utf-8").splitlines()[0])
    if args.summary:
        stats = summarize_06dc(load_jsonl(args.out), since=since, clip=args.clip)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        print(write_report(stats, args.report))
        print(json.dumps(stats, indent=2))
        return 0
    rows, counts = run_loop(
        out_path=args.out,
        once=bool(args.once),
        seconds=args.seconds,
        interval=args.interval,
        clip=float(args.clip),
    )
    if args.once:
        for rec in rows:
            if rec.get("taker_intend") or rec.get("maker_intend") or rec.get("atm_watch"):
                print(
                    json.dumps(
                        {
                            "kind": rec.get("kind"),
                            "asset": rec.get("asset"),
                            "slug": rec.get("slug"),
                            "yes_ask": rec.get("yes_ask"),
                            "no_ask": rec.get("no_ask"),
                            "yes_bid": rec.get("yes_bid"),
                            "no_bid": rec.get("no_bid"),
                            "ask_sum": rec.get("ask_sum"),
                            "bid_sum": rec.get("bid_sum"),
                            "taker_intend": rec.get("taker_intend"),
                            "maker_intend": rec.get("maker_intend"),
                            "rule": rec.get("rule"),
                            "atm_watch": rec.get("atm_watch"),
                            "live_order": False,
                        }
                    )
                )
        print(
            json.dumps(
                {
                    "once": True,
                    "monthly": counts["monthly"],
                    "R4": counts["R4"],
                    "R5": counts["R5"],
                    "R6": counts["R6"],
                    "rows": len(rows),
                    "live_order": False,
                }
            ),
            flush=True,
        )
    print(f"appended to {args.out} book=06dc clip={args.clip} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
