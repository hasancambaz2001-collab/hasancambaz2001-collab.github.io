#!/usr/bin/env python3
"""Validate mobo maker config on THEIR tape. Not paper intends. No live.

PASS = cover ≥80% of their pair<0.90 two-leg 5m/15m windows.
Config: pair_max=0.90, maker_only, clip=10.
Do not treat paper_maker rest lines as PnL.
"""

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

from scripts.phase1_maker_mobo import WALLETS, _leg, classify_tf, is_taker_fee_match
from whiskas.config import load_config

PAIR_MAX = 0.90
CLIP = 10.0
COVER_MIN = 0.80
TFS = ("5m", "15m")
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
FORBIDDEN_TAPE = (
    ROOT / "data" / "paper_maker" / "intended.jsonl",
    ROOT / "data" / "paper" / "intended.jsonl",
    ROOT / "data" / "paper06dc" / "intended.jsonl",
)


def tape_path(name: str) -> Path:
    return RAW / f"mobo_{name}_activity.jsonl"


def load_tape(path: Path) -> list[dict[str, Any]]:
    resolved = path.resolve()
    if resolved in {p.resolve() for p in FORBIDDEN_TAPE}:
        raise ValueError("refusing paper intends as tape; use their activity jsonl")
    if not path.is_file():
        raise FileNotFoundError(f"missing tape {path} (run scripts/phase1_maker_mobo.py --run)")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if isinstance(rec, dict):
                rows.append(rec)
    return rows


def two_leg_windows(rows: list[dict[str, Any]], *, tfs: tuple[str, ...] = TFS) -> list[dict[str, Any]]:
    """BUY two-leg 5m/15m windows on their tape. Pair = size-weighted CLOB prices."""
    legs: dict[str, dict[str, list[tuple[float, float, bool]]]] = defaultdict(lambda: {"Up": [], "Down": []})
    meta: dict[str, str] = {}
    for row in rows:
        if str(row.get("type") or "") != "TRADE":
            continue
        if str(row.get("side") or "").upper() != "BUY":
            continue
        tf = classify_tf(row.get("eventSlug"), row.get("slug"))
        if tf not in tfs:
            continue
        slug = str(row.get("eventSlug") or row.get("slug") or "")
        if not slug:
            continue
        leg = _leg(row)
        if leg not in {"Up", "Down"}:
            continue
        size = float(row.get("size") or 0.0)
        price = float(row.get("price") or 0.0)
        usdc = float(row.get("usdcSize") or row.get("usdc") or 0.0)
        if size <= 0 or price <= 0:
            continue
        taker = is_taker_fee_match(usdc, size, price)
        legs[slug][leg].append((size, price, taker))
        meta[slug] = tf
    out: list[dict[str, Any]] = []
    for slug, book in legs.items():
        if not book["Up"] or not book["Down"]:
            continue
        avgs: list[float] = []
        qs: list[float] = []
        maker_q = [0.0, 0.0]
        taker_n = 0
        maker_n = 0
        for i, side in enumerate(("Up", "Down")):
            q = sum(s for s, _, _ in book[side])
            notional = sum(s * p for s, p, _ in book[side])
            maker_q[i] = sum(s for s, _, t in book[side] if not t)
            taker_n += sum(1 for *_, t in book[side] if t)
            maker_n += sum(1 for *_, t in book[side] if not t)
            if q <= 0:
                avgs = []
                break
            avgs.append(notional / q)
            qs.append(q)
        if len(avgs) != 2:
            continue
        pair = avgs[0] + avgs[1]
        out.append(
            {
                "slug": slug,
                "tf": meta[slug],
                "pair": pair,
                "min_q": min(qs),
                "q_up": qs[0],
                "q_down": qs[1],
                "maker_min_q": min(maker_q),
                "any_maker": maker_n > 0,
                "all_maker": taker_n == 0,
                "maker_both_legs": maker_q[0] > 0 and maker_q[1] > 0,
            }
        )
    return out


def covers(
    window: dict[str, Any],
    *,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    maker_only: bool = True,
) -> bool:
    """Config rest rule on their observed cheap set. Not paper_maker PnL."""
    if float(window["pair"]) + 1e-12 >= float(pair_max):
        return False
    if maker_only and not window["any_maker"]:
        return False
    if float(window["min_q"]) + 1e-12 < float(clip):
        return False
    return True


def replay_wallet(
    name: str,
    wallet: str,
    rows: list[dict[str, Any]],
    *,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    maker_only: bool = True,
) -> dict[str, Any]:
    windows = two_leg_windows(rows)
    cheap = [w for w in windows if w["pair"] < 0.90]
    n_cover = sum(1 for w in cheap if covers(w, pair_max=pair_max, clip=clip, maker_only=maker_only))
    n_cheap = len(cheap)
    cover = (n_cover / n_cheap) if n_cheap else 0.0
    return {
        "name": name,
        "wallet": wallet,
        "n_tape": len(rows),
        "n_two_leg": len(windows),
        "n_cheap": n_cheap,
        "n_cover": n_cover,
        "cover": cover,
        "n_maker_both": sum(1 for w in cheap if w["maker_both_legs"]),
        "n_all_maker": sum(1 for w in cheap if w["all_maker"]),
        "pair_max": float(pair_max),
        "clip": float(clip),
        "maker_only": bool(maker_only),
        "passed": n_cheap > 0 and cover + 1e-12 >= COVER_MIN,
        "source": "their_tape",
        "pnl_from_paper_maker": False,
    }


def gate(stats: list[dict[str, Any]]) -> tuple[str, str]:
    if not stats:
        return "FAIL", "no wallets"
    ok = all(s["passed"] for s in stats)
    bits = ", ".join(f"{s['name']} {s['cover']:.0%} ({s['n_cover']}/{s['n_cheap']})" for s in stats)
    return ("PASS" if ok else "FAIL", f"cover ≥{COVER_MIN:.0%} of pair<0.90 two-leg 5m/15m: {bits}")


def write_report(stats: list[dict[str, Any]], verdict: str, reason: str) -> str:
    lines = [
        "# REPLAY_MOBO",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "Validated on **their tape** (`data/raw/mobo_*_activity.jsonl`). Not paper intends.",
        "Do **not** treat `paper_maker` rest lines as PnL.",
        "",
        f"Config: `pair_max={PAIR_MAX:.2f}` `maker_only=true` `clip={CLIP:.0f}`. TFs 5m+15m.",
        f"PASS = cover ≥{COVER_MIN:.0%} of their pair<0.90 two-leg 5m/15m windows.",
        "",
        f"## GATE **{verdict}**",
        "",
        reason + ".",
        "",
        "| wallet | two-leg 5m/15m | pair<0.90 | covered | cover | maker both legs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['name']} | {s['n_two_leg']} | {s['n_cheap']} | {s['n_cover']} | "
            f"{s['cover']:.1%} | {s['n_maker_both']} |"
        )
    lines.extend(
        [
            "",
            "Covered iff the cheap window has a maker fill and min size ≥ clip 10 "
            "(rest-both rule on their observed set). "
            "maker-both-legs is a separate count (bosona 72/80 = 90%); it is not PnL.",
            "",
            "No live. No paper restart. No clip bump on 5m/06dc.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    cfg = load_config(ROOT / "configs" / "mobo.yaml")
    pair_max = float(cfg.get("pair_max", PAIR_MAX))
    clip = float(cfg.get("clip", CLIP))
    maker_only = bool(cfg.get("maker_only", True))
    if "--paper-intends" in sys.argv:
        print("refusing paper intends as tape", file=sys.stderr)
        return 2
    all_stats: list[dict[str, Any]] = []
    for name, wallet in WALLETS:
        rows = load_tape(tape_path(name))
        stats = replay_wallet(name, wallet, rows, pair_max=pair_max, clip=clip, maker_only=maker_only)
        all_stats.append(stats)
        print(
            json.dumps(
                {
                    "name": name,
                    "cover": round(stats["cover"], 4),
                    "n_cover": stats["n_cover"],
                    "n_cheap": stats["n_cheap"],
                    "passed": stats["passed"],
                    "source": "their_tape",
                    "pnl_from_paper_maker": False,
                }
            ),
            flush=True,
        )
    verdict, reason = gate(all_stats)
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": verdict,
        "reason": reason,
        "pair_max": pair_max,
        "clip": clip,
        "maker_only": maker_only,
        "cover_min": COVER_MIN,
        "pnl_from_paper_maker": False,
        "wallets": all_stats,
    }
    (PROC / "replay_mobo.json").write_text(json.dumps(payload, indent=2) + "\n")
    report = write_report(all_stats, verdict, reason)
    (REPORTS / "REPLAY_MOBO.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"GATE {verdict}", flush=True)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
