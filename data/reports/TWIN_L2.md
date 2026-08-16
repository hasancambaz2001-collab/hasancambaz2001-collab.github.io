# TWIN_L2

Generated: 2026-08-16 17:43 UTC
S1 maker complete-set (bid_sum≤0.90). Not residual/TWAP directional. No live. No pair>1. size_ok=false.

**pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2**

## Recorder

- PID: **18356**
- start: 2026-08-16T17:25:53Z
- hours of L2: **0.2988**
- ticks: 4718 files=10

## Twins

| regime | n_ticks | % bid_sum≤0.90 | rest | replace | cancel | rich | fill |
|---|---:|---:|---:|---:|---:|---:|---|
| pre_2026_08_14_DEBUG | 4704518 | 0.2938 | 6499 | 1324 | 5 | 4690199 | none |
| post_2026_08_14 | 4272 | 12.5702 | 173 | 57 | 107 | 3571 | residual |

## Cross-check (mo/bosona pair<0.90 since 2026-08-14 vs recorded L2)

- cheap windows since 08-14: **217**
- those slugs with L2: **0**
- rest opportunity on same slug: **0**

## PMData

- no PMDATA_API_KEY (or PM_DATA_API_KEY). HF parquet covers pre-08-14 DEBUG. No paid Mar–May pull.

pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2
