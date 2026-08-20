# SIM — BTC 5m L2 inventory + hole lifetime

Label: **SIM**. `real_fill` is null. No live send. Clip 5. pair≤0.90. 1-tick. No pair>1.

## What we already have (full L2)

PMData Day API, Yes-token only, every bid/ask level + `price_change` ticks.

| file | windows | bytes | book gap p50 | levels (sample) |
|---|---:|---:|---:|---:|
| `btc-5m_l2_2026-08-14.zip` | 288 | 351 MB | 0.103s | 78 |
| `btc-5m_l2_2026-08-15.zip` | 288 | 251 MB | 0.1s | 98 |

This file cannot compute `bid_up+bid_down`. Down is a second token. Do not invent the complement.

## Both-leg hole (1s TOB, SIM)

Source: `data/parquet/btc_ticks.parquet`. 2026-03-24 22:10:00+00:00 → 2026-05-18 10:34:59+00:00.

- Seconds: **4,383,804**. Markets: **15,682**.
- Hole seconds (pair≤0.90, depth≥5, 1-tick both legs): **11,618** (0.265% of seconds).
- Windows with any hole second: **4,699** / 15,682 (30.0%).
- Hole runs: **8,542**. Duration p50 **1.0s**, p90 **2.0s**, p99 **5.0s**, max **253s**.
- Runs lasting 1s only: **83.0%**. ≥2s (still250 would pass): **17.0%**. ≥5s: **1.0%**.

Matches the live tape after REST still250: 39 rests, 37 `still250_false`. Most cheap prints do not stay 250ms.

## Not this

Not a fill. Not SLIP-ME / Bonereaper. Not clip bump. Not bot start.
