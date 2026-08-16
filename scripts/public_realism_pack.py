#!/usr/bin/env python3
"""Public realism pack. Dump-native tape preferred. No live orders."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.match.fees import complete_set_edge, taker_drag
from infra.match.public_tape import COMPETITORS, competitor_flow, dump_tape_for_slug, live_trades_for_slug
from infra.match.settlement import settlement_for_slug
from whiskas.kasa import is_s1, load_tape, two_leg_windows

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DUMPS = ROOT / "data" / "dumps"


def _load_dump(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        alt = ROOT / "data" / "raw" / f"mobo_{path.stem.replace('_activity', '')}_activity.jsonl"
        if "bosona" in path.name:
            alt = ROOT / "data" / "raw" / "mobo_bosona_activity.jsonl"
        elif "mo" in path.name:
            alt = ROOT / "data" / "raw" / "mobo_mo-money_activity.jsonl"
        path = alt
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix == ".jsonl":
        return load_tape(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("rows"), list):
        return [r for r in raw["rows"] if isinstance(r, dict)]
    return []


def _progress(row: dict[str, Any], slug: str) -> float | None:
    ts = row.get("timestamp")
    if ts is None:
        return None
    t = float(ts)
    if t > 1e12:
        t /= 1000.0
    try:
        t0 = int(str(slug).rsplit("-", 1)[-1])
    except ValueError:
        return None
    if t0 <= 0:
        return None
    width = 300 if "updown-5m" in slug else (900 if "updown-15m" in slug else 300)
    return max(0.0, min(1.0, (t - t0) / width))


def run_pack(path: Path, *, max_slugs: int, label: str) -> dict[str, Any]:
    rows = _load_dump(path)
    tfs = ("5m", "15m")
    wins = [w for w in two_leg_windows(rows, tfs=tfs) if is_s1(w)]
    wins = sorted(wins, key=lambda w: float(w.get("maker_matched") or 0.0), reverse=True)[: int(max_slugs)]
    fee_rows = []
    tape_n = 0
    progresses: list[float] = []
    settlements = []
    live_n = 0
    for win in wins:
        slug = str(win["slug"])
        pair = float(win["maker_pair"])
        maker = complete_set_edge(pair, 10.0, taker=False)
        # split pair for taker drag sample
        half = pair / 2.0
        taker = complete_set_edge(pair, 10.0, taker=True, p_up=half, p_down=pair - half)
        fee_rows.append({"slug": slug, "pair": pair, "maker_clip10": maker, "taker_clip10": taker, "drag": maker - taker})
        native = dump_tape_for_slug(rows, slug)
        tape_n += len(native)
        for rec in native:
            p = _progress(rec, slug)
            if p is not None:
                progresses.append(p)
        live = live_trades_for_slug(slug, limit=20)
        live_n += len(live)
        settlements.append(settlement_for_slug(slug))
    flow = {name: 0 for name in COMPETITORS}
    for win in wins:
        for k, v in competitor_flow(rows, str(win["slug"])).items():
            flow[k] += v
    mean_prog = sum(progresses) / len(progresses) if progresses else None
    return {
        "label": label,
        "dump": str(path),
        "n_s1_slugs": len(wins),
        "fee_sample_clip10": fee_rows,
        "mean_maker_clip10": sum(x["maker_clip10"] for x in fee_rows) / len(fee_rows) if fee_rows else 0.0,
        "mean_taker_clip10": sum(x["taker_clip10"] for x in fee_rows) / len(fee_rows) if fee_rows else 0.0,
        "mean_drag": sum(x["drag"] for x in fee_rows) / len(fee_rows) if fee_rows else 0.0,
        "dump_tape_lines": tape_n,
        "live_tape_lines": live_n,
        "time_in_window_n": len(progresses),
        "time_in_window_mean": mean_prog,
        "competitor_flow": flow,
        "settlements": settlements,
        "n_gamma_found": sum(1 for s in settlements if s.get("found")),
        "note": "Gamma may return 0 for purged old 5m — use dump-native tape.",
    }


def write_reports(packs: list[dict[str, Any]]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PUBLIC_REALISM",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "Dump-native tape preferred. Old 5m may purge. No live orders.",
        "",
    ]
    for p in packs:
        lines.extend(
            [
                f"## {p['label']}",
                "",
                f"- S1 slugs sampled: {p['n_s1_slugs']}",
                f"- fee drag clip10 (maker0 − taker): **{p['mean_drag']:.4f}** (maker {p['mean_maker_clip10']:.4f} vs taker {p['mean_taker_clip10']:.4f})",
                f"- dump-native tape lines: **{p['dump_tape_lines']}**",
                f"- live API trades: {p['live_tape_lines']} (purged old 5m → 0 is OK)",
                f"- time-in-window mean: **{p['time_in_window_mean']}** n={p['time_in_window_n']}",
                f"- competitor flow: {p['competitor_flow']}",
                f"- gamma found: {p['n_gamma_found']}/{p['n_s1_slugs']}",
                "",
            ]
        )
    lines.append("Early window progress (~0.1–0.2) means rest early in 5m — feature, not bug.")
    lines.append("")
    (REPORTS / "PUBLIC_REALISM.md").write_text("\n".join(lines), encoding="utf-8")
    doors = [
        "# OPEN_DOORS",
        "",
        "Remaining public doors. Not claimed as live $.",
        "",
        "1. Post-08-14 L2 hours (recorder just started) — fill band calibration.",
        "2. PMData paid L2 since 2026-08-14 only (no key this turn).",
        "3. Public trade prints aligned to our rest price (queue trade_index).",
        "4. Gamma settlement for purged 5m — use dump-native tape.",
        "5. 06dc daily/monthly are NOT in l2_recorder (5m/15m only). Truth = dump + paper_06dc + T6. T6 n≥20 still open.",
        "6. Human YES before size_ok / clip 67.",
        "",
        "S1 decision+selection solid; fill band model; 06dc/Whiskas modules present and gated.",
        "Never claim everyone’s strategy fully simulated to live $.",
        "",
    ]
    (REPORTS / "OPEN_DOORS.md").write_text("\n".join(doors), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Public realism. No live.")
    parser.add_argument("--dump", type=Path, default=DUMPS / "bosona_activity.json")
    parser.add_argument("--max-slugs", type=int, default=8)
    parser.add_argument("--also-mo", action="store_true", default=True)
    args = parser.parse_args()
    DUMPS.mkdir(parents=True, exist_ok=True)
    packs = [run_pack(args.dump, max_slugs=args.max_slugs, label="bosona")]
    if args.also_mo:
        packs.append(run_pack(ROOT / "data" / "raw" / "mobo_mo-money_activity.jsonl", max_slugs=args.max_slugs, label="mo-money"))
    PROC.mkdir(parents=True, exist_ok=True)
    (PROC / "public_realism.json").write_text(json.dumps(packs, indent=2) + "\n")
    write_reports(packs)
    print(json.dumps({p["label"]: {k: p[k] for k in p if k not in {"fee_sample_clip10", "settlements"}} for p in packs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
