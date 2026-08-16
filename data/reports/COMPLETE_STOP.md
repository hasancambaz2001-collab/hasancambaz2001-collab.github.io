# COMPLETE STOP (L2 TWIN onward)

Generated: 2026-08-16 17:44 UTC
No live. size_ok=false. pair_gt_1_trade=false. No merge.

## 1. Recorder

- PID **18356** alive since 2026-08-16T17:25:53Z
- hours of L2: **0.30**
- n files: **10** (`data/l2/*.jsonl`) · ticks ~4787 and growing
- assets btc/eth/sol/xrp/doge · tfs 5m/15m · interval 1s · live_order=false

## 2. Parquet DEBUG — REGIME=pre_2026_08_14_DEBUG

n_ticks 4,704,518 · **% bid_sum≤0.90 = 0.2938** · rest 6499 / replace 1324 / cancel 5 / rich 4,690,199
Span 2026-03-24 → 2026-05-18. `--fill none`. Policy wiring only.

## 3. Post-14 record twin — REGIME=post_2026_08_14

n_ticks 4272 · **% bid_sum≤0.90 = 12.5702** · rest 173 / replace 57 / cancel 107 / rich 3571
`--fill residual`. Cross-check: 217 cheap mo/bosona windows since 08-14; 0 slugs with L2 yet (recorder started after those windows).

## 4. Harness

| source | fill | s1 | s06dc | whiskas (legacy) | whiskas_full_measure |
|---|---|---:|---:|---:|---:|
| tape_bosona | parity_tape | 3307.48 | 0 (5m smoke) | 412.93 | 2302.63 |
| tape_mo | parity_tape | 3024.44 | 0 (5m smoke) | 700.56 | 2246.67 |
| record | residual | 316.10 intended | 0 (5m smoke) | 1.79 | −3616.39 (pair>1 ATTR) |

s06dc on 5m ticks is smoke. Real 06dc needs daily/monthly + T6. Whiskas full measure ≠ license to trade pair>1.

## 5. KASA

- **S1$ = 14110.75** n=209
- **S3$ = 5078.57** n=50 (not primary)
- **S1_frac = 0.735**
S1_cheap dominates. S3/pair>1 stay ATTR / trade=false.

## 6. Replay / cover / parity

- cover GATE **PASS**: mo 84.7% (94/111), bosona 80.2% (85/106) ≥80%
- parity their-size **14110.75**
- parity clip10 **797.60** (~5.7% of S1$ — size gap, not rule gap)

## 7. Queue v2 fill_ratio (NOT go/no-go)

| source | base | pes | opt |
|---|---:|---:|---:|
| record (~18 min L2) | 0.0864 | 0.0741 | 0.0988 |
| tape_bosona (coarse) | 0.3650 | 0.1901 | 0.9125 |

Low record fill% = short L2 + join-back/hidden/latency. Calibrate. Do not kill S1. Optimistic not for sizing. size_ok stays false.

## 8. Public realism

- fee drag clip10: bosona **0.3228** · mo **0.3001** (maker fee0 vs taker 0.07·p·(1-p))
- time-in-window mean: bosona **0.584** n=252 · mo **0.658** n=190
- dump-native tape lines: bosona 252 · mo 190
- live API trades: 160/wallet (gamma settlement found 0 — purged old 5m; use dump-native)

## 9. T6 / R7

GATE **UNCLEAR**. n directional resolved=8 (<20). hit-rate 50% (<58%). **r7_daily_t6=false**. R6 bid_sum≤0.99. No ATM directional invent.

## 10. Explicit

- pre-08-14 parquet is DEBUG only
- S1 go/no-go = replay edge, NOT queue fill%
- size_ok=false live=false pair_gt1_trade=false

Papers left up: 5m 14938 (legacy_ask_fok), 06dc 14808, maker 15594 (PRIMARY). doge in maker assets.
