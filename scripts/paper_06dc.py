#!/usr/bin/env python3
"""Second paper process: 0x06dc daily Up/Down complete-set. GET only.

Do not edit paper_whiskas.py. Do not write data/paper/intended.jsonl.
No live. No pair>=1. No ATM / single-leg directional.
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

from whiskas.paper import (
    best_ask,
    confirm_ask_exists,
    discover_tokens,
    fetch_book,
    load_jsonl,
)

CLIP_DEFAULT = 20.0
INTERVAL_DEFAULT = 45.0
PAIR_MAX = 1.0  # exclusive: never intend pair>=1
CONFIRM_DELAY_SEC = 0.25
ASSETS = (
    ("btc", "bitcoin"),
    ("eth", "ethereum"),
    ("sol", "solana"),
    ("xrp", "xrp"),
)
DEFAULT_OUT = ROOT / "data" / "paper06dc" / "intended.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "paper06dc" / "overnight_summary.json"
DEFAULT_REPORT = ROOT / "data" / "reports" / "PAPER_06DC.md"


def daily_slug(full_name: str, day: datetime) -> str:
    d = day.astimezone(timezone.utc)
    return f"{full_name}-up-or-down-on-{d.strftime('%B').lower()}-{d.day}-{d.year}"


def list_targets(now: datetime | None = None, extra_days: int = 1) -> list[dict[str, Any]]:
    day0 = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out: list[dict[str, Any]] = []
    for offset in range(0, max(1, int(extra_days) + 1)):
        day = day0 + timedelta(days=offset)
        for asset, full in ASSETS:
            out.append(
                {
                    "asset": asset,
                    "full": full,
                    "day": day.date().isoformat(),
                    "slug": daily_slug(full, day),
                }
            )
    return out


def decide_complete_set(
    ask_up: float | None,
    ask_down: float | None,
    depth_up: float,
    depth_down: float,
    *,
    clip: float = CLIP_DEFAULT,
) -> dict[str, Any]:
    """Both-leg BUY FOK iff ask_sum < 1 and min_size>=clip. Never one leg."""
    base = {
        "intend": False,
        "ask_up": ask_up,
        "ask_down": ask_down,
        "ask_sum": None,
        "orders": [],
        "reason": "missing_ask",
    }
    if ask_up is None or ask_down is None:
        return base
    try:
        up = float(ask_up)
        down = float(ask_down)
    except (TypeError, ValueError):
        base["reason"] = "invalid_ask"
        return base
    if not (0.0 < up < 1.0 and 0.0 < down < 1.0):
        base["ask_sum"] = up + down
        base["reason"] = "invalid_ask"
        return base
    ask_sum = up + down
    base["ask_sum"] = ask_sum
    if ask_sum + 1e-12 >= float(PAIR_MAX):
        base["reason"] = "pair_ge_1"
        return base
    if min(float(depth_up), float(depth_down)) + 1e-12 < float(clip):
        base["reason"] = "depth_short"
        return base
    return {
        "intend": True,
        "ask_up": up,
        "ask_down": down,
        "ask_sum": ask_sum,
        "reason": "complete_set_fok",
        "orders": [
            {"side": "BUY", "outcome": "Up", "type": "FOK", "price": up, "size": float(clip)},
            {"side": "BUY", "outcome": "Down", "type": "FOK", "price": down, "size": float(clip)},
        ],
    }


def snapshot_market(
    target: dict[str, Any],
    *,
    clip: float,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    slug = target["slug"]
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "book": "06dc",
        "tf": "daily",
        "asset": target["asset"],
        "day": target["day"],
        "slug": slug,
        "clip": float(clip),
        "pair_max": float(PAIR_MAX),
        "live_order": False,
        "maker_bid": False,
        "atm_directional": False,
        "intend": False,
        "still_there_250ms": None,
        "orders": [],
    }
    try:
        tok = tokens if tokens is not None else discover_tokens(slug)
    except Exception as exc:
        rec["error"] = f"gamma:{exc}"
        rec["reason"] = "gamma_error"
        return rec
    if "Up" not in tok or "Down" not in tok:
        rec["error"] = "missing_tokens"
        rec["reason"] = "missing_tokens"
        return rec
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
        return rec
    ask_up, depth_up = best_ask(book_up)
    ask_down, depth_down = best_ask(book_down)
    rec["ask_up"] = ask_up
    rec["ask_down"] = ask_down
    rec["depth_up"] = depth_up
    rec["depth_down"] = depth_down
    rec["min_ask_size"] = min(depth_up, depth_down) if ask_up is not None and ask_down is not None else 0.0
    rec["depth_ok"] = rec["min_ask_size"] + 1e-12 >= float(clip)
    d = decide_complete_set(ask_up, ask_down, depth_up, depth_down, clip=clip)
    rec["ask_sum"] = d["ask_sum"]
    rec["intend"] = bool(d["intend"])
    rec["reason"] = d["reason"]
    rec["orders"] = d["orders"]
    if rec["intend"] and len(rec["orders"]) != 2:
        rec["intend"] = False
        rec["orders"] = []
        rec["reason"] = "atm_directional_blocked"
    return rec


def append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


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


def summarize_06dc(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None = None,
    clip: float = CLIP_DEFAULT,
) -> dict[str, Any]:
    cells: dict[tuple[str, str], dict[str, int]] = {}
    first_ts = None
    last_ts = None
    n_err = 0
    for rec in rows:
        ts = _parse_ts(rec.get("ts"))
        if since is not None and ts is not None and ts < since:
            continue
        asset = str(rec.get("asset") or "?")
        day = str(rec.get("day") or rec.get("slug") or "?")
        key = (asset, day)
        cell = cells.setdefault(
            key, {"polls": 0, "intend": 0, "depth_ok": 0, "still250": 0, "n_lt_1": 0, "n_ge_1": 0}
        )
        cell["polls"] += 1
        if first_ts is None or (ts is not None and ts < first_ts):
            first_ts = ts
        if last_ts is None or (ts is not None and ts > last_ts):
            last_ts = ts
        if rec.get("error") or rec.get("reason") in {"gamma_error", "clob_error", "poll_error"}:
            n_err += 1
        if rec.get("intend"):
            cell["intend"] += 1
        if rec.get("depth_ok") is True:
            cell["depth_ok"] += 1
        if rec.get("still_there_250ms") is True:
            cell["still250"] += 1
        try:
            s = float(rec["ask_sum"]) if rec.get("ask_sum") is not None else None
        except (TypeError, ValueError):
            s = None
        if s is not None and s + 1e-12 < PAIR_MAX:
            cell["n_lt_1"] += 1
        elif s is not None:
            cell["n_ge_1"] += 1
    table = []
    for (asset, day), cell in sorted(cells.items()):
        table.append({"asset": asset, "day": day, **cell})
    n_poll = sum(c["polls"] for c in cells.values())
    n_intend = sum(c["intend"] for c in cells.values())
    return {
        "n_poll": n_poll,
        "n_intend": n_intend,
        "n_err": n_err,
        "clip": float(clip),
        "pair_max": PAIR_MAX,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "table": table,
        "note": "06dc daily complete-set only. No live. No pair>=1. No ATM directional. Separate from 5m jsonl.",
    }


def write_report(stats: dict[str, Any], path: Path) -> str:
    lines = [
        "# paper_06dc (daily complete-set)",
        "",
        "Second process. Clip **20**. Pair **< 1.00**. No ATM directional. No live. Not the 5m jsonl.",
        "",
        "| asset | day | polls | intend | depth_ok | still250 | n_<1 | n_>=1 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats.get("table") or []:
        lines.append(
            f"| {row['asset']} | {row['day']} | {row['polls']} | {row['intend']} | "
            f"{row['depth_ok']} | {row['still250']} | {row['n_lt_1']} | {row['n_ge_1']} |"
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
    extra_days: int,
    confirm_delay: float = CONFIRM_DELAY_SEC,
) -> list[dict[str, Any]]:
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    token_cache: dict[str, dict[str, str]] = {}
    rows: list[dict[str, Any]] = []
    n_cycles = 0
    n_lines = 0
    next_tick = time.time()
    while True:
        targets = list_targets(extra_days=extra_days)
        cycle_sums: dict[str, Any] = {}
        for target in targets:
            slug = target["slug"]
            tokens = token_cache.get(slug)
            if tokens is None:
                try:
                    tokens = discover_tokens(slug)
                except Exception:
                    tokens = {}
                if tokens:
                    token_cache[slug] = tokens
            try:
                rec = snapshot_market(target, clip=clip, tokens=tokens or None)
            except Exception as exc:
                rec = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "book": "06dc",
                    "tf": "daily",
                    "asset": target["asset"],
                    "day": target["day"],
                    "slug": slug,
                    "clip": float(clip),
                    "live_order": False,
                    "intend": False,
                    "reason": "poll_error",
                    "error": str(exc),
                    "orders": [],
                    "still_there_250ms": None,
                }
            if rec.get("intend") and tokens and rec.get("ask_up") is not None and rec.get("ask_down") is not None:
                time.sleep(max(0.0, float(confirm_delay)))
                rec["still_there_250ms"] = confirm_ask_exists(
                    tokens, float(rec["ask_up"]), float(rec["ask_down"]), float(clip)
                )
                rec["ts_250ms"] = datetime.now(timezone.utc).isoformat()
            else:
                rec["still_there_250ms"] = None
            rec["live_order"] = False
            append_jsonl(out_path, rec)
            n_lines += 1
            cycle_sums[slug] = rec.get("ask_sum")
            rows.append(rec)
        n_cycles += 1
        if n_cycles % 20 == 0:
            print(
                json.dumps(
                    {
                        "book": "06dc",
                        "heartbeat_cycles": n_cycles,
                        "lines": n_lines,
                        "ask_sum": cycle_sums,
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
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="06dc daily complete-set paper. Never sends orders.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seconds", type=float, default=0.0)
    parser.add_argument("--interval", type=float, default=INTERVAL_DEFAULT)
    parser.add_argument("--clip", type=float, default=CLIP_DEFAULT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--extra-days", type=int, default=1, help="also poll tomorrow (default 1)")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--since-file", type=Path, default=None)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.out.resolve() == (ROOT / "data" / "paper" / "intended.jsonl").resolve():
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
    rows = run_loop(
        out_path=args.out,
        once=bool(args.once),
        seconds=args.seconds,
        interval=args.interval,
        clip=float(args.clip),
        extra_days=int(args.extra_days),
    )
    if args.once:
        for rec in rows:
            print(
                json.dumps(
                    {
                        "ts": rec.get("ts"),
                        "asset": rec.get("asset"),
                        "day": rec.get("day"),
                        "slug": rec.get("slug"),
                        "ask_sum": rec.get("ask_sum"),
                        "intend": rec.get("intend"),
                        "reason": rec.get("reason"),
                        "depth_ok": rec.get("depth_ok"),
                        "still_there_250ms": rec.get("still_there_250ms"),
                        "live_order": rec.get("live_order"),
                    }
                )
            )
    print(f"appended to {args.out} book=06dc clip={args.clip} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
