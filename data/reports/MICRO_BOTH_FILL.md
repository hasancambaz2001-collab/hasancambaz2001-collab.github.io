# How mo-money both-fills (and what we change)

Generated: 2026-08-17 16:00 UTC
Clip 5. pair≤0.90. No pair>1. still250-false still SEND YOK.

## Mo-money is not magic — they sit

Their tape (`mobo_mo-money_activity.jsonl`): 111 two-leg windows with pair≤0.90.

| | mo-money cheap two-leg | our V2 live |
|---|---|---|
| pair p50 | **0.65** (p90 0.84) | rest at 0.82–0.90 |
| first Up vs first Down | **p50 107s** (1/111 same second) | we judge both in ~250ms |
| fill span p50 | **193s** | off_touch cancel or 45s flatten |
| min-leg size p50 | **60** | clip **5** |
| maker both legs | 88 / 111 cheap | 1 / 6 V2 sends |

They look like “every window both-fill” because the **window** completes over minutes. Second leg is a later maker hit, not a 250ms pair print.

## What actually raises both_fill

1. **Stay on the book while still cheap + maker.** Requote off-touch to the new best bid, max 8, only if bid_sum≤0.90 and join < ask and 1-tick spread. Do not cancel both at 250ms if the book is still a rest.
2. **45s timeout only when unpaired (one-leg).** Both-unfilled may sit until window end / rich / requote-max.
3. **Do not post a taker.** Live join ≥ live ask → `would_be_taker_blocked`. still250 is hole-stayed (sum+depth) only — do not post `bid_*_250`.
4. **First send: still250 + live 1-tick spread each leg + depth≥clip.** 2 ticks would have blocked 07:59 (Down spread 0.01). REST reread immediately before post.
5. **Prefer (not gate) bid_sum≤0.85 or asks far (≥0.05).** Mo p90 cheap pair is 0.84. Hard 0.85 would drop some 0.86–0.90 rests; leave as preference.
6. **Clip 5 stays.** Their size p50=60 helps queue, but the tape gap is **time-in-book**, not clip 67.

## Tape replay (this filter)

| window | book | blocked? | still send? |
|---|---|---|---|
| 07:14 | Down join 0.57 = ask 0.57 | **yes** `would_be_taker_blocked` | no |
| 08:27 | Up 0.26 > ask 0.23 | **yes** `would_be_taker_blocked` | no |
| 07:59 | 0.52/0.17 vs ask 0.84/0.18, bid_sum 0.69, depth 52 | no | **yes** |
| 12:07 | still250 WS 0.01/0.83; live Down 0.73 ≥ ask 0.64 | **yes** live taker gate | no |
| 12:20 | live REST 0.81 / 1-tick; WS 250 said 0.97 | **yes** (old `ws_age` gate) | REST still250 would send |

Logs: `would_be_taker_blocked`, `both_fill`, `one_leg_taker`, `off_touch`, `n_requote`.

## Event-driven sit (not a faster server)

First send: still250 hole + live pair≤0.90 + live join < live ask + 1 tick + clip 5. Join prices are live REST, not the 250ms WS snapshot.
Once resting, off-touch requote wakes on CLOB market WS book updates (`wait_change` / `bbo`), not only the 1s poll. Max 8 requotes/window. `requote_gap` (100ms) stays on the book — it does not flatten. pair>0.92 still exits. This is time-in-queue, not directional chase.

## Book source (2026-08-17 12:20 / 15:17)

- **still250 for send is REST + 250ms only.** WS `ws_age` / socket `bid_*_250` do **not** gate the first send. 12:20 live REST was 0.81 (1-tick) while WS 250 said 0.97 — that miss was a two-book bug, not a missing hole.
- **Join prices are REST live** (`join_source=live`). After the probe, REST 250 BBO is copied onto the join book so send-gate and join see the same venue.
- **WS is sit/requote only.** Subscribe the **current** BTC 5m Up+Down pair (2 tokens). Do not accumulate every window — that filled the send buffer (`slow consumer`) and made `ws_n_want` 46–68.
