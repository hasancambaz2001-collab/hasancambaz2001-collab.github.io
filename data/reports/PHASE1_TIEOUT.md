# PHASE1_TIEOUT — ledger lock

Generated: 2026-08-16 14:05 UTC  
Wallet: [@x-moneyforwhiskas](https://polymarket.com/@x-moneyforwhiskas) / `0x3048d65321be3497164cdfc2996f94f98a2e7537`  
Dump: 444,044 activity / 30,985 closed / 16,072 windows. Real dump, not a sketch.  
**No bot. No paper. No live. `pair_max=0.9513` is not a product rule.**

## Gate

`|reconstructed_fee0 − official| < $15,000`

| book | USDC |
|---|---:|
| Official ALL (`/v1/leaderboard timePeriod=ALL` and `lb-api/profit?window=all`) | **+211,013.58** |
| Reconstructed fee0 = Σ (winner shares − size×price) | **+210,876.56** |
| **\|diff\|** | **137.02** |

**GREEN.** $137 is 0.065% of the official number. The $133k hole was the fee register, not missing windows.

Do not retune from `PHASE1.md` `total_pnl=−$103,515`. That line subtracted the crypto taker curve **again** on top of `usdcSize` (which already has taker fees) and treated every BUY as a taker.

## What official +$210k actually is

Three different books were being compared as if they were one:

| book | amount | what it is |
|---|---:|---|
| Official leaderboard ALL | +211,013.58 | Gross trade PnL: mark winner shares at $1, cost at **CLOB price** (`size×price`). Fees not subtracted. Rebates not added. |
| Window “fee0” in PHASE1 | +76,971.96 | `payout − usdcSize`. **After taker fees.** Maker fills have `usdc≈size×price`, so they are already fee=0 here. |
| Closed-positions Σ `realizedPnl` | +82,809.33 | After-fee, 4-decimal `avgPrice`. Omits 320 unredeemed loser windows. |
| Activity cash `REDEEM+SELL+rebates+reward−BUY` | +127,018.38 | Bankroll movement, including $48,761 of account-level rebate/reward rows. |

User check 1 said closed `realizedPnl` must ≈ +$210k. **It does not.** Polymarket’s own closed-position cards sum to **+$82,809**, not +$211k. The leaderboard is a different formula (price notional, no fee).

## Dollar bridge (the $133k)

```
payout − usdcSize                         +76,971.96     PHASE1 "fee0"
+ taker fees already inside usdcSize     +133,904.60     usdc − size×price
= payout − size×price                    +210,876.56     reconstructed fee0
official ALL                             +211,013.58
leftover                                 +137.02
```

On 237,770 taker BUY fills, `usdcSize − size×price` equals the official curve `C × 0.07 × p × (1−p)` to the cent (embed $133,906.88 vs formula $133,907.50, error −$0.61).

On 190,324 BUY fills (44.5%), `|usdc − size×price| ≤ $0.02`. Those are **maker / bid fills**. BUY ≠ taker.

PHASE1 then applied the same curve to **every** BUY ($180,487). The extra $46,580 is fake taker fee on maker fills. That is how “fee=0 +$77k / fee’li −$104k” was manufactured. Flat 1.5% was never used; the curve was right and the universe was wrong.

## Leftover $137 (every dollar we can name)

This is **not** the $133k hole. Bound:

| candidate | $ | keep / drop |
|---|---:|---|
| Post-dump fills after 13:36 UTC (live 5m windows) | — | Drop. Official pnl is still exactly `211013.5806407136` after those fills; leaderboard did not move. |
| Non-`btc-updown-5m` closed PnL (NHL + 1h BTC) | −5.38 | If official includes them, leftover grows to ~$142. Negligible. |
| 320 unredeemed loser windows still in `/positions` | −4,311.94 usdc / −4,189.91 price | Already inside reconstructed fee0 (payout=0, cost counted). |
| 55 windows where `REDEEM ≠ q_winner` (net +$1,132.69) | +1,132.69 | Drop as an add-on. Official tracks position size (our `q`), not redeem cash. Adding redeem overshoots official by ~$996. |
| Official volume − Σ TRADE `size` | 3,631 shares | Plausible home of the $137. Leaderboard volume is $12,349,105 vs dump Σsize $12,345,474. Missing notional at 5m prices is a few thousand dollars; $137 PnL on that dust is in range. Pagination / index lag, not a second strategy. |
| Closed API 4-decimal `avgPrice` vs full-precision fills | identity error $417 across 9,733 rows | Explains closed vs window cents, not the official $211k. |

**$133,904.60 is fully allocated to embedded taker fees. $137.02 is dump-vs-leaderboard share dust (< $15k gate). No second $133k machine.**

## 1. Closed-positions realized PnL

| | n | Σ realizedPnl |
|---|---:|---:|
| All closed | 30,985 | +82,809.33 |
| `btc-updown-5m-*` | 30,983 | +82,814.71 |
| Other | 2 | −5.38 |

Identity `Σ (curPrice−avgPrice)×totalBought` = +83,226.78 (API rounding vs stored `realizedPnl`).

320 windows sit in our parquet and in `/positions` (redeemable losers) but **not** in closed-positions. Their usdc fee0 is **−$4,311.94** (payout 0). That is why closed (+$82.8k) is higher than window usdc fee0 (+$77.0k) by about $5.8k, together with 4-dp avg rounding on the 15,752 overlapping slugs (+$1,530.80).

Closed cards match **after-fee** window PnL, not the leaderboard.

## 2. Activity cash: REDEEM − BUY (SELL≈0)

| type | n | USDC |
|---|---:|---:|
| TRADE BUY | 428,097 | 6,144,824.94 |
| TRADE SELL | 9 | 17.96 |
| REDEEM | 15,808 | 6,223,064.03 |
| MAKER_REBATE | 62 | 9,293.85 |
| TAKER_REBATE | 61 | 39,175.47 |
| REWARD | 7 | 292.01 |
| MERGE / SPLIT / CONVERSION | 0 | 0 |

- `REDEEM − BUY` (all) = **+$78,239.09**
- btc5 `REDEEM − BUY` = **+$78,248.89**
- Full cash flow (redeem+sell+rebates+reward−buy) = **+$127,018.38**

SELL is ~$18. Eight btc5 sells + one NHL sell. Not a sell-the-set book.

Rebate/reward rows have **empty slugs** (130 rows). They are account-level Diamond credits, not per-window. They are real cash (+$48,761) and they are **not** in official +$211k. Do not copy them as a window rule.

## 3. Diff vs window totals

| | amount |
|---|---:|
| Window usdc fee0 | +76,971.96 |
| Activity btc5 REDEEM−BUY | +78,248.89 |
| Diff | +1,276.93 |
| Window price fee0 | +210,876.56 |
| Official | +211,013.58 |
| Diff | +137.02 |

The $1,277 usdc gap is the 55 redeem≠q windows plus the 320 unredeemed losers (cost in, redeem 0). Histogram is fine. The PHASE1 **formula** was wrong: cost = `usdcSize` is after-fee; subtracting `taker_fee_usdc` again is double-count; applying it to maker BUYs is fiction.

## 4. Twenty random windows vs profile UI

Sample: `sorted(slugs)` then `Random(210).sample(20)` from slugs in both windows and closed-positions.  
UI column = Data API `/closed-positions` for that event — the same ledger the profile **Closed** tab renders. Event page: `https://polymarket.com/event/btc-updown-5m-<t0>`.

`window_pnl` here is usdc fee0 (`payout − usdcSize`), which is what the Closed card’s `realizedPnl` is.

| slug | win | shares up/down | avg up/down | pair | redeem u/d | our pnl | UI shares | UI rp | Δ |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1781314200 | Down | 12.60 / 10.00 | 0.6065 / 0.3733 | 0.9798 | 0 / 10.00 | −1.38 | 12.60 / 10.00 | −1.38 | +0.00 |
| 1781548200 | Up | 22.00 / 25.00 | 0.3293 / 0.4439 | 0.7732 | 22.00 / 0 | +3.66 | 22.00 / 25.00 | +3.66 | +0.00 |
| 1781657400 | Down | 0 / 10.00 | — / 0.8494 | — | 0 / 10.00 | +1.51 | 0 / 10.00 | +1.51 | −0.00 |
| 1782095100 | Up | 207.84 / 115.56 | 0.6006 / 0.5064 | 1.1070 | 207.84 / 0 | +24.49 | 207.84 / 115.56 | +24.49 | +0.00 |
| 1782226500 | Down | 324.82 / 391.96 | 0.4584 / 0.4705 | 0.9288 | 0 / 391.96 | +58.67 | 324.82 / 391.96 | +58.67 | +0.00 |
| 1782406500 | Up | 332.80 / 427.70 | 0.5704 / 0.4110 | 0.9814 | 332.80 / 0 | −32.79 | 332.80 / 427.70 | −32.79 | +0.00 |
| 1782720600 | Down | 361.40 / 353.56 | 0.4436 / 0.5599 | 1.0035 | 0 / 353.56 | −4.71 | 361.40 / 353.56 | −4.71 | +0.00 |
| 1783038600 | Down | 355.65 / 287.02 | 0.3771 / 0.4561 | 0.8332 | 0 / 287.02 | +22.00 | 355.65 / 287.02 | +22.00 | +0.00 |
| 1783539900 | Down | 60.65 / 66.00 | 0.2916 / 0.7587 | 1.0502 | 0 / 66.00 | −1.76 | 60.65 / 66.00 | −1.76 | +0.00 |
| 1783649100 | Down | 60.00 / 120.00 | 0.1955 / 0.7071 | 0.9026 | 0 / 120.00 | +23.42 | 60.00 / 120.00 | +23.42 | +0.00 |
| 1784369700 | Down | 90.00 / 144.39 | 0.4168 / 0.5662 | 0.9830 | 0 / 144.39 | +25.13 | 90.00 / 144.39 | +25.13 | +0.00 |
| 1784823300 | Down | 423.52 / 509.79 | 0.4347 / 0.4983 | 0.9330 | 0 / 509.79 | +71.68 | 423.52 / 509.79 | +71.68 | +0.00 |
| 1784954700 | Up | 372.46 / 395.26 | 0.6306 / 0.3658 | 0.9964 | 372.46 / 0 | −6.98 | 372.46 / 395.26 | −6.98 | +0.00 |
| 1785066900 | Down | 136.38 / 124.19 | 0.2272 / 0.7518 | 0.9790 | 0 / 124.19 | −0.16 | 136.38 / 124.19 | −0.16 | +0.00 |
| 1785078300 | Down | 389.41 / 563.75 | 0.3699 / 0.4549 | 0.8247 | 0 / 563.75 | +163.29 | 389.41 / 563.75 | +163.30 | +0.00 |
| 1785124200 | Down | 460.21 / 646.10 | 0.3740 / 0.6093 | 0.9833 | 0 / 646.10 | +80.30 | 460.21 / 646.10 | +80.31 | +0.01 |
| 1785600000 | Down | 234.63 / 147.86 | 0.2496 / 0.8638 | 1.1133 | 0 / 147.86 | −38.41 | 234.63 / 147.86 | −38.41 | +0.00 |
| 1786397700 | Down | 170.00 / 139.72 | 0.5409 / 0.4656 | 1.0065 | 0 / 139.72 | −17.28 | 170.00 / 139.72 | −17.28 | +0.00 |
| 1786700400 | Down | 912.26 / 833.80 | 0.4052 / 0.7076 | 1.1128 | 0 / 833.80 | −125.84 | 912.26 / 833.80 | −125.83 | +0.01 |
| 1786760400 | Up | 305.29 / 456.03 | 0.7338 / 0.1452 | 0.8790 | 305.29 / 0 | +15.06 | 305.29 / 456.03 | +15.06 | +0.00 |

20/20 match to the cent (largest Δ = $0.01; UI `avgPrice` is 4 decimals). Sample includes cheap pairs (0.77–0.83), expensive completes (>1.10), a one-leg residual (`1781657400`), and a fat residual winner (`1785078300` +$163). The reconstruction is the profile book.

## 5. Fee model

- Formula used: **`fee = C × 0.07 × p × (1−p)`**, 5-decimal, [official crypto curve](https://docs.polymarket.com/trading/fees). 100 sh @ 0.50 → $1.75. **Not** flat 1.5% (that would be $0.75 on the same fill).
- Activity has no maker/taker flag. Classification is `usdcSize` vs `size×price`.
- **Not all fills are taker.** 190,324 / 428,102 fills (44.5%) are maker. Bid fill = maker. Diamond `takerTier=5` does not change the 0.07 curve on the take; it shows up later as lump `TAKER_REBATE` / `MAKER_REBATE` rows ($48,469) with empty slugs.
- 8 SELL rows are not the maker story. Maker is on the BUY side.

## 6. Non-`btc-updown-5m` rows in the 444k

135 rows are not 5m BTC:

| what | n | note |
|---|---:|---|
| Empty-slug `MAKER_REBATE` | 62 | +$9,293.85 |
| Empty-slug `TAKER_REBATE` | 61 | +$39,175.47 |
| Empty-slug `REWARD` | 7 | +$292.01 |
| `nhl-car-las-2026-06-09` | 2 trades | Buy 2.86 @ 0.70, sell 2.85 @ 0.70; closed rp −$0.03 |
| `bitcoin-up-or-down-june-12-2026-8am-et` | 2 | 5,000 Up @ 0.001; closed rp −$5.35 |
| `bitcoin-up-or-down-june-10-2026-12am-et` | 1 | 5 Up @ 0.47, still in `/positions`, dead |

No hidden sports book. No 15m book. Rebates are cash, not a 5m window type.

## T1–T5 reread (do not say “fail” and stop)

PHASE1 marked T1/T2 FAIL against the **full** book and an arbitrary 55% residual bar. That is the wrong read.

| test | PHASE1 call | Correct read |
|---|---|---|
| T1 full book | FAIL | Correct as “do not copy the full book.” Median **usdc** pair_cost 0.996: they often finish expensive sets. The cheap slice is a different machine. |
| T1 Layer A `pair_cost < 0.97` | buried in a footnote | 5,159 windows (33.9% of paired). After **real** taker fees (usdc book): **+$117,574** ($22.79/window). The +$75,522 line in PHASE1 is `pair_pnl` after **double-counted** taker fees — same slice, broken register. |
| T2 residual WR 54.0% | FAIL vs 55% | 55% was arbitrary. n≈15,723, 54% is ~10σ above 50%. Residual is weak and real. On the broken taker book it still printed +$30k. |
| T3 late | PASS +$13,227 | Exists. Not the spine. |
| T4 BUY / 8 SELL | PASS | Holds. |
| T5 clip ~21 | PASS | Holds. |

Mix, after the register is honest (still not a bot spec):

- ~34% of paired windows: usdc `pair_cost < 0.97`. Fee-eaten and still **+$117.6k**. Copyable *rule shape* (ask_sum cap), not a full-book clone.
- ~50%+ : pair ≥ 0.99 on the usdc book (p75=1.038). Set loses; the other leg is hedge / residual. Gabagool-shaped. Do not copy.
- Late cheap leg: small plus.

Pre-fee fill averages (`pair_px` = avg `size×price` on each leg) sit lower: p25=0.930, **p50=0.974**, p75=1.017. Median set is cheap on the CLOB and expensive after taker fees. That is why p25=0.9513 on the usdc book is cargo-cult — it is a fee-inclusive quantile, not an ask_sum.

## pair_max table (0.94–0.98)

Filter = historical **usdc** `pair_cost` (fee already inside the average). `fee'd pnl` = usdc fee0 = payout − `usdcSize` = after actual taker fees, maker fee 0. This is the copyable economic book.

| pair_max | n | fee’d pnl | $/window | % of paired |
|---:|---:|---:|---:|---:|
| 0.94 | 3,198 | +83,774 | 26.20 | 21.0% |
| 0.95 | 3,719 | +93,700 | 25.19 | 24.4% |
| 0.96 | 4,388 | +105,370 | 24.01 | 28.8% |
| **0.97** | **5,159** | **+117,574** | **22.79** | **33.9%** |
| 0.98 | 6,056 | +123,568 | 20.40 | 39.8% |

Same thresholds on **price** pair_cost (closer to live `ask_sum`; looser because fees are not in the average):

| pair_max | n | fee’d pnl (usdc) | $/window | % of paired |
|---:|---:|---:|---:|---:|
| 0.94 | 4,523 | +107,481 | 23.76 | 29.7% |
| 0.95 | 5,324 | +118,223 | 22.21 | 34.9% |
| 0.96 | 6,218 | +126,494 | 20.34 | 40.8% |
| 0.97 | 7,191 | +133,107 | 18.51 | 47.2% |
| 0.98 | 8,182 | +136,789 | 16.72 | 53.7% |

`configs/whiskas.yaml` still has `pair_max: 0.9513` because that was p25 of the usdc book. **Do not treat it as live. Do not write a new number in from p25.** After this green tie-out the product rule is: trade only `ask_sum ≤` the cell you pick from the table (spec default 0.97), clip ~21, late as a **separate** gate. Never copy the full book.

Rough capacity math on **their** fills, usdc book, 0.97 cell: 288 windows/day × 33.9% × $22.79 ≈ $2.2k/day after real taker fees **if** every cheap Whiskas window were ours. That is their history, not our fill quality. The old $1.3k/day used $14.6/window from the double-counted pair_pnl line. Do not ship a bot on either number from this PR.

## What this closes / what it does not

Closed:

- Official +$211k ↔ reconstructed price fee0 within **$137**.
- Profile Closed tab ↔ per-window usdc fee0 (20/20 sample).
- $133k “missing” ↔ taker fees inside `usdcSize`.
- Fee curve confirmed; maker share measured (44.5%).
- Non-5m audit: 135 rows, no second market.

Not closed, and not this PR:

- No policy module. No replay. No paper. No live.
- No `pair_max` rewrite.
- Rebates (+$48.5k) stay unexplained as a *window* rule (empty slug). They are Diamond credits, not Layer A.
- Full-book residual / expensive completes stay off-limits.

If someone wants to retune: **do not.** The histogram was never the bug. The PnL formula was. Cost for official-style fee0 is `size×price`. Cost for economic after-fee is `usdcSize` (taker already in). Apply `0.07×p×(1−p)` only when `usdc > size×price + ε`.

## Reproduce

```bash
python3 scripts/tieout_pnl.py
```

Writes `data/processed/tieout_stats.json`. Needs the local dump (`data/raw/*.jsonl`, gitignored) and `data/processed/whiskas_*.parquet`.
