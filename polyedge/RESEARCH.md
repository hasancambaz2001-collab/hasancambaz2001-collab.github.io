# Polymarket GitHub evreni — para basanlar vs yıldız farmı

Tarih: 17 Ağustos 2026. Kaynak: GitHub araması (yıldız / güncellik / org), resmi CLOB V2 dokümanı, Gamma + CLOB canlı API, on-chain cüzdan çalışmaları.

Bu bir yatırım tavsiyesi değil. Public kod **garanti kâr** değildir. Aşağıdaki sıra, “yıldız sayısı” değil **ekonomik kenarın türü**.

## 1. Önce bu üç gerçeği kabul et

**Public bot para basmaz.** Kenarı olan kişi onu GitHub’a 500 yıldızla koymaz. Açık kod, ya altyapıdır (SDK, veri) ya da protokolün herkese ödediği şeyi otomatikleştirir (market making). İkincisi hâlâ paradır — ama “gizli alpha” değildir.

**CLOB V2 (28 Nisan 2026) bir kesik.** Yeni exchange, yeni order struct, pUSD teminat, protokol-set fee, builder attribution. `py-clob-client`, `@polymarket/clob-client`, `rs-clob-client` resmi olarak arşivlendi ve üretimde çalışmıyor. 2025’te yıldız toplamış botların çoğu bugün **sessizce ölü**.

**Yön bahsi evreni eksi.** 2026 başı on-chain çalışmada ~2.5M cüzdanın ~%84’ü kârsız; kârın çoğu %0.1’de. “AI agent 1000 market tarasın” bu dağılımı tersine çevirmez.

## 2. Gerçekten nakit üreten sistemler (sıra)

### A. Protokolün ödediği — en tekrarlanabilir

Polymarket taker’dan fee alır, maker’a ve likiditeye geri basar. Siz “haklı” olmak zorunda değilsiniz; kotasyonu doğru tutmak zorundasınız.

| Akış | Ne öder | Kim alır | Tuzak |
|------|---------|----------|--------|
| **Liquidity Rewards** | Günlük pUSD, mid’e yakın resting limit | İki taraflı, max-spread / min-size içinde kalan maker | $1/gün altı yanar, devrolmaz. Tek taraf mid∈[0.10,0.90] iken 3× ceza; dışında sıfır. Quadratic skor: 1¢ daha sıkı, karesel daha çok puan. |
| **Maker Rebates** | Taker fee havuzunun %15–25’i | Fill olan maker likiditesi | Crypto %20, sports %15, finance/politics/weather %25. Jeopolitik fee-free → rebate yok. |
| **Holding Rewards** | ~%3.25 APY (resmi help, Haz 2026; UI hâlâ ~%4 der) | Eligible long-dated pozisyon | Saatlik örnek, günlük ödeme. Liste dar. YES+NO tutmak yönü nötrler, ~$1 kilitler. |

Ağustos 2026 ekstra: crypto **5dk / 15dk / 4s TWAP** marketlere **$1M** likidite ödülü (BTC ağırlıklı). Bu havuz kalabalık ve toksik — “ücretsiz getiri” değil, inventory riski yüksek.

**Bu işi fiilen yapan public kod:** [warproxxx/poly-maker](https://github.com/warproxxx/poly-maker) (CLOB V2, post-only, inventory skew, reward band, toxicity/vol, rejim makinesi, `--paper`, heartbeat, daily-loss kill). Resmi [Polymarket/poly-market-maker](https://github.com/Polymarket/poly-market-maker) eski Bands/AMM keeper; fikir için oku, V2’ye olduğu gibi sürme.

Stack: [Polymarket/py-sdk](https://github.com/Polymarket/py-sdk) veya `py-clob-client-v2`. V1 yok.

### B. Yapısal arb — teoride risksiz, pratikte yarış

| Tür | Koşul | Net kâr | Neden çoğu bot yalan söyler |
|-----|-------|---------|------------------------------|
| Completeness al | `ask_YES + ask_NO + fee_Y + fee_N < 1` | $1 − maliyet | Fee = `C·r·p·(1−p)`. 3¢ ham boşluk, crypto’da (`r=0.07`) **negatif**. |
| Completeness sat | Split $1 → YES+NO, `bid_Y + bid_N − fee > 1` | prim − fee | Envanter / split / relayer gerekir. |
| Dutch book | Neg-risk event, Σ YES ask + fee < 1 | $1 − Σ | Event exhaustive değilse $1 gelmez. |
| Cross-venue | Aynı olay Polymarket ≠ Kalshi | fark − iki bacak fee − KYC/latency | Fuzzy text-match sahte çift üretir. |

Fee eğrisi 50¢’te zirve. Jeopolitik `r=0` — completeness orada hâlâ nefes alır. Crypto/sports’ta “%2 arb” ekranı çoğu zaman **ücret illüzyonu**.

`/book` seviyeleri dışarıdan içeri sıralanır. `asks[0]` best ask **değil**. Best = `min(asks)` / `max(bids)`, veya `POST /prices`. Bunu yanlış yapan HFT README’leri çöpe.

**Düzgün iskeletler:** [P-x-J/polymarket-arbitrage-bot](https://github.com/P-x-J/polymarket-arbitrage-bot), [0xalberto/polymarket-arbitrage-bot](https://github.com/0xalberto/polymarket-arbitrage-bot) (alert). [ImMike/polymarket-arbitrage](https://github.com/ImMike/polymarket-arbitrage) Kalshi bacağı var; `taker_fee_bps: 0` default’u 2026’da yanlış. [pmxt-dev/pmxt](https://github.com/pmxt-dev/pmxt) venue birleştirir, kenar üretmez.

Bu repodaki `polyedge scan` aynı formülü **fee düşerek** çalıştırır. Derinlik yürümez; touch size 1 share olabilir.

### C. Bilgi kenarı — gerçek, emek ister, kalabalıklaşır

**Hava.** Settlement istasyonu + ensemble (GFS / Open-Meteo) vs CLOB bucket. 2024’te boştu; 2026’da NYC/London/Tokyo doldu. Tipik kural: model−market ≥ 8pp, 0.15–0.25 Kelly, sert cap. [yangyuan-zhen/PolyWeather](https://github.com/yangyuan-zhen/PolyWeather) ciddi stack (DEB, 52 şehir) ama **execution public değil** (AGPL + ürün). Küçük açık deneme: `idlepraxis/polymarket-weather-bot`. 7 günlük +%35 tweet’leri örneklem hatasıdır.

**Spor / ekonomi modeli.** Kendi olasılığın market’ten iyi kalibre ise EV vardır. Public “AI consensus” bunu yapmaz.

**Haber latency.** Sub-100ms + dedicated RPC. GitHub’daki Python script buranın oyuncusu değil.

### D. “Sistem” diye satılıp evreni eksi olanlar

| Tür | Neden eksi |
|-----|------------|
| BTC 5dk / 15dk yön botu | Casino + HFT. Maker ödülü ayrı; yön ayrı. |
| Copy-trade / whale Telegram | Gecikme, adverse selection, survivorship. Key isteyen = dolandırıcı. |
| LLM agent (archived `Polymarket/agents` ve klonları) | Dil modeli implied probability üretmez. |
| “Nothing ever happens” (NO-all) | Yazar meme diyor. Sol kuyruk bir günde yer. |
| SEO repo (`polymarket` × 30, 200–500★) | Boş README, simülasyon dashboard, V1 imza. |
| Geo-relay / “no KYC no VPN” | ToS + yaptırım. Kenar değil. |

## 3. GitHub’da neyi kullan, neyi okuma

Tam JSON: [catalog/github-systems.json](catalog/github-systems.json).

**Altyapı (şart):** `Polymarket/py-sdk`, `Polymarket/ts-sdk`, `Polymarket/polymarket-cli`, `warproxxx/poly_data`, `Jon-Becker/prediction-market-analysis`, `evan-kolberg/prediction-market-backtesting`.

**Para akışı otomasyonu:** `warproxxx/poly-maker` (maker + reward). Completeness için bu repo veya P-x-J / 0xalberto (alert). Cross-venue iskelet: ImMike + pmxt — fee’yi kendin yaz.

**Bilgi:** PolyWeather (sinyal), kendi ensemble’ın.

**Okuma / şüphe:** `HarrierOnChain/...` (10 strateji + managed waitlist), `ent0n29/polybot` (HFT iddiası), `sterlingcrispin/nothing-ever-happens`.

**Dokunma:** V1 SDK, Telegram copy bot, keyword-stuffed “arbitrage trading bot”, private key isteyen her şey.

## 4. 17 Ağu 2026 canlı kesit

Gamma 1500 market + `polyedge scan` (1200 market / 40 event / 350 CLOB kitap, 12:27 UTC). Ham çıktı: [snapshots/latest.md](snapshots/latest.md).

- Holding reward açık: **226**
- Günlük LP ödülü ≥ $1: **317** (örneklemde)
- Completeness / Dutch, **ücret sonrası: 0 hit** — defterler tamamlayıcı
- Fee: sports `r=0.05` rebate %15, politics `r=0.04` rebate %25, crypto `r=0.07` rebate %20; bazı jeopolitik `feesEnabled=false`

O anki en yüksek `farm_score` (yüksek $/gün, görece ince defter):

| $/gün | Min | Market |
|------:|----:|--------|
| 300 | 200 | Wisconsin governor 2026 (Republican) |
| 88 | 100 | OpenAI 2026’da IPO olmasın |
| 100 | 200 | McConnell dönem serbest bırakır mı |
| 400 | 200 | ABD İran’ı 2027’den önce işgal eder mi (kalabalık defter, skor düşük) |

Holding örnekleri: 2028 başkanlık adayları, 2026 Kongre balance of power, Putin 2026 sonu. YES+NO ≈ $1 kilit → protokol APY.

“Botu aç, arb yağsın” 2026’da yok. Ya protokol ödemesini farm edersin, ya ince bir bilgi kenarın vardır, ya da boşluk için milisaniye beklersin.

## 5. Sizin için somut sıra

1. Yasal olarak trade edebildiğinizden emin olun. Bypass yok.
2. `polyedge scan` çalıştırın. LP tablosundaki **yüksek $/gün + düşük likidite** satırlar farm adayıdır. Completeness/Dutch çoğu günde boş kalması **normal ve sağlıklı**.
3. Paper: `poly-maker --paper` veya kendi post-only kotasyonunuz. İki taraf, max-spread içi, min-size üstü, mid 10–90 dışında zorunlu hedge.
4. Holding: eligible long-dated’te YES+NO ≈ $1 kilit, ~%3.25. Bunu USDC/DeFi getirisiyle karşılaştırın; sihir değil.
5. Hava/spor ancak **kendi kalibrasyonunuz** 30–60 gün paper’da market’i yendikten sonra.
6. Canlı size: kaybetmeyi göze aldığınız miktar. Daily-loss kill. Haber anında quote çek.

## 6. Bu tarayıcının bilerek yapmadığı

- Emir / imza / private key
- Geo-block veya KYC aşma
- “Garanti %X / gün” iddiası
- BTC 5dk yön sinyali
- Başkasının cüzdanını kopyalama

Kenar, açık GitHub’da değil: protokolun yazdığı çek ve sizin kapalı modeliniz.
