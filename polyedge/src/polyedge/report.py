"""Render scan results as Markdown."""

from __future__ import annotations

from datetime import datetime, timezone

from .scanners import ScanResult


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def render_markdown(result: ScanResult) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    s = result.stats
    lines = [
        f"# Polyedge canlı tarama — {now}",
        "",
        "Bu çıktı **kâğıt / araştırma** amaçlıdır. Emir göndermez. "
        "Net edge, resmi taker fee formülünü düşer. Dokunuştaki derinlik yürülmez; "
        "görünen boşluk doldurulmadan kapanabilir.",
        "",
        "## Özet",
        "",
        f"- Taranan market: **{s.get('markets_scanned', 0)}**",
        f"- Taranan event: **{s.get('events_scanned', 0)}**",
        f"- Günlük LP ödülü ≥ $1: **{s.get('markets_with_daily_reward_ge_1', 0)}**",
        f"- Holding reward açık: **{s.get('holding_reward_markets', 0)}**",
        f"- Completeness (ücret-sonrası) hit: **{s.get('completeness_hits', 0)}**",
        f"- Neg-risk Dutch book hit: **{s.get('dutch_hits', 0)}**",
        "",
        "## 1) Likidite ödülü — kalabalık olmayan havuzlar",
        "",
        "Sıralama `farm_score = daily / (1 + liq/25k + vol/50k)`. "
        "Yüksek günlük havuz + ince defter = daha az rekabet (sezgisel). "
        "İki taraflı kotasyon şart; mid 0.10–0.90 dışında tek taraf skor almaz. "
        "Günlük ödeme eşiği $1.",
        "",
        "| Score | $/gün | Min size | Max spread | Likidite | 24s hacim | Holding | Market |",
        "|------:|------:|---------:|-----------:|---------:|----------:|:-------:|--------|",
    ]
    for row in result.rewards:
        q = row.question.replace("|", "/")[:70]
        lines.append(
            f"| {row.farm_score:.2f} | {row.daily_rate:.1f} | {row.min_size:.0f} | "
            f"{row.max_spread:.1f}¢ | {row.liquidity:,.0f} | {row.volume_24h:,.0f} | "
            f"{'evet' if row.holding else ''} | [{q}]({row.url}) |"
        )
    if not result.rewards:
        lines.append("| — | — | — | — | — | — | — | tarama boş |")

    lines += [
        "",
        "## 2) Holding reward (protokol ~%3.25–4 APY)",
        "",
        "Eligible long-dated pozisyonların mark-to-market değerine saatlik örnekleme. "
        "YES+NO birlikte tutmak yaklaşık $1 kilitler; getiri protokolden gelir, "
        "yön riski nötrlenir. DeFi getirisinden düşük olabilir — karşılaştır.",
        "",
        "| 24s hacim | Bid | Ask | Bitiş | Market |",
        "|----------:|----:|----:|-------|--------|",
    ]
    for row in result.holding[:20]:
        q = row.question.replace("|", "/")[:70]
        bid = "—" if row.best_bid is None else f"{row.best_bid:.3f}"
        ask = "—" if row.best_ask is None else f"{row.best_ask:.3f}"
        lines.append(
            f"| {row.volume_24h:,.0f} | {bid} | {ask} | {row.end_date[:10]} | [{q}]({row.url}) |"
        )
    if not result.holding:
        lines.append("| — | — | — | — | tarama boş |")

    lines += [
        "",
        "## 3) Completeness arb (YES+NO, ücret sonrası)",
        "",
        "`buy_both`: her iki ask'i kaldır, $1 ödeme. "
        "`sell_both_after_split`: $1 split et, her iki bid'e sat. "
        "Ham boşluk ücretten küçükse **hit yok** — GitHub botlarının çoğu bunu atlar.",
        "",
        "| Tür | Net edge | Ham gap | YES | NO | Fee | 24s hacim | Market |",
        "|-----|---------:|--------:|----:|---:|----:|----------:|--------|",
    ]
    if result.completeness:
        for hit in result.completeness:
            q = hit.question.replace("|", "/")[:60]
            lines.append(
                f"| {hit.kind} | {_pct(hit.net_edge)} | {_pct(hit.raw_gap)} | "
                f"{hit.yes_px:.3f} | {hit.no_px:.3f} | {hit.fee_rate:.2f} | "
                f"{hit.volume_24h:,.0f} | [{q}]({hit.url}) |"
            )
    else:
        lines.append("| — | — | — | — | — | — | — | ücret-sonrası boşluk yok |")

    lines += [
        "",
        "## 4) Neg-risk Dutch book (tüm YES ask toplamı)",
        "",
        "Yalnız `negRisk=true` eventler. Set eksikse $1 ödeme garanti değildir.",
        "",
        "| Net edge | Σ ask | N | Fee | Event |",
        "|---------:|------:|--:|----:|-------|",
    ]
    if result.dutch:
        for hit in result.dutch:
            t = hit.title.replace("|", "/")[:70]
            lines.append(
                f"| {_pct(hit.net_edge)} | {hit.sum_asks:.3f} | {hit.n_outcomes} | "
                f"{hit.fee_rate:.2f} | [{t}]({hit.url}) |"
            )
    else:
        lines.append("| — | — | — | — | ücret-sonrası boşluk yok |")

    lines += [
        "",
        "## Okuma notu",
        "",
        "- Protokol ödemeleri (LP rewards, maker rebate, holding) **tekrarlanabilir** gelir; "
        "yön tahmini değildir.",
        "- Completeness / Dutch book teoride risksizdir; pratikte latency, derinlik, "
        "kısmi fill ve CLOB V2 fee eğrisi yer.",
        "- BTC 5dk / kopya-ticaret / 'AI agent' public botları bu taramada **yok** — "
        "çoğu negatif EV veya V1 SDK ile kırık.",
        "",
    ]
    return "\n".join(lines) + "\n"
