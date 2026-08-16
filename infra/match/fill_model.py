"""Fill models: none | residual | fifo_share | parity_tape. Not a go/no-go."""

from __future__ import annotations

from typing import Any


def apply_fill(
    *,
    model: str,
    intended_edge: float,
    window: dict[str, Any] | None = None,
    fill_ratio: float | None = None,
) -> float:
    key = str(model or "none").strip().lower()
    if key == "none":
        return 0.0
    if key == "parity_tape":
        # Selection upper bound: they completed the set.
        return float(intended_edge)
    if key == "residual":
        ratio = 1.0 if fill_ratio is None else float(fill_ratio)
        return float(intended_edge) * max(0.0, min(1.0, ratio))
    if key == "fifo_share":
        if window is None:
            return 0.0
        matched = float(window.get("matched") or window.get("maker_matched") or 0.0)
        displayed = max(matched, 1e-9)
        share = min(1.0, matched / (displayed * 1.25))
        return float(intended_edge) * share
    return 0.0
