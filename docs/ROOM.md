# ROOM

Append-only running decisions. Short entries. Do not rewrite history.

## 2026-08-17

- Pipeline scaffold: RESEARCH→GATE→PLAN→BUILD→VERIFY. No live deploy. Human must type deploy.
- Locks restated: clip 5, pair_max 0.90, no pair>1, maker-only join<ask, still250/ws_age on first send, requote max 8 while cheap+maker.
- Verify stubs encode known tape cases from project reports: 07:14 join=ask BLOCK, 08:27 cross ask BLOCK, 07:59 maker both ALLOW. Not a sender change.
- Pipeline generalized to project-agnostic templates. Fill `docs/GOAL.md` before phase 1. `make pipeline-init` never overwrites a non-empty GOAL. `make verify` runs `scripts/verify.sh`.
- Owner filled GOAL: Polymarket, wish ~$1000/day, capital cap $5000, lawful paths only. $1000/day is not a lock. No live deploy. No pair>1. Illegal edge forbidden.
