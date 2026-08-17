# Agent pipeline

Project-agnostic. RESEARCH → GATE → PLAN → BUILD → VERIFY.

Fill `docs/GOAL.md` before phase 1. Do not invent a product goal.

`make verify` PASS is required before calling the work done. It is not a deploy.

## How to run

```bash
make pipeline-init
# fill docs/GOAL.md
make verify
```

## Phases

### 0 — GOAL

Owner (or an agent that is only allowed to transcribe the owner’s words) fills `docs/GOAL.md`:

- problem
- locks
- success metrics
- non-goals
- verify commands

Do not start phase 1 on placeholders.

### 1 — three independent researches (parallel)

Each agent writes **one** file. No code. No other docs.

- **web:** Follow `.cursor/rules/phase1_web.mdc`. Read `docs/GOAL.md`. Research the public web. Write only `docs/RESEARCH_WEB.md`. No code.
- **x / social:** Follow `.cursor/rules/phase1_x.mdc`. Read `docs/GOAL.md`. Research X/social (primary posts + dates). Write only `docs/RESEARCH_X.md`. No code.
- **code / repo:** Follow `.cursor/rules/phase1_code.mdc`. Read `docs/GOAL.md`. Mine this repo (code, tests, logs, docs). Write only `docs/RESEARCH_CODE.md`. No code changes.

### 2 — merge gate (no code)

- Follow `.cursor/rules/phase2_merge.mdc`. Merge `RESEARCH_*` into `docs/RESEARCH.md`. No code. List contradictions explicitly. Do not resolve by guessing.

### 3 — plan ARCH (from RESEARCH only)

- Follow `.cursor/rules/phase3_plan.mdc`. Write `docs/ARCH.md` from `docs/RESEARCH.md` only. Steps, metrics, non-goals. No implementation.

### 4 — implement + adversarial critic

- **impl:** Follow `.cursor/rules/phase4_impl.mdc`. Implement only what `ARCH.md` says. List files changed + verify commands from `GOAL.md`.
- **critic:** Follow `.cursor/rules/phase4_critic.mdc`. Do NOT improve. Try to break GOAL locks and success metrics.

Impl must not ship if critic records a required fix.

### 5 — verify

```bash
make verify
```

Runs `scripts/verify.sh`. PASS required before “done”.

- If `verify.d/commands.sh` exists, that script is the check list.
- Else: `pytest` / `npm test` / `cargo test` / `go test` when those project files exist.

Add project-specific checks to `verify.d/commands.sh`. See `verify.d/README.md`.
