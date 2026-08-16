# PMDATA_WALLET_CONFIG

Generated: 2026-08-16 18:03 UTC
Post-08-14 only. No Mar–May bulk. No live. size_ok=false. pair_gt_1_trade=false.

**Nautilus historical L2 = false** (orderbook-history dead). PMData is the L2 source.
**PMData does NOT cover 06dc daily/monthly.** 06dc truth = dump + paper_06dc + T6.
Whiskas official ledger locked — onchain counts only, no PHASE1 rewrite.
PMData L2 is a single Yes-token book. bid_sum is from the dump, not reconstructed.

slugs requested=10 onchain_ok=10 l2_ok=10

| wallet | n_fills | maker_share | size_p50 | join_best_yes | dump S1 n | dump pair p50 |
|---|---:|---:|---:|---:|---:|---:|
| mo-money | 403 | 0.526 | 10.14 | 0.324 | 7 | 0.582 |
| bosona | 426 | 0.444 | 11.11 | 0.318 | 6 | 0.573 |
| 06dc | 0 | — | — | — | — | — |
| whiskas | 162 | 0.481 | 15.89 | 0.135 | — | — |

Hottest 10 BTC/SOL 5m/15m slugs only. Full-tape mo/bosona maker_share is ~90% (dump fee-match). This sample is more competitive — do not override 90% with ~50%.
06dc n=0 here is expected: their books are daily/monthly/bracket, not PMData updown.

## Inferred vs yaml (no new alpha)

- pair_max **0.90** from dump S1 (not from PMData bid_sum)
- cancel_above **0.92** (unobserved in fills)
- paper_clip **10** (size gap vs their matched p50 on full tape)
- maker rest both; pair>1 trade=false
- join-best is intended; low join% on short align = calibrate, not kill S1

