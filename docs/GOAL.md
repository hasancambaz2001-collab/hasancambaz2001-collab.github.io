# Goal

Owner (2026-08-17): set up a Polymarket strategy aimed at **~$1000/day** profit; consider every *lawful* path; **max capital $5000**.

`$1000/day` is the owner’s **wish**, not a promised lock. 20%/day on $5k is not claimed and must not be chased by breaking locks.

## Problem

Design (not deploy) a Polymarket complete-set path that can be verified under a **$5000** hard capital ceiling, and record whether a **$1000/day** run-rate is supported by evidence.

## Locks

- **Capital:** max capital / notional at risk **$5000**. Never size above this.
- **$1000/day is not a lock.** Do not raise clip, pair, or risk to chase it.
- **Lawful paths only.** “Her yol mübah” means every *legal* strategy family (maker complete-set, taker complete-set, sit-in-book, etc.). Forbidden: market manipulation, wash trading, spoofing, venue/contract exploits, stolen keys, unauthorized access, fraud, phishing.
- **No live deploy** unless a human types `deploy` after `make verify` PASS. This run does not deploy a sender.
- **No pair>1** (complete-set inventory blowup).
- If the existing S1 micro path in this repo is used: **clip 5**, **pair_max 0.90**, maker-only **join < ask**, still250/ws_age on first send, requote max 8 while cheap+maker. No clip up.

## Success metrics

- `make verify` **PASS**
- config/invariants: capital cap **5000**, `clip==5` when S1 path is present, `pair_gt1` false
- fixture contract if S1 fixtures exist: `0714` BLOCK, `0827` BLOCK, `0759` ALLOW
- counters observed only (not invented): `both_fill`, `one_leg_taker`, `would_be_taker_blocked`, `requote_n`
- A written verdict in RESEARCH/ARCH: whether **$1000/day on $5k** is supported, contradicted, or unknown — no guessing a yes

## Non-goals

- Guaranteed $1000/day
- Live orders / sender deploy from this run
- Illegal or venue-hostile edge
- Size ladder, multi-asset live
- Mo-money directional sleeve
- Raising clip or pair_max to lever $5000

## Verify commands

- `make verify`
- `python3 scripts/check_invariants.py` (if present)
- `python3 scripts/replay_fixtures.py 0714 0827 0759` (if present)
