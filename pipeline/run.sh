#!/bin/sh
# Scaffold only. Do not --run. Do not restart paper. No live.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

for arg in "$@"; do
  if [ "$arg" = "--run" ]; then
    echo "refusing --run (scaffold only)" >&2
    exit 2
  fi
done

for f in \
  configs/mobo.yaml \
  configs/06dc.yaml \
  configs/size.yaml \
  scripts/phase1_maker_mobo.py \
  scripts/t6_daily_06dc.py \
  scripts/phase1_06dc_maker.py \
  scripts/size_gate.py \
  scripts/replay_mobo.py \
  scripts/kasa_attribution.py \
  scripts/size_schedule.py \
  scripts/replay_full.py \
  configs/mobo_full.yaml \
  configs/size_schedule.yaml \
  pipeline/FULL_KASA.md \
  pipeline/TWIN_L2.md \
  configs/l2.yaml \
  scripts/l2_recorder.py \
  scripts/twin_l2.py \
  whiskas/l2.py \
  pipeline/patches/BID_BUCKET.md
do
  if [ ! -f "$f" ]; then
    echo "missing $f" >&2
    exit 2
  fi
done

echo "SCAFFOLD READY"
