#!/usr/bin/env bash
# Option Riders — Trade Journal launcher
# First-time setup:
#   1. Copy .env.example to .env and fill in your IBKR_FLEX_TOKEN + IBKR_FLEX_QUERY_ID
#   2. Run `./run_journal.sh`
#   3. Open http://127.0.0.1:8125/journal.html and click Sync IBKR

set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "→ Created .env from .env.example"
    echo "→ Open .env in your editor, fill in IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID, then re-run this script."
    exit 0
  else
    echo "ERROR: no .env or .env.example found."
    exit 1
  fi
fi

if ! grep -q '^IBKR_FLEX_TOKEN=.\{10,\}' .env 2>/dev/null; then
  echo "→ .env exists but IBKR_FLEX_TOKEN is empty."
  echo "→ Open .env, paste your IBKR Flex Web Service token and Query ID, then re-run."
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed. Install Python 3.10+ and try again."
  exit 1
fi

PORT="${PORT:-8125}"
export PORT

echo "→ Starting trade journal on http://127.0.0.1:${PORT}/journal.html"
echo "→ Press Ctrl+C to stop."
python3 server.py
