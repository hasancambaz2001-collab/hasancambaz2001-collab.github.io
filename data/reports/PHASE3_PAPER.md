# PHASE3 paper (frozen)

Measure-only. No live. No pair>1. Clip 21. Repeat max 8. 4h = poll only.
Ask buckets 0.90 / 0.96 unchanged. Bid bucket: log bid_sum; maker_intend when bid_sum≤0.98 on 5m/15m only.

| asset | tf | bucket | polls | A_hits | A2_hits | repeat_hits | depth_ok | still250 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| btc | 5m | 0.90 | 7 | 0 | 0 | 0 | 0 | 0 |
| btc | 5m | 0.96 | 7 | 0 | 0 | 0 | 0 | 0 |
| btc | 15m | 0.90 | 7 | 0 | 0 | 0 | 0 | 0 |
| btc | 15m | 0.96 | 7 | 0 | 0 | 0 | 0 | 0 |
| btc | 4h | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| btc | 4h | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 5m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 5m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 15m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 15m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 4h | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| eth | 4h | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 5m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 5m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 15m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 15m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 4h | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| sol | 4h | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 5m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 5m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 15m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 15m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 4h | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| xrp | 4h | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 5m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 5m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 15m | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 15m | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 4h | 0.90 | 6 | 0 | 0 | 0 | 0 | 0 |
| doge | 4h | 0.96 | 6 | 0 | 0 | 0 | 0 | 0 |

Window: 2026-08-16T17:04:33.034589+00:00 → 2026-08-16T17:05:11.274170+00:00

0 prints with ask_sum≤0.96 is a paper PASS: live book did not show the pair.

maker_intend=32 bid_sum≤0.98=51 (measure only, no live)
