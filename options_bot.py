#!/usr/bin/env python3
"""
options_bot.py — Supply & Demand Break+Retest options trading bot for Option Riders.

Connects to Interactive Brokers paper trading (port 7497) via ib_insync.
Watches SPY, QQQ plus a dynamic watchlist on 5-minute bars.
Buys ATM calls/puts on Supply & Demand break+retest signals with 2–5 DTE.

Risk rules:
    - $200 max per trade (1 contract if premium ≤ $2.00, otherwise skip)
    - Max 3 open positions at once
    - Daily loss limit $600 — bot halts for the day if hit
    - Stop loss:   50% of premium paid
    - Take profit: 50% of premium paid
    - Auto-close all positions at 3:45pm ET
    - New entries only 9:30am–3:45pm ET

Confluence requires 4 of 7 factors:
    1. BOS direction aligned (bullish BOS for longs, bearish for shorts)
    2. Price above VWAP (longs) or below VWAP (shorts)
    3. Within London (3am-12pm ET) or NY (9:30am-4pm ET) session killzone
    4. At a key level (PDH/PDL/PWH/PWL/ORB high/low/VWAP)
    5. HTF zone aligned (1h trend check matches direction)
    6. BOS or CHoCH structural point
    7. Confirmation close (green candle body closes above level for longs,
                          red candle body closes below level for shorts)

Dynamic watchlist:
    - SPY + QQQ scanned first (primary).
    - If no signal fires on primaries within the first hour of market open,
      expand to curated fallback (NVDA, AAPL, TSLA, META, AMZN, MSFT, AMD,
      GOOGL, NFLX, CRM) plus any dynamically discovered trending equities.
    - Each symbol is scored for trendiness (ADX-based) and must pass:
        relative volume > 1.5x, ATR > 1% of price, OI > 1000 on ATM strikes.
"""

import asyncio
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz
import requests

from ibkr_client import IBKRClient
from signals import (
    SignalStateMachine,
    compute_vwap,
    compute_rsi,
    compute_orb,
    compute_pdh_pdl,
    fetch_weekly_levels,
    in_rth,
)
from watchlist import (
    build_watchlist,
    get_active_scan_symbols,
    mark_active,
    PRIMARY_SYMBOLS,
    CURATED_FALLBACK,
)

# ── ib_insync (only needed for util.patchAsyncio) ─────────────────────────────
from ib_insync import util

# ── Logging setup (dated file + stdout) ───────────────────────────────────────
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

def _make_log_handler():
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_path  = _LOG_DIR / f"options_bot_{today_str}.log"
    return logging.FileHandler(log_path, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        _make_log_handler(),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("options_bot")

# ── Timezone ──────────────────────────────────────────────────────────────────
ET = pytz.timezone("America/New_York")

# ── .env loader ───────────────────────────────────────────────────────────────
def _load_dotenv(dotenv_path: str = ".env"):
    env_file = Path(__file__).parent / dotenv_path
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value

_load_dotenv()

# ── Config (from .env or hardcoded defaults) ──────────────────────────────────
IBKR_HOST      = os.environ.get("IBKR_HOST",      "127.0.0.1")
IBKR_PORT      = int(os.environ.get("IBKR_PORT",  "7497"))
IBKR_CLIENT_ID = int(os.environ.get("IBKR_CLIENT_ID", "2"))

# Accept both SYMBOLS and OPTIONS_SYMBOLS env vars; skip SPX (European-style)
_raw_syms = os.environ.get("OPTIONS_SYMBOLS", os.environ.get("SYMBOLS", "SPY,QQQ"))
SYMBOLS = [s.strip() for s in _raw_syms.split(",") if s.strip() and s.strip() != "SPX"]

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_OPTIONS",
                  os.environ.get("DISCORD_WEBHOOK_URL",
                  os.environ.get("DISCORD_WEBHOOK", "")))

# Risk parameters — spec env var names take priority, legacy names as fallback
MAX_TRADE_COST   = float(os.environ.get("OPTIONS_MAX_PER_TRADE",
                         os.environ.get("MAX_TRADE_COST",   "200")))
MAX_PREMIUM      = float(os.environ.get("MAX_PREMIUM",      "2.00"))   # per share; skip if > $2.00
MAX_POSITIONS    = int(os.environ.get("MAX_POSITIONS",      "2"))      # spec: max 2 open
DAILY_LOSS_LIMIT = float(os.environ.get("OPTIONS_DAILY_LOSS_LIMIT",
                         os.environ.get("DAILY_LOSS_LIMIT", "600")))
STOP_LOSS_PCT    = float(os.environ.get("STOP_LOSS_PCT",    "0.50"))   # 50% of premium
TAKE_PROFIT_PCT  = float(os.environ.get("TAKE_PROFIT_PCT",  "1.00"))   # 100% = 2R

MIN_DTE = int(os.environ.get("OPTIONS_DTE_MIN", os.environ.get("MIN_DTE", "2")))
MAX_DTE = int(os.environ.get("OPTIONS_DTE_MAX", os.environ.get("MAX_DTE", "5")))

SESSION_START  = (9, 30)     # ET — new entries
SESSION_END    = (15, 45)    # ET — last entry time
EOD_CLOSE_TIME = (15, 45)    # ET — force-close all positions
BAR_DURATION   = "2 D"       # IBKR historical data duration
BAR_SIZE       = "5 mins"
BAR_POLL_INTERVAL = 60       # seconds between scan cycles
MONITOR_INTERVAL  = 60       # seconds between P&L / SL/TP checks

# ── Shared state (all writes go through _state_lock) ─────────────────────────
_state_lock = threading.Lock()

_state = {
    "status":       "stopped",  # stopped | connecting | running | error | halted
    "connected":    False,
    "symbols":      SYMBOLS,
    "positions":    {},          # symbol → position dict
    "today_trades": [],          # list of closed-trade dicts
    "signals":      [],          # recent active signals being watched
    "daily_pnl":    0.0,
    "daily_wins":   0,
    "daily_losses": 0,
    "error":        None,
    "last_update":  None,
    "levels":       {},          # symbol → {PDH, PDL, PWH, PWL, ORB_H, ORB_L}
    "vwap":         {},          # symbol → float
    "last_price":   {},          # symbol → float
    "log":          [],          # recent log lines (capped at 150)
    "halted":       False,       # True if daily loss limit hit
    "account":      {},          # IBKR account summary
    "signal_states": {},         # symbol → SignalStateMachine.get_state_dict()
    # ── Watchlist ──────────────────────────────────────────────────────────
    "watchlist":         [],     # list of WatchlistEntry dicts (all symbols scored)
    "active_symbols":    SYMBOLS,  # symbols being scanned this cycle
    "watchlist_updated": None,   # ISO timestamp of last watchlist build
    "first_hour_elapsed": False, # True once first hour passes without a primary signal
    "primary_signal_fired": False,  # True if SPY/QQQ fired a signal today
}


def _set_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)
        _state["last_update"] = datetime.now(ET).isoformat()


def _log_event(msg: str, kind: str = "info"):
    """Append to in-memory log (capped) and Python logger."""
    entry = {"time": datetime.now(ET).strftime("%H:%M:%S"), "msg": msg, "kind": kind}
    with _state_lock:
        _state["log"].append(entry)
        if len(_state["log"]) > 150:
            _state["log"] = _state["log"][-150:]
    if kind == "error":
        log.error(msg)
    elif kind == "warn":
        log.warning(msg)
    else:
        log.info(msg)


def get_state() -> dict:
    """Return a deep copy of the bot state (safe for JSON serialisation)."""
    with _state_lock:
        return json.loads(json.dumps(_state, default=str))


# ── Discord notifications ─────────────────────────────────────────────────────

def _send_discord(msg: str):
    """Fire-and-forget Discord webhook."""
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=6)
    except Exception as exc:
        log.warning("Discord alert failed: %s", exc)


# ── Session helpers ───────────────────────────────────────────────────────────

def _now_et() -> datetime:
    return datetime.now(ET)


def _in_session(check_entry: bool = True) -> bool:
    """True if we are in regular trading hours."""
    now = _now_et()
    if now.weekday() >= 5:
        return False
    h, m = now.hour, now.minute
    oh, om   = SESSION_START
    ch, cm   = SESSION_END if check_entry else (16, 0)
    return (h, m) >= (oh, om) and (h, m) < (ch, cm)


def _past_eod_close() -> bool:
    """True if it's time to force-close all positions."""
    now = _now_et()
    return (now.hour, now.minute) >= EOD_CLOSE_TIME


# ── Trade execution ───────────────────────────────────────────────────────────

async def _enter_trade(client: IBKRClient, symbol: str, signal: dict):
    """
    Execute an options buy order based on a confirmed signal.
    Skips if premium > MAX_PREMIUM (i.e. > $2.00/share = $200/contract).
    Stores the resulting position in _state["positions"].
    """
    direction = signal["direction"]
    right     = "C" if direction == "long" else "P"
    price     = signal["price"]

    _log_event(
        f"SIGNAL {symbol} {direction.upper()} | "
        f"level={signal['level_name']}@{signal['level_price']:.2f} "
        f"VWAP={signal['vwap']:.2f} "
        f"confluence={signal['confluence']}/7",
        "info",
    )

    contract, mid_price = await client.find_atm_option(
        symbol=symbol,
        right=right,
        price=price,
        min_dte=MIN_DTE,
        max_dte=MAX_DTE,
        max_premium=MAX_TRADE_COST,
    )

    if contract is None or mid_price <= 0:
        _log_event(f"No valid option found for {symbol} {right} — skipping", "warn")
        return

    # Spec: 1 contract if premium ≤ $2.00, otherwise skip entirely
    if mid_price > MAX_PREMIUM:
        _log_event(
            f"Premium ${mid_price:.2f} > ${MAX_PREMIUM:.2f} limit — skipping {symbol} {right}",
            "warn",
        )
        return

    qty       = 1
    limit_px  = round(mid_price + 0.01, 2)   # buy at ask + $0.01 for better fill

    _log_event(f"Placing BUY {symbol} {right} x{qty} @ ${limit_px:.2f} limit …", "info")
    _, fill_price = await client.buy_limit(contract, qty, limit_px, wait_secs=30)

    if fill_price <= 0:
        _log_event(f"Order not filled for {symbol} {right} — no position taken", "warn")
        return

    stop_px = round(fill_price * (1.0 - STOP_LOSS_PCT),   2)
    tp_px   = round(fill_price * (1.0 + TAKE_PROFIT_PCT), 2)
    cost    = round(fill_price * 100.0 * qty, 2)

    position = {
        "symbol":      symbol,
        "direction":   direction,
        "right":       right,
        "contract":    contract,            # ib_insync Contract (not JSON-serialisable)
        "con_id":      contract.conId,
        "strike":      contract.strike,
        "expiry":      contract.lastTradeDateOrContractMonth,
        "qty":         qty,
        "entry_price": fill_price,
        "stop_price":  stop_px,
        "tp_price":    tp_px,
        "total_cost":  cost,
        "entry_time":  _now_et().isoformat(),
        "level_name":  signal["level_name"],
        "level_price": signal["level_price"],
        "pnl":         0.0,
        "status":      "open",
    }

    with _state_lock:
        _state["positions"][symbol] = position

    msg = (
        f"ENTERED {symbol} {right} strike={contract.strike} "
        f"exp={contract.lastTradeDateOrContractMonth} "
        f"x{qty} @ ${fill_price:.2f} | SL=${stop_px:.2f} TP=${tp_px:.2f} cost=${cost:.0f}"
    )
    _log_event(msg, "entry")
    _send_discord(
        f":green_circle: **ENTRY** `{symbol}` {direction.upper()}\n"
        f"  {right} Strike={contract.strike} Exp={contract.lastTradeDateOrContractMonth} "
        f"x{qty} @ ${fill_price:.2f}\n"
        f"  SL=${stop_px:.2f}  |  TP=${tp_px:.2f}  |  Cost=${cost:.0f}\n"
        f"  Level: {signal['level_name']}={signal['level_price']:.2f}  "
        f"VWAP={signal['vwap']:.2f}\n"
        f"  Confluence {signal['confluence']}/7: {signal.get('confluence_breakdown', {})}"
    )


async def _exit_trade(client: IBKRClient, symbol: str, reason: str):
    """
    Close an open options position at market (limit at current bid).
    Updates daily P&L and trade log.
    """
    with _state_lock:
        position = _state["positions"].get(symbol)
    if position is None:
        return

    contract    = position["contract"]
    qty         = position["qty"]
    entry_price = position["entry_price"]

    # Get current mid to set sell limit
    mid = await client.get_mid_price(contract)
    sell_px = max(round(mid, 2), 0.01)

    _, fill_price = await client.sell_limit(contract, qty, sell_px, wait_secs=30)
    if fill_price <= 0:
        fill_price = sell_px   # use the attempted price even if fill unclear

    pnl = round((fill_price - entry_price) * 100.0 * qty, 2)
    won = pnl > 0

    closed = {
        **{k: v for k, v in position.items() if k != "contract"},  # strip non-serialisable
        "exit_price":  fill_price,
        "exit_time":   _now_et().isoformat(),
        "exit_reason": reason,
        "pnl":         pnl,
        "status":      "closed",
    }

    with _state_lock:
        _state["positions"].pop(symbol, None)
        _state["today_trades"].append(closed)
        _state["daily_pnl"] = round(_state["daily_pnl"] + pnl, 2)
        if won:
            _state["daily_wins"] += 1
        else:
            _state["daily_losses"] += 1
        if _state["daily_pnl"] <= -DAILY_LOSS_LIMIT and not _state["halted"]:
            _state["halted"] = True
            _log_event(
                f"DAILY LOSS LIMIT HIT (${_state['daily_pnl']:.2f}) — bot halted for today",
                "error",
            )
            _send_discord(
                f":no_entry: **DAILY LOSS LIMIT** reached "
                f"(${_state['daily_pnl']:.2f}) — no new trades today."
            )

    color = ":green_circle:" if won else ":red_circle:"
    msg = (
        f"EXIT {symbol} {position['direction'].upper()} [{reason}] | "
        f"entry=${entry_price:.2f} → exit=${fill_price:.2f}  P&L=${pnl:+.2f}"
    )
    _log_event(msg, "exit")
    _send_discord(
        f"{color} **{reason}** `{symbol}` {position['direction'].upper()}\n"
        f"  {position['right']} {position['strike']} exp={position['expiry']}\n"
        f"  Entry=${entry_price:.2f} → Exit=${fill_price:.2f}  "
        f"**P&L ${pnl:+.2f}**\n"
        f"  Daily P&L: ${_state['daily_pnl']:+.2f}"
    )


# ── Position monitor (SL / TP / EOD) ─────────────────────────────────────────

async def _monitor_positions(client: IBKRClient):
    """Check all open positions for stop-loss, take-profit, or EOD close triggers."""
    with _state_lock:
        positions = {k: dict(v) for k, v in _state["positions"].items()}

    for symbol, pos in positions.items():
        contract = pos.get("contract")
        if contract is None:
            continue
        try:
            mid = await client.get_mid_price(contract)
        except Exception as exc:
            log.warning("Price fetch failed for %s: %s", symbol, exc)
            continue

        if mid <= 0:
            continue

        # Update live P&L in state
        live_pnl = round((mid - pos["entry_price"]) * 100.0 * pos["qty"], 2)
        with _state_lock:
            if symbol in _state["positions"]:
                _state["positions"][symbol]["pnl"] = live_pnl

        sl = pos["stop_price"]
        tp = pos["tp_price"]

        if mid <= sl:
            await _exit_trade(client, symbol, "STOP LOSS")
        elif mid >= tp:
            await _exit_trade(client, symbol, "TAKE PROFIT")
        elif _past_eod_close():
            await _exit_trade(client, symbol, "EOD CLOSE")


# ── Account updater ───────────────────────────────────────────────────────────

async def _update_account(client: IBKRClient):
    """Fetch account summary and store in state (runs every few minutes)."""
    acct = await client.get_account_summary()
    if acct:
        with _state_lock:
            _state["account"] = acct


# ── Watchlist background refresh ──────────────────────────────────────────────

async def _watchlist_refresh_loop():
    """
    Background coroutine: rebuild the watchlist every SCAN_CACHE_TTL seconds
    (default 5 min) so scores stay fresh without blocking the scan loop.
    The first build runs immediately on startup so the dashboard shows data fast.
    """
    from watchlist import SCAN_CACHE_TTL
    while True:
        try:
            loop = asyncio.get_event_loop()
            # Run the blocking yfinance calls in a thread pool so the event loop
            # stays responsive.
            entries = await loop.run_in_executor(None, build_watchlist, True)
            with _state_lock:
                _state["watchlist"]         = entries
                _state["watchlist_updated"] = _now_et().isoformat()
                # Rebuild active_symbols based on current first_hour_elapsed flag
                fhe = _state["first_hour_elapsed"]
            active = get_active_scan_symbols(entries, fhe)
            entries_marked = mark_active(entries, active)
            with _state_lock:
                _state["watchlist"]      = entries_marked
                _state["active_symbols"] = active
            _log_event(
                f"Watchlist refreshed: {len(entries_marked)} symbols | "
                f"active scan: {', '.join(active)}",
                "info",
            )
        except Exception as exc:
            log.warning("Watchlist refresh error: %s", exc)
        await asyncio.sleep(SCAN_CACHE_TTL)


# ── Main bot loop ─────────────────────────────────────────────────────────────

async def _run_bot():
    """
    Primary async loop:
      1. Connect to IBKR.
      2. Pre-fetch weekly levels (yfinance).
      3. Every BAR_POLL_INTERVAL seconds:
         a. Determine active scan symbols (SPY/QQQ first; expand after first hour
            if no signal fired on primaries).
         b. For each active symbol: fetch bars, compute levels/VWAP, run signal
            state machine.
         c. Monitor open positions (SL/TP/EOD).
    """
    client = IBKRClient(
        host      = IBKR_HOST,
        port      = IBKR_PORT,
        client_id = IBKR_CLIENT_ID,
    )

    # signal_states dict grows dynamically as new symbols are added to the scan
    signal_states: dict = {}

    # Pre-fetch weekly levels via yfinance (these rarely change intraday)
    weekly_levels: dict = {}

    def _ensure_symbol_ready(sym: str):
        """Initialise signal state machine + weekly levels for a symbol."""
        if sym not in signal_states:
            signal_states[sym] = SignalStateMachine(sym)
        if sym not in weekly_levels:
            yf_sym = "^GSPC" if sym == "SPX" else sym
            wl = fetch_weekly_levels(yf_sym)
            weekly_levels[sym] = wl
            log.info("%s weekly: PWH=%s PWL=%s",
                     sym,
                     f"{wl.get('PWH'):.2f}" if wl.get("PWH") else "N/A",
                     f"{wl.get('PWL'):.2f}" if wl.get("PWL") else "N/A")

    # Initialise primary symbols immediately
    for sym in PRIMARY_SYMBOLS:
        _ensure_symbol_ready(sym)

    last_acct_update     = 0.0
    # Track the ET time at which market open occurred this session (for first-hour logic)
    session_open_time: Optional[datetime] = None

    while True:
        # ── Connect / reconnect ──────────────────────────────────────────────
        if not client.is_connected():
            _set_state(status="connecting", connected=False)
            ok = await client.connect()
            if ok:
                _set_state(status="running", connected=True, error=None)
                _log_event(f"Connected to IBKR paper trading (port {IBKR_PORT})", "info")
            else:
                _set_state(status="error", connected=False,
                           error="IBKR connection failed")
                _log_event("IBKR connection failed — retrying in 30s", "error")
                await asyncio.sleep(30)
                continue

        try:
            # ── Account update every 5 min ───────────────────────────────────
            now_ts = time.time()
            if now_ts - last_acct_update > 300:
                await _update_account(client)
                last_acct_update = now_ts

            # ── Outside market hours — idle ──────────────────────────────────
            if not _in_session(check_entry=False):
                session_open_time = None   # reset for next day
                await asyncio.sleep(60)
                continue

            # ── Record session open time (once per day) ───────────────────────
            now_et = _now_et()
            if session_open_time is None:
                session_open_time = now_et
                _log_event("Market session open — scanning SPY + QQQ (primary)", "info")

            # ── Evaluate first-hour expansion ────────────────────────────────
            with _state_lock:
                fhe              = _state["first_hour_elapsed"]
                primary_fired    = _state["primary_signal_fired"]
                watchlist_entries = list(_state["watchlist"])

            elapsed_minutes = (now_et - session_open_time).total_seconds() / 60.0
            if not fhe and elapsed_minutes >= 60 and not primary_fired:
                fhe = True
                with _state_lock:
                    _state["first_hour_elapsed"] = True
                _log_event(
                    "First hour elapsed with no primary signal — expanding scan to "
                    "curated + trending symbols",
                    "info",
                )
                # Update active symbols immediately
                if watchlist_entries:
                    active = get_active_scan_symbols(watchlist_entries, fhe)
                    entries_marked = mark_active(watchlist_entries, active)
                    with _state_lock:
                        _state["watchlist"]      = entries_marked
                        _state["active_symbols"] = active
                    _log_event(f"Active scan expanded to: {', '.join(active)}", "info")

            # ── Determine active symbols for this cycle ───────────────────────
            with _state_lock:
                active_symbols = list(_state["active_symbols"])

            # Fallback if watchlist not yet built
            if not active_symbols:
                active_symbols = list(PRIMARY_SYMBOLS)

            # ── Halted: only monitor existing positions ──────────────────────
            with _state_lock:
                halted = _state["halted"]
            if halted:
                await _monitor_positions(client)
                await asyncio.sleep(MONITOR_INTERVAL)
                continue

            # ── Per-symbol scan ──────────────────────────────────────────────
            for symbol in active_symbols:
                # Lazy-init signal state + weekly levels for newly-added symbols
                _ensure_symbol_ready(symbol)

                try:
                    # Fetch 5-min bars (2 days)
                    bars = await client.get_bars(symbol, duration=BAR_DURATION, bar_size=BAR_SIZE)
                    if not bars:
                        log.warning("No bars for %s", symbol)
                        continue

                    # Compute intraday levels
                    vwap        = compute_vwap(bars)
                    pdh_pdl     = compute_pdh_pdl(bars)
                    orb         = compute_orb(bars)
                    wk          = weekly_levels.get(symbol, {})
                    # Include VWAP as a named level for confluence scoring
                    levels      = {**pdh_pdl, **wk, **orb}
                    if vwap > 0:
                        levels["VWAP"] = vwap

                    last_price  = float(bars[-1].close) if bars else 0.0

                    # Update UI state
                    with _state_lock:
                        _state["levels"][symbol]        = {k: v for k, v in levels.items() if v}
                        _state["vwap"][symbol]          = round(vwap, 2)
                        _state["last_price"][symbol]    = round(last_price, 2)
                        _state["signal_states"][symbol] = signal_states[symbol].get_state_dict()
                        _state["symbols"]               = active_symbols  # keep UI in sync

                    # ── Gate: no new entries if at limits ────────────────────
                    with _state_lock:
                        has_pos   = symbol in _state["positions"]
                        total_pos = len(_state["positions"])

                    can_enter = (
                        not has_pos
                        and total_pos < MAX_POSITIONS
                        and _in_session(check_entry=True)
                    )

                    if can_enter:
                        signal = signal_states[symbol].update(bars, levels, vwap, symbol)
                        if signal:
                            # Record signal for UI
                            with _state_lock:
                                sig_rec = {**signal}
                                sig_rec.pop("confluence_breakdown", None)  # keep lean
                                _state["signals"].insert(0, sig_rec)
                                _state["signals"] = _state["signals"][:20]
                                # Mark primary signal fired (suppresses expansion)
                                if symbol in PRIMARY_SYMBOLS:
                                    _state["primary_signal_fired"] = True
                            await _enter_trade(client, symbol, signal)
                    else:
                        # Still run the state machine to track breaks even if we can't enter
                        signal_states[symbol].update(bars, levels, vwap, symbol)

                except Exception as exc:
                    _log_event(f"Error processing {symbol}: {exc}", "error")
                    log.exception("Symbol loop error: %s", symbol)

            # ── Monitor open positions ───────────────────────────────────────
            await _monitor_positions(client)

            # ── Sleep until next scan cycle ──────────────────────────────────
            await asyncio.sleep(BAR_POLL_INTERVAL)

        except Exception as exc:
            _set_state(status="error", connected=False, error=str(exc))
            _log_event(f"Bot loop error: {exc} — reconnecting in 15s", "error")
            log.exception("Unhandled bot loop error")
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(15)


# ── Daily P&L reset ───────────────────────────────────────────────────────────

async def _daily_reset_loop():
    """Resets daily counters at midnight ET each day and rotates the log file."""
    last_date = _now_et().date()
    while True:
        await asyncio.sleep(60)
        today = _now_et().date()
        if today != last_date:
            with _state_lock:
                _state["daily_pnl"]           = 0.0
                _state["daily_wins"]          = 0
                _state["daily_losses"]        = 0
                _state["today_trades"]        = []
                _state["halted"]              = False
                _state["signals"]             = []
                _state["first_hour_elapsed"]  = False
                _state["primary_signal_fired"] = False
                _state["active_symbols"]      = list(PRIMARY_SYMBOLS)
            last_date = today
            # Rotate to new dated log file
            root_logger = logging.getLogger()
            for hdlr in list(root_logger.handlers):
                if isinstance(hdlr, logging.FileHandler):
                    root_logger.removeHandler(hdlr)
                    hdlr.close()
            root_logger.addHandler(_make_log_handler())
            log.info("Daily P&L reset — new trading day: %s", today)


# ── Daily 4pm ET Discord summary ──────────────────────────────────────────────

async def _daily_summary_loop():
    """Send a daily trading summary to Discord at 4:00pm ET each trading day."""
    _sent_for: Optional[date] = None
    while True:
        await asyncio.sleep(30)
        now = _now_et()
        # Only on weekdays, at or after 4:00pm ET
        if now.weekday() >= 5:
            continue
        if (now.hour, now.minute) < (16, 0):
            continue
        today = now.date()
        if _sent_for == today:
            continue   # already sent today's summary
        # Persist sent date to disk so restarts don't re-send on the same day
        _sentinel = Path(__file__).parent / ".last_summary_date"
        try:
            if _sentinel.exists() and _sentinel.read_text().strip() == str(today):
                _sent_for = today
                continue
        except Exception:
            pass
        _sent_for = today
        try:
            _sentinel.write_text(str(today))
        except Exception:
            pass

        with _state_lock:
            pnl    = _state["daily_pnl"]
            wins   = _state["daily_wins"]
            losses = _state["daily_losses"]
            trades = list(_state["today_trades"])
            syms   = list(_state["symbols"])

        total = wins + losses
        # Skip summary on days with no trades
        if total == 0 and pnl == 0:
            log.info("No trades today — skipping daily summary.")
            continue
        wr    = f"{wins / total * 100:.1f}%" if total > 0 else "N/A"
        emoji = ":green_circle:" if pnl >= 0 else ":red_circle:"
        lines = [
            f"{emoji} **Daily Summary — {today.strftime('%A %b %d, %Y')}**",
            f"  Symbols: {', '.join(syms)}",
            f"  Trades:  {total}  |  Wins: {wins}  |  Losses: {losses}  |  Win Rate: {wr}",
            f"  **Daily P&L: ${pnl:+.2f}**",
        ]
        if trades:
            lines.append("  ─── Closed trades ───")
            for t in trades:
                t_pnl = t.get("pnl", 0)
                lines.append(
                    f"  • {t.get('symbol','')} {t.get('direction','').upper()} "
                    f"{t.get('right','')} {t.get('strike','')}"
                    f" exp={t.get('expiry','')}"
                    f" | entry=${t.get('entry_price',0):.2f}"
                    f" → exit=${t.get('exit_price',0):.2f}"
                    f" P&L=${t_pnl:+.2f}"
                    f" [{t.get('exit_reason','')}]"
                )
        msg = "\n".join(lines)
        log.info("Sending daily summary to Discord.")
        _send_discord(msg)


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    """Start the options bot event loop (blocking)."""
    log.info(
        "Options Bot starting — symbols=%s IBKR=%s:%d clientId=%d",
        SYMBOLS, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID,
    )
    log.info(
        "Risk: max_trade=$%.0f  max_premium=$%.2f  max_pos=%d  daily_loss=$%.0f  "
        "SL=%.0f%%  TP=%.0f%%  DTE=%d–%d",
        MAX_TRADE_COST, MAX_PREMIUM, MAX_POSITIONS, DAILY_LOSS_LIMIT,
        STOP_LOSS_PCT * 100, TAKE_PROFIT_PCT * 100, MIN_DTE, MAX_DTE,
    )
    log.info(
        "Session: %02d:%02d–%02d:%02d ET | EOD close %02d:%02d ET",
        *SESSION_START, *SESSION_END, *EOD_CLOSE_TIME,
    )

    util.patchAsyncio()   # lets ib_insync nest inside asyncio.run()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _main():
        await asyncio.gather(
            _run_bot(),
            _daily_reset_loop(),
            _daily_summary_loop(),
            _watchlist_refresh_loop(),
        )

    try:
        loop.run_until_complete(_main())
    except KeyboardInterrupt:
        log.info("Options Bot stopped by user.")
    finally:
        loop.close()


def _run_test():
    """Dry-run import/config test — no IBKR connection, no trading."""
    print("=" * 60)
    print("Option Riders — Options Bot  [ DRY-RUN / IMPORT TEST ]")
    print("=" * 60)
    print(f"  IBKR host:port   : {IBKR_HOST}:{IBKR_PORT}")
    print(f"  Client ID        : {IBKR_CLIENT_ID}")
    print(f"  Symbols          : {SYMBOLS}")
    print(f"  Max positions    : {MAX_POSITIONS}")
    print(f"  Max trade cost   : ${MAX_TRADE_COST:.0f}")
    print(f"  Max premium      : ${MAX_PREMIUM:.2f}/share")
    print(f"  Stop loss        : {STOP_LOSS_PCT*100:.0f}%")
    print(f"  Take profit      : {TAKE_PROFIT_PCT*100:.0f}%  (2R = 100%)")
    print(f"  Daily loss limit : ${DAILY_LOSS_LIMIT:.0f}")
    print(f"  DTE window       : {MIN_DTE}–{MAX_DTE} days")
    print(f"  Session          : {SESSION_START[0]:02d}:{SESSION_START[1]:02d}–"
          f"{SESSION_END[0]:02d}:{SESSION_END[1]:02d} ET")
    print(f"  Discord webhook  : {'SET' if DISCORD_WEBHOOK else 'NOT SET'}")
    print()

    # Verify all module imports work
    print("  Importing ibkr_client … ", end="")
    from ibkr_client import IBKRClient
    print("OK")
    print("  Importing signals …     ", end="")
    from signals import (
        SignalStateMachine, compute_vwap, compute_rsi,
        compute_orb, compute_pdh_pdl, in_rth,
    )
    print("OK")
    print("  Importing ib_insync …   ", end="")
    from ib_insync import IB, util as _util
    print("OK")

    # Test signal state machine instantiation
    print("  SignalStateMachine …    ", end="")
    for sym in SYMBOLS:
        sm = SignalStateMachine(sym)
        assert sm.state == "idle"
    print("OK")

    print()
    print("  All imports and config checks passed.")
    print("  Run without --test to start live trading.")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv or "--dry-run" in sys.argv:
        _run_test()
    else:
        run()
