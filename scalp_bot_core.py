#!/usr/bin/env python3
"""
scalp_bot_core.py — BTC/USDT momentum scalp bot engine for Option Riders
Runs as a background thread inside server.py
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
RISK_PCT = 0.01
RR_RATIO = 1.5
FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
VOLUME_LOOKBACK = 20
VOLUME_MULTIPLIER = 1.15
TIME_STOP_MINUTES = 12
POLL_SECONDS = 15
MAX_LOG_ENTRIES = 50
LEDGER_PATH = Path(__file__).parent / "data" / "scalp_bot_trade_ledger.json"


def _fetch_klines(client, symbol, interval, limit=500):
    import pandas as pd

    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


def _compute_vwap(df):
    now_utc = datetime.now(timezone.utc)
    midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    today = df[df["open_time"] >= midnight].copy()
    if today.empty:
        return float(df["close"].iloc[-1])
    tp = (today["high"] + today["low"] + today["close"]) / 3
    return float((tp * today["volume"]).cumsum().iloc[-1] / today["volume"].cumsum().iloc[-1])


def _compute_ema(series, period):
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def _compute_rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _compute_atr(df, period):
    prev_close = df["close"].shift(1)
    tr = (df["high"] - df["low"]).combine((df["high"] - prev_close).abs(), max).combine((df["low"] - prev_close).abs(), max)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return float(atr.iloc[-1])


def _volume_confirmation(df):
    recent = df["volume"].iloc[:-1]
    if len(recent) < VOLUME_LOOKBACK + 1:
        return False, 0.0, 0.0
    current_volume = float(recent.iloc[-1])
    baseline = float(recent.iloc[-(VOLUME_LOOKBACK + 1):-1].mean())
    return current_volume >= baseline * VOLUME_MULTIPLIER, current_volume, baseline


def _check_entry(df, vwap):
    closes = df["close"].iloc[:-1]
    if len(closes) < max(SLOW_EMA_PERIOD, RSI_PERIOD, ATR_PERIOD) + 3:
        return None

    fast_series = closes.ewm(span=FAST_EMA_PERIOD, adjust=False).mean()
    slow_series = closes.ewm(span=SLOW_EMA_PERIOD, adjust=False).mean()
    fast = float(fast_series.iloc[-1])
    slow = float(slow_series.iloc[-1])
    prev_fast = float(fast_series.iloc[-2])
    prev_slow = float(slow_series.iloc[-2])
    price = float(closes.iloc[-1])
    candle = df.iloc[-2]
    rsi = _compute_rsi(closes, RSI_PERIOD)
    atr = _compute_atr(df.iloc[:-1], ATR_PERIOD)
    volume_ok, current_volume, baseline_volume = _volume_confirmation(df)

    crossed_up = prev_fast <= prev_slow and fast > slow
    crossed_down = prev_fast >= prev_slow and fast < slow

    if crossed_up and price > vwap and 52 <= rsi <= 72 and volume_ok:
        return {
            "direction": "long",
            "signal_name": "EMA/VWAP Momentum Long",
            "entry_price": price,
            "stop_level": price - atr,
            "take_profit": price + atr * RR_RATIO,
            "atr": atr,
            "rsi": rsi,
            "fast_ema": fast,
            "slow_ema": slow,
            "candle_time": candle["close_time"],
            "volume": current_volume,
            "volume_baseline": baseline_volume,
        }

    if crossed_down and price < vwap and 28 <= rsi <= 48 and volume_ok:
        return {
            "direction": "short",
            "signal_name": "EMA/VWAP Momentum Short",
            "entry_price": price,
            "stop_level": price + atr,
            "take_profit": price - atr * RR_RATIO,
            "atr": atr,
            "rsi": rsi,
            "fast_ema": fast,
            "slow_ema": slow,
            "candle_time": candle["close_time"],
            "volume": current_volume,
            "volume_baseline": baseline_volume,
        }

    return None


def _check_exit(candle, position, fast_ema, slow_ema, rsi):
    direction = position["direction"]
    stop_level = position["stop_level"]
    take_profit = position["take_profit"]
    entry_time = position["entry_time"]
    close = float(candle["close"])
    candle_ts = candle["close_time"]

    elapsed = (candle_ts - entry_time).total_seconds() / 60
    if elapsed >= TIME_STOP_MINUTES:
        return True, "time_stop"
    if direction == "long" and close <= stop_level:
        return True, "stop_loss"
    if direction == "short" and close >= stop_level:
        return True, "stop_loss"
    if direction == "long" and close >= take_profit:
        return True, "take_profit"
    if direction == "short" and close <= take_profit:
        return True, "take_profit"
    if direction == "long" and (fast_ema < slow_ema or rsi < 48):
        return True, "momentum_fade"
    if direction == "short" and (fast_ema > slow_ema or rsi > 52):
        return True, "momentum_fade"
    return False, None


class ScalpBotCore:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._closed_trades = self._load_closed_trades()
        self._state = {
            "status": "stopped",
            "position": None,
            "levels": {},
            "vwap": None,
            "ema": None,
            "last_price": None,
            "last_candle_time": None,
            "trade_log": [],
            "started_at": None,
            "error": None,
            "testnet": True,
            "execution_mode": "paper",
            "performance": self._build_performance(),
            "trade_history": list(self._closed_trades[-12:][::-1]),
            "strategy_name": "EMA + VWAP + RSI momentum scalp",
        }

    def start(self):
        with self._lock:
            if self._running:
                return {"ok": False, "message": "Already running"}
            self._running = True
            self._state["status"] = "scanning"
            self._state["started_at"] = datetime.now(timezone.utc).isoformat()
            self._state["error"] = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return {"ok": True, "message": "Scalp bot started"}

    def stop(self):
        with self._lock:
            if not self._running:
                return {"ok": False, "message": "Not running"}
            self._running = False
            self._state["status"] = "stopped"
        return {"ok": True, "message": "Scalp bot stopped"}

    def get_state(self):
        with self._lock:
            state = dict(self._state)
            if state["position"] and hasattr(state["position"].get("entry_time"), "isoformat"):
                state["position"] = dict(state["position"])
                state["position"]["entry_time"] = state["position"]["entry_time"].isoformat()
            return state

    def _load_closed_trades(self):
        try:
            if not LEDGER_PATH.exists():
                return []
            payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
            closed = payload.get("closed_trades", [])
            return closed if isinstance(closed, list) else []
        except Exception:
            return []

    def _persist_closed_trades(self):
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "closed_trades": self._closed_trades,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        LEDGER_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _build_performance(self):
        trades = list(self._closed_trades)
        realized = round(sum(float(trade.get("pnl", 0.0)) for trade in trades), 2)
        wins = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) > 0)
        losses = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) < 0)
        total = len(trades)
        win_rate = round((wins / total) * 100, 1) if total else 0.0
        last_pnl = round(float(trades[-1].get("pnl", 0.0)), 2) if trades else 0.0
        return {
            "realized_pnl": realized,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "last_pnl": last_pnl,
        }

    def _refresh_history_state(self):
        self._state["performance"] = self._build_performance()
        self._state["trade_history"] = list(self._closed_trades[-12:][::-1])

    def _record_closed_trade(self, position, exit_price, reason, pnl):
        record = {
            "id": position.get("id"),
            "direction": position.get("direction"),
            "level_name": position.get("level_name"),
            "entry": round(float(position.get("entry", 0.0)), 2),
            "exit": round(float(exit_price), 2),
            "qty": round(float(position.get("qty", 0.0)), 6),
            "entry_time": position.get("entry_time").isoformat() if hasattr(position.get("entry_time"), "isoformat") else position.get("entry_time"),
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "pnl": round(float(pnl), 2),
            "reason": reason,
            "execution_mode": self._state.get("execution_mode", "paper"),
        }
        self._closed_trades.append(record)
        self._closed_trades = self._closed_trades[-250:]
        self._persist_closed_trades()
        self._refresh_history_state()

    def _update(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def _add_log(self, msg, kind="info"):
        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "msg": msg,
            "kind": kind,
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

            api_key = os.environ.get("BINANCE_API_KEY", "")
            api_secret = os.environ.get("BINANCE_API_SECRET", "")
            testnet = os.environ.get("BINANCE_TESTNET", "true").lower() != "false"
            execution_mode = os.environ.get("SCALP_BOT_EXECUTION_MODE", "paper").strip().lower() or "paper"

            if testnet:
                client = Client(api_key, api_secret, testnet=True)
                client.API_URL = "https://testnet.binance.vision/api"
            else:
                client = Client(api_key, api_secret)

            self._update(testnet=testnet, execution_mode=execution_mode)
            self._refresh_history_state()
            self._add_log(
                f"Scalp bot connected ({'TESTNET' if testnet else 'LIVE'}) | mode {execution_mode.upper()}",
                "info",
            )

            position = None
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

                    vwap = _compute_vwap(df.iloc[:-1])
                    closes = df["close"].iloc[:-1]
                    fast = _compute_ema(closes, FAST_EMA_PERIOD)
                    slow = _compute_ema(closes, SLOW_EMA_PERIOD)
                    rsi = _compute_rsi(closes, RSI_PERIOD)
                    atr = _compute_atr(df.iloc[:-1], ATR_PERIOD)
                    price = float(last_closed["close"])
                    volume_ok, current_volume, baseline_volume = _volume_confirmation(df)

                    self._update(
                        levels={
                            "Fast EMA": round(fast, 2),
                            "Slow EMA": round(slow, 2),
                            "ATR": round(atr, 2),
                            "RSI": round(rsi, 2),
                        },
                        vwap=round(vwap, 2),
                        ema=round(fast, 2),
                        last_price=round(price, 2),
                        last_candle_time=candle_time.strftime("%H:%M UTC"),
                    )

                    if position:
                        should_exit, reason = _check_exit(last_closed, position, fast, slow, rsi)
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
                            self._record_closed_trade(position, price, reason, pnl)
                            position = None
                            self._update(status="scanning", position=None)

                    if not position:
                        signal = _check_entry(df, vwap)
                        if signal:
                            balance = float(client.get_asset_balance(asset="USDT")["free"])
                            risk = abs(signal["entry_price"] - signal["stop_level"])
                            if risk > 0:
                                qty = (balance * RISK_PCT) / risk
                                position = {
                                    "id": f"scalp-{int(signal['candle_time'].timestamp())}",
                                    "direction": signal["direction"],
                                    "entry": round(signal["entry_price"], 2),
                                    "stop_level": round(signal["stop_level"], 2),
                                    "take_profit": round(signal["take_profit"], 2),
                                    "qty": round(qty, 6),
                                    "level_name": signal["signal_name"],
                                    "entry_time": signal["candle_time"],
                                }
                                self._update(status="in_trade", position=dict(position))
                                self._add_log(
                                    f"ENTRY {signal['direction'].upper()} @ {signal['entry_price']:.2f} | RSI {signal['rsi']:.1f} | vol {signal['volume']:.0f}/{signal['volume_baseline']:.0f}",
                                    "trade",
                                )
                            else:
                                self._add_log("Momentum signal skipped — zero risk distance", "info")
                        else:
                            self._add_log(
                                f"Scanning | BTC {price:.2f} | VWAP {vwap:.2f} | 9/21 EMA {fast:.2f}/{slow:.2f} | RSI {rsi:.1f} | vol {'OK' if volume_ok else 'light'}",
                                "info",
                            )

                except BinanceAPIException as exc:
                    self._add_log(f"Binance error: {exc}", "error")
                    time.sleep(30)
                except Exception as exc:
                    self._add_log(f"Error: {exc}", "error")
                    time.sleep(30)

                time.sleep(POLL_SECONDS)

        except Exception as exc:
            self._update(status="error", error=str(exc))
            self._add_log(f"Fatal: {exc}", "error")
        finally:
            with self._lock:
                self._running = False
                if self._state["status"] not in ("stopped", "error"):
                    self._state["status"] = "stopped"


bot = ScalpBotCore()
