#!/usr/bin/env python3
"""
bot_core.py — BTC/USDT retest bot engine for Option Riders
Runs as a background thread inside server.py
"""

import os
import time
import threading
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── SETTINGS (overridden by .env) ─────────────────────────────────────────────
SYMBOL               = "BTCUSDT"
TIMEFRAME            = "3m"   # Binance doesn't support 2m — 3m is the closest
RISK_PCT             = 0.02
RR_RATIO             = 2.0
EMA_PERIOD           = 9
LEVEL_TOLERANCE_PCT  = 0.001
REJECTION_WICK_RATIO = 1.5
TIME_STOP_MINUTES    = 25
POLL_SECONDS         = 15
MAX_LOG_ENTRIES      = 50


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


def _has_rejection_wick(candle, level, direction):
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = abs(c - o) or (h - l) * 0.1
    if direction == "long":
        return c > level and (min(o, c) - l) >= body * REJECTION_WICK_RATIO
    if direction == "short":
        return c < level and (h - max(o, c)) >= body * REJECTION_WICK_RATIO
    return False


def _check_entry(candle, levels, vwap):
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


def _check_exit(candle, position, ema):
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


# ── BOT ENGINE ────────────────────────────────────────────────────────────────
class BotCore:
    def __init__(self):
        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None
        self._state   = {
            "status":          "stopped",   # stopped | scanning | in_trade | error
            "position":        None,
            "levels":          {},
            "vwap":            None,
            "ema":             None,
            "last_price":      None,
            "last_candle_time": None,
            "trade_log":       [],
            "started_at":      None,
            "error":           None,
            "testnet":         True,
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

    def get_state(self):
        with self._lock:
            s = dict(self._state)
            # convert position entry_time to ISO string for JSON
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
            "kind": kind,   # info | signal | trade | exit | error
        }
        with self._lock:
            self._state["trade_log"].insert(0, entry)
            self._state["trade_log"] = self._state["trade_log"][:MAX_LOG_ENTRIES]

    def _is_running(self):
        with self._lock:
            return self._running

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
            self._add_log(f"Bot connected ({'TESTNET' if testnet else 'LIVE'})", "info")

            position         = None
            last_candle_time = None

            while self._is_running():
                try:
                    df = _fetch_klines(client, SYMBOL, TIMEFRAME, limit=500)
                    last_closed = df.iloc[-2]
                    candle_time = last_closed["close_time"]

                    if candle_time == last_candle_time:
                        time.sleep(POLL_SECONDS)
                        continue
                    last_candle_time = candle_time

                    levels = _get_key_levels(client, SYMBOL)
                    vwap   = _compute_vwap(df.iloc[:-1])
                    ema    = _compute_ema(df["close"].iloc[:-1], EMA_PERIOD)
                    price  = float(last_closed["close"])

                    self._update(
                        levels=levels,
                        vwap=round(vwap, 2),
                        ema=round(ema, 2),
                        last_price=round(price, 2),
                        last_candle_time=candle_time.strftime("%H:%M UTC"),
                    )

                    # ── EXIT ──────────────────────────────────────────────────
                    if position:
                        should_exit, reason = _check_exit(last_closed, position, ema)
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
                            position = None
                            self._update(status="scanning", position=None)

                    # ── ENTRY ─────────────────────────────────────────────────
                    if not position:
                        direction, lvl_name, lvl_price = _check_entry(last_closed, levels, vwap)
                        if direction:
                            entry = price
                            stop  = lvl_price * (0.9995 if direction == "long" else 1.0005)
                            risk  = abs(entry - stop)
                            if risk > 0:
                                bal = float(client.get_asset_balance(asset="USDT")["free"])
                                qty = (bal * RISK_PCT) / risk
                                tp  = entry + risk * RR_RATIO if direction == "long" else entry - risk * RR_RATIO

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
                                    f"ENTRY {direction.upper()} @ {entry:.2f} | {lvl_name} | SL {stop:.2f} | TP {tp:.2f}",
                                    "trade",
                                )
                            else:
                                self._add_log(f"Signal @ {lvl_name} skipped — zero risk distance", "info")
                        else:
                            self._add_log(
                                f"Scanning | BTC {price:.2f} | VWAP {vwap:.2f} | EMA {ema:.2f}",
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
