# paper_06dc

Wallet `0x06dc51826bc524d9a83770e7de9dd7e005b04524`. Clip **20**. No live. No pair>1 taker. R3 both-taker only if ask_sum≤0.96.
R1 tail / R4 favorite / R5 fade-wide / R6 maker bids. ATM without R6 = watch.
Second process. Not merged with 5m/15m/4h jsonl.

| kind | rows | taker_intend | maker_intend | R1 | R4 | R5 | R6 | atm_watch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| daily_ud | 12 | 0 | 8 | 0 | 0 | 0 | 8 | 7 |
| bracket | 66 | 48 | 12 | 18 | 8 | 22 | 12 | 12 |
| monthly | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **all** | 78 | 48 | 20 | 18 | 8 | 22 | 20 | 19 |

Window: 2026-08-16T17:04:24.360309+00:00 → 2026-08-16T17:05:11.551664+00:00

06dc measure-only. No live. No pair>1 taker. Separate from 5m jsonl.
Truth with dump + T6. l2_recorder does not cover daily/monthly.
