"""Queue v2: join BACK, hidden_factor, cancel_frac, latency_ticks. Fill band, not go/no-go."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from whiskas.l2 import BookTick, PolicyMaker, level_eaten

SCENARIOS = {
    "base": {"hidden_factor": 1.25, "cancel_frac": 0.35, "latency_ticks": 1, "label": "plan"},
    "pessimistic": {"hidden_factor": 1.60, "cancel_frac": 0.35, "latency_ticks": 2, "label": "stress"},
    "optimistic": {"hidden_factor": 1.00, "cancel_frac": 0.35, "latency_ticks": 0, "label": "upper_bound_only"},
}


@dataclass
class QueueState:
    px_up: float
    px_down: float
    ahead_up: float
    ahead_down: float
    wait: int
    filled_up: float = 0.0
    filled_down: float = 0.0
    clip: float = 10.0
    prev_su: float = 0.0
    prev_sd: float = 0.0


def _step_leg(
    *,
    rest_px: float,
    bid: float | None,
    ask: float | None,
    size: float,
    prev_size: float,
    ahead: float,
    filled: float,
    clip: float,
    cancel_frac: float,
    armed: bool,
) -> tuple[float, float]:
    if not armed or filled + 1e-12 >= clip:
        return ahead, filled
    if bid is None or (ask is not None and level_eaten(rest_px, bid, ask)):
        # level gone / crossed: remaining queue either fills or dies
        if ahead <= 1e-12:
            return 0.0, clip
        return 0.0, filled
    if abs(float(bid) - float(rest_px)) > 1e-12:
        return ahead, filled
    drop = max(0.0, float(prev_size) - float(size))
    cancels = drop * float(cancel_frac)
    trades = drop * (1.0 - float(cancel_frac))
    ahead = max(0.0, ahead - cancels - trades)
    if ahead <= 1e-12:
        return 0.0, clip
    return ahead, filled


def run_queue_on_ticks(
    ticks: Iterable[BookTick],
    *,
    clip: float = 10.0,
    hidden_factor: float = 1.25,
    cancel_frac: float = 0.35,
    latency_ticks: int = 1,
) -> dict[str, Any]:
    pm = PolicyMaker(pair_max=0.90, cancel_above=0.92, clip=clip, fill="none")
    states: dict[str, dict[str, Any] | None] = {}
    qstate: dict[str, QueueState | None] = {}
    n_rest = 0
    n_fill = 0
    filled_shares = 0.0
    intended_shares = 0.0
    for tick in ticks:
        rec, states[tick.slug] = pm.step(tick, states.get(tick.slug))
        qs = qstate.get(tick.slug)
        if rec.get("reason") == "rest" and rec.get("bid_up") is not None:
            n_rest += 1
            intended_shares += 2.0 * float(clip)
            qstate[tick.slug] = QueueState(
                px_up=float(rec["bid_up"]),
                px_down=float(rec["bid_down"]),
                ahead_up=float(tick.su) * float(hidden_factor),
                ahead_down=float(tick.sd) * float(hidden_factor),
                wait=int(latency_ticks),
                clip=float(clip),
                prev_su=float(tick.su),
                prev_sd=float(tick.sd),
            )
            continue
        if rec.get("cancel") or rec.get("reason") in {"rich_cancel", "cancel_age", "cancel_window"}:
            qstate[tick.slug] = None
            continue
        if qs is None:
            continue
        if qs.wait > 0:
            qs.wait -= 1
            qs.prev_su = float(tick.su)
            qs.prev_sd = float(tick.sd)
            continue
        qs.ahead_up, qs.filled_up = _step_leg(
            rest_px=qs.px_up,
            bid=tick.bu,
            ask=tick.au,
            size=float(tick.su),
            prev_size=qs.prev_su,
            ahead=qs.ahead_up,
            filled=qs.filled_up,
            clip=qs.clip,
            cancel_frac=cancel_frac,
            armed=True,
        )
        qs.ahead_down, qs.filled_down = _step_leg(
            rest_px=qs.px_down,
            bid=tick.bd,
            ask=tick.ad,
            size=float(tick.sd),
            prev_size=qs.prev_sd,
            ahead=qs.ahead_down,
            filled=qs.filled_down,
            clip=qs.clip,
            cancel_frac=cancel_frac,
            armed=True,
        )
        qs.prev_su = float(tick.su)
        qs.prev_sd = float(tick.sd)
        if qs.filled_up + 1e-12 >= qs.clip and qs.filled_down + 1e-12 >= qs.clip:
            n_fill += 1
            filled_shares += 2.0 * qs.clip
            qstate[tick.slug] = None
        else:
            qstate[tick.slug] = qs
    ratio = (filled_shares / intended_shares) if intended_shares else 0.0
    return {
        "n_rest": n_rest,
        "n_complete_fills": n_fill,
        "intended_shares": intended_shares,
        "filled_shares": filled_shares,
        "fill_ratio": ratio,
    }


def run_queue_on_windows(
    windows: list[dict[str, Any]],
    *,
    clip: float = 10.0,
    hidden_factor: float = 1.25,
    cancel_frac: float = 0.35,
    latency_ticks: int = 1,
) -> dict[str, Any]:
    """Coarse tape band: join back of their matched size * hidden. Not L2."""
    n_rest = 0
    filled_shares = 0.0
    intended_shares = 0.0
    for win in windows:
        pair = win.get("maker_pair") or win.get("pair")
        if pair is None or float(pair) >= 0.90:
            continue
        matched = float(win.get("maker_matched") or win.get("matched") or 0.0)
        if matched + 1e-12 < float(clip):
            continue
        n_rest += 1
        intended_shares += 2.0 * float(clip)
        ahead = matched * float(hidden_factor)
        # latency: skip a slice of the tape
        lat_pen = 1.0 / (1.0 + max(0, int(latency_ticks)))
        eat = matched * (1.0 - float(cancel_frac) * 0.25) * lat_pen
        got = min(2.0 * float(clip), max(0.0, eat / max(ahead, 1e-9) * 2.0 * float(clip)))
        filled_shares += got
    ratio = (filled_shares / intended_shares) if intended_shares else 0.0
    return {
        "n_rest": n_rest,
        "n_complete_fills": None,
        "intended_shares": intended_shares,
        "filled_shares": filled_shares,
        "fill_ratio": ratio,
        "note": "tape coarse band. hidden_factor on their matched size. Not L2.",
    }


def run_queue_v2(
    *,
    ticks: Iterable[BookTick] | None = None,
    windows: list[dict[str, Any]] | None = None,
    clip: float = 10.0,
    scenario: str = "base",
) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    kwargs = {
        "clip": clip,
        "hidden_factor": spec["hidden_factor"],
        "cancel_frac": spec["cancel_frac"],
        "latency_ticks": spec["latency_ticks"],
    }
    if ticks is not None:
        out = run_queue_on_ticks(ticks, **kwargs)
    else:
        out = run_queue_on_windows(windows or [], **kwargs)
    out["scenario"] = scenario
    out["label"] = spec["label"]
    out.update(kwargs)
    out["size_ok"] = False
    out["go_nogo"] = False
    return out
