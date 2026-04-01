#!/usr/bin/env python3
"""
futures_bot.py — VWAP/EMA scalping bot for MES (Micro E-mini S&P 500)
and MNQ (Micro E-mini Nasdaq 100) futures via IB Gateway.

Strategy:
    - VWAP as directional bias (price above = bullish, below = bearish)
    - EMA 9 / EMA 21 crossover for entry trigger
    - ATR(14)-based stop loss at 1.5x ATR
    - 2:1 R:R profit target (3x ATR)
    - NY session only (9:30am – 3:45pm ET, no new entries after 3:45pm)

Risk rules:
    - Max 1 contract per symbol
    - Max 2 open positions total
    - $100 daily loss limit — bot halts if hit
    - Auto-close all positions at 3:45pm ET

Flask API on port 8128:
    GET  /api/status  → full bot state JSON
    POST /api/start   → start bot thread
    POST /api/stop    → stop bot thread
    GET  /api/logs    → last 50 log entries
"""

import copy
import logging
import os
import sys
import threading
from collections import deque
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import pytz
from flask import Flask, jsonify, send_from_directory

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ── .env loader ───────────────────────────────────────────────────────────────
def _load_dotenv(dotenv_path: str = ".env"):
    env_file = _HERE / dotenv_path
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

# ── Logging setup (dated file + stdout) ───────────────────────────────────────
_LOG_DIR = _HERE / "logs"
_LOG_DIR.mkdir(exist_ok=True)

def _make_file_handler():
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_path = _LOG_DIR / f"futures_bot_{today_str}.log"
    return logging.FileHandler(log_path, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[_make_file_handler(), logging.StreamHandler()],
)
log = logging.getLogger("futures_bot")

# ── Config ────────────────────────────────────────────────────────────────────
IBKR_HOST        = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT        = int(os.environ.get("IBKR_PORT", "4002"))
IBKR_CLIENT_ID   = int(os.environ.get("FUTURES_CLIENT_ID", "3"))
PORT             = int(os.environ.get("FUTURES_BOT_PORT", "8128"))

SYMBOLS          = ["MES", "MNQ"]
MAX_CONTRACTS    = 1
MAX_POSITIONS    = 2
DAILY_LOSS_LIMIT = float(os.environ.get("FUTURES_DAILY_LOSS_LIMIT", "100"))
ATR_SL_MULT      = 1.5
RR_RATIO         = 2.0
EMA_FAST         = 9
EMA_SLOW         = 21
ATR_PERIOD       = 14
BAR_SIZE         = "5 mins"
HIST_DURATION    = "2 D"    # 2 days to have enough bars for EMA/ATR at open
SCAN_INTERVAL    = 30       # seconds between signal scans

# Contract multipliers ($ per 1 index point)
CONTRACT_MULT = {"MES": 5, "MNQ": 2}

ET             = pytz.timezone("America/New_York")
NY_OPEN        = time(9, 30)
NY_CLOSE       = time(16, 0)
NO_ENTRY_AFTER = time(15, 45)
AUTO_CLOSE_AT  = time(15, 45)

# ── In-memory log buffer ──────────────────────────────────────────────────────
_log_buffer: deque = deque(maxlen=50)
_log_lock = threading.Lock()


class _BufferHandler(logging.Handler):
    def emit(self, record):
        ts = datetime.now().strftime("%H:%M:%S")
        with _log_lock:
            _log_buffer.appendleft({
                "time":  ts,
                "level": record.levelname.lower(),
                "msg":   self.format(record).split("  ", 2)[-1] if "  " in self.format(record) else record.getMessage(),
            })


_buf_handler = _BufferHandler()
_buf_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S"))
_buf_handler.setLevel(logging.INFO)
log.addHandler(_buf_handler)

# ── Shared state ──────────────────────────────────────────────────────────────
_state_lock = threading.Lock()
_state = {
    "status":         "stopped",   # stopped | connecting | running | halted | error
    "connected":      False,
    "halted":         False,
    "daily_pnl":      0.0,
    "realized_pnl":   0.0,
    "session_trades": 0,
    "positions":      {},          # sym → {side, qty, entry, sl, tp, unrealized_pnl}
    "instruments": {
        "MES": {"price": None, "vwap": None, "ema9": None, "ema21": None,
                "atr": None, "signal": "neutral", "bars_loaded": 0},
        "MNQ": {"price": None, "vwap": None, "ema9": None, "ema21": None,
                "atr": None, "signal": "neutral", "bars_loaded": 0},
    },
    "last_update": None,
    "error":       None,
}

# ── Bot thread management ─────────────────────────────────────────────────────
_bot_thread: Optional[threading.Thread] = None
_bot_thread_lock = threading.Lock()
_stop_event = threading.Event()

# ── Technical indicators ──────────────────────────────────────────────────────

def _vwap_from_bars(bars) -> Optional[float]:
    """VWAP anchored to 9:30am ET today (NY session open)."""
    today_et = datetime.now(ET).date()
    ny_open_dt = ET.localize(datetime.combine(today_et, time(9, 30)))
    cumvol, cumtpv = 0.0, 0.0
    for bar in bars:
        bar_dt = bar.date
        if isinstance(bar_dt, str):
            continue  # skip if date is a string (daily bar format)
        if bar_dt.tzinfo is None:
            bar_dt = ET.localize(bar_dt)
        else:
            bar_dt = bar_dt.astimezone(ET)
        if bar_dt < ny_open_dt:
            continue
        tp  = (bar.high + bar.low + bar.close) / 3
        vol = max(float(bar.volume), 1.0) if bar.volume else 1.0
        cumvol += vol
        cumtpv += tp * vol
    return cumtpv / cumvol if cumvol > 0 else None


def _ema(prices: list, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    k   = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def _atr(bars, period: int = ATR_PERIOD) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low  - bars[i - 1].close),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _compute_indicators(bars) -> dict:
    if not bars:
        return {}
    closes = [b.close for b in bars]
    return {
        "price":       closes[-1],
        "vwap":        _vwap_from_bars(bars),
        "ema9":        _ema(closes, EMA_FAST),
        "ema21":       _ema(closes, EMA_SLOW),
        "atr":         _atr(bars),
        "bars_loaded": len(bars),
    }


def _get_signal(prev: dict, curr: dict) -> str:
    """EMA crossover + VWAP bias → 'long', 'short', or 'neutral'."""
    keys = ("price", "vwap", "ema9", "ema21")
    if not all(curr.get(k) is not None for k in keys):
        return "neutral"
    if not all(prev.get(k) is not None for k in ("ema9", "ema21")):
        return "neutral"

    price, vwap   = curr["price"], curr["vwap"]
    e9, e21       = curr["ema9"],  curr["ema21"]
    pe9, pe21     = prev["ema9"],  prev["ema21"]

    cross_up   = pe9 <= pe21 and e9 > e21
    cross_down = pe9 >= pe21 and e9 < e21

    if cross_up   and price > vwap:
        return "long"
    if cross_down and price < vwap:
        return "short"
    return "neutral"


# ── Session helpers ───────────────────────────────────────────────────────────

def _in_session() -> bool:
    t = datetime.now(ET).time()
    return NY_OPEN <= t < NY_CLOSE


def _can_enter() -> bool:
    t = datetime.now(ET).time()
    return NY_OPEN <= t < NO_ENTRY_AFTER


def _should_auto_close() -> bool:
    return datetime.now(ET).time() >= AUTO_CLOSE_AT


# ── Bot main loop ─────────────────────────────────────────────────────────────

def run():
    """Bot entry point — runs in a background daemon thread."""
    global _state

    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        from ib_insync import IB, Future, MarketOrder, StopOrder, LimitOrder, util
    except ImportError:
        log.error("ib_insync not installed. Run: pip install ib_insync")
        with _state_lock:
            _state["status"] = "error"
            _state["error"]  = "ib_insync not installed"
        return

    util.patchAsyncio()
    _stop_event.clear()

    with _state_lock:
        _state.update({
            "status": "connecting", "connected": False, "halted": False,
            "daily_pnl": 0.0, "realized_pnl": 0.0, "session_trades": 0,
            "positions": {}, "error": None,
        })

    log.info("Futures bot starting — connecting to %s:%d (clientId=%d)",
             IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID)

    ib = IB()

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=20)
        log.info("Connected to IB Gateway")
    except Exception as exc:
        log.error("IB connection failed: %s", exc)
        with _state_lock:
            _state["status"] = "error"
            _state["error"]  = str(exc)
        return

    with _state_lock:
        _state["connected"] = True
        _state["status"]    = "running"

    # ── Qualify front-month contracts ─────────────────────────────────────────
    contracts: dict = {}
    try:
        for sym in SYMBOLS:
            c = Future(symbol=sym, exchange="CME", currency="USD")
            details = ib.reqContractDetails(c)
            if not details:
                # Try GLOBEX routing
                c = Future(symbol=sym, exchange="CME", currency="USD")
                details = ib.reqContractDetails(c)
            if not details:
                raise ValueError(f"No contract details for {sym}")
            # Pick nearest non-expired expiry
            details.sort(key=lambda d: d.contract.lastTradeDateOrContractMonth)
            front = details[0].contract
            ib.qualifyContracts(front)
            contracts[sym] = front
            log.info("Qualified %s → expiry %s  conId=%s",
                     sym, front.lastTradeDateOrContractMonth, front.conId)
    except Exception as exc:
        log.error("Contract qualification failed: %s", exc)
        with _state_lock:
            _state["status"] = "error"
            _state["error"]  = str(exc)
        ib.disconnect()
        return

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _sync_positions() -> dict:
        result = {}
        for pos in ib.positions():
            sym = pos.contract.symbol
            if sym in SYMBOLS and pos.position != 0:
                result[sym] = {
                    "side":           "long" if pos.position > 0 else "short",
                    "qty":            abs(int(pos.position)),
                    "entry":          round(pos.avgCost, 2),
                    "sl":             None,
                    "tp":             None,
                    "unrealized_pnl": 0.0,
                }
        return result

    def _close_position(sym: str, side: str):
        if sym not in contracts:
            return
        action = "SELL" if side == "long" else "BUY"
        trade  = ib.placeOrder(contracts[sym], MarketOrder(action, MAX_CONTRACTS))
        log.info("Closing %s %s → orderId=%d", sym, side, trade.order.orderId)

    def _place_bracket(sym: str, signal: str, ind: dict):
        atr   = ind.get("atr")
        price = ind.get("price")
        if atr is None or price is None or atr == 0:
            log.warning("Cannot place bracket for %s — invalid ATR/price", sym)
            return

        sl_dist = round(ATR_SL_MULT * atr, 2)
        tp_dist = round(RR_RATIO * sl_dist, 2)

        action    = "BUY"  if signal == "long"  else "SELL"
        sl_action = "SELL" if signal == "long"  else "BUY"

        if signal == "long":
            sl_price = round(price - sl_dist, 2)
            tp_price = round(price + tp_dist, 2)
        else:
            sl_price = round(price + sl_dist, 2)
            tp_price = round(price - tp_dist, 2)

        # Assign explicit order IDs so children can reference parent
        parent_id = ib.client.getReqId()
        sl_id     = ib.client.getReqId()
        tp_id     = ib.client.getReqId()

        parent         = MarketOrder(action, MAX_CONTRACTS)
        parent.orderId = parent_id
        parent.transmit = False

        sl_order           = StopOrder(sl_action, MAX_CONTRACTS, sl_price)
        sl_order.orderId   = sl_id
        sl_order.parentId  = parent_id
        sl_order.transmit  = False

        tp_order           = LimitOrder(sl_action, MAX_CONTRACTS, tp_price)
        tp_order.orderId   = tp_id
        tp_order.parentId  = parent_id
        tp_order.ocaGroup  = f"fut_brk_{parent_id}"
        tp_order.ocaType   = 1
        tp_order.transmit  = True

        ib.placeOrder(contracts[sym], parent)
        ib.placeOrder(contracts[sym], sl_order)
        ib.placeOrder(contracts[sym], tp_order)

        log.info("ENTRY %s %s: ≈%.2f  SL=%.2f  TP=%.2f  ATR=%.4f",
                 signal.upper(), sym, price, sl_price, tp_price, atr)

        with _state_lock:
            _state["positions"][sym] = {
                "side":           signal,
                "qty":            MAX_CONTRACTS,
                "entry":          price,
                "sl":             sl_price,
                "tp":             tp_price,
                "unrealized_pnl": 0.0,
            }
            _state["session_trades"] += 1

    # ── Main scan loop ─────────────────────────────────────────────────────────
    prev_ind: dict = {}   # sym → previous indicator snapshot (for crossover)
    log.info("Futures bot running — scanning every %ds", SCAN_INTERVAL)

    while not _stop_event.is_set():
        try:
            with _state_lock:
                halted    = _state["halted"]
                daily_pnl = _state["daily_pnl"]

            # Check daily loss limit
            if not halted and daily_pnl <= -DAILY_LOSS_LIMIT:
                log.warning("Daily loss limit hit (%.2f). Halting bot.", daily_pnl)
                with _state_lock:
                    _state["halted"] = True
                    _state["status"] = "halted"
                with _state_lock:
                    open_pos = copy.deepcopy(_state["positions"])
                for sym, pos in open_pos.items():
                    _close_position(sym, pos["side"])
                ib.sleep(SCAN_INTERVAL)
                continue

            if halted:
                ib.sleep(SCAN_INTERVAL)
                continue

            # Auto-close at session end
            if _should_auto_close():
                with _state_lock:
                    open_pos = copy.deepcopy(_state["positions"])
                if open_pos:
                    log.info("Session end — auto-closing all positions")
                    for sym, pos in open_pos.items():
                        _close_position(sym, pos["side"])
                    ib.sleep(5)
                    with _state_lock:
                        _state["positions"] = {}

            # ── Fetch bars + compute indicators ───────────────────────────────
            new_instruments: dict = {}
            for sym in SYMBOLS:
                if sym not in contracts:
                    continue
                try:
                    bars = ib.reqHistoricalData(
                        contracts[sym],
                        endDateTime="",
                        durationStr=HIST_DURATION,
                        barSizeSetting=BAR_SIZE,
                        whatToShow="TRADES",
                        useRTH=True,
                        formatDate=1,
                        keepUpToDate=False,
                    )
                    ind    = _compute_indicators(bars)
                    prev   = prev_ind.get(sym, {})
                    signal = _get_signal(prev, ind)
                    ind["signal"] = signal
                    prev_ind[sym] = copy.copy(ind)
                    new_instruments[sym] = ind

                    # ── Entry logic ───────────────────────────────────────────
                    if signal != "neutral" and _can_enter():
                        with _state_lock:
                            open_pos = copy.deepcopy(_state["positions"])
                        if sym not in open_pos and len(open_pos) < MAX_POSITIONS:
                            log.info("Signal %s on %s — entering", signal.upper(), sym)
                            _place_bracket(sym, signal, ind)

                except Exception as exc:
                    log.warning("Bar fetch error for %s: %s", sym, exc)
                    with _state_lock:
                        new_instruments[sym] = copy.deepcopy(_state["instruments"].get(sym, {}))

                # Small pause between requests to avoid IB pacing violations
                ib.sleep(2)

            # ── Sync positions and unrealized P&L ─────────────────────────────
            ib_positions = _sync_positions()
            pnl_unrealized = 0.0
            mult = CONTRACT_MULT

            for sym, pos in ib_positions.items():
                last_price = new_instruments.get(sym, {}).get("price")
                if last_price and pos["entry"]:
                    m = mult.get(sym, 5)
                    if pos["side"] == "long":
                        upnl = (last_price - pos["entry"]) * m
                    else:
                        upnl = (pos["entry"] - last_price) * m
                    ib_positions[sym]["unrealized_pnl"] = round(upnl, 2)
                    pnl_unrealized += upnl

                    # Carry over SL/TP from state if not in IB positions
                    with _state_lock:
                        st_pos = _state["positions"].get(sym, {})
                    if st_pos:
                        ib_positions[sym]["sl"] = st_pos.get("sl")
                        ib_positions[sym]["tp"] = st_pos.get("tp")

            # ── Update shared state ───────────────────────────────────────────
            with _state_lock:
                for sym, ind in new_instruments.items():
                    _state["instruments"][sym] = {
                        "price":       ind.get("price"),
                        "vwap":        ind.get("vwap"),
                        "ema9":        ind.get("ema9"),
                        "ema21":       ind.get("ema21"),
                        "atr":         ind.get("atr"),
                        "signal":      ind.get("signal", "neutral"),
                        "bars_loaded": ind.get("bars_loaded", 0),
                    }
                _state["positions"]    = ib_positions
                _state["daily_pnl"]   = round(pnl_unrealized, 2)
                _state["last_update"] = datetime.now(ET).strftime("%H:%M:%S ET")
                _state["error"]       = None

        except Exception as exc:
            log.error("Scan loop error: %s", exc, exc_info=True)
            with _state_lock:
                _state["error"] = str(exc)

        ib.sleep(SCAN_INTERVAL)

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Futures bot stopping — closing any open positions")
    with _state_lock:
        open_pos = copy.deepcopy(_state["positions"])
    for sym, pos in open_pos.items():
        try:
            _close_position(sym, pos["side"])
        except Exception:
            pass
    ib.sleep(3)
    ib.disconnect()
    with _state_lock:
        _state["status"]    = "stopped"
        _state["connected"] = False
    log.info("Futures bot stopped.")


# ── Public state accessor ─────────────────────────────────────────────────────

def get_state() -> dict:
    with _state_lock:
        s = copy.deepcopy(_state)
    with _log_lock:
        s["logs"] = list(_log_buffer)
    return s


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(_HERE), static_url_path="")
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/")
def index():
    return send_from_directory(str(_HERE), "futures_bot.html")


@app.route("/futures_bot.html")
def futures_html():
    return send_from_directory(str(_HERE), "futures_bot.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(get_state())


@app.route("/api/start", methods=["POST"])
def api_start():
    global _bot_thread
    with _bot_thread_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            return jsonify({"ok": False, "message": "Bot already running"})
        _stop_event.clear()
        _bot_thread = threading.Thread(target=run, daemon=True, name="futures-bot")
        _bot_thread.start()
        log.info("Futures bot thread started via API")
    return jsonify({"ok": True, "message": "Bot started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    _stop_event.set()
    with _state_lock:
        _state["halted"] = True
    log.info("Futures bot stop requested via API")
    return jsonify({"ok": True, "message": "Stop requested"})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    with _log_lock:
        logs = list(_log_buffer)
    return jsonify(logs)


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(str(_HERE), filename)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _bot_thread
    with _bot_thread_lock:
        if _bot_thread is None or not _bot_thread.is_alive():
            _stop_event.clear()
            _bot_thread = threading.Thread(target=run, daemon=True, name="futures-bot")
            _bot_thread.start()
            log.info("Futures bot auto-started")

    log.info("Futures Bot dashboard: http://0.0.0.0:%d", PORT)
    log.info("API endpoints: /api/status  /api/start  /api/stop  /api/logs")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
