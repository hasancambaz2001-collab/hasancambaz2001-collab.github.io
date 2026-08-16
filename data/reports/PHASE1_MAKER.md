# PHASE1_MAKER — role split + rebate

Generated: 2026-08-16 14:25 UTC  
Dump: 428,102 btc5 fills. Tag = `usdcSize − size×price`. `|embed| ≤ $0.02` → maker; `embed > $0.02` → taker (equals `C×0.07×p×(1−p)`).  
No bot. Tie-out not redone. `pair_max` decision recorded as **default 0.96 / cap 0.97 / never 0.98**.

## Role-split table

| | maker | taker | other (8 SELLs) |
|---|---:|---:|---:|
| fills | **190,324 (44.5%)** | 237,770 (55.5%) | 8 |
| shares | 3,242,507 | 9,097,917 | 40 |
| notional `size×price` | $1,637,051 | $4,373,827 | $17 |
| `usdcSize` | $1,637,081 | $4,507,734 | $16 |
| embedded fee | $30 | **$133,907** | −$0.67 |
| fee-correct pnl (`payout − usdc` by fill) | **+$44,303** | **+$32,653** | −$16 |
| same, price book (`payout − size×price`) | +$44,334 | +$166,559 | −$17 |
| t-in-window p25 / p50 / p75 | 80 / **158** / 240 s | 74 / **140** / 216 s | — |
| late (t>240s) | 24.8% | 17.9% | 0 |

Maker is the smaller book by size (26.7% of shares) but the larger **after-fee** profit (+$44.3k vs +$32.7k). Taker looks huge before fees (+$167k) and is eaten down to +$33k. That is the same $134k hole the tie-out already closed.

## Two pair_costs per window

A window can complete a set on taker fills only, maker fills only, or both. `pair_*` needs both legs in that role.

| | n both legs | p10 | p25 | **p50** | p75 | p90 |
|---|---:|---:|---:|---:|---:|---:|
| taker-only `size×price` | 14,504 | 0.848 | 0.915 | **0.969** | 1.015 | 1.069 |
| maker-only `size×price` | 11,100 | 0.820 | 0.910 | **0.990** | 1.070 | 1.172 |
| taker-only usdc (fee in) | 14,504 | 0.877 | 0.944 | 0.998 | 1.044 | 1.098 |
| maker-only usdc | 11,100 | 0.820 | 0.910 | 0.990 | 1.070 | 1.173 |
| mixed window usdc (PHASE1) | 15,235 | 0.893 | 0.951 | 0.996 | 1.038 | 1.089 |

Maker-only completes sit **to the right**. Taker-only median is already under 0.97 on the book.

### Histograms (`size×price` pair)

| bin | taker-only n | maker-only n |
|---|---:|---:|
| [0.80, 0.90) | 2,203 | 1,574 |
| [0.90, 0.94) | 2,121 | 1,178 |
| [0.94, 0.96) | 1,419 | 715 |
| [0.96, 0.97) | 837 | 391 |
| [0.97, 0.98) | 834 | 395 |
| [0.98, 1.00) | 1,659 | 785 |
| [1.00, 1.02) | 1,301 | 801 |
| [1.02, 1.10) | 2,437 | 2,221 |
| [1.10, 1.50] | 909 | **2,112** |

Maker-only: 5,134 / 11,100 (46%) have pair_px > 1.00. Taker-only: 4,647 / 14,504 (32%).

## Hypothesis

> pair<0.97 is mostly TAKER lifts; pair>1.00 is mostly MAKER bids.

Measured on the **mixed** window (PHASE1 usdc `pair_cost`) and share of usdc notional in that window:

| slice | n | mean taker share | median taker share | taker notional |
|---|---:|---:|---:|---:|
| pair_usdc < 0.97 | 5,159 | **73.2%** | 75.4% | 73.0% |
| 0.97 ≤ pair < 1.00 | 2,842 | 74.7% | — | — |
| pair_usdc > 1.00 | 7,233 | **73.1%** | 75.5% | 72.8% maker=**27.2%** |

| claim | verdict |
|---|---|
| pair<0.97 is mostly taker lifts | **ACCEPT** (73% taker notional, mean share 0.73) |
| pair>1.00 is mostly maker bids | **REJECT** (still 73% taker). Expensive windows are not a maker book. |

What *is* true: when they **complete both legs as maker**, that pair_cost is the fat right tail (p75=1.07, p90=1.17). The expensive *mixed* window is still mostly taker size plus a maker residual/hedge leg. Do not invert the product rule into “copy the bids.”

## Time-of-fill (t+s)

| t in window | maker % | taker % |
|---|---:|---:|
| 0–30s | 6.0 | 7.1 |
| 30–90s | 22.0 | 23.9 |
| 90–180s | 28.0 | 31.9 |
| 180–240s | 18.9 | 18.9 |
| 240–300s | **24.7** | 17.9 |

Makers arrive later and die later. Median +18s vs taker. Late rate 24.8% vs 17.9%. Compatible with resting bids that get hit into the close, not with a pure lift-the-ask open.

## Rebate (+$48,761 empty-slug)

Activity, not a 5m type:

| type | n payouts | USDC | clock |
|---|---:|---:|---|
| `MAKER_REBATE` | 62 | **$9,293.85** | daily ~00:45 UTC, 2026-06-13 → 08-16 |
| `TAKER_REBATE` | 61 | **$39,175.47** | daily ~00:10 UTC, 2026-06-20 → 08-16 |
| `REWARD` | 7 | **$292.01** | daily 00:00 UTC, 2026-08-08 → 08-16 |
| **sum** | 130 | **$48,761.33** | |

### Source

- **Maker $9,294** = [Maker Rebates Program](https://docs.polymarket.com/programs/maker-rebates), crypto **20%** of the fee-curve pool. Theoretical `0.20 × Σ C×0.07×p×(1−p)` on *our* maker fills = **$9,315.88**. Actual / theo = **99.8%**. They are paid as if they receive the full crypto maker share of their own fee-equivalent (the identity PolyScalping documents).
- **Taker $39,175** = [Taker Rebate Program](https://docs.polymarket.com/trading/taker-rebates). Profile is **Diamond (tier 5)**; Diamond headline is 44% of taker fees. 44% × $133,907 = $58,919. Actual is **29.2%** of taker fees — they were not Diamond for the whole dump (joined 2026-06-08; current gamma `weightedVolume` = $3.01M, under the $4M Diamond line, likely grace / mix of Gold–Platinum–Diamond days). Daily taker credits start 2026-06-20.
- **Reward $292** ≠ Diamond level-up ($7,500). Seven ~$40 midnight credits from Aug 8. Holding / yield style, not the maker book.

### ¢ / fill

| | |
|---|---:|
| maker rebate / 190,324 maker fills | **4.88 ¢/fill** |
| maker rebate / maker share | 0.287 ¢/share |
| maker rebate / maker notional | **5.68 bps** |
| taker rebate / 237,770 taker fills | **16.48 ¢/fill** |
| taker rebate / taker fees | 29.2% |

### PolyScalping maker-rebate leaderboard

`https://polyscalping.org/wallet/<proxy>` → 404. Search on `/leaderboard/maker` did not return this address in the public HTML we could fetch (no wallet API). Lifetime maker rebate **$9,294** is above their published top-1,000 threshold (~$2,934) **if** they index the wallet. We cannot print a rank. They are unambiguously **in** the official maker-rebate program (62 on-book daily credits matching the 20% crypto curve).

### Does rebate make pair>1.00 net-flat?

No.

| | USDC |
|---|---:|
| windows with usdc pair_cost > 1.00 | 7,233 |
| pair edge `matched × (1 − pair_cost)` | **−$111,905** |
| window fee0 (includes residual) | −$61,170 |
| maker rebate allocated by maker notional in those windows | **+$4,730** |
| pair edge + rebate | **−$107,175** |
| fee0 + rebate | −$56,441 |

4.88 ¢/fill cannot flatten a 7k-window set that is 3–4 ¢ over $1 on size. Residual, not rebate, is what keeps expensive windows from being a total wipe. Do not take pair>1 because “maker rebate will save it.”

## Product (still no bot)

- Default **ask_sum / pair_max = 0.96**, cap **0.97**, never **0.98**. Not 0.9513.
- Cheap slice is taker-heavy. Copy the **lift** when the book is cheap, not the full bid stack.
- Maker book is real (+$44k after fee, +$9.3k rebate) and later in the window. Separate gate if you ever quote. Not this PR.
