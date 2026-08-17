#!/usr/bin/env python3
"""Assert S1 config locks: clip==5, pair_gt1 false, capital_max==5000. Not a sender."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ROOT / "configs" / "s1_micro.yaml"
OPTIONAL = (
    ROOT / "configs" / "generated" / "MICRO_LIVE_TRIAL.yaml",
)


def load_flat_yaml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            data[key] = value
    return data


def _truthy_false(value: str) -> bool:
    return value.lower() in {"false", "0", "no", "off"}


def check_config(path: Path) -> list[str]:
    errors: list[str] = []
    cfg = load_flat_yaml(path)
    clip = cfg.get("clip")
    if clip is None:
        errors.append(f"{path}: missing clip")
    else:
        try:
            if abs(float(clip) - 5.0) > 1e-12:
                errors.append(f"{path}: clip=={clip} want 5")
        except ValueError:
            errors.append(f"{path}: clip not numeric ({clip})")

    pair_gt1 = cfg.get("pair_gt1", cfg.get("pair_gt_1_trade"))
    if pair_gt1 is None:
        errors.append(f"{path}: missing pair_gt1 / pair_gt_1_trade")
    elif not _truthy_false(pair_gt1):
        errors.append(f"{path}: pair_gt1={pair_gt1} want false")

    pair_max = cfg.get("pair_max")
    if pair_max is not None:
        try:
            if float(pair_max) > 1.0 + 1e-12:
                errors.append(f"{path}: pair_max={pair_max} > 1 forbidden")
        except ValueError:
            errors.append(f"{path}: pair_max not numeric ({pair_max})")

    capital = cfg.get("capital_max")
    if path == REQUIRED:
        if capital is None:
            errors.append(f"{path}: missing capital_max")
        else:
            try:
                if abs(float(capital) - 5000.0) > 1e-12:
                    errors.append(f"{path}: capital_max=={capital} want 5000")
                if float(capital) > 5000.0 + 1e-12:
                    errors.append(f"{path}: capital_max={capital} > 5000 forbidden")
            except ValueError:
                errors.append(f"{path}: capital_max not numeric ({capital})")
    elif capital is not None:
        try:
            if float(capital) > 5000.0 + 1e-12:
                errors.append(f"{path}: capital_max={capital} > 5000 forbidden")
        except ValueError:
            errors.append(f"{path}: capital_max not numeric ({capital})")
    return errors


def main() -> int:
    errors: list[str] = []
    if not REQUIRED.is_file():
        errors.append(f"missing {REQUIRED}")
    else:
        errors.extend(check_config(REQUIRED))
    for path in OPTIONAL:
        if path.is_file():
            errors.extend(check_config(path))
    if errors:
        for err in errors:
            print(err)
        print("check_invariants FAIL")
        return 1
    print("check_invariants PASS clip==5 pair_gt1=false capital_max==5000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
