"""Entry decision: hard red-flag elimination first, then a soft signal score."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import EntryCfg, FilterCfg
from .features import TokenState


@dataclass
class Verdict:
    enter: bool
    permanent_reject: bool = False
    reasons: list[str] = field(default_factory=list)
    score: int = 0
    signals: dict = field(default_factory=dict)


def launch_red_flags(st: TokenState, fc: FilterCfg, creator_launches: int) -> list[str]:
    """Flags that are fixed once the snipe window has passed -> permanent reject."""
    r = []
    if st.dev_initial_pct() > fc.max_dev_initial_buy_pct:
        r.append(f"dev_buy {st.dev_initial_pct():.1f}%")
    if st.sniper_pct() > fc.max_sniper_supply_pct:
        r.append(f"snipers {st.sniper_pct():.1f}%")
    if creator_launches > fc.max_creator_launches:
        r.append(f"serial_creator x{creator_launches}")
    return r


def live_red_flags(st: TokenState, fc: FilterCfg, post_migration: bool, exclude: set[str]) -> list[str]:
    r = []
    top10 = st.top10_pct(exclude)
    if top10 > fc.max_top10_pct:
        r.append(f"top10 {top10:.1f}%")
    if not post_migration and st.dev_sold_pct() > fc.max_dev_sold_pct:
        r.append(f"dev_sold {st.dev_sold_pct():.0f}%")
    return r


def score(st: TokenState, now: float, fc: FilterCfg) -> tuple[int, dict]:
    w = st.window(now, 60.0)
    checks = {
        "unique_buyers": st.unique_buyers() >= fc.min_unique_buyers,
        "buy_sell_ratio": w["buy_sell_ratio"] >= fc.min_buy_sell_ratio,
        "net_inflow": w["net_inflow_sol"] >= fc.min_net_inflow_sol_60s,
        "new_buyers": w["new_buyers"] >= fc.min_new_buyers_60s,
        "distributed_buys": st.single_buy_share() <= fc.max_single_buy_share,
        "momentum": w["mcap_momentum"] >= fc.min_mcap_momentum_60s,
    }
    return sum(checks.values()), checks


def evaluate(
    st: TokenState,
    now: float,
    fc: FilterCfg,
    ec: EntryCfg,
    creator_launches: int,
    exclude: set[str] | None = None,
) -> Verdict:
    exclude = exclude or set()
    # 1) permanent launch flags
    if st.age(now) >= fc.snipe_window_s:
        flags = launch_red_flags(st, fc, creator_launches)
        if flags:
            return Verdict(False, permanent_reject=True, reasons=flags)

    # 2) entry window
    post_mig = st.migrated_ts is not None
    if post_mig:
        if ec.mode not in ("migration", "both"):
            return Verdict(False, reasons=["migrated_not_in_mode"])
        since = now - st.migrated_ts
        if since < ec.migration_wait_s:
            return Verdict(False, reasons=["waiting_post_migration"])
        if since > ec.migration_max_age_s:
            return Verdict(False, permanent_reject=True, reasons=["migration_window_over"])
        if st.migration_mcap and st.mcap / st.migration_mcap < ec.migration_min_hold_ratio:
            return Verdict(False, reasons=["failed_to_hold_migration"])
    else:
        if ec.mode not in ("curve", "both"):
            return Verdict(False, reasons=["curve_not_in_mode"])
        age = st.age(now)
        if age < ec.min_age_s:
            return Verdict(False, reasons=["too_young"])
        if age > ec.max_age_s and ec.mode == "curve":
            return Verdict(False, permanent_reject=True, reasons=["too_old"])
        if not (ec.min_mcap_sol <= st.mcap <= ec.max_mcap_sol):
            return Verdict(False, reasons=["mcap_out_of_window"])

    # 3) live red flags
    flags = live_red_flags(st, fc, post_mig, exclude)
    if flags:
        return Verdict(False, reasons=flags)

    # 4) soft score
    s, checks = score(st, now, fc)
    return Verdict(s >= fc.min_score, reasons=[] if s >= fc.min_score else [f"score {s}"], score=s, signals=checks)
