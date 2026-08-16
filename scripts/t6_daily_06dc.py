#!/usr/bin/env python3
"""06dc daily T6 gate for R7. No live. No ATM directional invent. Do not reopen Whiskas T6."""

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

from scripts.phase1_maker_mobo import _leg
from whiskas.config import load_config
from whiskas.kasa import load_tape, tape_path
from infra.match.settlement import settlement_for_slug

HIT_MIN = 0.58
N_MIN = 20
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def _is_daily_ud(row: dict[str, Any]) -> bool:
    text = f"{row.get('eventSlug') or ''} {row.get('slug') or ''}".lower()
    return "up-or-down-on" in text


def _winner_from_redeem(rows: list[dict[str, Any]], slug: str) -> str | None:
    for row in rows:
        if str(row.get("type") or "") != "REDEEM":
            continue
        ev = str(row.get("eventSlug") or row.get("slug") or "")
        if ev != slug and str(row.get("slug") or "") != slug:
            continue
        leg = _leg(row)
        if leg in {"Up", "Down"}:
            return leg
    return None


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    books: dict[str, dict[str, float]] = defaultdict(lambda: {"Up": 0.0, "Down": 0.0})
    for row in rows:
        if str(row.get("type") or "") != "TRADE":
            continue
        if str(row.get("side") or "").upper() != "BUY":
            continue
        if not _is_daily_ud(row):
            continue
        slug = str(row.get("eventSlug") or row.get("slug") or "")
        leg = _leg(row)
        if leg not in {"Up", "Down"}:
            continue
        books[slug][leg] += float(row.get("size") or 0.0)
    samples = []
    hits = 0
    n = 0
    for slug, book in books.items():
        net = book["Up"] - book["Down"]
        if abs(net) <= 1e-6:
            continue  # complete-set / flat — not directional
        guessed = "Up" if net > 0 else "Down"
        winner = _winner_from_redeem(rows, slug)
        aligned = winner is not None
        if winner is None:
            st = settlement_for_slug(slug)
            raw = str(st.get("outcome") or "").lower()
            if raw in {"up", "yes"}:
                winner = "Up"
                aligned = True
            elif raw in {"down", "no"}:
                winner = "Down"
                aligned = True
        if winner is None:
            samples.append({"slug": slug, "guess": guessed, "winner": None, "aligned": False})
            continue
        n += 1
        hit = guessed == winner
        hits += int(hit)
        samples.append({"slug": slug, "guess": guessed, "winner": winner, "hit": hit, "aligned": aligned})
    rate = (hits / n) if n else 0.0
    if n >= N_MIN and rate + 1e-12 >= HIT_MIN:
        gate = "PASS"
        r7 = True
    elif n < N_MIN:
        gate = "UNCLEAR"
        r7 = False
    else:
        gate = "FAIL"
        r7 = False
    return {
        "n_daily_slugs": len(books),
        "n_directional_resolved": n,
        "hits": hits,
        "hit_rate": rate,
        "hit_min": HIT_MIN,
        "n_min": N_MIN,
        "gate": gate,
        "r7_daily_t6": r7,
        "samples": samples,
        "note": "No ATM directional taker invent. R7 only if hit-rate>=58% and n>=20 with spot alignment.",
    }


def main() -> int:
    if "--run" not in sys.argv:
        print(f"SCAFFOLD {Path(__file__).name} cfg={ROOT / 'configs' / '06dc.yaml'} (pass --run)")
        return 0
    cfg = load_config(ROOT / "configs" / "06dc.yaml")
    rows = load_tape(tape_path(ROOT, "06dc"))
    stats = analyze(rows)
    stats["r6_bid_max"] = float(cfg.get("r6_bid_max", 0.99))
    stats["live"] = False
    stats["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Never flip yaml r7 true unless PASS. This turn stays false if UNCLEAR/FAIL.
    if not stats["r7_daily_t6"]:
        stats["r7_written"] = False
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "t6_daily_06dc.json").write_text(json.dumps(stats, indent=2) + "\n")
    lines = [
        "# T6_DAILY_06DC",
        "",
        f"Generated: {stats['generated']}",
        "R7 enable ONLY if hit-rate≥58% and n≥20 with spot alignment. No ATM directional invent.",
        "",
        f"## GATE **{stats['gate']}**",
        "",
        f"- n directional resolved: **{stats['n_directional_resolved']}** (need ≥{N_MIN})",
        f"- hit-rate: **{stats['hit_rate']:.2%}** (need ≥{HIT_MIN:.0%})",
        f"- r7_daily_t6: **{str(stats['r7_daily_t6']).lower()}**",
        f"- R6 threshold: bid_sum≤{stats['r6_bid_max']}",
        "",
        "No live. configs/06dc.yaml r7 stays false unless GATE PASS.",
        "",
    ]
    (REPORTS / "T6_DAILY_06DC.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in stats if k != "samples"}, indent=2))
    print(f"GATE {stats['gate']} r7_daily_t6={stats['r7_daily_t6']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
