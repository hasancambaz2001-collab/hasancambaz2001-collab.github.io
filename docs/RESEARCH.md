# RESEARCH

Merge of `RESEARCH_WEB.md`, `RESEARCH_X.md`, `RESEARCH_CODE.md`. No code. Contradictions left unresolved.

## 1) Accepted claims (strong)

- Official crypto taker fee is `C × 0.07 × p × (1−p)`; makers pay 0 fee. Source: docs.polymarket.com/trading/fees (conf 5).
- Official crypto maker rebate is 20% of taker fees, fee-curve weighted, daily pUSD, min $1. Source: docs.polymarket.com/programs/maker-rebates (conf 5).
- Official MM path: two-sided quotes, GTC/GTD, inventory split/merge/redeem, kill switch. Source: docs.polymarket.com/market-makers/trading (conf 5).
- No official Polymarket page promises $1000/day on $5000. Source: same official docs (conf 5).
- S1 tape contract: 07:14 join=ask BLOCK; 08:27 cross-ask BLOCK; 07:59 maker-both ALLOW. Source: fixtures + MICRO_BOTH_FILL.md (conf 5).
- mo-money cheap two-leg sit: first-leg gap p50 107s, fill span p50 193s, 88/111 maker both. Source: MICRO_BOTH_FILL.md (conf 5).
- Live micro sample: both_fill 0/3, Down taker one-leg all 3, cash ~$50.60, loss ~$3.38, lag 1.5–1.9s. Sources: MICRO_P0_P1, MICRO_ONE_LEG, MICRO_LAG (conf 5).
- 24h micro net_pnl and real_fill_rate are null. Source: MICRO_LIVE_24H (conf 5).
- LIVE_BLOCKED / G5 size_ok FAIL / trial clip 5 / max_daily_loss_usd 25. Source: LIVE_CONFIG + MICRO_LIVE_TRIAL.yaml (conf 5).
- `pair_gt_1_trade` false in processed artifacts (conf 5).
- X MCP was unauthenticated; no primary tweets retrieved (conf 5).
- Under clip 5 and pair_max 0.90, max edge per window is $0.50; 288 BTC 5m windows ⇒ ~$144 if every window both-fills at the cap. Source: GOAL locks + cadence arithmetic (conf 4).

## 2) Contradictions

- **$1000/day wish vs evidence:** official docs give no ROI; in-repo live PnL is null or negative; clip-5 arithmetic caps a perfect BTC-5m day near $144; no $5000-capital tape exists. Unresolved as a promise — evidence side is strong, wish is owner-only.
- **Sports maker rebate %:** help.polymarket.com lists 20%; docs.polymarket.com/trading/fees lists 15%. Unresolved.
- **Sit time:** mo-money p50 107s/193s vs this repo’s ~250ms both-leg judge / still250 first-send. Unresolved which window length is “correct”; both are in tape.
- **Replay scale:** their-size S1 $14110.75 (n=209) vs clip10 $797.60 on the same windows; clip5 row missing. Unresolved what clip-5 dollars would be.
- **Whale daily PnL:** PHASE1 shows +$1021.67 on 2026-07-01 and −$585.51 on 2026-08-16 (plus other large down days). A +$1k day exists at whale size; it is not clip-5 / $5k.
- **Blog/YouTube vs official+tape:** $200–800/day on $10k, $500–1000/day on $50k, $313→$414k lag-bot. No primary X posts; no wallets. Do not treat as true.

## 3) Weak/anecdotal

- PolyTrack “$200 → $700–800/day on $10k” (conf 1).
- Poly Syncer “$50k–$200k MM floor” (conf 2).
- PredictEngine “LiquidityKing” $50k → $500–1000/day (conf 1).
- YouTube $313 → $414k / 30 days latency story (conf 1).
- QuantVPS sum-to-one arb sketch (conf 2).

## 4) Open questions

- Maker-rebate dollars at clip 5 on BTC 5m: not measured in this repo.
- Authenticated X search for dated wallet-backed daily PnL.
- Clip-5 replay of the 209 S1 windows (row absent).
- Whether more *lawful* markets could raise the $144 arithmetic cap without breaking the multi-asset-live non-goal (out of scope until GOAL changes).
