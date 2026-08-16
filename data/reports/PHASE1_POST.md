# PHASE1_POST (light)

Activity since **2026-08-14 00:00 UTC** only. Cap **2000** rows/wallet (Data API `/activity`, DESC).
No Whiskas reopen. No bot. No replay. No live.

Pair = size-weighted CLOB `price` Up + Down on the same `eventSlug` (BUY). Clip = median BUY size.

| wallet | n trade | %5m | %15m | %other | pair p25 | p50 | p75 | n pair | <0.90 | <0.96 | >1.00 | med clip | SELL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bosona | 1695 | 69.2% | 20.5% | 10.3% | 0.6833 | 0.8406 | 1.0503 | 97 | 56 | 63 | 31 | 10.00 | 0 |
| almach | 1713 | 67.0% | 21.5% | 11.5% | 0.7007 | 0.8578 | 1.0649 | 110 | 60 | 71 | 37 | 9.77 | 0 |
| 0xb55f | 1957 | 0.0% | 65.3% | 34.7% | 0.8891 | 1.0036 | 1.0772 | 46 | 13 | 18 | 23 | 12.00 | 0 |

Wallets: `bosona` `0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed`, `almach` `0x3725d52f3c252e8374999cc8617292ea2608ad88`, `0xb55f` `0xb55fa1296e6ec55d0ce53d93b9237389f11764d4`.

All of bosona, almach, 0xb55f hit the **2000-row cap**. Table is the newest slice, not the full since-14 book. Observed: bosona 2026-08-16 12:03 UTC → 2026-08-16 15:35 UTC; almach 2026-08-16 11:52 UTC → 2026-08-16 15:35 UTC; 0xb55f 2026-08-16 12:43 UTC → 2026-08-16 15:34 UTC.
