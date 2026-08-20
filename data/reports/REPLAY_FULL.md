# REPLAY_FULL

Their tape. S1 maker pair<0.90. pair_gt_1_trade=false.

- parity their-size = **14110.75** n=209 clip=None (2026-08-16 17:46 UTC)

- parity clip10 = **797.60** n=209 clip=10.0 (2026-08-16 17:46 UTC)

## clip10 vs their-size

- parity their-size = **14110.75** n=209
- parity clip10 = **797.60** n=209
- usd_ratio (clip10 / their-size) = **0.056524 (5.6524% of their-size $)** — computed from the two $ figures
- clip10 << their-size: **True** · gap_usd = **13313.15**
- kind = **size_gap** (same n=True; only size changes)
- their matched size: n=209 sum=62315.6649 mean=298.1611 p25=12.083332 p50=50.0 p75=182.84 p90=380.4355922000004 max=11773.616062000001
- paper clip size sum = 2090.0000 · size_sum_ratio = 0.033539
- windows with their size > clip: 163 / 209

| wallet | n | their-size $ | clip10 $ | usd_ratio |
|---|---:|---:|---:|---:|
| mo-money | 95 | 3024.44 | 364.97 | 0.120674 |
| bosona | 97 | 3307.48 | 393.64 | 0.119015 |
| 06dc | 17 | 7778.83 | 38.99 | 0.005012 |

Same S1 windows and pairs; only size changes (paper clip vs their matched). usd_ratio = parity_clip10 / parity_their_size, computed, not hardcoded.
