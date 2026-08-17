# Agent pipeline

RESEARCH → GATE → PLAN → BUILD → VERIFY.

No live trading from this pipeline. Do not deploy the sender. `make verify` PASS is not deploy. A human must type `deploy` explicitly.

## Phase order

1. Three **parallel** agents: phase1 web / x / code
2. One agent: phase2 merge
3. One agent: phase3 plan
4. Impl agent **and** critic agent
5. `make verify` — only then consider deploy (human types `deploy`)

## Phase 1 — research (parallel)

Each agent writes **one** file. No code. No other docs.

Paste these prompts as-is:

- **web:** Follow `.cursor/rules/phase1_web.mdc`. Research Polymarket S1 maker complete-set (`both_fill`↑, `one_leg_taker`≈0). Write only `docs/RESEARCH_WEB.md`. No code.
- **x:** Follow `.cursor/rules/phase1_x.mdc`. Research X/Twitter for Polymarket maker complete-set mechanisms (primary posts + dates). Write only `docs/RESEARCH_X.md`. No code.
- **code:** Follow `.cursor/rules/phase1_code.mdc`. Mine repo/tape for 07:14 block, 08:27 block, 07:59 allow, lag notes, mo-money ~107s. Write only `docs/RESEARCH_CODE.md`. No code changes.

If logs/dumps are missing on the current branch, inspect `origin/cursor/whiskas-phase1-4921` and `tests/fixtures/s1/`. Do not invent prices.

## Phase 2 — merge (gate)

- Prompt: Follow `.cursor/rules/phase2_merge.mdc`. Merge `RESEARCH_*` into `docs/RESEARCH.md`. No code. List contradictions explicitly. Do not resolve by guessing.

## Phase 3 — plan

- Prompt: Follow `.cursor/rules/phase3_plan.mdc`. Write `docs/ARCH.md` from `docs/RESEARCH.md` only. Steps, metrics, non-goals. No implementation.

## Phase 4 — build + critic

- **impl:** Follow `.cursor/rules/phase4_impl.mdc`. Implement only what `ARCH.md` says. clip 5 locks. Output files changed + how to verify.
- **critic:** Follow `.cursor/rules/phase4_critic.mdc`. Do NOT improve. Prove breaks S1: taker one-leg, pair>1, residual, still250 false send, join>=ask.

Impl must not ship if critic finds a required fix. Do not deploy the sender.

## Verify

```bash
make verify
```

Runs `scripts/verify_s1.sh`:

1. `pytest` if tests exist
2. `python3 scripts/replay_fixtures.py` for `0714`, `0827`, `0759`
3. `python3 scripts/check_invariants.py` — `clip==5`, `pair_gt1` false

Exit non-zero on fail. Prints `PASS` or `FAIL`.

## Deploy

Forbidden unless a human types `deploy` after verify PASS. This setup task does not deploy.
