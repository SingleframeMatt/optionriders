#!/usr/bin/env python3
"""
market_data.py — Live market data engine for Option Riders.

Fetches daily OHLCV from Yahoo Finance (yfinance), computes RSI(14), ATR(14),
SMA(20/50), pivot-based support/resistance, bias score, and auto-generates
trade setups and watchlist rankings. Results are cached for CACHE_TTL_SECONDS
to avoid hammering Yahoo on every page load.
"""

import threading
import time

CACHE_TTL_SECONDS = 300  # refresh every 5 minutes

_cache_lock = threading.Lock()
_cache = {"expires_at": 0.0, "payload": None}

TICKERS = [
    "SPY", "QQQ", "NVDA", "MU", "META", "AVGO",
    "AMD", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN",
]

TICKER_NAMES = {
    "SPY":  "S&P 500 ETF",
    "QQQ":  "Nasdaq 100 ETF",
    "NVDA": "NVIDIA",
    "MU":   "Micron",
    "META": "Meta Platforms",
    "AVGO": "Broadcom",
    "AMD":  "AMD",
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "MSFT": "Microsoft",
    "GOOGL":"Alphabet",
    "AMZN": "Amazon",
    "ES":   "S&P 500 Futures",
    "NQ":   "Nasdaq Futures",
}

# Futures symbols for yfinance (mapped to short keys for the front-end)
INDEX_FUTURES = [("ES=F", "ES"), ("NQ=F", "NQ")]


# ─── Technical indicators ──────────────────────────────────────────────────────

def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + avg_g / avg_l), 1)


def _atr(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return 0.0
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]))
        for i in range(1, len(highs))
    ]
    val = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        val = (val * (period - 1) + trs[i]) / period
    return round(val, 2)


def _sma(values, period):
    if len(values) < period:
        return values[-1] if values else 0.0
    return sum(values[-period:]) / period


def _levels(highs, lows, price, n=3):
    """Pivot-based support & resistance from the last 30 bars."""
    h = highs[-30:] if len(highs) >= 30 else highs
    l = lows[-30:]  if len(lows)  >= 30 else lows

    swing_highs, swing_lows = [], []
    for i in range(2, len(h) - 2):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            swing_highs.append(round(h[i], 2))
    for i in range(2, len(l) - 2):
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
            swing_lows.append(round(l[i], 2))

    resistance = sorted([x for x in swing_highs if x > price * 1.001])[:n]
    support    = sorted([x for x in swing_lows  if x < price * 0.999], reverse=True)[:n]

    step = (max(h) - min(l)) / max(len(h), 1)
    while len(resistance) < n:
        resistance.append(round((resistance[-1] if resistance else price) + step, 2))
    while len(support) < n:
        support.append(round((support[-1] if support else price) - step, 2))

    return support[:n], resistance[:n]


def _bias(rsi, price, sma20, sma50):
    score = 0
    if   rsi > 65: score += 2
    elif rsi > 55: score += 1
    elif rsi < 35: score -= 2
    elif rsi < 45: score -= 1
    score += 1 if price > sma20 else -1
    score += 1 if price > sma50 else -1
    if   score >= 3:  return "Bullish"
    elif score >= 1:  return "Neutral → Bullish"
    elif score <= -3: return "Bearish"
    elif score <= -1: return "Bearish → Neutral"
    else:             return "Range"


def _strategy(bias, rsi):
    if rsi < 35: return "Oversold Bounce"
    if rsi > 70: return "Overbought Short"
    return {
        "Bullish":           "Momentum Breakout",
        "Neutral → Bullish": "Pullback Long",
        "Range":             "Range Fade",
        "Bearish → Neutral": "Breakdown Short",
        "Bearish":           "Breakdown Short",
    }.get(bias, "Range Fade")


# ─── Entry builder ─────────────────────────────────────────────────────────────

def _build_entry(rank, symbol, name, opens, highs, lows, closes):
    if len(closes) < 22:
        return None

    price      = closes[-1]
    prev_close = closes[-2]
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    rsi_val  = _rsi(closes)
    atr_val  = _atr(highs, lows, closes)
    atr_pct  = round(atr_val / price * 100, 2) if price else 0.0
    sma20    = _sma(closes, 20)
    sma50    = _sma(closes, 50)

    support, resistance = _levels(highs, lows, price)
    bias_str  = _bias(rsi_val, price, sma20, sma50)
    strat_str = _strategy(bias_str, rsi_val)

    bull_trig = f"Break above {resistance[0]}" if resistance else f"Reclaim {round(price * 1.01, 2)}"
    bear_trig = f"Lose {support[0]}"           if support    else f"Break below {round(price * 0.99, 2)}"

    if "Bullish" in bias_str:
        call_s = int(resistance[0]) if resistance else int(price * 1.02)
        put_s  = int(support[0])    if support    else int(price * 0.98)
        opts   = f"Calls or {call_s}c above breakout; put spreads below {put_s}"
    elif "Bearish" in bias_str:
        put_s  = int(support[0])    if support    else int(price * 0.98)
        call_s = int(resistance[0]) if resistance else int(price * 1.02)
        opts   = f"Put spreads {put_s}/{int(put_s * 0.97)}; calls above {call_s}"
    else:
        opts = "Iron condor around current range"

    rsi_note = (
        "oversold — watch for bounce"      if rsi_val < 35 else
        "overbought — watch for reversal"  if rsi_val > 70 else
        "neutral"
    )
    summary = (
        f"{symbol} at ${price:.2f} ({change_pct:+.2f}%). "
        f"RSI {rsi_val} — {rsi_note}. "
        f"{bull_trig} to turn bullish; {bear_trig} for downside."
    )

    n_bars = min(35, len(opens))
    ohlcv  = [
        [round(opens[-n_bars + i], 2), round(highs[-n_bars + i], 2),
         round(lows[-n_bars + i], 2),  round(closes[-n_bars + i], 2)]
        for i in range(n_bars)
    ]

    return {
        "rank":        rank,
        "ticker":      symbol,
        "name":        name,
        "price":       round(price, 2),
        "friChange":   change_pct,
        "ahPrice":     round(price, 2),
        "ahChange":    0.0,
        "bias":        bias_str,
        "star":        rank <= 3,
        "rsi":         rsi_val,
        "atr":         atr_val,
        "atrPct":      atr_pct,
        "prevDayHigh": round(highs[-2], 2) if len(highs) >= 2 else round(highs[-1], 2),
        "prevDayLow":  round(lows[-2],  2) if len(lows)  >= 2 else round(lows[-1],  2),
        "fiveDayHigh": round(max(highs[-5:]), 2) if len(highs) >= 5 else round(max(highs), 2),
        "fiveDayLow":  round(min(lows[-5:]),  2) if len(lows)  >= 5 else round(min(lows),  2),
        "support":     support,
        "resistance":  resistance,
        "bullTrigger": bull_trig,
        "bearTrigger": bear_trig,
        "strategy":    strat_str,
        "optionsIdea": opts,
        "expectedMove": f"±${atr_val:.2f} ({atr_pct:.1f}%)",
        "summary":     summary,
        "sma20":       round(sma20, 2),
        "sma50":       round(sma50, 2),
        "liveData":    True,
        "_ohlcv":      ohlcv,   # stripped out before JSON response
    }


def _build_watchlist(ticker_entries):
    """Rank tickers by signal strength and auto-generate trade setups."""
    items = []
    for e in ticker_entries:
        if not e:
            continue
        bias   = e.get("bias", "Range")
        rsi    = e.get("rsi", 50)
        sup    = e.get("support", [])
        res    = e.get("resistance", [])
        price  = e.get("price", 0)
        atr    = e.get("atr", 0)

        if "Bullish" in bias:
            direction = "LONG"
            entry_lv  = f"Above {res[0]}" if res else f"Above {round(price, 2)}"
            target    = f"{res[1]}-{res[2]}" if len(res) >= 3 else str(round(price + atr, 2))
            stop      = str(sup[0])          if sup        else str(round(price - atr, 2))
            catalyst  = "Bullish momentum + technical breakout"
        elif "Bearish" in bias:
            direction = "SHORT"
            entry_lv  = f"Below {sup[0]}" if sup else f"Below {round(price, 2)}"
            target    = f"{sup[1]}-{sup[2]}" if len(sup) >= 3 else str(round(price - atr, 2))
            stop      = str(res[0])           if res        else str(round(price + atr, 2))
            catalyst  = "Bearish momentum + technical breakdown"
        else:
            continue   # skip range-bound for watchlist

        items.append({
            "ticker":    e["ticker"],
            "direction": direction,
            "entry":     entry_lv,
            "target":    target,
            "stop":      stop,
            "catalyst":  catalyst,
            "_strength": abs(rsi - 50),
        })

    items.sort(key=lambda x: x["_strength"], reverse=True)
    result = []
    for i, item in enumerate(items[:7], 1):
        item["rank"] = i
        del item["_strength"]
        result.append(item)
    return result


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_market_data():
    """
    Return live market data with computed indicators.
    Cached for CACHE_TTL_SECONDS to avoid excessive Yahoo Finance calls.
    """
    now = time.time()
    with _cache_lock:
        if _cache["payload"] and _cache["expires_at"] > now:
            return _cache["payload"]

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. "
            "Run: pip install yfinance --break-system-packages"
        )

    all_yf_symbols = TICKERS + [yf_sym for yf_sym, _ in INDEX_FUTURES]

    raw = yf.download(
        all_yf_symbols,
        period="90d",
        interval="1d",
        progress=False,
        auto_adjust=True,
    )

    def series(field, symbol):
        try:
            if hasattr(raw.columns, "levels"):
                return list(raw[field][symbol].dropna().astype(float))
            return list(raw[field].dropna().astype(float))
        except Exception:
            return []

    # ── Main tickers ─────────────────────────────────────────────
    ticker_entries = []
    for rank, sym in enumerate(TICKERS, 1):
        try:
            o = series("Open",  sym)
            h = series("High",  sym)
            l = series("Low",   sym)
            c = series("Close", sym)
            if len(c) < 22:
                continue
            entry = _build_entry(rank, sym, TICKER_NAMES.get(sym, sym), o, h, l, c)
            if entry:
                ticker_entries.append(entry)
        except Exception as exc:
            print(f"[market_data] {sym}: {exc}")

    # ── Index / futures entries ───────────────────────────────────
    index_entries = []
    # SPY and QQQ reuse their already-computed ticker_entries
    for sym in ("SPY", "QQQ"):
        e = next((t for t in ticker_entries if t["ticker"] == sym), None)
        if e:
            index_entries.append(e)

    for yf_sym, short_key in INDEX_FUTURES:
        try:
            o = series("Open",  yf_sym)
            h = series("High",  yf_sym)
            l = series("Low",   yf_sym)
            c = series("Close", yf_sym)
            if len(c) < 22:
                continue
            entry = _build_entry(0, short_key, TICKER_NAMES.get(short_key, short_key), o, h, l, c)
            if entry:
                index_entries.append(entry)
        except Exception as exc:
            print(f"[market_data] {yf_sym}: {exc}")

    # ── Auto-generate watchlist ───────────────────────────────────
    watchlist = _build_watchlist(ticker_entries)

    # ── Build chartData map and strip _ohlcv from entries ─────────
    chart_data = {}
    all_entries = ticker_entries + [
        e for e in index_entries if e["ticker"] not in ("SPY", "QQQ")
    ]
    for entry in all_entries:
        chart_data[entry["ticker"]] = entry.pop("_ohlcv", [])
    # SPY/QQQ ohlcv was already popped above via the same object reference
    for e in index_entries:
        if "_ohlcv" in e:
            chart_data[e["ticker"]] = e.pop("_ohlcv")

    payload = {
        "tickers":   ticker_entries,
        "indexes":   index_entries,
        "watchlist": watchlist,
        "chartData": chart_data,
        "updatedAt": int(now),
        "liveData":  True,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = now + CACHE_TTL_SECONDS

    return payload
