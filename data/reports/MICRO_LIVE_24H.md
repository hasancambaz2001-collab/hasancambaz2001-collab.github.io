# MICRO_LIVE_24H

Generated: 2026-08-16 19:59 UTC
BTC 5m only. clip 5. No pair>1 trade. No clip 10/67. No multi-asset live.
No Whiskas live. No 06dc live. No full LIVE_READY.
Layers unmixed: INTENT / still_there_250ms / REAL FILL.

| metric | value |
|---|---|
| n_rest_intent | 0 |
| still250_rate | null |
| real_fill_rate | null |
| n_partial | 0 |
| n_cancel | 0 |
| fee-estimated net PnL | null |
| hit max_daily_loss? | false |
| any pair>1 trade? | 0 |
| AUTH | l2_ready |
| sent | false |
| clip | 5 |

- paper_maker still250 logging (all books, diagnostic): true
- paper_maker still250_rate all books (not BTC-5m trial): 0.766292
- BTC 5m still250_rate is null when n_rest_intent=0 (book has been rich).
- real_fill is null unless an order_id was returned. Not invented.
- Live loop up (24h) with SIGNATURE_TYPE=3 + funder 0x881e. GTC only if bid_sum<=0.90 and depth>=5. BTC 5m currently rich (~0.99); no order_id yet.
- micro trial ≠ full live; next step only if real_fill>0 and loss cap OK
