#!/usr/bin/env python3
"""Phase1 maker/taker split for mo-money + bosona. GET activity only. No live. No paper edit."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.fees import taker_fee_usdc
from whiskas.http import get_json
from whiskas.windows import normalize_leg

DATA_API = "https://data-api.polymarket.com"
MAX_ROWS = 3000
LIMIT = 500
FEE_TOL = 0.15
GATE_MAKER_SHARE = 0.25
GATE_MAKER_CHEAP_N = 5
GATE_MAKER_PAIR = 0.98

WALLETS = (
    ("mo-money", "0x32ed2e546b187ca15e2841edc82b22c713cf8ec3"),
    ("bosona", "0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed"),
)

RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "data" / "reports"
PROC = ROOT / "data" / "processed"


def is_taker_fee_match(usdc: float, size: float, price: float, *, tol: float = FEE_TOL) -> bool:
    """Taker iff embed usdc−size×price matches 0.07·p·(1−p)·size ±15%."""
    if size <= 0 or price <= 0 or price >= 1:
        return False
    exp = taker_fee_usdc(size, price)
    obs = float(usdc) - float(size) * float(price)
    band = max(abs(exp) * float(tol), 1e-5)
    return abs(obs - exp) <= band + 1e-12


def fetch_activity(user: str, *, max_rows: int = MAX_ROWS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < max_rows and offset <= 2500:
        rows = get_json(
            f"{DATA_API}/activity",
            {
                "user": user,
                "limit": LIMIT,
                "offset": offset,
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
            out.append(row)
            if len(out) >= max_rows:
                return out
        if len(rows) < LIMIT:
            break
        offset += LIMIT
    return out


def classify_tf(event_slug: str | None, slug: str | None) -> str:
    text = f"{event_slug or ''} {slug or ''}".lower()
    if "updown-5m" in text:
        return "5m"
    if "updown-15m" in text:
        return "15m"
    if "updown-4h" in text:
        return "4h"
    return "other"


def _leg(row: dict[str, Any]) -> str | None:
    leg = normalize_leg(row.get("outcome"), row.get("outcomeIndex"))
    if leg in {"Up", "Down"}:
        return leg
    o = str(row.get("outcome") or "").strip().lower()
    if o in {"yes", "up"}:
        return "Up"
    if o in {"no", "down"}:
        return "Down"
    return None


def two_leg_pairs(trades: list[dict[str, Any]]) -> list[float]:
    legs: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: {"Up": [], "Down": []})
    for row in trades:
        if str(row.get("side") or "").upper() != "BUY":
            continue
        slug = str(row.get("eventSlug") or row.get("slug") or "")
        if not slug:
            continue
        leg = _leg(row)
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
    buys = [r for r in trades if str(r.get("side") or "").upper() == "BUY"]
    n_taker = 0
    n_maker = 0
    taker_rows: list[dict[str, Any]] = []
    maker_rows: list[dict[str, Any]] = []
    tfs: Counter[str] = Counter()
    doge = 0
    for row in buys:
        size = float(row.get("size") or 0.0)
        price = float(row.get("price") or 0.0)
        usdc = float(row.get("usdcSize") or row.get("usdc") or 0.0)
        slug = f"{row.get('eventSlug') or ''} {row.get('slug') or ''}".lower()
        tfs[classify_tf(row.get("eventSlug"), row.get("slug"))] += 1
        if "doge" in slug:
            doge += 1
        if is_taker_fee_match(usdc, size, price):
            n_taker += 1
            taker_rows.append(row)
        else:
            n_maker += 1
            maker_rows.append(row)
    n_buy = len(buys)
    taker_pairs = two_leg_pairs(taker_rows)
    maker_pairs = two_leg_pairs(maker_rows)
    all_pairs = two_leg_pairs(buys)
    return {
        "name": name,
        "wallet": wallet,
        "n_activity": len(rows),
        "n_trade": len(trades),
        "n_buy": n_buy,
        "n_taker": n_taker,
        "n_maker": n_maker,
        "pct_taker": (n_taker / n_buy) if n_buy else 0.0,
        "pct_maker": (n_maker / n_buy) if n_buy else 0.0,
        "n_5m": tfs["5m"],
        "n_15m": tfs["15m"],
        "n_4h": tfs["4h"],
        "n_other": tfs["other"],
        "n_doge": doge,
        "n_pair": len(all_pairs),
        "pair_p50": _quantile(all_pairs, 0.50),
        "n_pair_lt_090": sum(1 for p in all_pairs if p < 0.90),
        "n_pair_lt_096": sum(1 for p in all_pairs if p < 0.96),
        "n_pair_gt_100": sum(1 for p in all_pairs if p > 1.00),
        "taker_n_pair": len(taker_pairs),
        "taker_pair_p50": _quantile(taker_pairs, 0.50),
        "taker_pair_lt_096": sum(1 for p in taker_pairs if p < 0.96),
        "maker_n_pair": len(maker_pairs),
        "maker_pair_p50": _quantile(maker_pairs, 0.50),
        "maker_pair_le_098": sum(1 for p in maker_pairs if p <= 0.98 + 1e-12),
        "maker_pair_gt_100": sum(1 for p in maker_pairs if p > 1.00),
        "ts_min": min((int(r.get("timestamp") or 0) for r in rows), default=None),
        "ts_max": max((int(r.get("timestamp") or 0) for r in rows), default=None),
    }


def gate(stats: list[dict[str, Any]]) -> tuple[str, str]:
    n_buy = sum(s["n_buy"] for s in stats)
    n_maker = sum(s["n_maker"] for s in stats)
    n_cheap_maker = sum(s["maker_pair_le_098"] for s in stats)
    share = (n_maker / n_buy) if n_buy else 0.0
    ok = n_buy >= 50 and share + 1e-12 >= GATE_MAKER_SHARE and n_cheap_maker >= GATE_MAKER_CHEAP_N
    reason = (
        f"maker_share={share:.1%} (need ≥{GATE_MAKER_SHARE:.0%}), "
        f"maker two-leg pair≤0.98 n={n_cheap_maker} (need ≥{GATE_MAKER_CHEAP_N})"
    )
    return ("PASS" if ok else "FAIL", reason)


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "n/a"
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_report(stats: list[dict[str, Any]], verdict: str, reason: str) -> str:
    lines = [
        "# PHASE1_MAKER_MOBO",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "Activity cap **3000** newest rows/wallet. GET `/activity` only. No live. Paper not edited.",
        "Role: **taker** iff `usdc − size×price` matches `0.07·p·(1−p)·size` ±15%. Else maker.",
        "",
        f"## GATE **{verdict}**",
        "",
        reason + ".",
        "PASS requires combined maker share ≥25% and ≥5 maker two-leg pairs with pair≤0.98 (bid-bucket gate).",
        "",
        "| wallet | n buy | %maker | %taker | 5m | 15m | doge | pair p50 | <0.96 | taker p50 | taker<0.96 | maker p50 | maker≤0.98 | maker>1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['name']} | {s['n_buy']} | {s['pct_maker']:.1%} | {s['pct_taker']:.1%} | "
            f"{s['n_5m']} | {s['n_15m']} | {s['n_doge']} | {_fmt(s['pair_p50'])} | {s['n_pair_lt_096']} | "
            f"{_fmt(s['taker_pair_p50'])} | {s['taker_pair_lt_096']} | {_fmt(s['maker_pair_p50'])} | "
            f"{s['maker_pair_le_098']} | {s['maker_pair_gt_100']} |"
        )
    lines.extend(
        [
            "",
            "Wallets: "
            + ", ".join(f"`{s['name']}` `{s['wallet']}`" for s in stats)
            + ".",
            "",
            "Observed: "
            + "; ".join(f"{s['name']} {_fmt_ts(s.get('ts_min'))} → {_fmt_ts(s.get('ts_max'))}" for s in stats)
            + ".",
            "",
            "No clip bump. No R7. No pair>1 taker. No paper restart in this step.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    if "--run" not in sys.argv:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run to dump ≤3000)", flush=True)
        return 0
    RAW.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    all_stats: list[dict[str, Any]] = []
    for name, wallet in WALLETS:
        print(f"fetch {name} {wallet}", flush=True)
        rows = fetch_activity(wallet)
        path = RAW / f"mobo_{name}_activity.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        stats = analyze(name, wallet, rows)
        all_stats.append(stats)
        print(json.dumps({k: stats[k] for k in ("name", "n_activity", "n_buy", "pct_maker", "n_doge", "maker_pair_le_098")}), flush=True)
    verdict, reason = gate(all_stats)
    (PROC / "phase1_maker_mobo.json").write_text(json.dumps({"gate": verdict, "reason": reason, "wallets": all_stats}, indent=2) + "\n")
    report = write_report(all_stats, verdict, reason)
    (REPORTS / "PHASE1_MAKER_MOBO.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"GATE {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
