#!/usr/bin/env python3
"""Produce PAPER_ONLY.yaml. LIVE_READY only with G5+G6+--i-accept-risk.

No hand-edited live. No pair>1. No clip 67 day-one.
do not live without G5 G6.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.config import load_config
from whiskas.live_config import (
    COVER_MIN,
    G5_FLAG,
    G6_FLAG,
    LIVE_BLOCKED,
    LIVE_READY,
    PAPER_ONLY,
    ensure_pmdata_env_file,
    evaluate_gates,
    live_blocked_payload,
    live_ready_payload,
    live_status,
    load_pmdata_env,
    paper_only_payload,
    write_yaml,
)

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def _cover(name: str) -> float | None:
    path = PROC / f"unified_{name}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return float(data.get("cover")) if data.get("cover") is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce paper config. Live blocked by default.")
    parser.add_argument("--i-accept-risk", action="store_true", dest="accept_risk")
    args = parser.parse_args()
    ensure_pmdata_env_file(ROOT / "configs" / ".env.pmdata")
    load_pmdata_env(ROOT / "configs" / ".env.pmdata")
    cfg = load_config(ROOT / "configs" / "unified.yaml")
    paper = cfg.get("paper") or {}
    smart = cfg.get("smart_copy") or {}
    pair_gt1 = bool(cfg.get("pair_gt_1_trade", False))
    ev = evaluate_gates(
        bosona_cover=_cover("bosona"),
        mo_cover=_cover("mo-money"),
        pair_gt_1_trade=pair_gt1,
        shadow_only=bool(smart.get("shadow_only", True)),
        g5_flag=ROOT / G5_FLAG,
        g6_flag=ROOT / G6_FLAG,
        cover_min=float(cfg.get("cover_min", COVER_MIN)),
        accept_risk=bool(args.accept_risk),
    )
    paper_path = ROOT / (paper.get("path") or PAPER_ONLY)
    write_yaml(paper_path, paper_only_payload())
    status = live_status(eval_gates=ev, accept_risk=bool(args.accept_risk))
    live_path = None
    blocked_path = None
    if status == "LIVE_READY":
        live_path = write_yaml(ROOT / LIVE_READY, live_ready_payload())
    else:
        blocked_path = write_yaml(
            ROOT / LIVE_BLOCKED,
            live_blocked_payload(gates=ev["gates"]),
        )
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "status": status,
        "paper_only": str(paper_path),
        "live_blocked": str(blocked_path),
        "live_ready": None if live_path is None else str(live_path),
        "accept_risk": bool(args.accept_risk),
        "pair_gt_1_trade": False,
        "live_orders": False if status != "LIVE_READY" else True,
        "size_ok": bool(ev["gates"]["G5_size_ok"]["pass"]),
        "note": "do not live without G5 G6",
        **ev,
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "live_config.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# LIVE_CONFIG",
        "",
        f"Generated: {payload['generated']}",
        f"status: **{status}**",
        f"PAPER: `{paper_path}`",
        f"blocked file: `{blocked_path}`",
        "do not live without G5 G6",
        "",
        "| gate | result | detail |",
        "|---|---|---|",
    ]
    labels = {
        "G1_bosona_cover": "G1 bosona cover ≥80%",
        "G2_mo_cover": "G2 mo cover ≥80%",
        "G3_pair_gt1_trade": "G3 pair_gt1_trade false",
        "G4_shadow_path": "G4 shadow path",
        "G5_size_ok": "G5 size_ok",
        "G6_fill_calibration": "G6 fill calibration",
        "G7_accept_risk": "G7 --i-accept-risk",
    }
    for key, label in labels.items():
        cell = ev["gates"][key]
        mark = "PASS" if cell["pass"] else "FAIL"
        extra = {k: v for k, v in cell.items() if k != "pass"}
        lines.append(f"| {label} | **{mark}** | {extra} |")
    lines.extend([
        "",
        "No hand-edited LIVE_READY. No clip 67 day-one. No pair>1.",
        "MICRO_LIVE_TRIAL.yaml is not LIVE_READY. Full LIVE_READY stays BLOCKED without G5+G6+G7.",
        "",
    ])
    report = "\n".join(lines)
    (REPORTS / "LIVE_CONFIG.md").write_text(report, encoding="utf-8")
    (REPORTS / "LIVE_GATE_REPORT.md").write_text(report.replace("# LIVE_CONFIG", "# LIVE_GATE_REPORT"), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "paper_only": str(paper_path),
        "live_blocked": str(blocked_path),
        "live_ready": payload["live_ready"],
        "gates": {k: ("PASS" if v["pass"] else "FAIL") for k, v in ev["gates"].items()},
        "note": "do not live without G5 G6",
        "pair_gt_1_trade": False,
    }, indent=2))
    return 0 if status == "LIVE_BLOCKED" or status == "LIVE_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
