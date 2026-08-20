from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from whiskas.constants import LATE_T_SECONDS, WINDOW_SECONDS
from whiskas.fees import notional_usdc, taker_fee_usdc
from whiskas.slug import is_btc_5m, parse_btc_5m_slug


def normalize_leg(outcome: str | None, outcome_index: int | None) -> str | None:
    if outcome:
        o = str(outcome).strip().lower()
        if o == "up":
            return "Up"
        if o == "down":
            return "Down"
    if outcome_index == 0:
        return "Up"
    if outcome_index == 1:
        return "Down"
    return None


@dataclass
class Fill:
    timestamp: int
    t0: int
    leg: str
    side: str
    size: float
    price: float
    usdc: float
    fee: float
    tx: str
    t_in_window: int

    @property
    def late(self) -> bool:
        return self.t_in_window > LATE_T_SECONDS


@dataclass
class Window:
    t0: int
    slug: str
    fills: list[Fill] = field(default_factory=list)
    q_up: float = 0.0
    q_down: float = 0.0
    cost_up: float = 0.0
    cost_down: float = 0.0
    fee_up: float = 0.0
    fee_down: float = 0.0
    n_buy: int = 0
    n_sell: int = 0
    n_late: int = 0
    first_ts: int | None = None
    last_ts: int | None = None
    winner: str | None = None
    redeem_up: float = 0.0
    redeem_down: float = 0.0
    merge_usdc: float = 0.0
    rebate_usdc: float = 0.0

    @property
    def matched(self) -> float:
        return min(self.q_up, self.q_down)

    @property
    def residual(self) -> float:
        return abs(self.q_up - self.q_down)

    @property
    def residual_leg(self) -> str | None:
        if self.q_up > self.q_down:
            return "Up"
        if self.q_down > self.q_up:
            return "Down"
        return None

    @property
    def avg_up(self) -> float | None:
        return (self.cost_up / self.q_up) if self.q_up > 0 else None

    @property
    def avg_down(self) -> float | None:
        return (self.cost_down / self.q_down) if self.q_down > 0 else None

    @property
    def pair_cost(self) -> float | None:
        if self.matched <= 0 or self.avg_up is None or self.avg_down is None:
            return None
        return self.avg_up + self.avg_down

    @property
    def residual_ratio(self) -> float:
        total = self.q_up + self.q_down
        return (self.residual / total) if total > 0 else 0.0

    @property
    def total_cost(self) -> float:
        return self.cost_up + self.cost_down

    @property
    def total_fee(self) -> float:
        return self.fee_up + self.fee_down

    def pair_pnl(self) -> float | None:
        if self.pair_cost is None:
            return None
        fee_pair = 0.0
        tot_q = self.q_up + self.q_down
        if tot_q > 0:
            fee_pair = self.total_fee * (2.0 * self.matched / tot_q)
        return self.matched * (1.0 - self.pair_cost) - fee_pair

    def residual_pnl(self) -> float | None:
        if self.winner is None or self.residual <= 0 or self.residual_leg is None:
            return None
        avg = self.avg_up if self.residual_leg == "Up" else self.avg_down
        if avg is None:
            return None
        tot_q = self.q_up + self.q_down
        fee_res = self.total_fee * (self.residual / tot_q) if tot_q > 0 else 0.0
        if self.residual_leg == self.winner:
            return self.residual * (1.0 - avg) - fee_res
        return -self.residual * avg - fee_res

    def total_pnl(self) -> float | None:
        if self.winner is None:
            return None
        payout = self.q_up if self.winner == "Up" else self.q_down
        return payout - self.total_cost - self.total_fee + self.rebate_usdc

    def residual_won(self) -> bool | None:
        if self.winner is None or self.residual_leg is None or self.residual <= 0:
            return None
        return self.residual_leg == self.winner


def _signed_size(side: str, size: float) -> float:
    return -abs(size) if str(side).upper() == "SELL" else abs(size)


def build_windows(rows: Iterable[dict[str, Any]]) -> dict[int, Window]:
    windows: dict[int, Window] = {}
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug")
        t0 = parse_btc_5m_slug(slug)
        if t0 is None and not is_btc_5m(row.get("eventSlug"), row.get("slug")):
            continue
        if t0 is None:
            continue
        win = windows.get(t0)
        if win is None:
            win = Window(t0=t0, slug=f"btc-updown-5m-{t0}")
            windows[t0] = win

        rtype = str(row.get("type") or "")
        ts = int(row.get("timestamp") or 0)
        usdc = float(row.get("usdcSize") or 0.0)

        if rtype in {"MAKER_REBATE", "TAKER_REBATE"}:
            win.rebate_usdc += usdc
            continue
        if rtype == "MERGE":
            win.merge_usdc += usdc
            continue
        if rtype == "REDEEM":
            leg = normalize_leg(row.get("outcome"), row.get("outcomeIndex"))
            if leg == "Up":
                win.redeem_up += usdc
            elif leg == "Down":
                win.redeem_down += usdc
            continue
        if rtype != "TRADE":
            continue

        leg = normalize_leg(row.get("outcome"), row.get("outcomeIndex"))
        if leg is None:
            continue
        size = float(row.get("size") or 0.0)
        price = float(row.get("price") or 0.0)
        side = str(row.get("side") or "BUY").upper()
        if size <= 0:
            continue
        cost = usdc if usdc > 0 else notional_usdc(size, price)
        fee = taker_fee_usdc(size, price) if side == "BUY" else 0.0
        signed = _signed_size(side, size)
        signed_cost = cost if signed > 0 else -cost
        signed_fee = fee if signed > 0 else -fee

        if leg == "Up":
            win.q_up += signed
            win.cost_up += signed_cost
            win.fee_up += signed_fee
        else:
            win.q_down += signed
            win.cost_down += signed_cost
            win.fee_down += signed_fee

        if side == "SELL":
            win.n_sell += 1
        else:
            win.n_buy += 1

        t_in = ts - t0 if ts else 0
        fill = Fill(
            timestamp=ts,
            t0=t0,
            leg=leg,
            side=side,
            size=size,
            price=price,
            usdc=cost,
            fee=fee,
            tx=str(row.get("transactionHash") or ""),
            t_in_window=t_in,
        )
        win.fills.append(fill)
        if fill.late:
            win.n_late += 1
        if ts:
            win.first_ts = ts if win.first_ts is None else min(win.first_ts, ts)
            win.last_ts = ts if win.last_ts is None else max(win.last_ts, ts)

    for win in windows.values():
        win.q_up = max(0.0, win.q_up)
        win.q_down = max(0.0, win.q_down)
        win.cost_up = max(0.0, win.cost_up)
        win.cost_down = max(0.0, win.cost_down)
        win.fills.sort(key=lambda f: f.timestamp)
    return windows


def apply_winners(windows: dict[int, Window], winners: dict[int, str]) -> None:
    for t0, winner in winners.items():
        if t0 in windows and winner in {"Up", "Down"}:
            windows[t0].winner = winner


def infer_winners_from_redeems(windows: dict[int, Window]) -> dict[int, str]:
    out: dict[int, str] = {}
    for t0, win in windows.items():
        if win.redeem_up > 0 and win.redeem_down <= 0:
            out[t0] = "Up"
        elif win.redeem_down > 0 and win.redeem_up <= 0:
            out[t0] = "Down"
    return out


def windows_to_records(windows: Iterable[Window]) -> list[dict[str, Any]]:
    recs = []
    for w in windows:
        recs.append(
            {
                "t0": w.t0,
                "slug": w.slug,
                "q_up": w.q_up,
                "q_down": w.q_down,
                "cost_up": w.cost_up,
                "cost_down": w.cost_down,
                "fee_up": w.fee_up,
                "fee_down": w.fee_down,
                "avg_up": w.avg_up,
                "avg_down": w.avg_down,
                "matched": w.matched,
                "residual": w.residual,
                "residual_leg": w.residual_leg,
                "residual_ratio": w.residual_ratio,
                "pair_cost": w.pair_cost,
                "pair_pnl": w.pair_pnl(),
                "residual_pnl": w.residual_pnl(),
                "total_pnl": w.total_pnl(),
                "residual_won": w.residual_won(),
                "winner": w.winner,
                "n_buy": w.n_buy,
                "n_sell": w.n_sell,
                "n_late": w.n_late,
                "n_fills": len(w.fills),
                "first_ts": w.first_ts,
                "last_ts": w.last_ts,
                "t_first": (w.first_ts - w.t0) if w.first_ts else None,
                "t_last": (w.last_ts - w.t0) if w.last_ts else None,
                "redeem_up": w.redeem_up,
                "redeem_down": w.redeem_down,
                "merge_usdc": w.merge_usdc,
                "rebate_usdc": w.rebate_usdc,
                "window_end": w.t0 + WINDOW_SECONDS,
            }
        )
    recs.sort(key=_record_t0)
    return recs


def fills_to_records(windows: Iterable[Window]) -> list[dict[str, Any]]:
    recs = []
    for w in windows:
        for f in w.fills:
            recs.append(
                {
                    "t0": f.t0,
                    "slug": w.slug,
                    "timestamp": f.timestamp,
                    "t_in_window": f.t_in_window,
                    "late": f.late,
                    "leg": f.leg,
                    "side": f.side,
                    "size": f.size,
                    "price": f.price,
                    "usdc": f.usdc,
                    "fee": f.fee,
                    "tx": f.tx,
                    "winner": w.winner,
                }
            )
    recs.sort(key=_record_t0_ts)
    return recs


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _record_t0(row: dict[str, Any]) -> int:
    return _as_int(row.get("t0"))


def _record_t0_ts(row: dict[str, Any]) -> tuple[int, int]:
    return _as_int(row.get("t0")), _as_int(row.get("timestamp"))


def group_rows_by_slug(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        slug = row.get("eventSlug") or row.get("slug")
        if slug:
            grouped[str(slug)].append(row)
    return grouped
