# PHASE1_MAKER_MOBO

Generated: 2026-08-16 17:14 UTC
Activity cap **3000** newest rows/wallet. GET `/activity` only. No live. Paper not edited.
Role: **taker** iff `usdc − size×price` matches `0.07·p·(1−p)·size` ±15%. Else maker.

## GATE **PASS**

maker_share=90.4% (need ≥25%), maker two-leg pair≤0.98 n=194 (need ≥5).
PASS requires combined maker share ≥25% and ≥5 maker two-leg pairs with pair≤0.98 (bid-bucket gate).

| wallet | n buy | %maker | %taker | 5m | 15m | doge | pair p50 | <0.96 | taker p50 | taker<0.96 | maker p50 | maker≤0.98 | maker>1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mo-money | 2499 | 90.1% | 9.9% | 1474 | 668 | 218 | 0.8684 | 115 | 0.8616 | 18 | 0.7736 | 100 | 40 |
| bosona | 2479 | 90.6% | 9.4% | 1642 | 537 | 193 | 0.8340 | 106 | 0.9112 | 14 | 0.7778 | 94 | 28 |

Wallets: `mo-money` `0x32ed2e546b187ca15e2841edc82b22c713cf8ec3`, `bosona` `0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed`.

Observed: mo-money 2026-08-16 10:08 UTC → 2026-08-16 17:13 UTC; bosona 2026-08-16 11:12 UTC → 2026-08-16 17:13 UTC.

No clip bump. No R7. No pair>1 taker. No paper restart in this step.
