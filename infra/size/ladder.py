"""Size ladder. size_ok stays false. 10 → after_parity → target_p50. Not armed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from whiskas.config import load_config

ROOT = Path(__file__).resolve().parents[2]


def load_ladder(path: Path | None = None) -> dict[str, Any]:
    paper = ROOT / "configs" / "generated" / "PAPER_ONLY.yaml"
    cfg = load_config(path or (ROOT / "configs" / "size_schedule.yaml"))
    if paper.is_file() and path is None:
        paper_cfg = load_config(paper)
        if paper_cfg.get("clip") is not None:
            cfg = {**cfg, "paper_clip": paper_cfg.get("clip", cfg.get("paper_clip", 10))}
    ladder = cfg.get("ladder") or {}
    return {
        "size_ok": False,
        "paper_clip": float(cfg.get("paper_clip", ladder.get("now", 10))),
        "now": float(ladder.get("now") or 10),
        "after_parity": ladder.get("after_parity"),
        "target_p50": ladder.get("target_p50"),
        "armed": False,
        "pair_gt_1_trade": False,
        "note": "10 -> after_parity -> target_p50 (~67). Not armed. Queue does not set size_ok.",
    }
