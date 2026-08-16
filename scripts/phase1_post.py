#!/usr/bin/env python3
"""Light PHASE1_POST: three wallets, activity since 2026-08-14, max 2k each. No bot."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.http import get_json
from whiskas.windows import normalize_leg

DATA_API = "https://data-api.polymarket.com"
SINCE_TS = 1786665600  # 2026-08-14 00:00:00 UTC
MAX_ROWS = 2000
LIMIT = 500

WALLETS = (
    ("bosona", "0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed"),
    ("almach", "0x3725d52f3c252e8374999cc8617292ea2608ad88"),
    ("0xb55f", "0xb55fa1296e6ec55d0ce53d93b9237389f11764d4"),
)

RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "data" / "reports"


def classify_market(event_slug: str | None, slug: str | None) -> str:
    text = f"{event_slug or ''} {slug or ''}".lower()
    if "updown-5m" in text:
        return "5m"
    if "updown-15m" in text:
        return "15m"
    return "other"


def fetch_activity(user: str, *, since: int = SINCE_TS, max_rows: int = MAX_ROWS) -> list[dict[str, Any]]:
    """Most recent activity in [since, now], capped at max_rows. GET only."""
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < max_rows and offset <= 1500:
        rows = get_json(
            f"{DATA_API}/activity",
            {
                "user": user,
                "limit": LIMIT,
                "offset": offset,
                "start": since,
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
            timeout=30,
            retries=4,
            pause=0.10,
        )
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            ts = int(row.get("timestamp") or 0)
            if ts < since:
                return out
            out.append(row)
            if len(out) >= max_rows:
                return out
        if len(rows) < LIMIT:
            break
        offset += LIMIT
    return out


def two_leg_pairs(trades: list[dict[str, Any]]) -> list[float]:
    """Size-weighted CLOB price Up+Down per eventSlug. BUY only."""
    legs: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: {"Up": [], "Down": []})
    for row in trades:
        if str(row.get("side") or "").upper() != "BUY":
            continue
        slug = str(row.get("eventSlug") or row.get("slug") or "")
        if not slug:
            continue
        leg = normalize_leg(row.get("outcome"), row.get("outcomeIndex"))
        if leg not in {"Up", "Down"}:
            continue
        size = float(row.get("size") or 0.0)
        price = float(row.get("price") or 0.0)
        if size <= 0 or price <= 0:
            continue
        legs[slug][leg].append((size, price))
    pairs: list[float] = []
    for book in legs.values():
        if not book["Up"] or not book["Down"]:
            continue
        avgs = []
        for side in ("Up", "Down"):
            q = sum(s for s, _ in book[side])
            notional = sum(s * p for s, p in book[side])
            if q <= 0:
                avgs = []
                break
            avgs.append(notional / q)
        if len(avgs) == 2:
            pairs.append(avgs[0] + avgs[1])
    return pairs


def _quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def analyze(name: str, wallet: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [r for r in rows if str(r.get("type") or "") == "TRADE"]
    n = len(trades)
    buckets = {"5m": 0, "15m": 0, "other": 0}
    buy_sizes: list[float] = []
    n_sell = 0
    for row in trades:
        buckets[classify_market(row.get("eventSlug"), row.get("slug"))] += 1
        side = str(row.get("side") or "").upper()
        if side == "SELL":
            n_sell += 1
        elif side == "BUY":
            sz = float(row.get("size") or 0.0)
            if sz > 0:
                buy_sizes.append(sz)
    pairs = two_leg_pairs(trades)
    def pct(k: str) -> float:
        return (buckets[k] / n) if n else 0.0
    return {
        "name": name,
        "wallet": wallet,
        "n_activity": len(rows),
        "n_trade": n,
        "pct_5m": pct("5m"),
        "pct_15m": pct("15m"),
        "pct_other": pct("other"),
        "n_5m": buckets["5m"],
        "n_15m": buckets["15m"],
        "n_other": buckets["other"],
        "n_pair": len(pairs),
        "pair_p25": _quantile(pairs, 0.25),
        "pair_p50": _quantile(pairs, 0.50),
        "pair_p75": _quantile(pairs, 0.75),
        "n_pair_lt_090": sum(1 for p in pairs if p < 0.90),
        "n_pair_lt_096": sum(1 for p in pairs if p < 0.96),
        "n_pair_gt_100": sum(1 for p in pairs if p > 1.00),
        "median_clip": _quantile(buy_sizes, 0.50),
        "n_sell": n_sell,
        "ts_min": min((int(r.get("timestamp") or 0) for r in rows), default=None),
        "ts_max": max((int(r.get("timestamp") or 0) for r in rows), default=None),
    }


def _fmt_pct(x: float) -> str:
    return f"{x:.1%}"


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "n/a"
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_report(stats: list[dict[str, Any]]) -> str:
    lines = [
        "# PHASE1_POST (light)",
        "",
        "Activity since **2026-08-14 00:00 UTC** only. Cap **2000** rows/wallet (Data API `/activity`, DESC).",
        "No Whiskas reopen. No bot. No replay. No live.",
        "",
        "Pair = size-weighted CLOB `price` Up + Down on the same `eventSlug` (BUY). Clip = median BUY size.",
        "",
        "| wallet | n trade | %5m | %15m | %other | pair p25 | p50 | p75 | n pair | <0.90 | <0.96 | >1.00 | med clip | SELL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['name']} | {s['n_trade']} | {_fmt_pct(s['pct_5m'])} | {_fmt_pct(s['pct_15m'])} | "
            f"{_fmt_pct(s['pct_other'])} | {_fmt(s['pair_p25'])} | {_fmt(s['pair_p50'])} | {_fmt(s['pair_p75'])} | "
            f"{s['n_pair']} | {s['n_pair_lt_090']} | {s['n_pair_lt_096']} | {s['n_pair_gt_100']} | "
            f"{_fmt(s['median_clip'], 2)} | {s['n_sell']} |"
        )
    capped = [s["name"] for s in stats if s.get("n_activity", 0) >= MAX_ROWS]
    lines.extend(
        [
            "",
            "Wallets: "
            + ", ".join(f"`{s['name']}` `{s['wallet']}`" for s in stats)
            + ".",
            "",
        ]
    )
    if capped:
        ranges = "; ".join(
            f"{s['name']} {_fmt_ts(s.get('ts_min'))} → {_fmt_ts(s.get('ts_max'))}" for s in stats
        )
        lines.append(
            f"All of {', '.join(capped)} hit the **2000-row cap**. "
            f"Table is the newest slice, not the full since-14 book. Observed: {ranges}."
        )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    all_stats: list[dict[str, Any]] = []
    for name, wallet in WALLETS:
        print(f"fetch {name} {wallet}", flush=True)
        rows = fetch_activity(wallet)
        path = RAW / f"post_{name}_activity.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        stats = analyze(name, wallet, rows)
        all_stats.append(stats)
        print(json.dumps({k: stats[k] for k in ("name", "n_activity", "n_trade", "pct_5m", "n_pair", "n_sell")}), flush=True)
    (ROOT / "data" / "processed" / "phase1_post_stats.json").write_text(
        json.dumps(all_stats, indent=2) + "\n", encoding="utf-8"
    )
    report = write_report(all_stats)
    (REPORTS / "PHASE1_POST.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
