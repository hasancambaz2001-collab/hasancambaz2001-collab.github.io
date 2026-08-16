#!/bin/bash
# Overnight paper: GET-only. No orders. Does not touch replay or clip.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/paper data/reports
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$START" > data/paper/overnight_start.txt
SECONDS_RUN="${PAPER_SECONDS:-57600}"
INTERVAL="${PAPER_INTERVAL:-5}"
echo "paper overnight start=${START} seconds=${SECONDS_RUN} interval=${INTERVAL} out=data/paper/intended.jsonl live=0" >&2
python3 scripts/paper_whiskas.py --seconds "$SECONDS_RUN" --interval "$INTERVAL" --out data/paper/intended.jsonl
python3 scripts/paper_whiskas.py --summary --since-file data/paper/overnight_start.txt --out data/paper/intended.jsonl
echo "paper overnight done $(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
