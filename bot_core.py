#!/usr/bin/env python3
"""
bot_core.py — Crypto scalping bot engine for Option Riders
Runs as a background thread inside server.py

Config env vars:
  BOT_SYMBOL    — trading pair, e.g. ETHUSDT, SOLUSDT (default: BTCUSDT)

Supported strategies (BOT_STRATEGY env var):
  level_retest  — key-level retest with rejection wick (original)
  ema_pullback  — 9/21 EMA trend-following pullback
  vwap_bounce   — VWAP touch-and-go with momentum confirmation
  bb_reversal   — Bollinger Band mean-reversion
  supertrend    — ATR supertrend direction flip (scalping)
  macd_scalp    — MACD histogram crossover with EMA/VWAP filter (scalping)
  combo_scalp   — Supertrend direction + MACD crossover + VWAP side (3-confirmation, both long/short)
"""

import os
import time
import threading
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── SETTINGS (overridden by .env) ─────────────────────────────────────────────
SYMBOL               = os.environ.get("BOT_SYMBOL", "BTCUSDT")
TIMEFRAME            = "1m"   # 1-minute candles for scalping
RISK_PCT             = 0.02
RR_RATIO             = 2.0
EMA_PERIOD           = 9
LEVEL_TOLERANCE_PCT  = 0.001
REJECTION_WICK_RATIO = 1.5
TIME_STOP_MINUTES    = 25
POLL_SECONDS         = 15
MAX_LOG_ENTRIES       = 50
PAPER_STARTING_BAL   = float(os.environ.get("BOT_STARTING_BALANCE", "10000"))

# Active strategy — read once at import; can be overridden at runtime via set_strategy()
STRATEGY = os.environ.get("BOT_STRATEGY", "combo_scalp")

_VALID_STRATEGIES = {
    "level_retest", "ema_pullback", "vwap_bounce", "bb_reversal",
    "supertrend", "macd_scalp", "combo_scalp",
}


# ── INDICATORS ────────────────────────────────────────────────────────────────
def _compute_vwap(df):
    import pandas as pd
    now_utc  = datetime.now(timezone.utc)
    midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    today    = df[df["open_time"] >= midnight].copy()
    if today.empty:
        return float(df["close"].iloc[-1])
    tp = (today["high"] + today["low"] + today["close"]) / 3
    return float((tp * today["volume"]).cumsum().iloc[-1] / today["volume"].cumsum().iloc[-1])


def _compute_ema(series, period):
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def _compute_rsi(series, period=14):
    """Standard Wilder's smoothed RSI."""
    delta  = series.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _compute_bollinger(series, period=20, num_std=2):
    """Returns (upper, mid, lower) as floats."""
    mid   = series.rolling(period).mean()
    std   = series.rolling(period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])


def _compute_atr(df, period=10):
    """Wilder's Average True Range."""
    import numpy as np
    high  = df["high"].values
    low   = df["low"].values
    close = df["close"].values
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.zeros(n)
    if period - 1 < n:
        atr[period - 1] = float(np.mean(tr[:period]))
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return float(atr[-1])


def _compute_supertrend(df, period=10, multiplier=3.0):
    """
    Returns (st_value, current_dir, prev_dir).
    dir: 1 = bullish (price above supertrend), -1 = bearish.
    Entry signal on direction flip.
    """
    import numpy as np
    high  = df["high"].values
    low   = df["low"].values
    close = df["close"].values
    n = len(close)

    # True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))

    # Wilder's ATR
    atr = np.zeros(n)
    if period - 1 < n:
        atr[period - 1] = float(np.mean(tr[:period]))
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period

    hl2 = (high + low) / 2.0
    raw_upper = hl2 + multiplier * atr
    raw_lower = hl2 - multiplier * atr

    upper     = raw_upper.copy()
    lower     = raw_lower.copy()
    direction = np.ones(n, dtype=int)
    st        = np.zeros(n)
    st[0]     = lower[0]

    for i in range(1, n):
        # Tighten bands — don't let them widen while price moves in same direction
        upper[i] = raw_upper[i] if raw_upper[i] < upper[i-1] or close[i-1] > upper[i-1] else upper[i-1]
        lower[i] = raw_lower[i] if raw_lower[i] > lower[i-1] or close[i-1] < lower[i-1] else lower[i-1]

        if direction[i-1] == 1:
            direction[i] = -1 if close[i] < lower[i] else 1
        else:
            direction[i] = 1 if close[i] > upper[i] else -1

        st[i] = lower[i] if direction[i] == 1 else upper[i]

    return float(st[-1]), int(direction[-1]), int(direction[-2] if n >= 2 else direction[-1])


def _compute_macd(series, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram_now, histogram_prev)."""
    ema_fast  = series.ewm(span=fast,   adjust=False).mean()
    ema_slow  = series.ewm(span=slow,   adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig_line  = macd_line.ewm(span=signal, adjust=False).mean()
    hist      = macd_line - sig_line
    return (
        float(macd_line.iloc[-1]),
        float(sig_line.iloc[-1]),
        float(hist.iloc[-1]),
        float(hist.iloc[-2]) if len(hist) >= 2 else 0.0,
    )


def _fetch_klines(client, symbol, interval, limit=500):
    import pandas as pd
    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df  = pd.DataFrame(raw, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_vol","trades","taker_base","taker_quote","ignore",
    ])
    for col in ("open","high","low","close","volume"):
        df[col] = df[col].astype(float)
    df["open_time"]  = pd.to_datetime(df["open_time"],  unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


def _get_key_levels(client, symbol):
    from binance.client import Client as BClient
    daily  = _fetch_klines(client, symbol, BClient.KLINE_INTERVAL_1DAY,  limit=3)
    weekly = _fetch_klines(client, symbol, BClient.KLINE_INTERVAL_1WEEK, limit=3)
    prev_day  = daily.iloc[-2]
    prev_week = weekly.iloc[-2]
    return {
        "PDH": float(prev_day["high"]),
        "PDL": float(prev_day["low"]),
        "PWH": float(prev_week["high"]),
        "PWL": float(prev_week["low"]),
    }


# ── STRATEGY: level_retest (original) ─────────────────────────────────────────
def _has_rejection_wick(candle, level, direction):
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = abs(c - o) or (h - l) * 0.1
    if direction == "long":
        return c > level and (min(o, c) - l) >= body * REJECTION_WICK_RATIO
    if direction == "short":
        return c < level and (h - max(o, c)) >= body * REJECTION_WICK_RATIO
    return False


def _check_entry_level_retest(candle, levels, vwap):
    low, high, close = candle["low"], candle["high"], candle["close"]
    for name, lvl in levels.items():
        tol = lvl * LEVEL_TOLERANCE_PCT
        if low <= lvl + tol and close > lvl and close > vwap:
            if _has_rejection_wick(candle, lvl, "long"):
                return "long", name, lvl
        if high >= lvl - tol and close < lvl and close < vwap:
            if _has_rejection_wick(candle, lvl, "short"):
                return "short", name, lvl
    return None, None, None


def _check_exit_level_retest(candle, position, ema):
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP_MINUTES:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    if direction == "long"  and close < ema:
        return True, "ema_cross"
    if direction == "short" and close > ema:
        return True, "ema_cross"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── STRATEGY: ema_pullback ─────────────────────────────────────────────────────
def _check_entry_ema_pullback(candle, ema9, ema21, rsi):
    low   = candle["low"]
    high  = candle["high"]
    close = candle["close"]

    if ema9 > ema21:
        if low <= ema9 * 1.0005 and close > ema9 + (ema9 * 0.0003) and rsi > 50:
            return "long", "EMA9", ema9
    elif ema9 < ema21:
        if high >= ema9 * 0.9995 and close < ema9 - (ema9 * 0.0003) and rsi < 50:
            return "short", "EMA9", ema9

    return None, None, None


def _check_exit_ema_pullback(candle, position):
    TIME_STOP = 20
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── STRATEGY: vwap_bounce ──────────────────────────────────────────────────────
def _check_entry_vwap_bounce(candle, vwap, rsi):
    low   = candle["low"]
    high  = candle["high"]
    close = candle["close"]
    open_ = candle["open"]

    if low <= vwap * 1.0005 and close > vwap and close > open_ and 40 <= rsi <= 60:
        return "long", "VWAP", vwap
    if high >= vwap * 0.9995 and close < vwap and close < open_ and 40 <= rsi <= 60:
        return "short", "VWAP", vwap

    return None, None, None


def _check_exit_vwap_bounce(candle, position):
    TIME_STOP = 15
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── STRATEGY: bb_reversal ──────────────────────────────────────────────────────
def _check_entry_bb_reversal(candle, bb_upper, bb_mid, bb_lower, rsi):
    close = candle["close"]

    if close < bb_lower and rsi < 35:
        return "long", "BB_LOWER", bb_lower
    if close > bb_upper and rsi > 65:
        return "short", "BB_UPPER", bb_upper

    return None, None, None


def _check_exit_bb_reversal(candle, position, bb_mid):
    TIME_STOP = 30
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    if direction == "long"  and close >= bb_mid:
        return True, "take_profit"
    if direction == "short" and close <= bb_mid:
        return True, "take_profit"
    return False, None


# ── STRATEGY: supertrend ────────────────────────────────────────────────────────
def _check_entry_supertrend(st_dir, st_prev_dir):
    """
    Entry on ATR supertrend direction flip.
    Long:  trend just turned bullish  (prev -1 → now +1)
    Short: trend just turned bearish  (prev +1 → now -1)
    """
    if st_prev_dir == -1 and st_dir == 1:
        return "long", "ST_BULL", None
    if st_prev_dir == 1 and st_dir == -1:
        return "short", "ST_BEAR", None
    return None, None, None


def _check_exit_supertrend(candle, position, st_dir):
    TIME_STOP = 15
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    # Exit when supertrend flips against us
    if direction == "long"  and st_dir == -1:
        return True, "st_flip"
    if direction == "short" and st_dir == 1:
        return True, "st_flip"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── STRATEGY: macd_scalp ────────────────────────────────────────────────────────
def _check_entry_macd_scalp(candle, macd_hist, macd_prev_hist, ema9, ema21, vwap):
    """
    Long:  MACD histogram crosses above zero + uptrend (EMA9 > EMA21) + price > VWAP
    Short: MACD histogram crosses below zero + downtrend (EMA9 < EMA21) + price < VWAP
    """
    close = candle["close"]
    if macd_hist > 0 and macd_prev_hist <= 0 and ema9 > ema21 and close > vwap:
        return "long", "MACD_X", None
    if macd_hist < 0 and macd_prev_hist >= 0 and ema9 < ema21 and close < vwap:
        return "short", "MACD_X", None
    return None, None, None


def _check_exit_macd_scalp(candle, position, macd_hist):
    TIME_STOP = 20
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    # Exit when MACD histogram flips against us
    if direction == "long"  and macd_hist < 0:
        return True, "macd_flip"
    if direction == "short" and macd_hist > 0:
        return True, "macd_flip"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── STRATEGY: combo_scalp ───────────────────────────────────────────────────────
def _check_entry_combo_scalp(candle, st_dir, st_prev_dir, macd_hist, macd_prev_hist, vwap, rsi):
    """
    High-confidence scalp requiring 3 confirmations:
      Long:  Supertrend bullish + MACD histogram just crossed above 0 + price > VWAP + RSI 40-65
      Short: Supertrend bearish + MACD histogram just crossed below 0 + price < VWAP + RSI 35-60

    Additionally fires if Supertrend just flipped direction and MACD is already on the right side.
    """
    close = candle["close"]

    # Long: supertrend bull, MACD hist crosses positive, price above VWAP
    long_macd_cross  = macd_hist > 0 and macd_prev_hist <= 0
    long_st_flip     = st_prev_dir == -1 and st_dir == 1 and macd_hist > 0
    if st_dir == 1 and (long_macd_cross or long_st_flip) and close > vwap and 40 <= rsi <= 65:
        trigger = "COMBO_ST+MACD↑" if long_macd_cross else "COMBO_ST_FLIP↑"
        return "long", trigger, None

    # Short: supertrend bear, MACD hist crosses negative, price below VWAP
    short_macd_cross = macd_hist < 0 and macd_prev_hist >= 0
    short_st_flip    = st_prev_dir == 1 and st_dir == -1 and macd_hist < 0
    if st_dir == -1 and (short_macd_cross or short_st_flip) and close < vwap and 35 <= rsi <= 60:
        trigger = "COMBO_ST+MACD↓" if short_macd_cross else "COMBO_ST_FLIP↓"
        return "short", trigger, None

    return None, None, None


def _check_exit_combo_scalp(candle, position, st_dir, macd_hist):
    TIME_STOP   = 20
    direction   = position["direction"]
    stop_level  = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time  = position["entry_time"]
    close       = float(candle["close"])
    candle_ts   = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP:
        return True, "time_stop"
    if direction == "long"  and close < stop_level:
        return True, "stop_loss"
    if direction == "short" and close > stop_level:
        return True, "stop_loss"
    # Exit when either confirmation flips against us
    if direction == "long"  and st_dir == -1:
        return True, "st_flip"
    if direction == "short" and st_dir == 1:
        return True, "st_flip"
    if direction == "long"  and macd_hist < 0:
        return True, "macd_flip"
    if direction == "short" and macd_hist > 0:
        return True, "macd_flip"
    if direction == "long"  and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    return False, None


# ── BOT ENGINE ────────────────────────────────────────────────────────────────
class BotCore:
    def __init__(self, symbol=None):
        self._symbol   = (symbol or SYMBOL).upper()
        self._lock     = threading.Lock()
        self._running  = False
        self._thread   = None
        self._strategy = STRATEGY
        self._state    = {
            "symbol":           self._symbol,
            "status":           "stopped",
            "strategy":         STRATEGY,
            "position":         None,
            "levels":           {},
            "vwap":             None,
            "ema":              None,
            "ema21":            None,
            "rsi":              None,
            "bb_upper":         None,
            "bb_mid":           None,
            "bb_lower":         None,
            # Supertrend
            "supertrend":       None,   # ST line value
            "supertrend_dir":   None,   # 1 = bull, -1 = bear
            # MACD
            "macd_line":        None,
            "macd_signal":      None,
            "macd_hist":        None,
            # ATR
            "atr":              None,
            "last_price":       None,
            "last_candle_time": None,
            "trade_log":        [],
            "started_at":       None,
            "error":            None,
            "testnet":          True,
            "pnl": {
                "total":         0.0,
                "wins":          0,
                "losses":        0,
                "total_trades":  0,
                "best_trade":    0.0,
                "worst_trade":   0.0,
                "history":       [],
                "starting_bal":  None,
                "current_bal":   None,
                "bal_pct_change": None,
            },
        }

    # ── PUBLIC API ────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._running:
                return {"ok": False, "message": "Already running"}
            self._running = True
            self._state["status"]     = "scanning"
            self._state["started_at"] = datetime.now(timezone.utc).isoformat()
            self._state["error"]      = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return {"ok": True, "message": "Bot started"}

    def stop(self):
        with self._lock:
            if not self._running:
                return {"ok": False, "message": "Not running"}
            self._running = False
            self._state["status"] = "stopped"
        return {"ok": True, "message": "Bot stopped"}

    def set_strategy(self, strategy):
        if strategy not in _VALID_STRATEGIES:
            return {"ok": False, "message": f"Unknown strategy: {strategy}. Valid: {sorted(_VALID_STRATEGIES)}"}
        with self._lock:
            self._strategy = strategy
            self._state["strategy"] = strategy
        return {"ok": True, "message": f"Strategy set to {strategy}"}

    def get_state(self):
        with self._lock:
            s = dict(self._state)
            if s["position"] and hasattr(s["position"].get("entry_time"), "isoformat"):
                s["position"] = dict(s["position"])
                s["position"]["entry_time"] = s["position"]["entry_time"].isoformat()
            return s

    # ── INTERNAL LOOP ─────────────────────────────────────────────────────────
    def _update(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def _add_log(self, msg, kind="info"):
        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "msg":  msg,
            "kind": kind,
        }
        with self._lock:
            self._state["trade_log"].insert(0, entry)
            self._state["trade_log"] = self._state["trade_log"][:MAX_LOG_ENTRIES]

    def _record_pnl(self, pnl, position, exit_price, reason):
        with self._lock:
            p = self._state["pnl"]
            p["total"]        = round(p["total"] + pnl, 2)
            p["total_trades"] += 1
            if pnl >= 0:
                p["wins"] += 1
            else:
                p["losses"] += 1
            p["best_trade"]  = round(max(p["best_trade"],  pnl), 2)
            p["worst_trade"] = round(min(p["worst_trade"], pnl), 2)
            p["history"].insert(0, {
                "direction":  position["direction"],
                "entry":      position["entry"],
                "exit":       round(exit_price, 2),
                "pnl":        round(pnl, 2),
                "reason":     reason,
                "level":      position["level_name"],
                "time":       datetime.now(timezone.utc).strftime("%H:%M:%S"),
            })
            p["history"] = p["history"][:50]

    def _refresh_balance(self, client, closed_pnl=None):
        with self._lock:
            p = self._state["pnl"]

            real_bal = None
            try:
                result = client.get_asset_balance(asset="USDT")
                if result and float(result.get("free", 0)) > 0:
                    real_bal = round(float(result["free"]), 2)
            except Exception:
                pass

            if p["starting_bal"] is None:
                p["starting_bal"] = real_bal if real_bal else PAPER_STARTING_BAL
                p["current_bal"]  = p["starting_bal"]
                p["mode"] = "live" if real_bal else "paper"
            elif closed_pnl is not None:
                if real_bal and p.get("mode") == "live":
                    p["current_bal"] = real_bal
                else:
                    p["current_bal"] = round(p["current_bal"] + closed_pnl, 2)

            if p["starting_bal"] and p["starting_bal"] > 0:
                p["bal_pct_change"] = round(
                    ((p["current_bal"] - p["starting_bal"]) / p["starting_bal"]) * 100, 2
                )

        return p["current_bal"]

    def _is_running(self):
        with self._lock:
            return self._running

    def _get_strategy(self):
        with self._lock:
            return self._strategy

    def _loop(self):
        try:
            from binance.client import Client
            from binance.exceptions import BinanceAPIException

            api_key    = os.environ.get("BINANCE_API_KEY", "")
            api_secret = os.environ.get("BINANCE_API_SECRET", "")
            testnet    = os.environ.get("BINANCE_TESTNET", "true").lower() != "false"

            if testnet:
                client = Client(api_key, api_secret, testnet=True)
                client.API_URL = "https://testnet.binance.vision/api"
            else:
                client = Client(api_key, api_secret)

            self._update(testnet=testnet)
            starting = self._refresh_balance(client)
            mode = self._state["pnl"].get("mode", "paper")
            self._add_log(
                f"Bot connected ({'TESTNET' if testnet else 'LIVE'}) | {mode.upper()} | Balance: ${starting:,.2f} USDT",
                "info",
            )

            position         = None
            last_candle_time = None

            while self._is_running():
                try:
                    strategy = self._get_strategy()

                    df = _fetch_klines(client, self._symbol, TIMEFRAME, limit=500)
                    last_closed = df.iloc[-2]
                    candle_time = last_closed["close_time"]

                    if candle_time == last_candle_time:
                        time.sleep(POLL_SECONDS)
                        continue
                    last_candle_time = candle_time

                    # ── Core indicators (always computed) ─────────────────────
                    df_closed    = df.iloc[:-1]           # all closed candles
                    close_series = df_closed["close"]
                    vwap  = _compute_vwap(df_closed)
                    ema9  = _compute_ema(close_series, EMA_PERIOD)
                    ema21 = _compute_ema(close_series, 21)
                    rsi   = _compute_rsi(close_series, period=14)
                    price = float(last_closed["close"])

                    bb_upper, bb_mid, bb_lower = _compute_bollinger(close_series, period=20, num_std=2)

                    # ── Scalping indicators (supertrend + MACD) ───────────────
                    atr_val                       = _compute_atr(df_closed, period=10)
                    st_value, st_dir, st_prev_dir = _compute_supertrend(df_closed, period=10, multiplier=3.0)
                    macd_line, macd_sig, macd_hist, macd_prev_hist = _compute_macd(close_series)

                    # ── Key levels (level_retest only) ─────────────────────────
                    levels = {}
                    if strategy == "level_retest":
                        levels = _get_key_levels(client, self._symbol)

                    self._update(
                        levels=levels,
                        strategy=strategy,
                        vwap=round(vwap, 2),
                        ema=round(ema9, 2),
                        ema21=round(ema21, 2),
                        rsi=round(rsi, 2),
                        bb_upper=round(bb_upper, 2),
                        bb_mid=round(bb_mid, 2),
                        bb_lower=round(bb_lower, 2),
                        supertrend=round(st_value, 2),
                        supertrend_dir=st_dir,
                        macd_line=round(macd_line, 4),
                        macd_signal=round(macd_sig, 4),
                        macd_hist=round(macd_hist, 4),
                        atr=round(atr_val, 2),
                        last_price=round(price, 2),
                        last_candle_time=candle_time.strftime("%H:%M UTC"),
                    )

                    # ── EXIT ──────────────────────────────────────────────────
                    if position:
                        if strategy == "level_retest":
                            should_exit, reason = _check_exit_level_retest(last_closed, position, ema9)
                        elif strategy == "ema_pullback":
                            should_exit, reason = _check_exit_ema_pullback(last_closed, position)
                        elif strategy == "vwap_bounce":
                            should_exit, reason = _check_exit_vwap_bounce(last_closed, position)
                        elif strategy == "bb_reversal":
                            should_exit, reason = _check_exit_bb_reversal(last_closed, position, bb_mid)
                        elif strategy == "supertrend":
                            should_exit, reason = _check_exit_supertrend(last_closed, position, st_dir)
                        elif strategy == "macd_scalp":
                            should_exit, reason = _check_exit_macd_scalp(last_closed, position, macd_hist)
                        elif strategy == "combo_scalp":
                            should_exit, reason = _check_exit_combo_scalp(last_closed, position, st_dir, macd_hist)
                        else:
                            should_exit, reason = False, None

                        if should_exit:
                            pnl = (
                                (price - position["entry"]) * position["qty"]
                                if position["direction"] == "long"
                                else (position["entry"] - price) * position["qty"]
                            )
                            self._add_log(
                                f"EXIT {position['direction'].upper()} @ {price:.2f} | {reason} | PnL {pnl:+.2f} USDT",
                                "exit",
                            )
                            self._record_pnl(pnl, position, price, reason)
                            self._refresh_balance(client, closed_pnl=pnl)
                            position = None
                            self._update(status="scanning", position=None)

                    # ── ENTRY ─────────────────────────────────────────────────
                    if not position:
                        direction, lvl_name, lvl_price = None, None, None

                        if strategy == "level_retest":
                            direction, lvl_name, lvl_price = _check_entry_level_retest(last_closed, levels, vwap)
                        elif strategy == "ema_pullback":
                            direction, lvl_name, lvl_price = _check_entry_ema_pullback(last_closed, ema9, ema21, rsi)
                        elif strategy == "vwap_bounce":
                            direction, lvl_name, lvl_price = _check_entry_vwap_bounce(last_closed, vwap, rsi)
                        elif strategy == "bb_reversal":
                            direction, lvl_name, lvl_price = _check_entry_bb_reversal(last_closed, bb_upper, bb_mid, bb_lower, rsi)
                        elif strategy == "supertrend":
                            direction, lvl_name, _ = _check_entry_supertrend(st_dir, st_prev_dir)
                            lvl_price = st_value
                        elif strategy == "macd_scalp":
                            direction, lvl_name, _ = _check_entry_macd_scalp(last_closed, macd_hist, macd_prev_hist, ema9, ema21, vwap)
                            lvl_price = macd_line
                        elif strategy == "combo_scalp":
                            direction, lvl_name, _ = _check_entry_combo_scalp(last_closed, st_dir, st_prev_dir, macd_hist, macd_prev_hist, vwap, rsi)
                            lvl_price = st_value

                        if direction:
                            entry = price

                            # Strategy-specific stop distances
                            if strategy == "level_retest":
                                stop = lvl_price * (0.9995 if direction == "long" else 1.0005)
                            elif strategy == "ema_pullback":
                                stop = entry * (0.998 if direction == "long" else 1.002)
                            elif strategy == "vwap_bounce":
                                stop = entry * (0.9985 if direction == "long" else 1.0015)
                            elif strategy == "bb_reversal":
                                stop = entry * (0.9975 if direction == "long" else 1.0025)
                            elif strategy in ("supertrend", "macd_scalp", "combo_scalp"):
                                # ATR-based stop: 1.5x ATR from entry
                                stop = (entry - 1.5 * atr_val) if direction == "long" else (entry + 1.5 * atr_val)
                            else:
                                stop = entry * (0.999 if direction == "long" else 1.001)

                            risk = abs(entry - stop)

                            if risk > 0:
                                with self._lock:
                                    bal = self._state["pnl"]["current_bal"] or PAPER_STARTING_BAL
                                qty = (bal * RISK_PCT) / risk

                                if strategy == "bb_reversal":
                                    tp = bb_mid
                                else:
                                    tp = (
                                        entry + risk * RR_RATIO
                                        if direction == "long"
                                        else entry - risk * RR_RATIO
                                    )

                                position = {
                                    "direction":   direction,
                                    "entry":       round(entry, 2),
                                    "stop_level":  round(stop, 2),
                                    "take_profit": round(tp, 2),
                                    "qty":         round(qty, 6),
                                    "level_name":  lvl_name,
                                    "entry_time":  candle_time,
                                }
                                self._update(status="in_trade", position=dict(position))
                                self._add_log(
                                    f"[{strategy}] ENTRY {direction.upper()} @ {entry:.2f} | {lvl_name} | SL {stop:.2f} | TP {tp:.2f} | ATR {atr_val:.2f}",
                                    "trade",
                                )
                            else:
                                self._add_log(f"Signal @ {lvl_name} skipped — zero risk distance", "info")
                        else:
                            st_label = "↑ BULL" if st_dir == 1 else "↓ BEAR"
                            macd_label = f"MACD {macd_hist:+.1f}"
                            self._add_log(
                                f"[{strategy}] Scanning | {self._symbol} {price:.2f} | VWAP {vwap:.2f} | EMA9 {ema9:.2f} | RSI {rsi:.1f} | ST {st_label} | {macd_label}",
                                "info",
                            )

                except BinanceAPIException as e:
                    self._add_log(f"Binance error: {e}", "error")
                    time.sleep(30)
                except Exception as e:
                    self._add_log(f"Error: {e}", "error")
                    time.sleep(30)

                time.sleep(POLL_SECONDS)

        except Exception as e:
            self._update(status="error", error=str(e))
            self._add_log(f"Fatal: {e}", "error")
        finally:
            with self._lock:
                self._running = False
                if self._state["status"] not in ("stopped", "error"):
                    self._state["status"] = "stopped"


# Singleton — imported by server.py
bot = BotCore()


class BotRegistry:
    """Manages multiple BotCore instances keyed by trading symbol."""

    def __init__(self):
        self._bots = {}        # symbol -> BotCore instance
        self._lock = threading.Lock()

    def add(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            if symbol in self._bots:
                return {"ok": False, "message": f"{symbol} already running"}
            b = BotCore(symbol=symbol)
            self._bots[symbol] = b
        return {"ok": True, "message": f"Added {symbol}"}

    def remove(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            b = self._bots.pop(symbol, None)
        if b:
            b.stop()
            return {"ok": True, "message": f"Removed {symbol}"}
        return {"ok": False, "message": f"{symbol} not found"}

    def get(self, symbol):
        return self._bots.get(symbol.upper())

    def list_symbols(self):
        with self._lock:
            return list(self._bots.keys())

    def get_all_states(self):
        with self._lock:
            bots = dict(self._bots)
        return {sym: b.get_state() for sym, b in bots.items()}


registry = BotRegistry()
