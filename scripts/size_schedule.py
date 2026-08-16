#!/usr/bin/env python3
"""Size ladder only. size_ok stays false. No live. No clip bump."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.kasa import CLIP_NOW, is_s1, load_all_windows, quantile

PROC = ROOT / "data" / "processed"
CFG = ROOT / "configs" / "size_schedule.yaml"


def main() -> int:
    if "--run" not in sys.argv:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run)", flush=True)
        return 0
    windows = load_all_windows(ROOT)
    cheap = [w for w in windows if w.get("pair") is not None and float(w["pair"]) < 0.90]
    sizes = [float(w["matched"]) for w in cheap if w.get("matched") is not None]
    target = quantile(sizes, 0.50)
    payload = {
        "size_ok": False,
        "pair_gt_1_trade": False,
        "ladder": {
            "now": CLIP_NOW,
            "after_parity": None,
            "target_p50": target,
        },
        "n_cheap": len(cheap),
        "armed": False,
        "note": "10 -> after_parity -> target_p50. after_parity not armed. size_ok=false.",
    }
    PROC.mkdir(parents=True, exist_ok=True)
    (PROC / "size_schedule.json").write_text(json.dumps(payload, indent=2) + "\n")
    yaml_out = {
        "size_ok": False,
        "pair_gt_1_trade": False,
        "ladder": {
            "now": CLIP_NOW,
            "after_parity": None,
            "target_p50": None if target is None else round(float(target), 4),
        },
        "notes": "10 -> after_parity -> target_p50 (~67). after_parity and target are recorded, not armed.",
    }
    CFG.write_text(yaml.safe_dump(yaml_out, sort_keys=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "size_ok": False,
                "now": CLIP_NOW,
                "after_parity": None,
                "target_clip_p50": None if target is None else round(float(target), 4),
                "n_cheap": len(cheap),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
