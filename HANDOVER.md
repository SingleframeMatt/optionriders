# Option Riders BTC Trading Bot — Handover

## Repo
- **GitHub:** `https://github.com/SingleframeMatt/optionriders.git` (branch: `main`)
- **Local path (Windows):** `C:\Users\matth\OneDrive\Documents\Claude\Projects\TradingBot\optionriders`

## Python
- **Installed at:** `C:\Users\matth\AppData\Local\Programs\Python\Python312\python.exe`
- **NOT on system PATH** — must use full path or set `$env:Path` per session
- **Deps installed:** `python-binance`, `pandas`, `yfinance`, `requests` (user site-packages)

## How to Start
```powershell
cd "$env:USERPROFILE\OneDrive\Documents\Claude\Projects\TradingBot\optionriders"
& "C:\Users\matth\AppData\Local\Programs\Python\Python312\python.exe" server.py
```
Dashboard: `http://127.0.0.1:8125/bot.html`
Landing page: `http://127.0.0.1:8125/`
Main dashboard: `http://127.0.0.1:8125/index.html`

## Key Files

### server.py
Python HTTP server on `0.0.0.0:8125`. Serves static files plus API endpoints:
- `GET /api/bot-status` — returns full bot state as JSON
- `POST /api/bot-control` — accepts `{"action":"start"}` or `{"action":"stop"}`
- `GET /api/options-flow`, `/api/market-data`, `/api/top-watch`, `/api/alpha-vantage` — existing dashboard endpoints
- Imports `bot` singleton from `bot_core.py`

### bot_core.py
BTC/USDT trading bot engine running as a background daemon thread.

**Strategy:** PDH/PDL/PWH/PWL level retest + rejection wick confirmation + VWAP filter + 9 EMA exit, on 3-minute candles.

**Settings (top of file):**
- `SYMBOL = "BTCUSDT"`, `TIMEFRAME = "3m"`
- `RISK_PCT = 0.02` (2% of balance per trade)
- `RR_RATIO = 2.0` (2:1 reward-to-risk)
- `EMA_PERIOD = 9`, `LEVEL_TOLERANCE_PCT = 0.001`
- `REJECTION_WICK_RATIO = 1.5`
- `TIME_STOP_MINUTES = 25`, `POLL_SECONDS = 15`
- `PAPER_STARTING_BAL` — read from env `BOT_STARTING_BALANCE`, default 10000

**Entry logic (`_check_entry`):**
- Price touches a key level (PDH/PDL/PWH/PWL) within tolerance
- Rejection wick confirms (wick >= 1.5x body)
- Close is on the right side of VWAP (above for long, below for short)

**Exit logic (`_check_exit`):**
- Stop loss hit
- EMA cross (close crosses 9 EMA against trade direction)
- Take profit hit
- Time stop (25 min)

**Balance & P&L tracking:**
- `_refresh_balance(client, closed_pnl=None)` — tries Binance `get_asset_balance("USDT")` first; if testnet returns nothing, falls back to paper tracking
- `_record_pnl(pnl, position, exit_price, reason)` — updates cumulative stats (total P&L, wins, losses, best/worst trade, trade history)
- Position sizing uses tracked balance (paper or live), not a fresh Binance call

**State dict returned by `get_state()`:**
```json
{
  "status": "stopped|scanning|in_trade|error",
  "position": null | {direction, entry, stop_level, take_profit, qty, level_name, entry_time},
  "levels": {PDH, PDL, PWH, PWL},
  "vwap": float,
  "ema": float,
  "last_price": float,
  "last_candle_time": "HH:MM UTC",
  "trade_log": [{time, msg, kind}],
  "started_at": ISO string,
  "error": string|null,
  "testnet": bool,
  "pnl": {
    "total": float,
    "wins": int,
    "losses": int,
    "total_trades": int,
    "best_trade": float,
    "worst_trade": float,
    "history": [{direction, entry, exit, pnl, reason, level, time}],
    "starting_bal": float,
    "current_bal": float,
    "bal_pct_change": float,
    "mode": "paper|live"
  }
}
```

### bot.html
Visual dashboard integrated into the Option Riders site. Polls `/api/bot-status` every 10 seconds. Sections:
1. Header with status pill + Start/Stop button
2. Testnet banner (shown when testnet=true)
3. Metric cards: BTC Price, VWAP, 9 EMA, Last Candle
4. Key Levels grid: PDH, PDL, PWH, PWL
5. Active Trade card (direction, entry, SL, TP, level, entry time)
6. Session P&L card (starting balance, current balance, total P&L, balance change %, trades, W/L, win rate, best/worst trade, trade history table)
7. Signal & Trade Log

### .env (gitignored)
```
BINANCE_API_KEY=WCcByyWQVO3crZumvIgzu0Uy9sbzN6hTd8r1RMdIOM2HB5vraC8NVU1cpgJYk9sn
BINANCE_API_SECRET=NtwON4aSA3vJjPUT3tpkAwdB5Zxhx7mWOQNDwWQ5kBLfKsjucVEtc5yVGKok0VOi
BINANCE_TESTNET=true
BOT_STARTING_BALANCE=10000
```

## Current State & Known Issues

1. **Paper trading only** — The bot does NOT place real orders on Binance. It simulates entries/exits using real testnet price data and tracks paper P&L against a $10,000 starting budget.
2. **Testnet has no USDT** — `get_asset_balance("USDT")` returns nothing on Matthew's testnet account, so the bot auto-falls back to paper mode. This is handled gracefully.
3. **P&L resets on restart** — No persistence. When server.py restarts, all P&L, trade history, and balance tracking reset to zero.
4. **Server binds to 0.0.0.0** — Changed from original 127.0.0.1 during setup. Works fine on Windows.
5. **favicon.ico 404** — Browser requests it, file doesn't exist. Harmless.
6. **Local files are ahead of GitHub** — The balance tracking, P&L section, and paper trading fallback were added locally but NOT pushed to the repo yet.

## Possible Next Steps
- Add real order execution on Binance testnet (`client.create_order()`)
- Persist P&L data across restarts (JSON file or SQLite)
- Push latest local changes to GitHub
- Add Python to Windows PATH permanently
- Add favicon
