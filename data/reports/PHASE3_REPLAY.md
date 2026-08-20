# PHASE3 replay — taker complete-set

Context locked. This file does **not** reopen T6–T9 or the official tie-out.
Maker / Diamond rebate is **their** edge, not ours. We assume we are **not** Diamond
(no 29% taker rebate).

## Product

| field | value |
|---|---|
| book | BUY both asks FOK |
| SELL | none |
| residual | none (both-or-nothing) |
| signal | none (no spot / TWAP) |
| redeem | after resolve (winner-independent) |
| pair_max | **0.96** (inclusive) |
| pair_max_cap | 0.97 (not traded) |
| clip | **21** |
| fee | `0.07 * p * (1 − p)` on **our** taker fills |
| Diamond | no |
| maker bids | no |
| live | no |

`pair_max=0.9513` is forbidden (broken PHASE1 p25).

## Ask proxy

Eligible window = both Up and Down have at least one **taker BUY** fill on the
Whiskas tape. Ask = size-weighted VWAP of those CLOB `price` fields
(`Σ size×price / Σ size`). That is what they paid lifting the ask — conservative
versus a maker bid.

Replay size is always `clip=21`, not their size. Our fee is the official curve
on that clip at the proxy asks. Their embedded fee / rebate is not reused.

Windows with only one taker leg, or `ask_sum > 0.96`, are skipped.
`(0.96, 0.97]` is reported as excluded-cap only (after-fee can flip negative
near 0.50/0.47).

## Universe

| | n |
|---|---:|
| tape windows (unique slug on fills) | 16072 |
| both taker legs | 14504 |
| **eligible `ask_sum ≤ 0.96`** | **6556** |
| excluded `(0.96, 0.97]` | 838 |

Median pair on eligible: **0.9077**
(p10=0.7862, p90=0.9511).

## PnL (after fee, no rebate)

Complete-set: `21 × (1 − ask_sum) − fee(21, ask_up) − fee(21, ask_down)`.
Winner does not matter. Residual is always 0.

Fill 1.00 = every eligible window FOKs. Fill 0.30 = P(pair FOK succeeds) = 0.30
(both-or-nothing; independent per-leg 30% would leave residual and is rejected).
EV = `0.30 × fill1`. MC = seeded Bernoulli per window (seed=4921).

Start equity for day %: **$1000**. Day halt if `day_pnl / equity_at_open ≤ −15%`.
Old kill-switch default (−8%) is unchanged and unused here.

| fill | windows filled | pnl after fee | worst day % |
|---|---:|---:|---:|
| 1.00 | 6556 | 11649.56 | 0.27% |
| 0.30 EV | 6556 (EV) | 3494.87 | 0.09% |
| 0.30 MC | 1933 | 3431.56 | 0.00% |

Fees at fill 1.00 (both legs): $4295.45.

### Daily path — fill 1.00

- days traded: 64
- worst day: 2026-06-13 pnl=3.1394 (0.27%) halt=False
- best day: 2026-06-15 pnl=244.7354 (21.03%)
- last day equity: 12649.56 (2026-08-16)

| day | n | pnl | day % | equity end | halt |
|---|---:|---:|---:|---:|---|
| 2026-06-12 | 34 | 152.7463 | 15.27% | 1152.75 | False |
| 2026-06-13 | 4 | 3.1394 | 0.27% | 1155.89 | False |
| 2026-06-14 | 3 | 7.6727 | 0.66% | 1163.56 | False |
| 2026-06-15 | 112 | 244.7354 | 21.03% | 1408.29 | False |
| 2026-06-16 | 92 | 218.9047 | 15.54% | 1627.20 | False |
| 2026-06-17 | 73 | 178.6759 | 10.98% | 1805.87 | False |
| 2026-06-18 | 94 | 173.0272 | 9.58% | 1978.90 | False |
| 2026-06-19 | 91 | 169.7516 | 8.58% | 2148.65 | False |
| … | 56 more days | | | | |

### Daily path — fill 0.30 EV

- days traded: 64
- worst day: 2026-06-13 pnl=0.9418 (0.09%) halt=False
- best day: 2026-06-15 pnl=73.4206 (7.00%)
- last day equity: 4494.87 (2026-08-16)

| day | n | pnl | day % | equity end | halt |
|---|---:|---:|---:|---:|---|
| 2026-06-12 | 34 | 45.8239 | 4.58% | 1045.82 | False |
| 2026-06-13 | 4 | 0.9418 | 0.09% | 1046.77 | False |
| 2026-06-14 | 3 | 2.3018 | 0.22% | 1049.07 | False |
| 2026-06-15 | 112 | 73.4206 | 7.00% | 1122.49 | False |
| 2026-06-16 | 92 | 65.6714 | 5.85% | 1188.16 | False |
| 2026-06-17 | 73 | 53.6028 | 4.51% | 1241.76 | False |
| 2026-06-18 | 94 | 51.9082 | 4.18% | 1293.67 | False |
| 2026-06-19 | 91 | 50.9255 | 3.94% | 1344.60 | False |
| … | 56 more days | | | | |

### Daily path — fill 0.30 MC (seed 4921)

- days traded: 64
- worst day: 2026-06-14 pnl=0.0000 (0.00%) halt=False
- best day: 2026-06-16 pnl=73.4743 (6.66%)
- last day equity: 4431.56 (2026-08-16)

| day | n | pnl | day % | equity end | halt |
|---|---:|---:|---:|---:|---|
| 2026-06-12 | 34 | 40.3846 | 4.04% | 1040.38 | False |
| 2026-06-13 | 4 | 0.8784 | 0.08% | 1041.26 | False |
| 2026-06-14 | 3 | 0.0000 | 0.00% | 1041.26 | False |
| 2026-06-15 | 112 | 61.1867 | 5.88% | 1102.45 | False |
| 2026-06-16 | 92 | 73.4743 | 6.66% | 1175.92 | False |
| 2026-06-17 | 73 | 19.4293 | 1.65% | 1195.35 | False |
| 2026-06-18 | 94 | 45.6479 | 3.82% | 1241.00 | False |
| 2026-06-19 | 91 | 53.6892 | 4.33% | 1294.69 | False |
| … | 56 more days | | | | |

## PASS

| gate | need | got | ok |
|---|---|---|---|
| windows | > 400 | 6556 | True |
| pnl after fee @ 30% fill | > 0 | 3494.87 | True |
| median pair | ≤ 0.96 | 0.9077 | True |
| no day −15% | fill1 + 0.30 EV + 0.30 MC | worst=0.09% / MC 0.00% | True |

**PASS**. Fail reasons: none.

## Paper (no orders)

`scripts/paper_whiskas.py` polls the public CLOB for the current `btc-updown-5m-{t0}`
window and appends *intended* BUY FOKs to `data/paper/intended.jsonl` when
`ask_up + ask_down ≤ 0.96`. GET only. No maker bids. No live.

```bash
python3 scripts/paper_whiskas.py --once
python3 scripts/paper_whiskas.py --seconds 60 --interval 5
```

## Replay command

```bash
python3 scripts/replay_whiskas.py
```

Writes `data/processed/replay_stats.json`, `data/processed/replay_eligible.parquet`,
and this file.
