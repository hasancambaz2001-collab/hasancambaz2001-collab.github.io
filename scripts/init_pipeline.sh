#!/usr/bin/env bash
# Create missing pipeline docs/rules from templates.
# Never overwrites a non-empty docs/GOAL.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

created=0
skipped=0

write_if_missing() {
  local path="$1"
  if [[ -e "$path" ]]; then
    echo "skip $path (exists)"
    cat >/dev/null
    skipped=$((skipped + 1))
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  echo "created $path"
  created=$((created + 1))
}

# GOAL: create only if missing or empty. Never overwrite non-empty.
if [[ -s docs/GOAL.md ]]; then
  echo "skip docs/GOAL.md (non-empty)"
  skipped=$((skipped + 1))
else
  mkdir -p docs
  cat > docs/GOAL.md <<'EOF'
# Goal

Fill this file **before phase 1**. Later phases must not invent or widen it.

Replace placeholders. Do not invent a product if the owner has not set one.

## Problem

_TBD — one sentence._

## Locks

- _TBD — invariants later phases must not break_

## Success metrics

- _TBD — measurable pass/fail_

## Non-goals

- _TBD_

## Verify commands

- `make verify`
- _TBD — project-specific commands, if any_
EOF
  echo "created docs/GOAL.md"
  created=$((created + 1))
fi

write_if_missing docs/RESEARCH_WEB.md <<'EOF'
# RESEARCH_WEB

Phase 1 WEB only. No code. Official docs > papers > blogs. Max ~25 sources. Rank by confidence.

| claim | evidence | source | date | confidence | supports_goal | contradicts |
| --- | --- | --- | --- | --- | --- | --- |
EOF

write_if_missing docs/RESEARCH_X.md <<'EOF'
# RESEARCH_X

Phase 1 social/X only. No code. Primary posts + dates. Ignore hype without a mechanism.

| claim | evidence | source | date | confidence | supports_goal | contradicts |
| --- | --- | --- | --- | --- | --- | --- |
EOF

write_if_missing docs/RESEARCH_CODE.md <<'EOF'
# RESEARCH_CODE

Phase 1 repo/code/logs only. No code changes. Use existing code, tests, logs, and docs. Do not invent evidence.

| claim | evidence | source | date | confidence | supports_goal | contradicts |
| --- | --- | --- | --- | --- | --- | --- |
EOF

write_if_missing docs/RESEARCH.md <<'EOF'
# RESEARCH

Merge of `RESEARCH_WEB.md`, `RESEARCH_X.md`, `RESEARCH_CODE.md`. No code. Do not resolve contradictions by guessing.

## 1) Accepted claims (strong)

_None yet. Phase 2 fills this from RESEARCH_* rows with high confidence and no contradiction._

## 2) Contradictions

_None yet. List opposing claims side by side. Leave unresolved._

## 3) Weak/anecdotal

_None yet._

## 4) Open questions

_None yet._
EOF

write_if_missing docs/ARCH.md <<'EOF'
# ARCH

Decisions only from `docs/RESEARCH.md`. No code speculation. No implementation.

Until phase 2 writes accepted claims, this file holds structure only.

## Source rule

- Allowed: `docs/RESEARCH.md` accepted claims + `docs/GOAL.md` locks
- Forbidden: inventing behavior, widening GOAL, or “improvements”

## Steps

_None from RESEARCH yet._

## Metrics

_From GOAL / RESEARCH — none yet._

## Non-goals

_From GOAL / RESEARCH — none yet._

## Decisions from RESEARCH

_None yet._
EOF

write_if_missing docs/ROOM.md <<'EOF'
# ROOM

Append-only running decisions. Short entries. Do not rewrite history.
EOF

write_if_missing docs/STATE.md <<'EOF'
# STATE

Last known snapshot. Placeholders until something is observed.

| field | value |
| --- | --- |
| updated | _never_ |
| status | _TBD_ |
| note | _TBD_ |
EOF

write_if_missing docs/PIPELINE.md <<'EOF'
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
EOF

write_if_missing .cursor/rules/phase1_web.mdc <<'EOF'
---
description: Phase 1 WEB researcher — write only docs/RESEARCH_WEB.md
globs: docs/RESEARCH_WEB.md
alwaysApply: false
---

You are WEB researcher only. No code. Write only `docs/RESEARCH_WEB.md`.

Read `docs/GOAL.md` first. If GOAL is still placeholders, stop and say so. Do not invent a product goal.

Max ~25 high-quality sources. Official docs > papers > blogs. Rank by confidence.

Table columns exactly: claim | evidence | source | date | confidence | supports_goal | contradicts

No other files. No implementation.
EOF

write_if_missing .cursor/rules/phase1_x.mdc <<'EOF'
---
description: Phase 1 social/X researcher — write only docs/RESEARCH_X.md
globs: docs/RESEARCH_X.md
alwaysApply: false
---

You are social/X researcher only. No code. Write only `docs/RESEARCH_X.md`.

Read `docs/GOAL.md` first. If GOAL is still placeholders, stop and say so. Do not invent a product goal.

Primary posts + dates. Ignore pure hype without a mechanism.

Table columns exactly: claim | evidence | source | date | confidence | supports_goal | contradicts

No other files. No implementation.
EOF

write_if_missing .cursor/rules/phase1_code.mdc <<'EOF'
---
description: Phase 1 repo/code/logs researcher — write only docs/RESEARCH_CODE.md
globs: docs/RESEARCH_CODE.md
alwaysApply: false
---

You are repo/code/logs researcher only. No code changes. Write only `docs/RESEARCH_CODE.md`.

Read `docs/GOAL.md` first. If GOAL is still placeholders, stop and say so. Do not invent a product goal.

Use existing code, tests, logs, docs, and fixtures in this repo. Quote paths. Do not invent evidence.

Table columns exactly: claim | evidence | source | date | confidence | supports_goal | contradicts

No other files. No implementation.
EOF

write_if_missing .cursor/rules/phase2_merge.mdc <<'EOF'
---
description: Phase 2 merge RESEARCH_* into docs/RESEARCH.md
globs: docs/RESEARCH.md
alwaysApply: false
---

Merge `docs/RESEARCH_WEB.md`, `docs/RESEARCH_X.md`, and `docs/RESEARCH_CODE.md` into `docs/RESEARCH.md`. No code.

Required sections:

1) Accepted claims (strong)
2) Contradictions
3) Weak/anecdotal
4) Open questions

Surface contradictions explicitly. Do not resolve by guessing.

No implementation. No other files except `docs/RESEARCH.md`.
EOF

write_if_missing .cursor/rules/phase3_plan.mdc <<'EOF'
---
description: Phase 3 write ARCH.md from RESEARCH.md only
globs: docs/ARCH.md
alwaysApply: false
---

Write `docs/ARCH.md` from `docs/RESEARCH.md` only. Steps, metrics, non-goals. No implementation.

Decisions only from RESEARCH. No code speculation. Do not invent behavior.

Honor `docs/GOAL.md` locks. Do not widen GOAL.

No other files except `docs/ARCH.md`.
EOF

write_if_missing .cursor/rules/phase4_impl.mdc <<'EOF'
---
description: Phase 4 implement only what ARCH.md says
alwaysApply: false
---

Implement only what `docs/ARCH.md` says.

Honor `docs/GOAL.md` locks. Do not widen GOAL.

Output: files changed + verify commands from `docs/GOAL.md` (and `make verify`).

If ARCH has no RESEARCH decisions, change nothing.

Do not declare the work done until `scripts/verify.sh` (or `make verify`) is PASS.
EOF

write_if_missing .cursor/rules/phase4_critic.mdc <<'EOF'
---
description: Phase 4 critic — break GOAL locks, do not improve
alwaysApply: false
---

Do NOT improve. Try to break `docs/GOAL.md` locks and success metrics.

Write findings as:

| claim | evidence | severity | required fix |
| --- | --- | --- | --- |

No drive-by refactors. No widening GOAL. No “while we’re here”.
EOF

echo "init_pipeline created=${created} skipped=${skipped}"
