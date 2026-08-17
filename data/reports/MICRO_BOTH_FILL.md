# How mo-money both-fills (and what we keep)

Generated: 2026-08-17 10:00 UTC
Clip 5. pair≤0.90. No pair>1. still250-false still SEND YOK.

## This does not undo the 07:59 set

Live contract stays exactly what already shipped (`03a6fad`):

1. **join ≥ ask → `would_be_taker_blocked`.** 07:14 (0.57=ask) and 08:27 (0.26>0.23) stay blocked. No taker one-leg.
2. **First send:** still250 + 1-tick spread each leg + depth≥5. 2 ticks would kill 07:59 (Down spread 0.01).
3. **bid_sum≤0.85 / ask far:** preference only, not a gate. Mo cheap p90 is already 0.84.
4. **Off-touch:** both unfilled and still pair≤0.90 + maker → cancel + best-bid rejoin, max 8/window. Not a force-fill.
5. **45s timeout only on one-leg.** Both-unfilled sit until window end / pair>0.92 / requote-max.
6. **Logs:** `would_be_taker_blocked`, `both_fill`, `one_leg_taker`, `off_touch`, `n_requote`.
7. **Replay:** 07:14 block, 08:27 block, 07:59 still sends.

We are **not** full mo-money. Stay on this path: fill both legs as maker, without loosening the rule.

## What they do differently (not a copy list)

Mo-money “sık iki bacak” is sit + size + time, not a looser filter.

| | mo-money cheap two-leg | our V2 live |
|---|---|---|
| pair p50 | **0.65** (p90 0.84) | rest at 0.82–0.90 |
| first Up vs first Down | **p50 107s** (1/111 same second) | we used to judge both in ~250ms |
| fill span p50 | **193s** | now: sit / requote in-window |
| min-leg size p50 | **60** | clip **5** |
| maker both legs | 88 / 111 cheap | 1 / 6 V2 sends before sit |

They look like every window both-fills because the **window** completes over minutes. Second leg is a later maker hit.

## Copy / do not copy

**Copy (already on):** maker-only join, 1-tick hole, still250 first entry, cheap off-touch requote, sit while pair≤0.90.

**Do not copy:**

- pair>1 hedge
- one-way 1500 Up skew
- taker on every spike
- clip jump 5→10→21 before both_fill repeats, and never without G5

## Realistic target

`both_fill / send`: 1/6 → maybe 2–3/10 with requote + maker-only.
Mo-money frequency needs their size + 24/7 queue; will not match 1:1.

One line: fill like mo-money = stay in queue without becoming taker (requote) + grow size later; not by loosening the rule.
