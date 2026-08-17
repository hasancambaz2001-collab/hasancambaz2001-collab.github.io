# Polyedge canlı tarama — 2026-08-17 12:27 UTC

Bu çıktı **kâğıt / araştırma** amaçlıdır. Emir göndermez. Net edge, resmi taker fee formülünü düşer. Dokunuştaki derinlik yürülmez; görünen boşluk doldurulmadan kapanabilir.

## Özet

- Taranan market: **1200**
- Taranan event: **40**
- Günlük LP ödülü ≥ $1: **317**
- Holding reward açık: **226**
- Completeness (ücret-sonrası) hit: **0**
- Neg-risk Dutch book hit: **0**

## 1) Likidite ödülü — kalabalık olmayan havuzlar

Sıralama `farm_score = daily / (1 + liq/25k + vol/50k)`. Yüksek günlük havuz + ince defter = daha az rekabet (sezgisel). İki taraflı kotasyon şart; mid 0.10–0.90 dışında tek taraf skor almaz. Günlük ödeme eşiği $1.

| Score | $/gün | Min size | Max spread | Likidite | 24s hacim | Holding | Market |
|------:|------:|---------:|-----------:|---------:|----------:|:-------:|--------|
| 56.65 | 300.0 | 200 | 4.5¢ | 107,329 | 125 |  | [Will the Republicans win the Wisconsin governor race in 2026?](https://polymarket.com/market/will-the-republicans-win-the-wisconsin-governor-race-in-2026) |
| 43.69 | 88.0 | 100 | 4.5¢ | 24,067 | 2,567 |  | [Will OpenAI not IPO by December 31, 2026?](https://polymarket.com/market/will-openai-not-ipo-by-december-31-2026) |
| 31.47 | 100.0 | 200 | 3.5¢ | 45,179 | 18,517 |  | [Mitch McConnell steps down from Senate before his term ends?](https://polymarket.com/market/will-mitch-mcconnell-resign-from-the-senate-before-his-term-ends) |
| 25.81 | 30.0 | 200 | 3.5¢ | 3,853 | 406 |  | [Will OpenAI launch a new consumer hardware product by December 31, 202](https://polymarket.com/market/will-openai-launch-a-new-consumer-hardware-product-by-december-31-2026-538) |
| 20.08 | 30.0 | 200 | 3.5¢ | 11,320 | 2,069 |  | [OpenAI IPO before 2027?](https://polymarket.com/market/openai-ipo-before-2027) |
| 18.35 | 50.0 | 200 | 3.5¢ | 43,125 | 14 |  | [Will Saudi Arabia join the Abraham Accords before 2027?](https://polymarket.com/market/will-saudi-arabia-join-the-abraham-accords-before-2027) |
| 17.74 | 26.0 | 50 | 4.5¢ | 9,887 | 3,496 |  | [Will Spider-Man: Brand New Day have the best domestic opening weekend ](https://polymarket.com/market/will-spider-man-brand-new-day-have-the-best-domestic-opening-weekend-in-2026) |
| 16.35 | 132.0 | 50 | 4.5¢ | 160,716 | 32,166 |  | [Will Harry Kane win the 2026 Ballon d'Or?](https://polymarket.com/market/will-harry-kane-win-the-2026-ballon-dor) |
| 15.70 | 20.0 | 200 | 3.5¢ | 4,882 | 3,934 |  | [Will OpenAI IPO by December 31 2026?](https://polymarket.com/market/will-openai-ipo-by-december-31-2026) |
| 14.11 | 63.0 | 100 | 4.5¢ | 77,184 | 18,927 |  | [Will NVIDIA be the largest company in the world by market cap on Decem](https://polymarket.com/market/will-nvidia-be-the-largest-company-in-the-world-by-market-cap-on-december-31-244) |
| 12.89 | 116.0 | 50 | 4.5¢ | 192,358 | 15,273 |  | [Will no Fed rate cuts happen in 2026?](https://polymarket.com/market/will-no-fed-rate-cuts-happen-in-2026) |
| 11.89 | 20.0 | 200 | 3.5¢ | 15,908 | 2,301 |  | [Will GPT-6 be released by December 31, 2026?](https://polymarket.com/market/will-gpt-6-be-released-by-december-31-2026-834-362-194-984-527-328-225) |
| 11.71 | 24.0 | 50 | 4.5¢ | 16,839 | 18,831 |  | [Will Avengers: Doomsday have the best domestic opening weekend in 2026](https://polymarket.com/market/will-avengers-doomsday-have-the-best-domestic-opening-weekend-in-2026) |
| 10.17 | 400.0 | 200 | 3.5¢ | 903,519 | 108,625 |  | [Will the U.S. invade Iran before 2027?](https://polymarket.com/market/will-the-us-invade-iran-before-2027) |
| 9.07 | 11.0 | 20 | 4.5¢ | 4,909 | 790 |  | [Will Tom Begich win the 2026 Alaska governor election?](https://polymarket.com/market/will-tom-begich-win-the-2026-alaska-governor-election) |
| 8.51 | 10.0 | 50 | 6.5¢ | 3,958 | 870 |  | [Will Trump meet with Aleksandr Lukashenko in 2026?](https://polymarket.com/market/will-trump-meet-with-aleksandr-lukashenko-in-2026) |
| 8.25 | 30.0 | 200 | 3.5¢ | 65,832 | 239 |  | [Friedrich Merz out as Chancellor of Germany before 2027?](https://polymarket.com/market/friedrich-merz-out-as-chancellor-of-germany-before-2027) |
| 8.13 | 66.0 | 50 | 4.5¢ | 172,705 | 10,337 |  | [Will 1 Fed rate cut happen in 2026?](https://polymarket.com/market/will-1-fed-rate-cut-happen-in-2026) |
| 7.74 | 20.0 | 200 | 4.5¢ | 39,358 | 430 |  | [Will the Democrats win the Wisconsin governor race in 2026?](https://polymarket.com/market/will-the-democrats-win-the-wisconsin-governor-race-in-2026) |
| 7.38 | 15.0 | 100 | 4.5¢ | 25,823 | 0 |  | [Will a new country join the Abraham Accords before 2027?](https://polymarket.com/market/will-a-new-country-join-the-abraham-accords-before-2027) |
| 7.24 | 93.0 | 100 | 5.5¢ | 232,464 | 127,267 |  | [Will Flávio Bolsonaro win the 2026 Brazilian presidential election?](https://polymarket.com/market/will-flvio-bolsonaro-win-the-2026-brazilian-presidential-election) |
| 6.13 | 107.0 | 100 | 5.5¢ | 360,449 | 101,872 |  | [Will Luiz Inácio Lula da Silva win the 2026 Brazilian presidential ele](https://polymarket.com/market/will-luiz-incio-lula-da-silva-win-the-2026-brazilian-presidential-election) |
| 5.91 | 30.0 | 200 | 3.5¢ | 95,759 | 12,180 | evet | [Netanyahu out by end of 2026?](https://polymarket.com/market/netanyahu-out-before-2027-684-719-226-657) |
| 5.11 | 10.0 | 20 | 4.5¢ | 23,437 | 911 |  | [Will the Democrats win the Ohio governor race in 2026?](https://polymarket.com/market/will-the-democrats-win-the-ohio-governor-race-in-2026) |
| 5.00 | 10.0 | 50 | 6.5¢ | 23,042 | 3,821 |  | [Will Trump meet with Kim Jong Un in 2026?](https://polymarket.com/market/will-trump-meet-with-kim-jong-un-in-2026) |

## 2) Holding reward (protokol ~%3.25–4 APY)

Eligible long-dated pozisyonların mark-to-market değerine saatlik örnekleme. YES+NO birlikte tutmak yaklaşık $1 kilitler; getiri protokolden gelir, yön riski nötrlenir. DeFi getirisinden düşük olabilir — karşılaştır.

| 24s hacim | Bid | Ask | Bitiş | Market |
|----------:|----:|----:|-------|--------|
| 349,895 | 0.070 | 0.080 | 2026-12-31 | [Putin out as President of Russia by December 31, 2026?](https://polymarket.com/market/putin-out-before-2027-346) |
| 245,405 | 0.220 | 0.230 | 2027-01-01 | [Will Bitcoin dip to $45,000 by December 31, 2026?](https://polymarket.com/market/will-bitcoin-dip-to-45000-by-december-31-2026-674-923-755-971-998-525-926-245-316-517-544-589-965-923-986-841-815-224-586-231-289-533-573) |
| 80,607 | 0.015 | 0.017 | 2028-11-07 | [Will Wes Moore win the 2028 Democratic presidential nomination?](https://polymarket.com/market/will-wes-moore-win-the-2028-democratic-presidential-nomination-714) |
| 59,159 | 0.026 | 0.027 | 2028-11-07 | [Will Tucker Carlson win the 2028 Republican presidential nomination?](https://polymarket.com/market/will-tucker-carlson-win-the-2028-republican-presidential-nomination) |
| 58,071 | 0.470 | 0.480 | 2026-11-03 | [2026 Balance of Power: D Senate, D House](https://polymarket.com/market/2026-balance-of-power-d-senate-d-house-949) |
| 52,022 | 0.001 | 0.002 | 2028-11-07 | [Will Kim Kardashian win the 2028 US Presidential Election?](https://polymarket.com/market/will-kim-kardashian-win-the-2028-us-presidential-election) |
| 50,519 | 0.131 | 0.132 | 2028-11-07 | [Will Alexandria Ocasio-Cortez win the 2028 US Presidential Election?](https://polymarket.com/market/will-alexandria-ocasio-cortez-win-the-2028-us-presidential-election) |
| 47,124 | 0.006 | 0.007 | 2028-11-07 | [Will Elon Musk win the 2028 US Presidential Election?](https://polymarket.com/market/will-elon-musk-win-the-2028-us-presidential-election) |
| 36,582 | 0.370 | 0.380 | 2026-11-03 | [2026 Balance of Power: R Senate, D House](https://polymarket.com/market/2026-balance-of-power-r-senate-d-house-444) |
| 33,444 | 0.070 | 0.080 | 2027-01-01 | [Will Bitcoin reach $100,000 by December 31, 2026?](https://polymarket.com/market/will-bitcoin-reach-100000-by-december-31-2026-571-361-361) |
| 27,816 | 0.120 | 0.130 | 2026-11-03 | [2026 Balance of Power: R Senate, R House](https://polymarket.com/market/2026-balance-of-power-r-senate-r-house-537) |
| 26,667 | 0.161 | 0.162 | 2028-11-07 | [Will Gavin Newsom win the 2028 Democratic presidential nomination?](https://polymarket.com/market/will-gavin-newsom-win-the-2028-democratic-presidential-nomination-568) |
| 25,113 | 0.002 | 0.003 | 2028-11-07 | [Will Pete Hegseth win the 2028 US Presidential Election?](https://polymarket.com/market/will-pete-hegseth-win-the-2028-us-presidential-election) |
| 24,191 | 0.204 | 0.205 | 2028-11-07 | [Will Alexandria Ocasio-Cortez win the 2028 Democratic presidential nom](https://polymarket.com/market/will-alexandria-ocasio-cortez-win-the-2028-democratic-presidential-nomination-653) |
| 23,256 | 0.049 | 0.050 | 2028-11-07 | [Will Josh Shapiro win the 2028 Democratic presidential nomination?](https://polymarket.com/market/will-josh-shapiro-win-the-2028-democratic-presidential-nomination-977) |
| 22,709 | 0.230 | 0.231 | 2028-11-07 | [Will JD Vance win the 2028 US Presidential Election?](https://polymarket.com/market/will-jd-vance-win-the-2028-us-presidential-election) |
| 21,926 | 0.005 | 0.006 | 2028-11-07 | [Will Hunter Biden win the 2028 Democratic presidential nomination?](https://polymarket.com/market/will-person-a-win-the-2028-democratic-presidential-nomination) |
| 21,449 | 0.148 | 0.149 | 2028-11-07 | [Will Jon Ossoff win the 2028 Democratic presidential nomination?](https://polymarket.com/market/will-jon-ossoff-win-the-2028-democratic-presidential-nomination-885) |
| 21,229 | 0.002 | 0.003 | 2028-11-07 | [Will Nikki Haley win the 2028 Republican presidential nomination?](https://polymarket.com/market/will-nikki-haley-win-the-2028-republican-presidential-nomination) |
| 20,893 | 0.001 | 0.002 | 2028-11-07 | [Will Abigail Spanberger win the 2028 Democratic presidential nominatio](https://polymarket.com/market/will-abigail-spanberger-win-the-2028-democratic-presidential-nomination) |

## 3) Completeness arb (YES+NO, ücret sonrası)

`buy_both`: her iki ask'i kaldır, $1 ödeme. `sell_both_after_split`: $1 split et, her iki bid'e sat. Ham boşluk ücretten küçükse **hit yok** — GitHub botlarının çoğu bunu atlar.

| Tür | Net edge | Ham gap | YES | NO | Fee | 24s hacim | Market |
|-----|---------:|--------:|----:|---:|----:|----------:|--------|
| — | — | — | — | — | — | — | ücret-sonrası boşluk yok |

## 4) Neg-risk Dutch book (tüm YES ask toplamı)

Yalnız `negRisk=true` eventler. Set eksikse $1 ödeme garanti değildir.

| Net edge | Σ ask | N | Fee | Event |
|---------:|------:|--:|----:|-------|
| — | — | — | — | ücret-sonrası boşluk yok |

## Okuma notu

- Protokol ödemeleri (LP rewards, maker rebate, holding) **tekrarlanabilir** gelir; yön tahmini değildir.
- Completeness / Dutch book teoride risksizdir; pratikte latency, derinlik, kısmi fill ve CLOB V2 fee eğrisi yer.
- BTC 5dk / kopya-ticaret / 'AI agent' public botları bu taramada **yok** — çoğu negatif EV veya V1 SDK ile kırık.

