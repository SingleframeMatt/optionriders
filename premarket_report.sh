#!/usr/bin/env bash
# Daily pre-market report — gap scanner + ADX trend hunter, written to output/.
# Run manually any time, or on a schedule via com.optionriders.premarket.plist.
#
# Output is plain text (no ANSI colour when redirected) at:
#   output/premarket_YYYY-MM-DD.txt
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output

PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

OUT="output/premarket_$(date +%F).txt"

{
  echo "OPTION RIDERS — PRE-MARKET REPORT   $(date '+%a %d %b %Y  %H:%M %Z')"
  echo "======================================================================"
  echo
  echo "Rules: ATM · scanned setup · <=GBP4k / GBP1k-risk · underlying stop · never add · flat 19:00"
  echo
  echo "###############  GAP SCAN — whitelist, penny-wide options  ###############"
  "$PY" premarket_scan.py --confluence --top 20 || echo "(gap scan failed)"
  echo
  echo "###############  TREND HUNT — broad, UPTRENDS (ADX-confirmed)  ###########"
  echo "# Your SNDK-style edge. Fresh trends = best R:R. Off-whitelist = check option spread."
  "$PY" premarket_scan.py --trend --all --side up --top 15 || echo "(trend up scan failed)"
  echo
  echo "###############  TREND HUNT — broad, DOWNTRENDS  #########################"
  "$PY" premarket_scan.py --trend --all --side down --top 10 || echo "(trend down scan failed)"
  echo
  echo "======================================================================"
  echo "No fresh trends + no clean gaps = chop day = sit out. That's a valid report."
} > "$OUT" 2>&1

echo "Wrote $OUT"
