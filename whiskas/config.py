from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from whiskas.constants import (
    CLIP,
    DAY_DD_PRODUCT,
    FILL_PROB_STRESS,
    PAIR_MAX,
    PAIR_MAX_CAP,
    START_EQUITY,
)

DEFAULT_PATH = Path("configs/whiskas.yaml")


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path is not None else DEFAULT_PATH
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {p}")
    return data


def product_from_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    fee = cfg.get("fee") or {}
    return {
        "pair_max": float(cfg.get("pair_max", PAIR_MAX)),
        "pair_max_cap": float(cfg.get("pair_max_cap", PAIR_MAX_CAP)),
        "clip": float(cfg.get("clip", CLIP)),
        "fill_prob_stress": float(cfg.get("fill_prob_stress", FILL_PROB_STRESS)),
        "day_dd": float(cfg.get("day_dd", DAY_DD_PRODUCT)),
        "start_equity": float(cfg.get("start_equity", START_EQUITY)),
        "assume_diamond": bool(fee.get("assume_diamond", False)),
        "assume_taker": bool(fee.get("assume_taker", True)),
    }
