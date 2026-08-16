"""Shared L2 BookTick + PolicyMaker. S1 maker complete-set. No live. No pair>1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PAIR_MAX = 0.90
CANCEL_ABOVE = 0.92
CLIP = 10.0
MAX_AGE_SEC = 45.0
REQUOTE_MAX = 2.0
REGIME_CUTOFF = datetime(2026, 8, 14, tzinfo=timezone.utc)
REGIME_PRE = "pre_2026_08_14_DEBUG"
REGIME_POST = "post_2026_08_14"
ASSETS = ("btc", "eth", "sol", "xrp", "doge")
TFS = ("5m", "15m")  # l2_recorder only. Does not cover 06dc daily/monthly.


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _size(value: Any) -> float:
    x = _finite(value)
    return 0.0 if x is None or x < 0 else float(x)


def level_eaten(rest_px: float | None, best_bid_px: float | None, best_ask_px: float | None) -> bool:
    """True if our join-best bid was hit or the level disappeared below us."""
    if rest_px is None:
        return False
    if best_ask_px is not None and float(best_ask_px) <= float(rest_px) + 1e-12:
        return True
    if best_bid_px is None:
        return True
    return float(best_bid_px) + 1e-12 < float(rest_px)


def rest_orders(px_up: float, px_down: float, clip: float) -> list[dict[str, Any]]:
    return [
        {"side": "BUY", "outcome": "Up", "type": "GTC", "price": float(px_up), "size": float(clip), "maker_bid": True},
        {"side": "BUY", "outcome": "Down", "type": "GTC", "price": float(px_down), "size": float(clip), "maker_bid": True},
    ]


def new_state(t0: int, now: float, px_up: float, px_down: float, clip: float) -> dict[str, Any]:
    return {"t0": int(t0), "rest_ts": float(now), "px_up": float(px_up), "px_down": float(px_down), "clip": float(clip)}


def regime_for_ts(ts: datetime | float | None) -> str:
    if ts is None:
        return REGIME_PRE
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    else:
        dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    if dt >= REGIME_CUTOFF:
        return REGIME_POST
    return REGIME_PRE


@dataclass(frozen=True)
class BookTick:
    """Top-of-book tick. Same fields as recorder jsonl / kachoio parquet."""

    t: float
    slug: str
    asset: str
    tf: str
    t0: int
    bu: float | None
    bd: float | None
    au: float | None
    ad: float | None
    su: float
    sd: float
    sau: float = 0.0
    sad: float = 0.0
    condition_id: str | None = None

    @property
    def bid_sum(self) -> float | None:
        if self.bu is None or self.bd is None:
            return None
        return float(self.bu) + float(self.bd)

    @property
    def ask_sum(self) -> float | None:
        if self.au is None or self.ad is None:
            return None
        return float(self.au) + float(self.ad)

    @property
    def min_bid_size(self) -> float:
        if self.bu is None or self.bd is None:
            return 0.0
        return min(float(self.su), float(self.sd))

    def to_record(self) -> dict[str, Any]:
        return {
            "t": float(self.t),
            "ts": datetime.fromtimestamp(float(self.t), tz=timezone.utc).isoformat(),
            "slug": self.slug,
            "asset": self.asset,
            "tf": self.tf,
            "t0": int(self.t0),
            "bu": self.bu,
            "bd": self.bd,
            "au": self.au,
            "ad": self.ad,
            "su": float(self.su),
            "sd": float(self.sd),
            "sau": float(self.sau),
            "sad": float(self.sad),
            "condition_id": self.condition_id,
            "bid_sum": self.bid_sum,
            "ask_sum": self.ask_sum,
            "live_order": False,
        }

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> BookTick:
        t = rec.get("t")
        if t is None and rec.get("ts"):
            text = str(rec["ts"]).replace("Z", "+00:00")
            t = datetime.fromisoformat(text).timestamp()
        t = float(t or 0.0)
        slug = str(rec.get("slug") or "")
        asset = str(rec.get("asset") or "")
        tf = str(rec.get("tf") or "5m")
        t0 = int(rec.get("t0") or int(t // 300) * 300)
        return cls(
            t=t,
            slug=slug,
            asset=asset,
            tf=tf,
            t0=t0,
            bu=_finite(rec.get("bu", rec.get("bid_up"))),
            bd=_finite(rec.get("bd", rec.get("bid_down"))),
            au=_finite(rec.get("au", rec.get("ask_up"))),
            ad=_finite(rec.get("ad", rec.get("ask_down"))),
            su=_size(rec.get("su", rec.get("bid_depth_up"))),
            sd=_size(rec.get("sd", rec.get("bid_depth_down"))),
            sau=_size(rec.get("sau")),
            sad=_size(rec.get("sad")),
            condition_id=(str(rec["condition_id"]) if rec.get("condition_id") else None),
        )

    @classmethod
    def from_parquet_row(
        cls,
        *,
        t: Any,
        bu: Any,
        bd: Any,
        au: Any,
        ad: Any,
        su: Any,
        sd: Any,
        sau: Any,
        sad: Any,
        condition_id: Any,
        slug: str,
        asset: str,
        tf: str = "5m",
    ) -> BookTick:
        ts = float(t)
        sec = 300 if tf == "5m" else 900
        t0 = int(ts // sec) * sec
        return cls(
            t=ts,
            slug=str(slug),
            asset=str(asset),
            tf=str(tf),
            t0=t0,
            bu=_finite(bu),
            bd=_finite(bd),
            au=_finite(au),
            ad=_finite(ad),
            su=_size(su),
            sd=_size(sd),
            sau=_size(sau),
            sad=_size(sad),
            condition_id=(str(condition_id) if condition_id else None),
        )


def decide_maker(
    *,
    bid_up: float | None,
    bid_down: float | None,
    bid_sz_up: float,
    bid_sz_down: float,
    ask_up: float | None,
    ask_down: float | None,
    state: dict[str, Any] | None,
    now: float,
    t0: int,
    clip: float = CLIP,
    rest_max: float = PAIR_MAX,
    cancel_rich: float = CANCEL_ABOVE,
    max_age: float = MAX_AGE_SEC,
    fill: str = "residual",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Measure-only rest/requote/cancel. Never live. Never pair>1 complete.

    fill=residual: one-leg eaten completes only if fill_px+opp_ask<=pair_max.
    fill=none: DEBUG wiring — rest/replace/cancel/rich only, no simulated fills.
    """
    fill_mode = str(fill or "residual").strip().lower()
    bid_sum = None if bid_up is None or bid_down is None else float(bid_up) + float(bid_down)
    ask_sum = None if ask_up is None or ask_down is None else float(ask_up) + float(ask_down)
    min_bid = min(float(bid_sz_up), float(bid_sz_down)) if bid_up is not None and bid_down is not None else 0.0
    rec: dict[str, Any] = {
        "book": "maker",
        "live_order": False,
        "pair_gt_1": False,
        "clip": float(clip),
        "bid_up": bid_up,
        "bid_down": bid_down,
        "bid_sum": bid_sum,
        "bid_depth_up": float(bid_sz_up),
        "bid_depth_down": float(bid_sz_down),
        "min_bid_size": min_bid,
        "ask_up": ask_up,
        "ask_down": ask_down,
        "ask_sum": ask_sum,
        "rest": False,
        "requote": False,
        "cancel": False,
        "complete": False,
        "eaten_up": False,
        "eaten_down": False,
        "orders": [],
        "reason": "watch",
        "age_sec": None,
        "fill": fill_mode,
    }

    resting = None
    if state and int(state.get("t0") or 0) == int(t0) and state.get("px_up") is not None:
        resting = state

    if state and int(state.get("t0") or 0) != int(t0) and state.get("px_up") is not None:
        rec["cancel"] = True
        rec["reason"] = "cancel_window"
        rec["orders"] = []
        resting = None

    if resting is not None:
        age = float(now) - float(resting.get("rest_ts") or now)
        rec["age_sec"] = age
        rec["rest_px_up"] = resting.get("px_up")
        rec["rest_px_down"] = resting.get("px_down")
        eaten_up = level_eaten(resting.get("px_up"), bid_up, ask_up)
        eaten_down = level_eaten(resting.get("px_down"), bid_down, ask_down)
        rec["eaten_up"] = eaten_up
        rec["eaten_down"] = eaten_down

        if age > float(max_age) + 1e-12:
            rec["cancel"] = True
            rec["reason"] = "cancel_age"
            return rec, None

        if bid_sum is not None and bid_sum > float(cancel_rich) + 1e-12:
            rec["cancel"] = True
            rec["reason"] = "rich_cancel"
            return rec, None

        simulate_fill = fill_mode != "none"
        if simulate_fill and eaten_up and eaten_down:
            rec["reason"] = "filled_both"
            rec["fill_up"] = resting.get("px_up")
            rec["fill_down"] = resting.get("px_down")
            return rec, None

        if simulate_fill and (eaten_up ^ eaten_down):
            fill_px = float(resting["px_up"] if eaten_up else resting["px_down"])
            opp = "Down" if eaten_up else "Up"
            opp_ask = ask_down if eaten_up else ask_up
            rec["fill_px"] = fill_px
            rec["opp"] = opp
            rec["opp_ask"] = opp_ask
            pair = None if opp_ask is None else float(fill_px) + float(opp_ask)
            rec["complete_pair"] = pair
            if pair is not None and pair > 1.0 + 1e-12:
                rec["cancel"] = True
                rec["reason"] = "pair_gt_1"
                rec["pair_gt_1"] = False
                return rec, None
            if pair is not None and pair <= float(rest_max) + 1e-12:
                rec["complete"] = True
                rec["reason"] = "complete"
                rec["orders"] = [
                    {
                        "side": "BUY",
                        "outcome": opp,
                        "type": "FOK",
                        "price": float(opp_ask),
                        "size": float(clip),
                        "complete": True,
                    }
                ]
                return rec, None
            rec["cancel"] = True
            rec["reason"] = "rich_complete"
            return rec, None

        if fill_mode == "none" and bid_sum is None:
            rec["cancel"] = True
            rec["reason"] = "cancel_missing"
            return rec, None

        moved = (
            bid_up is not None
            and bid_down is not None
            and (
                abs(float(bid_up) - float(resting["px_up"])) > 1e-12
                or abs(float(bid_down) - float(resting["px_down"])) > 1e-12
            )
        )
        can_join = (
            bid_sum is not None
            and bid_sum <= float(rest_max) + 1e-12
            and min_bid + 1e-12 >= float(clip)
        )
        if moved and can_join:
            rec["requote"] = True
            rec["rest"] = True
            rec["reason"] = "requote"
            rec["orders"] = rest_orders(float(bid_up), float(bid_down), clip)
            return rec, new_state(t0, now, float(bid_up), float(bid_down), clip)
        rec["reason"] = "hold"
        rec["rest"] = True
        return rec, resting

    if bid_sum is None:
        rec["reason"] = "missing_bid"
        return rec, None
    if bid_sum > 1.0 + 1e-12:
        rec["reason"] = "rich_bid_sum"
        rec["pair_gt_1"] = False
        return rec, None
    if bid_sum > float(rest_max) + 1e-12:
        rec["reason"] = "rich_bid_sum"
        return rec, None
    if min_bid + 1e-12 < float(clip):
        rec["reason"] = "thin_bid"
        return rec, None
    rec["rest"] = True
    rec["reason"] = "rest"
    rec["orders"] = rest_orders(float(bid_up), float(bid_down), clip)
    return rec, new_state(t0, now, float(bid_up), float(bid_down), clip)


@dataclass
class PolicyMaker:
    """S1 maker rest. pair_max=0.90, cancel_above=0.92, clip=10. No live. No pair>1."""

    pair_max: float = PAIR_MAX
    cancel_above: float = CANCEL_ABOVE
    clip: float = CLIP
    max_age_sec: float = MAX_AGE_SEC
    fill: str = "residual"

    def step(self, tick: BookTick, state: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        rec, new = decide_maker(
            bid_up=tick.bu,
            bid_down=tick.bd,
            bid_sz_up=tick.su,
            bid_sz_down=tick.sd,
            ask_up=tick.au,
            ask_down=tick.ad,
            state=state,
            now=float(tick.t),
            t0=int(tick.t0),
            clip=float(self.clip),
            rest_max=float(self.pair_max),
            cancel_rich=float(self.cancel_above),
            max_age=float(self.max_age_sec),
            fill=self.fill,
        )
        rec["slug"] = tick.slug
        rec["asset"] = tick.asset
        rec["tf"] = tick.tf
        rec["t0"] = tick.t0
        rec["t"] = tick.t
        rec["pair_max"] = float(self.pair_max)
        rec["cancel_above"] = float(self.cancel_above)
        rec["live_order"] = False
        rec["pair_gt_1"] = False
        rec["size_ok"] = False
        return rec, new


def action_bucket(reason: str, *, cancel: bool = False) -> str:
    r = str(reason or "")
    if r == "rest":
        return "rest"
    if r == "requote":
        return "replace"
    if r.startswith("rich_"):
        return "rich"
    if cancel or r.startswith("cancel") or r == "pair_gt_1":
        return "cancel"
    return r or "watch"
