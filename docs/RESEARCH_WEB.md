# RESEARCH_WEB

Phase 1 WEB only. Official docs > papers > blogs. Ranked by confidence. Date of retrieval: 2026-08-17.

| claim | evidence | source | date | confidence | supports_goal | contradicts |
| --- | --- | --- | --- | --- | --- | --- |
| Crypto taker fee is `C × 0.07 × p × (1−p)`; makers are never charged fees | Official fee formula and table: Crypto taker 0.07, maker 0 | https://docs.polymarket.com/trading/fees | 2026-08-17 (docs; retrieved) | 5 | partial | no |
| Crypto maker rebate pool is 20% of taker fees, fee-curve weighted, paid daily in pUSD, min $1 | `rebate = (your_fee_equivalent / total_fee_equivalent) * rebate_pool`; Crypto 20% | https://docs.polymarket.com/programs/maker-rebates | 2026-08-17 (docs; retrieved) | 5 | partial | yes — rebate is a share of others’ taker fees, not a 20%/day return on $5k |
| Complete sets are split/merge/redeem inventory ops, not a guaranteed daily PnL | Official MM page: split pUSD → complete set; merge → pUSD; redeem after resolve | https://docs.polymarket.com/market-makers/trading | 2026-08-17 (docs; retrieved) | 5 | partial | no |
| Official MM path is two-sided quotes, GTC/GTD, post-only, inventory skew, kill switch | Best-practice list: quote both sides, cancel stale, batch, realtime WS | https://docs.polymarket.com/market-makers/trading | 2026-08-17 (docs; retrieved) | 5 | partial | no |
| CLOB V2 is the production trading API; fees set at match time, collateral pUSD | V2 migration: fees operator-set; USDC.e → pUSD | https://docs.polymarket.com/v2-migration | 2026-08-17 (docs; retrieved) | 5 | no | no |
| Positions can be redeemed to pUSD after resolution via collateral adapter | `redeemPositions` on CtfCollateralAdapter | https://docs.polymarket.com/trading/positions/manage | 2026-08-17 (docs; retrieved) | 5 | no | no |
| Help center restates same fee/rebate tables (Sports rebate 20% there vs 15% on docs) | Help article tables vs docs tables differ on Sports rebate 20% vs 15% | https://help.polymarket.com/en/articles/13364471-maker-rebates-program vs https://docs.polymarket.com/trading/fees | 2026-08-17 | 3 | no | yes — Sports rebate % disagrees across official pages |
| Blog claim: one MM “$200/day → $700–800/day on $10k” | Unsourced case study; table also lists $50k for $500–1000/day | https://www.polytrackhq.app/blog/polymarket-market-making-guide | undated blog (retrieved 2026-08-17) | 1 | no | yes — even the anecdote uses $10k min, not $5k, and is not an official result |
| Blog claim: realistic MM capital floor $50k–$200k | “Below that, fixed costs and minimum quote sizes consume most of the edge” | https://www.polysyncer.com/blog/polymarket-market-making-bot | undated blog (retrieved 2026-08-17) | 2 | no | yes — $5k below stated floor |
| No official Polymarket page promises $1000/day on $5000 | Fee/rebate/MM docs describe mechanics only; no ROI guarantee | docs.polymarket.com fees + maker-rebates + market-makers/trading | 2026-08-17 | 5 | no | yes — $1000/day wish has no official support |
