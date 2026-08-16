# MICRO RTT cut + clocks

Generated: 2026-08-16 22:30 UTC
No clip up. No pair>1. still250 gate kept. No Rust.

## Live now

1. Clocks: `t_intent` / `intent_ts` at rest decision (not snapshot `ts`). Logged: `still_ms`, `sign_ms`, `post_ack_ms` (sign+HTTP), `lag_ms = ack - t_intent`. `clob_created_at` optional only. Primary lag is never CLOB seconds.
2. Token cache across loops (`cached_discover_tokens`). Parallel book GET before decision and inside still250 (`fetch_books_parallel`).
3. Unchanged: still250 false or bid_sum_250>0.90 → SEND YOK. One `post_orders`. Adverse before rich_cancel. Clip 5.

## Old-6 CLOB-second lag (biased)

| window | lag_ms (created_at − jsonl ts) |
|---|---|
| A/B/C six orders | 1520–1852 |

That number includes early `ts`, double still250 (old), serial posts, and **1s CLOB bucket**. Do not use it to prove &lt;500ms.

## After this patch

Next jsonl intents (blocked or sent) must carry `t_intent`, `still_ms`. Sent rows also `sign_ms`, `post_ack_ms`, `lag_ms`.
First still250-true SEND: report `still_ms`, `post_ack_ms`, `lag_ms`, `both_fill`/`one_leg`, `residual`, `adverse_action`.

Rust: only if `post_ack_ms` median stays &gt;500 after cache+parallel books. Not now.
