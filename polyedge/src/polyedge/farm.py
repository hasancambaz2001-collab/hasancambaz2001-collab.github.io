"""Protocol-yield farm planner: LP rewards + maker rebates + holding sleeve.

Paper by default. Uses official polymarket-client when installed, else Gamma.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import clob, gamma
from .adapters import datasets, pmxt, pysdk
from .fees import FeeSchedule
from .quoting import BookTouch, QuoteParams, QuoteSet, construct_quotes
from .scoring import MarketScore, score_market

SHORT_CRYPTO = re.compile(
    r"(up or down|5-?\s*min|15-?\s*min|4-?\s*hour|btc up|eth up|sol up)",
    re.I,
)
MENTIONS = re.compile(r"\b(tweets?|posts?|mentions?)\b", re.I)
WEEK_OF = re.compile(r"week of\s+([A-Za-z]+)\s+(\d{1,2})", re.I)
HOLDING_APY = 0.0325


@dataclass
class FarmConfig:
    bankroll_usdc: float = 2000.0
    holding_frac: float = 0.15
    max_markets: int = 6
    min_daily_rate: float = 15.0
    max_min_size: float = 250.0
    min_max_spread: float = 3.0
    reward_limit: int = 2000
    include_short_crypto: bool = False
    include_same_day: bool = False
    include_mentions: bool = False
    min_liquidity: float = 2500.0
    min_hours_to_end: float = 48.0
    cross_check_kalshi: bool = False
    quote: QuoteParams = field(default_factory=QuoteParams)


@dataclass
class FarmSlot:
    question: str
    slug: str
    condition_id: str
    url: str
    daily_rate: float
    min_size: float
    max_spread: float
    liquidity: float
    volume_24h: float
    fee_rate: float
    rebate_rate: float
    holding: bool
    score: MarketScore
    quotes: QuoteSet
    est_daily_reward: float
    est_daily_rebate: float
    est_holding_daily: float
    kalshi: list[dict[str, Any]]
    skip_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score"] = self.score.as_dict()
        d["quotes"] = self.quotes.as_dict()
        return d


@dataclass
class FarmPlan:
    generated_at: str
    config: dict[str, Any]
    infrastructure: dict[str, bool]
    slots: list[FarmSlot]
    skipped: list[dict[str, Any]]
    totals: dict[str, Any]
    instructions: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "config": self.config,
            "infrastructure": self.infrastructure,
            "slots": [s.as_dict() for s in self.slots],
            "skipped": self.skipped,
            "totals": self.totals,
            "instructions": self.instructions,
        }


def _toxic(question: str, end_date: str, max_spread: float, daily: float, cfg: FarmConfig) -> str:
    if not cfg.include_short_crypto and SHORT_CRYPTO.search(question or ""):
        return "short-crypto-twap"
    if not cfg.include_short_crypto and max_spread <= 2.0 and daily >= 200:
        return "tight-band-hft"
    if not cfg.include_mentions and MENTIONS.search(question or ""):
        return "mentions-clock"
    week = WEEK_OF.search(question or "")
    if week and not cfg.include_same_day:
        now = datetime.now(timezone.utc)
        try:
            mark = datetime.strptime(f"{week.group(1)} {week.group(2)} {now.year}", "%B %d %Y")
            if abs((mark.date() - now.date()).days) <= 2:
                return "same-week-expiry"
        except ValueError:
            pass
    if not end_date:
        return ""
    try:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        hours = (end - datetime.now(timezone.utc)).total_seconds() / 3600.0
        if hours < cfg.min_hours_to_end and not cfg.include_same_day:
            return f"resolves-within-{int(cfg.min_hours_to_end)}h"
    except ValueError:
        pass
    return ""


def _from_gamma_market(market: dict) -> dict[str, Any]:
    ids = gamma.parse_token_ids(market)
    sched = FeeSchedule.from_market(market)
    return {
        "condition_id": str(market.get("conditionId") or ""),
        "slug": str(market.get("slug") or ""),
        "question": str(market.get("question") or ""),
        "yes_token": ids[0] if ids else "",
        "no_token": ids[1] if len(ids) > 1 else "",
        "best_bid": float(market["bestBid"]) if market.get("bestBid") is not None else None,
        "best_ask": float(market["bestAsk"]) if market.get("bestAsk") is not None else None,
        "liquidity": float(market.get("liquidityNum") or market.get("liquidity") or 0),
        "volume_24h": float(market.get("volume24hr") or 0),
        "min_order_size": float(market.get("orderMinSize") or 5),
        "tick_size": float(market.get("orderPriceMinTickSize") or 0.01),
        "fees_enabled": bool(market.get("feesEnabled")),
        "fee_rate": sched.rate,
        "rebate_rate": sched.rebate_rate,
        "fee_type": str(market.get("feeType") or ""),
        "rewards_daily_rate": gamma.daily_reward(market),
        "rewards_min_size": float(market.get("rewardsMinSize") or 0),
        "rewards_max_spread": float(market.get("rewardsMaxSpread") or 0),
        "holding": bool(market.get("holdingRewardsEnabled")),
        "accepting_orders": bool(market.get("acceptingOrders")),
        "enable_order_book": bool(market.get("enableOrderBook")),
        "end_date": str(market.get("endDate") or market.get("endDateIso") or ""),
        "source": "gamma",
    }


def _load_candidates(cfg: FarmConfig) -> tuple[list[dict[str, Any]], str]:
    if pysdk.available():
        rewards = pysdk.iter_reward_configs(limit=cfg.reward_limit)
        rewards.sort(key=lambda r: r["daily_rate"], reverse=True)
        picked: list[dict[str, Any]] = []
        for row in rewards:
            if row["daily_rate"] < cfg.min_daily_rate:
                continue
            if row["min_size"] > cfg.max_min_size:
                continue
            if row["max_spread"] < cfg.min_max_spread:
                continue
            picked.append(row)
            if len(picked) >= 80:
                break
        markets = pysdk.fetch_markets([r["condition_id"] for r in picked])
        by_cid = {m["condition_id"]: m for m in markets}
        merged = []
        for row in picked:
            m = by_cid.get(row["condition_id"])
            if not m:
                continue
            m = dict(m)
            m["rewards_daily_rate"] = max(m.get("rewards_daily_rate") or 0, row["daily_rate"])
            m["rewards_min_size"] = m.get("rewards_min_size") or row["min_size"]
            m["rewards_max_spread"] = m.get("rewards_max_spread") or row["max_spread"]
            merged.append(m)
        return merged, "polymarket-client"
    # Gamma fallback
    raw = list(gamma.iter_markets(max_markets=1200))
    return [_from_gamma_market(m) for m in raw], "gamma"


def _enrich_touches(markets: list[dict[str, Any]]) -> None:
    tokens: list[str] = []
    for m in markets:
        if m.get("yes_token"):
            tokens.append(m["yes_token"])
        if m.get("no_token"):
            tokens.append(m["no_token"])
    if pysdk.available():
        try:
            prices = pysdk.fetch_prices(tokens)
        except Exception:
            prices = clob.fetch_prices(tokens)
    else:
        prices = clob.fetch_prices(tokens)
    for m in markets:
        yt, nt = m.get("yes_token"), m.get("no_token")
        yp, np = prices.get(yt or ""), prices.get(nt or "")
        if yp:
            m["yes_bid"] = yp.get("BUY")
            m["yes_ask"] = yp.get("SELL")
            m["best_bid"] = yp.get("BUY")
            m["best_ask"] = yp.get("SELL")
        else:
            m["yes_bid"] = m.get("best_bid")
            m["yes_ask"] = m.get("best_ask")
        if np:
            m["no_bid"] = np.get("BUY")
            m["no_ask"] = np.get("SELL")
        else:
            # complementary fallback only for quoting if NO book missing
            yb, ya = m.get("yes_bid"), m.get("yes_ask")
            m["no_bid"] = (1.0 - ya) if ya else None
            m["no_ask"] = (1.0 - yb) if yb else None


def build_plan(cfg: FarmConfig | None = None) -> FarmPlan:
    cfg = cfg or FarmConfig()
    markets, source = _load_candidates(cfg)
    _enrich_touches(markets)

    skipped: list[dict[str, Any]] = []
    ranked: list[tuple[MarketScore, dict[str, Any], QuoteSet]] = []
    for m in markets:
        reason = _toxic(
            m.get("question") or "",
            m.get("end_date") or "",
            float(m.get("rewards_max_spread") or 0),
            float(m.get("rewards_daily_rate") or 0),
            cfg,
        )
        if reason:
            skipped.append({"question": m.get("question"), "reason": reason, "daily": m.get("rewards_daily_rate")})
            continue
        if not m.get("accepting_orders") or not m.get("enable_order_book"):
            skipped.append({"question": m.get("question"), "reason": "not-accepting"})
            continue
        if not m.get("yes_token") or not m.get("no_token"):
            skipped.append({"question": m.get("question"), "reason": "no-tokens"})
            continue
        daily = float(m.get("rewards_daily_rate") or 0)
        if daily < cfg.min_daily_rate:
            continue
        min_size = max(float(m.get("rewards_min_size") or 0), float(m.get("min_order_size") or 0))
        if min_size <= 0 or min_size > cfg.max_min_size:
            continue
        liq_now = float(m.get("liquidity") or 0)
        size_mult = cfg.quote.reward_size_mult
        if liq_now >= 20_000:
            size_mult = max(size_mult, 2.0)
        elif liq_now >= 8_000:
            size_mult = max(size_mult, 1.5)
        qparams = QuoteParams(
            gamma=cfg.quote.gamma,
            delta_min_ticks=cfg.quote.delta_min_ticks,
            min_edge_ticks=cfg.quote.min_edge_ticks,
            reward_size_mult=size_mult,
            inventory_yes=cfg.quote.inventory_yes,
            inventory_no=cfg.quote.inventory_no,
            q_max_usdc=cfg.quote.q_max_usdc,
        )
        mid_px = 0.5
        if m.get("yes_bid") and m.get("yes_ask"):
            mid_px = (float(m["yes_bid"]) + float(m["yes_ask"])) / 2.0
        per_side_usdc = min(120.0, max(min_size * mid_px * 1.25, 0.045 * liq_now))
        size_shares = max(min_size, per_side_usdc / max(mid_px, 0.08))
        quotes = construct_quotes(
            yes_token=m["yes_token"],
            no_token=m["no_token"],
            yes_touch=BookTouch(m.get("yes_bid"), m.get("yes_ask")),
            no_touch=BookTouch(m.get("no_bid"), m.get("no_ask")),
            tick=float(m.get("tick_size") or 0.01),
            min_size=min_size,
            max_spread_cents=float(m.get("rewards_max_spread") or 0),
            params=qparams,
            size_shares=size_shares,
        )
        if float(m.get("liquidity") or 0) < cfg.min_liquidity:
            skipped.append({"question": m.get("question"), "reason": "thin-book", "liq": m.get("liquidity")})
            continue
        if not quotes.two_sided:
            skipped.append({"question": m.get("question"), "reason": "could-not-quote-two-sided"})
            continue
        scored = score_market(
            condition_id=m.get("condition_id") or "",
            daily_rate=daily,
            liquidity=float(m.get("liquidity") or 0),
            volume_24h=float(m.get("volume_24h") or 0),
            best_bid=m.get("yes_bid") or m.get("best_bid"),
            best_ask=m.get("yes_ask") or m.get("best_ask"),
            fee_rate=float(m.get("fee_rate") or 0),
            rebate_rate=float(m.get("rebate_rate") or 0),
        )
        ranked.append((scored, m, quotes))

    ranked.sort(key=lambda t: t[0].score, reverse=True)

    mm_budget = cfg.bankroll_usdc * (1.0 - cfg.holding_frac)
    hold_budget = cfg.bankroll_usdc * cfg.holding_frac
    remaining = mm_budget
    slots: list[FarmSlot] = []
    for scored, m, quotes in ranked:
        if len(slots) >= cfg.max_markets:
            break
        cap = quotes.capital_usdc
        if cap <= 0 or cap > remaining:
            continue
        liq = max(float(m.get("liquidity") or 0), cap)
        share = min(0.35, cap / liq)
        est_reward = float(m.get("rewards_daily_rate") or 0) * share
        est_rebate = scored.rebate_pool * min(0.2, share)
        est_hold = 0.0
        if m.get("holding") and hold_budget > 0:
            # small overlay: hold both sides with leftover sleeve, once
            est_hold = hold_budget * HOLDING_APY / 365.0
        kalshi: list[dict[str, Any]] = []
        if cfg.cross_check_kalshi:
            kalshi = pmxt.kalshi_complements(str(m.get("question") or ""), limit=3)
        slug = str(m.get("slug") or "")
        slots.append(
            FarmSlot(
                question=str(m.get("question") or ""),
                slug=slug,
                condition_id=str(m.get("condition_id") or ""),
                url=f"https://polymarket.com/market/{slug}" if slug else "https://polymarket.com",
                daily_rate=float(m.get("rewards_daily_rate") or 0),
                min_size=float(m.get("rewards_min_size") or 0),
                max_spread=float(m.get("rewards_max_spread") or 0),
                liquidity=float(m.get("liquidity") or 0),
                volume_24h=float(m.get("volume_24h") or 0),
                fee_rate=float(m.get("fee_rate") or 0),
                rebate_rate=float(m.get("rebate_rate") or 0),
                holding=bool(m.get("holding")),
                score=scored,
                quotes=quotes,
                est_daily_reward=round(est_reward, 3),
                est_daily_rebate=round(est_rebate, 3),
                est_holding_daily=round(est_hold, 4),
                kalshi=kalshi,
            )
        )
        remaining -= cap
        if m.get("holding"):
            hold_budget = 0.0  # attach sleeve to first eligible only

    locked = sum(s.quotes.capital_usdc for s in slots)
    est = sum(s.est_daily_reward + s.est_daily_rebate + s.est_holding_daily for s in slots)
    infra = {
        "polymarket-client": pysdk.available(),
        "pmxt_key": pmxt.available(),
        "poly_data": datasets.poly_data_trades_path() is not None,
        "prediction_market_analysis": datasets.pma_data_dir() is not None,
        "catalog_source": source,
    }
    instructions = [
        "Mod varsayılanı KAĞIT. Emir gitmez.",
        "Her markette YES ve NO için post-only BUY (maker). Ask'i geçme.",
        "İki bacak da fill olursa merge: kilitli edge = 1 - p_yes - p_no.",
        "Tek bacak fill = envanter. Karşı tarafı daha agresif al veya REDUCE_ONLY sat.",
        "Haber/jump: kotasyonu çek. Daily-loss kill kullan.",
        "Canlı için POLYEDGE_LIVE=1 + resmi SDK kimliği. Geo-bypass yok.",
        "est_daily_* rekabet payı sezgiselidir, garanti değildir.",
    ]
    return FarmPlan(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        config={
            "bankroll_usdc": cfg.bankroll_usdc,
            "holding_frac": cfg.holding_frac,
            "max_markets": cfg.max_markets,
            "min_daily_rate": cfg.min_daily_rate,
            "include_short_crypto": cfg.include_short_crypto,
        },
        infrastructure=infra,
        slots=slots,
        skipped=skipped[:40],
        totals={
            "markets_considered": len(markets),
            "slots": len(slots),
            "capital_locked_usdc": round(locked, 2),
            "capital_left_usdc": round(remaining, 2),
            "est_daily_usd": round(est, 3),
            "est_daily_on_locked_pct": round((est / locked * 100.0), 3) if locked else 0.0,
            "note": "Estimates assume you keep two-sided in-band quotes and win a liquidity share. Inventory can erase this.",
        },
        instructions=instructions,
    )


def render_farm_markdown(plan: FarmPlan) -> str:
    t = plan.totals
    lines = [
        f"# Polyedge farm planı — {plan.generated_at}",
        "",
        "En karlı **tekrarlanabilir** sistem: iki taraflı maker kotasyonu "
        "(likidite ödülü + maker rebate) + isteğe bağlı holding sleeve. "
        "Yön bahsi değil. **Kâğıt plan** — emir yok.",
        "",
        f"- Kaynak: `{plan.infrastructure.get('catalog_source')}` | "
        f"py-sdk={plan.infrastructure.get('polymarket-client')} | "
        f"pmxt_key={plan.infrastructure.get('pmxt_key')}",
        f"- Bankroll: **${plan.config['bankroll_usdc']:.0f}** · kilit **${t['capital_locked_usdc']:.2f}** · "
        f"kalan **${t['capital_left_usdc']:.2f}**",
        f"- Sezgisel günlük: **${t['est_daily_usd']:.2f}** "
        f"({t['est_daily_on_locked_pct']:.2f}% kilitli sermaye / gün) — garanti değil",
        f"- Slot: **{t['slots']}** / aday {t['markets_considered']}",
        "",
        "## Kotasyonlar (post-only BUY YES + BUY NO)",
        "",
        "| Est $/gün | Havuz $/gün | Kilit $ | Edge | YES bid | NO bid | Size | Market |",
        "|----------:|------------:|--------:|-----:|--------:|-------:|-----:|--------|",
    ]
    for s in plan.slots:
        y = s.quotes.yes.price if s.quotes.yes else 0
        n = s.quotes.no.price if s.quotes.no else 0
        sz = s.quotes.yes.size if s.quotes.yes else 0
        q = s.question.replace("|", "/")[:56]
        daily = s.est_daily_reward + s.est_daily_rebate + s.est_holding_daily
        lines.append(
            f"| {daily:.2f} | {s.daily_rate:.0f} | {s.quotes.capital_usdc:.1f} | "
            f"{s.quotes.locked_edge:.3f} | {y:.3f} | {n:.3f} | {sz:.0f} | [{q}]({s.url}) |"
        )
    if not plan.slots:
        lines.append("| — | — | — | — | — | — | — | uygun slot yok |")

    lines += ["", "## Slot detayı", ""]
    for i, s in enumerate(plan.slots, 1):
        lines += [
            f"### {i}. {s.question}",
            "",
            f"- {s.url}",
            f"- Havuz ${s.daily_rate:.0f}/gün · min {s.min_size:.0f} · band ±{s.max_spread:.1f}¢ · "
            f"liq ${s.liquidity:,.0f} · fee {s.fee_rate:.2f} rebate {s.rebate_rate:.0%}"
            f"{' · holding açık' if s.holding else ''}",
            f"- Skor {s.score.score:.3f} (density {s.score.reward_density:.2f}, "
            f"rebate-pool {s.score.rebate_pool:.2f}, extremity {s.score.extremity:.2f})",
            f"- Tahmini: reward ${s.est_daily_reward:.2f} + rebate ${s.est_daily_rebate:.2f}"
            f"{f' + holding ${s.est_holding_daily:.3f}' if s.est_holding_daily else ''}",
        ]
        if s.quotes.yes and s.quotes.no:
            lines.append(
                f"- Emir: BUY YES {s.quotes.yes.size:.0f} @ {s.quotes.yes.price:.3f} "
                f"(`{s.quotes.yes.token[:12]}…`) · "
                f"BUY NO {s.quotes.no.size:.0f} @ {s.quotes.no.price:.3f}"
            )
            lines.append(
                f"- Çift fill merge edge **{s.quotes.locked_edge:.3f}** · "
                f"FV {s.quotes.fair_value:.3f} · δ {s.quotes.half_spread:.3f}"
            )
        if s.kalshi:
            lines.append(f"- Kalshi eşleşme: {s.kalshi}")
        lines.append("")

    lines += [
        "## Çalıştırma",
        "",
        "```bash",
        "PYTHONPATH=src python3 -m polyedge farm --bankroll 2000",
        "```",
        "",
        "Canlı maker bot (ayrı repo, paper önce): "
        "https://github.com/warproxxx/poly-maker",
        "",
        "Tahminler rekabet ve envanterle değişir. Bu bir yatırım tavsiyesi değildir.",
        "",
    ]
    return "\n".join(lines) + "\n"
