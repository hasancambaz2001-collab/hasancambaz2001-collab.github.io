# ARCH

Decisions only from `docs/RESEARCH.md` + `docs/GOAL.md` locks. No implementation in this file.

## Source rule

- Allowed: RESEARCH accepted claims + GOAL locks
- Forbidden: inventing a $1000/day bot, widening clip/pair/capital, live deploy

## Verdict (from RESEARCH)

`$1000/day` on `$5000` under current locks is **contradicted**, not supported:

- Official docs describe fees/rebates/complete-set mechanics, not a 20%/day return.
- In-repo live sample: one-leg taker, ~$50 cash, loss, null 24h PnL.
- Clip 5 × pair_max 0.90 ⇒ max ~$0.50/window; 288 BTC 5m windows ⇒ ~$144 on a perfect day.
- No artifact deploys $5000 or prints $1000/day under these locks.

Do not resolve the Sports-rebate 15% vs 20% contradiction by guessing. Do not treat blog/YouTube ROI as true.

## Steps

1. Keep S1 first-send contract: 07:14 BLOCK, 08:27 BLOCK, 07:59 ALLOW.
2. Keep locks in config: clip **5**, pair_max **0.90**, pair_gt1 **false**, capital_max **5000**.
3. Extend invariants so `capital_max == 5000` (and not above).
4. Point `verify.d/commands.sh` at pytest + fixture replay + invariants (GOAL verify commands).
5. Write the $1000/day verdict into STATE (not a live sender).
6. **Do not** implement or start a live sender. **Do not** raise clip or pair to chase $1000/day. **Do not** add illegal/venue-hostile paths.

## Metrics

- `make verify` PASS
- clip==5, pair_gt1 false, capital_max==5000
- fixtures 0714/0827/0759
- counters remain observational placeholders until a human types `deploy`

## Non-goals

- Guaranteed $1000/day
- Live orders / sender deploy
- Illegal edge
- Size ladder, multi-asset live, mo-money directional sleeve
- Clip up / pair>1

## Decisions from RESEARCH

- Lawful path that matches tape + official MM docs: maker complete-set, join < ask, still250 on first send — already the S1 verify path.
- $1000/day is a wish; ARCH does not schedule work to “hit” it.
- Live deploy stays blocked.
