# TWIN_L2

Generated: 2026-08-16 17:30 UTC
S1 maker complete-set (bid_sum≤0.90). Not residual/TWAP directional. No live. No pair>1. size_ok=false.

**pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2**

## Recorder

- PID: **18356** (alive)
- start: 2026-08-16T17:25:53Z
- hours of L2: **0.0832** (~5 min)
- assets: btc,eth,sol,xrp,doge · tfs: 5m,15m · interval 1s
- ticks written: 1314 across 10 jsonl files under `data/l2/`
- GET only. No live orders.

## Parquet DEBUG — REGIME=pre_2026_08_14_DEBUG

kachoio `btc_ticks.parquet` + `btc_markets.parquet`. Span **2026-03-24 → 2026-05-18**. `--fill none`. Policy wiring only.

| | |
|---|---:|
| n_ticks | 4,704,518 |
| n_slugs | 15,682 |
| **% bid_sum≤0.90** | **0.2938** (13,821 ticks) |
| rest | 6,499 |
| replace | 1,324 |
| cancel | 5 (cancel_age) |
| rich | 4,690,199 |

Reasons: rich_bid_sum 4,683,974 · rest 6,499 · rich_cancel 6,225 · thin_bid 4,294 · hold 2,197 · requote 1,324 · cancel_age 5.

## Post-regime record — REGIME=post_2026_08_14

`data/l2/*.jsonl` from this recorder. `--fill residual`. Truth for config. ~5 minutes of books.

| | |
|---|---:|
| n_ticks | 1,029 |
| n_slugs | 20 |
| **% bid_sum≤0.90** | **9.3294** (96 ticks) |
| rest | 30 |
| replace | 12 |
| cancel | 21 (pair_gt_1 refused, not traded) |
| rich | 914 |

Reasons: rich_bid_sum 907 · rest 30 · thin_bid 22 · pair_gt_1 21 · hold 16 · requote 12 · missing_bid 12 · rich_cancel 6 · filled_both 2 · rich_complete 1.

## Cross-check

mo/bosona two-leg **pair<0.90** since 2026-08-14: **217** windows.
Slugs with L2 available: **0**. Rest opportunity on same slug: **0**.
Recorder started 17:25Z; dump cheap slugs are earlier 5m/15m windows, so no overlap yet. Keep recorder.

## PMData

Skipped: no `PMDATA_API_KEY`. HF already covers pre-08-14 DEBUG. No paid Mar–May pull.

pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2
