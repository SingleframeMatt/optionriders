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


def _ema(values, period):
    """Exponential moving average — uses full history for warmup."""
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _macd_histogram(closes, fast=12, slow=26, sig=9):
    """
    MACD histogram = MACD line − signal line.
    Positive → bullish momentum, negative → bearish.
    Returns 0 if insufficient data.
    """
    min_bars = slow + sig + 5
    if len(closes) < min_bars:
        return 0.0

    # Build MACD line over the last (sig * 3) bars for signal line warmup
    lookback = sig * 3
    macd_series = []
    start = max(slow - 1, len(closes) - lookback - slow)
    for i in range(start, len(closes)):
        window = closes[:i + 1]
        macd_series.append(_ema(window[-fast * 3:], fast) - _ema(window[-slow * 2:], slow))

    if len(macd_series) < sig:
        return 0.0

    signal_line = _ema(macd_series, sig)
    return macd_series[-1] - signal_line


def _volume_ratio(volumes):
    """
    Current volume / 20-day average volume.
    Returns 1.0 (neutral) if insufficient data.
    """
    if not volumes or len(volumes) < 21:
        return 1.0
    avg = sum(volumes[-21:-1]) / 20
    return (volumes[-1] / avg) if avg > 0 else 1.0


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


def _signal_score(rsi, price, sma20, sma50, closes, volumes=None, spy_closes=None):
    """
    Composite signal score from -100 (strong sell) to +100 (strong buy).

    Components:
      RSI momentum       : ±30   (deviation from neutral 50)
      Price vs SMA20     : ±15   (% distance above/below)
      Price vs SMA50     : ±15   (% distance above/below)
      5d vs 20d momentum : ±15   (short-term acceleration)
      MACD histogram     : ±15   (crossover momentum)
      Volume confirm     : ±10   (high-volume moves score higher)
      Relative vs SPY    : ±10   (outperforming/underperforming market)
    Max possible: ±110 → capped to ±100
    """
    score = 0.0

    # RSI (±30)
    score += max(-30.0, min(30.0, (rsi - 50.0) * 0.6))

    # Price vs SMA20 (±15)
    if sma20 > 0:
        pct = (price - sma20) / sma20 * 100.0
        score += max(-15.0, min(15.0, pct * 1.5))

    # Price vs SMA50 (±15)
    if sma50 > 0:
        pct = (price - sma50) / sma50 * 100.0
        score += max(-15.0, min(15.0, pct * 1.5))

    # 5-day vs 20-day momentum (±15)
    if len(closes) >= 21 and closes[-6] and closes[-21]:
        ret5  = (closes[-1] - closes[-6])  / closes[-6]  * 100.0
        ret20 = (closes[-1] - closes[-21]) / closes[-21] * 100.0
        score += max(-15.0, min(15.0, (ret5 - ret20) * 1.2))

    # MACD histogram (±15)
    hist = _macd_histogram(closes)
    if hist != 0.0 and price > 0:
        hist_norm = hist / price * 1000.0   # normalise by price
        score += max(-15.0, min(15.0, hist_norm))

    # Volume confirmation (±10) — high-volume day amplifies last move direction
    if volumes:
        vol_r = _volume_ratio(volumes)
        if vol_r > 1.3 and len(closes) >= 2 and closes[-2]:
            last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100.0
            direction = 1.0 if last_ret > 0 else -1.0
            boost = min(10.0, (vol_r - 1.0) * 6.0) * direction
            score += boost

    # Relative strength vs SPY (±10) — outperformers score higher
    if spy_closes and len(spy_closes) >= 6 and len(closes) >= 6:
        try:
            tk_ret  = (closes[-1]     - closes[-6])     / closes[-6]     * 100.0
            spy_ret = (spy_closes[-1] - spy_closes[-6]) / spy_closes[-6] * 100.0
            rel = tk_ret - spy_ret
            score += max(-10.0, min(10.0, rel * 0.8))
        except (ZeroDivisionError, IndexError):
            pass

    return int(round(max(-100.0, min(100.0, score))))


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

def _build_entry(rank, symbol, name, opens, highs, lows, closes, volumes=None, spy_closes=None):
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
    macd_h   = round(_macd_histogram(closes), 4)
    vol_r    = round(_volume_ratio(volumes), 2) if volumes else None

    support, resistance = _levels(highs, lows, price)
    bias_str   = _bias(rsi_val, price, sma20, sma50)
    strat_str  = _strategy(bias_str, rsi_val)
    sig_score  = _signal_score(rsi_val, price, sma20, sma50, closes, volumes, spy_closes)

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
        "sma20":          round(sma20, 2),
        "sma50":          round(sma50, 2),
        "macdHistogram":  macd_h,
        "volumeRatio":    vol_r,
        "signalScore":    sig_score,
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
            "ticker":      e["ticker"],
            "direction":   direction,
            "entry":       entry_lv,
            "target":      target,
            "stop":        stop,
            "catalyst":    catalyst,
            "signalScore": e.get("signalScore", 0),
            "_strength":   abs(e.get("signalScore", 0)),  # rank by absolute score strength
        })

    items.sort(key=lambda x: x["_strength"], reverse=True)
    result = []
    for i, item in enumerate(items[:7], 1):
        item["rank"] = i
        del item["_strength"]
        result.append(item)
    return result


# ─── Backtesting ──────────────────────────────────────────────────────────────

_BUCKETS = [
    ("STRONG BUY",  50,  100),
    ("BUY",         20,   49),
    ("NEUTRAL",    -19,   19),
    ("SELL",       -49,  -20),
    ("STRONG SELL",-100, -50),
]
_FWD_DAYS = (1, 3, 5)


def _backtest_ticker(highs, lows, closes, volumes=None, spy_closes=None, lookback=51):
    """
    Walk-forward backtest for one ticker.

    For every day from `lookback` to len-max(FWD_DAYS)-1:
      - compute signal score using only data up to that day  (no lookahead)
      - record forward returns at 1, 3, 5 days

    Returns list of (score, {1: ret1, 3: ret3, 5: ret5}).
    """
    max_fwd = max(_FWD_DAYS)
    records = []
    for i in range(lookback, len(closes) - max_fwd):
        c   = closes[:i + 1]
        h   = highs[:i + 1]
        l   = lows[:i + 1]
        v   = volumes[:i + 1] if volumes else None
        spy = spy_closes[:i + 1] if spy_closes else None
        rsi_v = _rsi(c)
        sma20 = _sma(c, 20)
        sma50 = _sma(c, 50)
        score = _signal_score(rsi_v, c[-1], sma20, sma50, c, v, spy)
        fwd   = {d: round((closes[i + d] - closes[i]) / closes[i] * 100, 3)
                 for d in _FWD_DAYS if i + d < len(closes)}
        records.append((score, fwd))
    return records


def _aggregate_backtest(all_records):
    """
    Aggregate walk-forward records across all tickers into per-bucket stats.

    Returns dict keyed by bucket label:
      { n, win1d, avg1d, win3d, avg3d, win5d, avg5d }
    """
    buckets = {name: [] for name, _, _ in _BUCKETS}

    for score, fwd in all_records:
        for name, lo, hi in _BUCKETS:
            if lo <= score <= hi:
                buckets[name].append(fwd)
                break

    stats = {}
    for name, _, _ in _BUCKETS:
        items = buckets[name]
        if not items:
            stats[name] = {"n": 0}
            continue
        n = len(items)
        row = {"n": n}
        for d in _FWD_DAYS:
            rets = [item[d] for item in items if d in item]
            if rets:
                row[f"win{d}d"]  = round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1)
                row[f"avg{d}d"]  = round(sum(rets) / len(rets), 3)
                row[f"best{d}d"] = round(max(rets), 2)
                row[f"worst{d}d"]= round(min(rets), 2)
        stats[name] = row
    return stats


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

    # ── Fetch SPY closes for relative-strength signal ─────────────
    spy_closes = series("Close", "SPY")   # already in TICKERS; will be populated

    # ── Main tickers ─────────────────────────────────────────────
    ticker_entries  = []
    _bt_records     = []   # all-ticker walk-forward records
    _bt_per_ticker  = {}   # per-ticker walk-forward records

    for rank, sym in enumerate(TICKERS, 1):
        try:
            o = series("Open",   sym)
            h = series("High",   sym)
            l = series("Low",    sym)
            c = series("Close",  sym)
            v = series("Volume", sym)
            if len(c) < 22:
                continue
            spy = spy_closes if sym != "SPY" else None
            entry = _build_entry(rank, sym, TICKER_NAMES.get(sym, sym), o, h, l, c,
                                 volumes=v or None, spy_closes=spy)
            if entry:
                ticker_entries.append(entry)
            # Accumulate backtest records (needs 56+ bars for full signal)
            if len(c) >= 56:
                recs = _backtest_ticker(h, l, c, volumes=v or None,
                                        spy_closes=spy)
                _bt_records.extend(recs)
                _bt_per_ticker[sym] = _aggregate_backtest(recs)
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

    # ── Backtest accuracy stats ───────────────────────────────────
    backtest_stats = _aggregate_backtest(_bt_records) if _bt_records else {}

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
        "tickers":          ticker_entries,
        "indexes":          index_entries,
        "watchlist":        watchlist,
        "chartData":        chart_data,
        "backtestStats":    backtest_stats,
        "backtestPerTicker":_bt_per_ticker,
        "backtestN":        len(_bt_records),
        "updatedAt":        int(now),
        "liveData":         True,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = now + CACHE_TTL_SECONDS

    return payload
