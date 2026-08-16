# TAPE — Aug 2026 windows, Binance 1s + Chainlink strike

Scope: windows with `t0 ≥ 2026-08-01 00:00 UTC` (4,081 windows, 147,407 fills), then stop.  
Strike / official close: Gamma `eventMetadata.priceToBeat` / `finalPrice` (Chainlink). 3,947 / 4,081 windows had strike.  
Intra-window spot and TWAP: Binance BTCUSDT **1s close** (data.binance.vision, Aug 1 00:00 → Aug 15 23:59 UTC). Aug 16 1s zip is not published; REST 451.  
TWAP regimes (from Gamma `cryptoMarketConfig`):

| when | resolution |
|---|---|
| through 2026-08-06 | Chainlink snapshot (`btc-usd`) |
| 2026-08-07 00:00 → 2026-08-13 | 30s Chainlink TWAP |
| **2026-08-14 00:00 →** | **60s Chainlink TWAP** |

Live TWAP used in T7 = Binance rolling 30s before Aug 14, 60s after (proxy). Official `sign(finalPrice − priceToBeat)` is also reported. No bot.

## T6 — taker side vs sign(spot − strike)

Taker BUY Up iff Binance 1s close at fill > Chainlink strike.

| sample | n | agree | se | vs 50% |
|---|---:|---:|---:|---|
| all Aug 1–15 | 75,811 | **50.43%** | 0.18% | +2.3σ, economically flat |
| pre Aug 14 | 67,936 | 50.29% | 0.19% | flat |
| post Aug 14 (14–15) | 7,875 | 51.61% | 0.56% | +2.9σ, still ~coin |

**T6: no. They do not lift with the Binance tape vs strike.** 50% is the right prior for a complete-set / both-sides book.

## T7 — taker side vs sign(TWAP − strike), split on 2026-08-14

| sample | n | agree | se |
|---|---:|---:|---:|
| live TWAP (regime-correct) all | 75,811 | 50.40% | 0.18% |
| pre Aug 14 (spot or 30s) | 67,936 | 50.26% | 0.19% |
| **post Aug 14 60s TWAP** | 7,875 | **51.59%** | 0.56% |
| official `finalPrice − strike` | 75,065 | 50.49% | 0.18% |
| Aug 1–6 snapshot only | 30,389 | 49.98% | 0.29% |
| Aug 7–13 30s TWAP | 37,547 | 50.49% | 0.26% |

**T7: no regime break that turns them into a TWAP-direction bot.** Post-14 60s is 51.6% — same noise band as T6, two days of data. Official Chainlink close vs strike is 50.5%. They buy both legs; the taker side is not `sign(twap − strike)`.

## T8 — are maker fills adverse-selected?

| | maker | taker (contrast) |
|---|---:|---:|
| Aug fills | 67,954 | 79,453 |
| P(side = window loser) | **52.63%** | 49.54% |
| 5s Binance markout mean | **+0.013 bps** | +0.051 bps |
| 30s markout mean | +0.051 bps | — |
| P(markout 5s < 0) | 31.6% | — |
| P(markout 30s < 0) | 43.1% | — |

5s/30s “adverse” rates are pulled down by zero-change seconds (BTC 1s often flat). Means are **+0.01–0.05 bps** — not a pickoff on the short markout.

On the **binary resolution**, makers are on the losing side 52.6% of the time (vs taker 49.5%). That is mild adverse selection into the winner, consistent with resting bids that get hit when the other side is informed, not with “every maker fill is toxic.”

**T8: weakly yes on the window winner; no on 5s/30s Binance markout.**

## T9 — daily fee0 + pair<0.97, pre vs post TWAP

Fee0 = `payout − usdcSize` (after real taker fees). Cheap = PHASE1 usdc `pair_cost < 0.97` (and `< 0.96` next to it).

| era | n win | fee0 | $/win | pair<0.97 n | % | cheap fee0 | pair<0.96 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aug 1–6 snapshot | 1,667 | +$6,177 | +3.71 | 575 | 34.5% | +$14,964 | 28.8% |
| Aug 7–13 TWAP 30s | 1,790 | +$9,757 | +5.45 | 542 | 30.3% | +$19,648 | 25.6% |
| **pre Aug 14** | **3,457** | **+$15,934** | **+4.61** | **1,117** | **32.3%** | **+$34,612** | 27.2% |
| **post Aug 14 TWAP 60s** | **624** | **−$1,726** | **−2.77** | **216** | **34.6%** | **+$3,018** | 29.8% |

Full-book fee0 flips from +$4.61/win to **−$2.77/win** after the 60s TWAP cutover. The cheap slice **does not die**: 32% → 35% of windows still print pair<0.97, and that slice stays **positive** (+$3.0k on 216 windows, $14.0/win). The post-14 bleed is the expensive / residual book, not Layer A.

Aug 16 is inside the post-14 window count (no 1s tape that day). Two weeks vs two days: do not retune `pair_max` from T9. Default stays **0.96**, cap **0.97**.

## Expand later

This pack stops at Aug 1–16. A longer tape needs Binance 1s before August and a Chainlink TWAP archive (RTDS has no public REST history). Gamma strike cache is in `data/processed/gamma_strikes.json`.
