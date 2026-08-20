"""Strategy interface. No live."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    name: str
    intend: bool
    trade: bool
    reason: str
    edge: float = 0.0
    measure_edge: float = 0.0
    pair: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "intend": self.intend,
            "trade": self.trade,
            "reason": self.reason,
            "edge": self.edge,
            "measure_edge": self.measure_edge,
            "pair": self.pair,
            **self.extra,
        }


class Strategy:
    name = "base"
    trade = False

    def on_window(self, window: dict[str, Any]) -> Decision:
        return Decision(self.name, False, self.trade, "noop")

    def on_tick(self, tick: Any, state: dict[str, Any] | None) -> tuple[Decision, dict[str, Any] | None]:
        return Decision(self.name, False, self.trade, "noop"), state
