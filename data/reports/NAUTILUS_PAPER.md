# NAUTILUS_PAPER

Generated: 2026-08-16 18:29 UTC
nautilus 1.231.0 core QuoteTick bus. No Polymarket execution client.
Historical L2 still PMData/recorder. live_orders=false · size_ok=false · g5_g6_unlocked=false
do not live without G5 G6

| source | n_ticks | n_quotes | n_rest | reasons |
|---|---:|---:|---:|---|
| record | 2000 | 3855 | 0 | {'rich_bid_sum': 1928, 'missing_bid': 72} |
| tape_bosona | 186 | 372 | 84 | {'rich_bid_sum': 76, 'thin_bid': 26, 'rest': 84} |

Paper bus only. Does not unlock G5/G6. Does not write LIVE_READY.
