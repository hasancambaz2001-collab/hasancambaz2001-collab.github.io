# PHASE1 — Whiskas BTC 5m reconstruction

Generated: 2026-08-16 13:44 UTC

**Ledger lock is `PHASE1_TIEOUT.md`, not this file.** `total_pnl=−$103,515` double-counts taker fees on top of `usdcSize` and treats every BUY as a taker. Official ALL is +$211,013.58; reconstructed fee0 (`payout − size×price`) is +$210,876.56 (`|$137|`). Do not retune `pair_max` from the p25=0.9513 line below.

Do not start the bot loop from this file. Config below is quantile-fitted, not a live go.

## Identity

- Username: `x-MoneyForWhiskas`
- Profile: https://polymarket.com/@x-moneyforwhiskas
- Proxy wallet: `0x3048d65321be3497164cdfc2996f94f98a2e7537`
- Scope: `btc-updown-5m-*` only

## Dump

- Activity rows: 444044
- Closed-position rows: 30985
- Winner sources: {'from_redeem': 15701, 'from_closed': 15707, 'from_gamma': 364, 'resolved': 16072, 'unresolved': 0}

## Coverage

- Windows: **16072**
- Resolved: **16072**
- Unresolved: 0
- Windows with both legs (pair_cost defined): **15235**
- Residual windows: 15723
- Fills: 428102 (BUY 428094 / SELL 8, sell_rate=0.0000)

## Pair-cost distribution

| q | pair_cost |
|---|---:|
| p10 | 0.8932 |
| p25 | 0.9513 |
| p50 | 0.9962 |
| p75 | 1.0384 |
| p90 | 1.0895 |
| p95 | 1.1370 |

| bin | n |
|---|---|
| [0.80, 0.90) | 1307 |
| [0.90, 0.94) | 1502 |
| [0.94, 0.96) | 1190 |
| [0.96, 0.97) | 771 |
| [0.97, 0.98) | 897 |
| [0.98, 0.99) | 963 |
| [0.99, 1.00) | 982 |
| [1.00, 1.02) | 1947 |
| [1.02, 1.10) | 3971 |
| [1.10, 1.50] | 1313 |

## PnL decomposition (resolved windows)

| component | USDC |
|---|---:|
| pair_pnl (matched × (1 − pair_cost) − allocated fee) | -133695.85 |
| residual_pnl | 30184.30 |
| estimated taker fees | 180486.91 |
| rebates observed | 0.00 |
| total_pnl (payout − cost − fee + rebate) | -103514.95 |

- Window win rate (total_pnl > 0): 0.443
- Residual win rate: 0.540
- Late fills: 89826 ; late markout 13227.11 ; late price p50/p90 0.4700 / 0.8100

Fees use the official crypto curve `fee = C × 0.07 × p × (1−p)` ([docs](https://docs.polymarket.com/trading/fees)). Activity does not mark maker vs taker; Phase 1 treats BUY fills as taker (conservative). That fee load is **$180,487**. If every fill were maker (fee = 0), total_pnl would be **+$76,972** and pair_pnl **+$28,178**.

Cheap-set slice (same fills, still assuming taker fees):

| filter | n paired | pair_pnl after fees |
|---|---:|---:|
| pair_cost < 0.97 | 5159 | +75521.93 |
| pair_cost < 1.00 | 7612 | +54946.47 |
| all paired | 15235 | -133695.85 |

T1 fails on the **full** book because they often complete sets above $1 (p75 = 1.038). Layer A `pair_max` is the filter that would have kept the cheap slice.

## T1–T5

| test | result | rule |
|---|---|---|
| T1 complete-set | FAIL | median pair_cost < 1.00 AND pair_pnl > 0 |
| T2 residual | FAIL | residual WR ≥ 55% on resolved leftover inventory |
| T3 late | PASS | t > 240s fill markout > 0 (n≥20) |
| T4 buy-only | PASS | SELL rate < 1% on btc-updown-5m |
| T5 clip/burst | PASS | median BUY clip in 5–50 and some windows with ≥4 fills |

## Daily resolved PnL

| day | windows | total_pnl | pair_pnl |
|---|---:|---:|---:|
| 2026-06-10 | 1 | 1.35 | 0.00 |
| 2026-06-12 | 125 | -78.08 | 53.38 |
| 2026-06-13 | 33 | -44.81 | -19.45 |
| 2026-06-14 | 15 | -15.14 | -2.03 |
| 2026-06-15 | 265 | -47.23 | 2.11 |
| 2026-06-16 | 268 | 118.39 | -358.04 |
| 2026-06-17 | 263 | 458.74 | -3610.28 |
| 2026-06-18 | 272 | -2276.99 | -3389.66 |
| 2026-06-19 | 272 | -403.27 | -980.01 |
| 2026-06-20 | 200 | -868.92 | -1055.28 |
| 2026-06-21 | 264 | -551.17 | -441.97 |
| 2026-06-22 | 276 | -473.31 | -365.43 |
| 2026-06-23 | 182 | 219.96 | -244.50 |
| 2026-06-24 | 273 | -431.73 | -1070.83 |
| 2026-06-25 | 232 | -376.42 | -1119.81 |
| 2026-06-26 | 283 | -2230.10 | -3433.54 |
| 2026-06-27 | 280 | 175.33 | -1117.49 |
| 2026-06-28 | 280 | 140.02 | -1142.74 |
| 2026-06-29 | 279 | -1075.45 | -1752.27 |
| 2026-06-30 | 279 | -732.53 | -1360.53 |
| 2026-07-01 | 276 | 1021.67 | -734.11 |
| 2026-07-02 | 273 | -910.99 | -932.72 |
| 2026-07-03 | 278 | 187.08 | -679.23 |
| 2026-07-04 | 278 | 133.38 | -757.61 |
| 2026-07-05 | 275 | -743.77 | -1188.01 |
| 2026-07-06 | 277 | -65.17 | -984.17 |
| 2026-07-07 | 266 | 272.04 | -499.94 |
| 2026-07-08 | 283 | 269.39 | -554.98 |
| 2026-07-09 | 275 | 432.84 | -884.24 |
| 2026-07-10 | 266 | -83.25 | -1270.64 |
| 2026-07-11 | 257 | -857.94 | -1082.20 |
| 2026-07-12 | 238 | -148.60 | -2045.48 |
| 2026-07-13 | 275 | -3250.93 | -5199.44 |
| 2026-07-14 | 269 | -1898.51 | -4615.04 |
| 2026-07-15 | 275 | -3828.48 | -6112.61 |
| 2026-07-16 | 279 | -5028.70 | -6499.98 |
| 2026-07-17 | 280 | -5207.34 | -8638.03 |
| 2026-07-18 | 276 | -1687.19 | -2512.63 |
| 2026-07-19 | 286 | 939.73 | -793.90 |
| 2026-07-20 | 275 | -5042.99 | -4016.53 |
| 2026-07-21 | 281 | -4849.07 | -3630.98 |
| 2026-07-22 | 284 | -2885.93 | -3556.02 |
| 2026-07-23 | 286 | -1894.76 | -3359.51 |
| 2026-07-24 | 285 | -3073.99 | -3206.01 |
| 2026-07-25 | 286 | -253.84 | -464.38 |
| 2026-07-26 | 283 | 66.82 | 123.66 |
| 2026-07-27 | 110 | -2116.12 | -861.80 |
| 2026-07-30 | 98 | -929.98 | -406.98 |
| 2026-07-31 | 279 | -3925.34 | -4329.35 |
| 2026-08-01 | 279 | -2199.56 | -509.34 |
| 2026-08-02 | 284 | -1125.87 | -1673.46 |
| 2026-08-03 | 277 | -3184.08 | -2491.29 |
| 2026-08-04 | 279 | -4255.19 | -2148.27 |
| 2026-08-05 | 265 | -3855.71 | -2746.43 |
| 2026-08-06 | 283 | -4571.97 | -6130.86 |
| 2026-08-07 | 258 | -3938.91 | -3376.96 |
| 2026-08-08 | 279 | -386.43 | -811.95 |
| 2026-08-09 | 212 | -2540.71 | -1587.80 |
| 2026-08-10 | 241 | -499.75 | -2312.05 |
| 2026-08-11 | 240 | -1325.62 | -2910.49 |
| 2026-08-12 | 282 | -6702.43 | -5933.69 |
| 2026-08-13 | 278 | -5517.60 | -5993.96 |
| 2026-08-14 | 242 | -6866.09 | -4446.46 |
| 2026-08-15 | 246 | -2108.19 | 181.95 |
| 2026-08-16 | 136 | -585.51 | 296.41 |

## Quantiles used for config

| field | source | value |
|---|---|---:|
| pair_max | min(0.97, pair_cost p25) if p25 else 0.97 | see `configs/whiskas.yaml` |
| clip | BUY size p50 | 20.86 |
| max_residual | residual_ratio p75 | 0.248 |
| burst_windows | n_fills p90 | 59.0 |
| late_max_price | late fill price p50 | 0.4700 |
| fee.rate | official crypto taker | 0.07 |

## Stop

Phase 1 only. Policy / replay / paper loop are later steps.
