"""Coupon builder and paper-trading ledger.

Only legs whose strategy is listed as `approved` in config/live_strategies.json
can enter a recommended coupon. Everything else is logged as `watch` so its
real-time performance (incl. closing line value) builds evidence without money.
"""
from __future__ import annotations

import csv
import itertools
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

LEDGER = os.path.join(os.path.dirname(__file__), "..", "results", "paper_ledger.csv")
STRATS = os.path.join(os.path.dirname(__file__), "..", "config", "live_strategies.json")


@dataclass
class Leg:
    match_id: str
    match: str
    kickoff: str
    market: str
    pick: str
    prob: float          # our fair probability
    odds: float          # best available price
    book: str
    strategy: str
    approved: bool = False
    pinnacle: float | None = None
    note: str = ""
    ev: float = field(init=False)

    def __post_init__(self):
        self.ev = self.prob * self.odds - 1


def load_strategies() -> dict:
    try:
        return json.load(open(STRATS))
    except FileNotFoundError:
        return {}


def build_coupons(legs: list[Leg], max_legs: int = 3, min_ev: float = 0.0):
    """Return singles, best-EV combo and highest-hit-probability combo.
    Legs from the same match are never combined (they are correlated)."""
    good = [l for l in legs if l.approved and l.ev > min_ev]
    singles = sorted(good, key=lambda l: -l.ev)
    best_ev = None
    for k in range(2, max_legs + 1):
        for combo in itertools.combinations(singles[:12], k):
            if len({l.match_id for l in combo}) < k:
                continue
            p = 1.0
            o = 1.0
            for l in combo:
                p *= l.prob
                o *= l.odds
            ev = p * o - 1
            if best_ev is None or ev > best_ev["ev"]:
                best_ev = {"legs": combo, "prob": p, "odds": o, "ev": ev}
    # "most likely to land": highest joint probability among approved +EV legs
    safe = sorted(good, key=lambda l: -l.prob)
    chosen, seen = [], set()
    for l in safe:
        if l.match_id not in seen:
            chosen.append(l)
            seen.add(l.match_id)
        if len(chosen) == max_legs:
            break
    likely = None
    if len(chosen) >= 2:
        p = o = 1.0
        for l in chosen:
            p *= l.prob
            o *= l.odds
        likely = {"legs": tuple(chosen), "prob": p, "odds": o, "ev": p * o - 1}
    return singles, best_ev, likely


def log_legs(legs: list[Leg]):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    new = not os.path.exists(LEDGER)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["logged_at", *asdict(legs[0]).keys(), "closing_odds", "result", "profit", "clv"]
                           if legs else ["logged_at"])
        if new:
            w.writeheader()
        for l in legs:
            w.writerow({"logged_at": now, **asdict(l), "closing_odds": "", "result": "", "profit": "", "clv": ""})
