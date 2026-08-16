#!/bin/bash
# Multi-asset paper: GET-only. No orders. Does not touch replay or clip.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/paper
START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$START" > data/paper/overnight_start.txt
INTERVAL="${PAPER_INTERVAL:-5}"
echo "paper multi-asset start=${START} interval=${INTERVAL} assets=btc,eth,sol,xrp out=data/paper/intended.jsonl live=0 leave_up=1" >&2
# No --once, --seconds 0 → leave the loop up.
python3 scripts/paper_whiskas.py --interval "$INTERVAL" --out data/paper/intended.jsonl --assets btc,eth,sol,xrp
