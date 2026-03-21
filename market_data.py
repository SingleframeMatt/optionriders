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
_cache = {}

TICKERS = [
    "SPY", "QQQ", "NVDA", "MU", "META", "AVGO",
    "AMD", "AAPL", "TSLA", "MSFT", "GOOGL", "AMZN",
    "SMCI", "PLTR",
]

DEFAULT_TICKERS = list(TICKERS)

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
    "SMCI": "Super Micro Computer",
    "PLTR": "Palantir",
    "ES":   "S&P 500 Futures",
    "NQ":   "Nasdaq Futures",
    "VIX":  "CBOE Volatility Index",
}

# Futures + volatility index symbols for yfinance
INDEX_FUTURES = [("ES=F", "ES"), ("NQ=F", "NQ"), ("^VIX", "VIX")]


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


def _adx(highs, lows, closes, period=14):
    """
    Average Directional Index — trend strength 0-100.
    >30 = strong trend, 20-30 = moderate, <20 = weak/ranging.
    Returns 20.0 (neutral) if insufficient data.
    """
    if len(closes) < period * 2 + 2:
        return 20.0

    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr       = max(h - l, abs(h - pc), abs(l - pc))
        up_move   = highs[i]   - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move   if up_move   > down_move and up_move   > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move   and down_move > 0 else 0.0)
        tr_list.append(tr)

    def _wilder(data, n):
        if len(data) < n:
            return []
        s = sum(data[:n])
        result = [s]
        for v in data[n:]:
            s = s - s / n + v
            result.append(s)
        return result

    s_tr   = _wilder(tr_list,   period)
    s_plus = _wilder(plus_dm,   period)
    s_minus= _wilder(minus_dm,  period)

    dx_list = []
    for i in range(len(s_tr)):
        if s_tr[i] == 0:
            continue
        pdi = 100.0 * s_plus[i]  / s_tr[i]
        mdi = 100.0 * s_minus[i] / s_tr[i]
        dx  = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
        dx_list.append(dx)

    if not dx_list:
        return 20.0

    # ADX = Wilder smooth of DX
    adx_val = sum(dx_list[:period]) / min(period, len(dx_list))
    for v in dx_list[period:]:
        adx_val = (adx_val * (period - 1) + v) / period
    return round(adx_val, 1)


def _bollinger_pct_b(closes, period=20, num_std=2.0):
    """
    %B position within Bollinger Bands.
    0 = at lower band, 0.5 = at middle (SMA), 1 = at upper band.
    Returns 0.5 (neutral) if insufficient data.
    """
    if len(closes) < period:
        return 0.5
    window   = closes[-period:]
    mean_v   = sum(window) / period
    variance = sum((x - mean_v) ** 2 for x in window) / period
    std      = variance ** 0.5
    if std == 0:
        return 0.5
    upper = mean_v + num_std * std
    lower = mean_v - num_std * std
    pct_b = (closes[-1] - lower) / (upper - lower)
    return round(max(-0.2, min(1.2, pct_b)), 3)  # allow slightly outside bands


def _week52_position(closes):
    """
    Where is the current price within its trailing 252-bar range?
    0.0 = at 52-week low, 1.0 = at 52-week high.
    """
    window = closes[-252:] if len(closes) >= 252 else closes
    if not window:
        return 0.5
    lo, hi = min(window), max(window)
    if hi == lo:
        return 0.5
    return round((closes[-1] - lo) / (hi - lo), 3)


def _fetch_earnings_date(symbol):
    """
    Return next earnings date as ISO string (YYYY-MM-DD) or None.
    Uses yfinance Ticker.calendar — best-effort, silently fails.
    """
    import datetime
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        cal = t.calendar
        if cal is None:
            return None
        today = datetime.date.today()

        # yfinance ≥ 0.2 returns a dict; older versions return a DataFrame
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or cal.get("earningsDate") or []
            if not dates:
                return None
            if not hasattr(dates, "__iter__"):
                dates = [dates]
            upcoming = []
            for d in dates:
                try:
                    if hasattr(d, "date"):
                        dobj = d.date()
                    else:
                        dobj = datetime.date.fromisoformat(str(d)[:10])
                    if dobj >= today:
                        upcoming.append(dobj)
                except Exception:
                    pass
            if upcoming:
                return min(upcoming).isoformat()
        elif hasattr(cal, "columns"):
            # Older DataFrame format
            col = next((c for c in cal.columns if "Earnings" in str(c)), None)
            if col:
                vals = cal[col].dropna()
                if len(vals):
                    d = vals.iloc[0]
                    dobj = d.date() if hasattr(d, "date") else datetime.date.fromisoformat(str(d)[:10])
                    if dobj >= today:
                        return dobj.isoformat()
    except Exception:
        pass
    return None


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


def _signal_score(rsi, price, sma20, sma50, closes, highs=None, lows=None,
                  volumes=None, spy_closes=None):
    """
    Composite signal score from -100 (strong sell) to +100 (strong buy).

    Components:
      RSI momentum       : ±24   (deviation from neutral 50)
      Price vs SMA20     : ±12   (% distance above/below)
      Price vs SMA50     : ±12   (% distance above/below)
      5d vs 20d momentum : ±12   (short-term acceleration)
      MACD histogram     : ±12   (crossover momentum)
      Volume confirm     : ±8    (high-volume moves score higher)
      Relative vs SPY    : ±8    (outperforming/underperforming market)
      Bollinger %B       : ±6    (oversold/overbought via BB bands)
      52-week position   : ±5    (near highs = bullish, near lows = bearish)
    Raw max: ±99 → ADX multiplier applied → capped to ±100
    """
    score = 0.0

    # RSI (±24)
    score += max(-24.0, min(24.0, (rsi - 50.0) * 0.48))

    # Price vs SMA20 (±12)
    if sma20 > 0:
        pct = (price - sma20) / sma20 * 100.0
        score += max(-12.0, min(12.0, pct * 1.2))

    # Price vs SMA50 (±12)
    if sma50 > 0:
        pct = (price - sma50) / sma50 * 100.0
        score += max(-12.0, min(12.0, pct * 1.2))

    # 5-day vs 20-day momentum (±12)
    if len(closes) >= 21 and closes[-6] and closes[-21]:
        ret5  = (closes[-1] - closes[-6])  / closes[-6]  * 100.0
        ret20 = (closes[-1] - closes[-21]) / closes[-21] * 100.0
        score += max(-12.0, min(12.0, (ret5 - ret20) * 1.0))

    # MACD histogram (±12)
    hist = _macd_histogram(closes)
    if hist != 0.0 and price > 0:
        hist_norm = hist / price * 1000.0   # normalise by price
        score += max(-12.0, min(12.0, hist_norm))

    # Volume confirmation (±8) — high-volume day amplifies last move direction
    if volumes:
        vol_r = _volume_ratio(volumes)
        if vol_r > 1.3 and len(closes) >= 2 and closes[-2]:
            last_ret = (closes[-1] - closes[-2]) / closes[-2] * 100.0
            direction = 1.0 if last_ret > 0 else -1.0
            boost = min(8.0, (vol_r - 1.0) * 5.0) * direction
            score += boost

    # Relative strength vs SPY (±8) — outperformers score higher
    if spy_closes and len(spy_closes) >= 6 and len(closes) >= 6:
        try:
            tk_ret  = (closes[-1]     - closes[-6])     / closes[-6]     * 100.0
            spy_ret = (spy_closes[-1] - spy_closes[-6]) / spy_closes[-6] * 100.0
            rel = tk_ret - spy_ret
            score += max(-8.0, min(8.0, rel * 0.8))
        except (ZeroDivisionError, IndexError):
            pass

    # Bollinger %B (±6) — oversold bounce when near/below lower band
    pct_b = _bollinger_pct_b(closes)
    # pct_b < 0.2 → oversold → bullish; pct_b > 0.8 → overbought → bearish
    bb_score = (0.5 - pct_b) * 12.0   # inverted: low %B = positive score
    score += max(-6.0, min(6.0, bb_score))

    # 52-week position (±5) — momentum: near highs is bullish
    pos52 = _week52_position(closes)
    score += max(-5.0, min(5.0, (pos52 - 0.5) * 10.0))

    # ADX multiplier — amplify score when trending, dampen when choppy
    if highs and lows and len(highs) >= 30:
        adx_val = _adx(highs, lows, closes)
        if adx_val >= 30:
            multiplier = 1.15   # strong trend: trust the signal more
        elif adx_val >= 20:
            multiplier = 1.0    # moderate trend: no change
        else:
            multiplier = 0.85   # ranging/choppy: reduce confidence
        score *= multiplier

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

def _build_entry(rank, symbol, name, opens, highs, lows, closes, volumes=None, spy_closes=None, live_price=None):
    if len(closes) < 22:
        return None

    prev_close = closes[-2]
    price      = live_price if (live_price and live_price > 0) else closes[-1]
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    rsi_val  = _rsi(closes)
    atr_val  = _atr(highs, lows, closes)
    atr_pct  = round(atr_val / price * 100, 2) if price else 0.0
    sma20    = _sma(closes, 20)
    sma50    = _sma(closes, 50)
    macd_h   = round(_macd_histogram(closes), 4)
    vol_r    = round(_volume_ratio(volumes), 2) if volumes else None
    adx_val  = round(_adx(highs, lows, closes), 1)
    pct_b    = round(_bollinger_pct_b(closes), 3)
    pos52    = round(_week52_position(closes), 3)

    support, resistance = _levels(highs, lows, price)
    bias_str   = _bias(rsi_val, price, sma20, sma50)
    strat_str  = _strategy(bias_str, rsi_val)
    sig_score  = _signal_score(rsi_val, price, sma20, sma50, closes,
                               highs=highs, lows=lows, volumes=volumes,
                               spy_closes=spy_closes)

    rel_strength = None
    if spy_closes and len(spy_closes) >= 6 and len(closes) >= 6:
        try:
            tk_ret  = (closes[-1] - closes[-6]) / closes[-6] * 100.0
            spy_ret = (spy_closes[-1] - spy_closes[-6]) / spy_closes[-6] * 100.0
            rel_strength = round(tk_ret - spy_ret, 2)
        except (ZeroDivisionError, IndexError):
            pass

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
        "adx":            adx_val,
        "bollingerPctB":  pct_b,
        "week52Position": pos52,
        "signalScore":    sig_score,
        "relStrength":    rel_strength,
        "liveData":    True,
        "_ohlcv":      ohlcv,   # stripped out before JSON response
    }


def _build_watchlist_item(entry, pinned=False):
    if not entry:
        return None

    bias         = entry.get("bias", "Range")
    sup          = entry.get("support", [])
    res          = entry.get("resistance", [])
    price        = entry.get("price", 0)
    atr          = entry.get("atr", 0)
    score        = entry.get("signalScore", 0)
    rel_strength = entry.get("relStrength")

    if "Bullish" in bias:
        direction = "LONG"
        entry_lv  = f"Above {res[0]}" if res else f"Above {round(price, 2)}"
        target    = f"{res[1]}-{res[2]}" if len(res) >= 3 else str(round(price + atr, 2))
        stop      = str(sup[0]) if sup else str(round(price - atr, 2))
        catalyst  = "Bullish momentum + technical breakout"
    elif "Bearish" in bias:
        direction = "SHORT"
        entry_lv  = f"Below {sup[0]}" if sup else f"Below {round(price, 2)}"
        target    = f"{sup[1]}-{sup[2]}" if len(sup) >= 3 else str(round(price - atr, 2))
        stop      = str(res[0]) if res else str(round(price + atr, 2))
        catalyst  = "Bearish momentum + technical breakdown"
    elif pinned:
        direction = "LONG" if score >= 0 else "SHORT"
        entry_lv  = f"Above {res[0]}" if direction == "LONG" and res else f"Below {sup[0]}" if sup else f"Near {round(price, 2)}"
        target    = f"{res[1]}-{res[2]}" if direction == "LONG" and len(res) >= 3 else f"{sup[1]}-{sup[2]}" if direction == "SHORT" and len(sup) >= 3 else str(round(price + atr, 2)) if direction == "LONG" else str(round(price - atr, 2))
        stop      = str(sup[0]) if direction == "LONG" and sup else str(res[0]) if res else str(round(price - atr, 2)) if direction == "LONG" else str(round(price + atr, 2))
        catalyst  = "Custom ticker tracking"
    else:
        return None

    return {
        "ticker":      entry["ticker"],
        "direction":   direction,
        "entry":       entry_lv,
        "target":      target,
        "stop":        stop,
        "catalyst":    catalyst,
        "signalScore": score,
        "relStrength": rel_strength,
        "_strength":   abs(score),
    }


def _build_watchlist(ticker_entries, pinned_symbols=None):
    """Rank tickers by signal strength and auto-generate trade setups."""
    pinned_symbols = set(pinned_symbols or [])
    by_symbol = {entry["ticker"]: entry for entry in ticker_entries if entry and entry.get("ticker")}

    items = []
    for entry in ticker_entries:
        item = _build_watchlist_item(entry, pinned=entry.get("ticker") in pinned_symbols)
        if item:
            items.append(item)

    items.sort(key=lambda x: x["_strength"], reverse=True)

    selected = []
    used = set()
    for item in items:
        if item["ticker"] in used:
            continue
        if len(selected) >= 7:
            break
        selected.append(item)
        used.add(item["ticker"])

    for symbol in pinned_symbols:
        if symbol in used:
            continue
        item = _build_watchlist_item(by_symbol.get(symbol), pinned=True)
        if item:
            selected.append(item)
            used.add(symbol)

    result = []
    for i, item in enumerate(selected, 1):
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
        score = _signal_score(rsi_v, c[-1], sma20, sma50, c,
                               highs=h, lows=l, volumes=v, spy_closes=spy)
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

def _normalize_extra_tickers(extra_tickers=None):
    normalized = []
    seen = set(DEFAULT_TICKERS)
    for ticker in extra_tickers or []:
        symbol = str(ticker or "").strip().upper()
        if not symbol or len(symbol) > 5 or not symbol.isalnum() or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
    return normalized


def fetch_market_data(extra_tickers=None, force_refresh=False):
    """
    Return live market data with computed indicators.
    Cached for CACHE_TTL_SECONDS to avoid excessive Yahoo Finance calls.
    """
    now = time.time()
    extra_symbols = _normalize_extra_tickers(extra_tickers)
    cache_key = tuple(extra_symbols)
    if not force_refresh:
        with _cache_lock:
            cached = _cache.get(cache_key)
            if cached and cached["expires_at"] > now:
                return cached["payload"]

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. "
            "Run: pip install yfinance --break-system-packages"
        )

    request_tickers = DEFAULT_TICKERS + extra_symbols
    all_yf_symbols = request_tickers + [yf_sym for yf_sym, _ in INDEX_FUTURES]

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

    # ── Live 1-minute prices (low latency) ───────────────────────
    live_prices = {}
    try:
        live_raw = yf.download(
            all_yf_symbols,
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=True,
        )

        def live_series(field, symbol):
            try:
                if hasattr(live_raw.columns, "levels"):
                    return list(live_raw[field][symbol].dropna().astype(float))
                return list(live_raw[field].dropna().astype(float))
            except Exception:
                return []

        for sym in all_yf_symbols:
            closes_1m = live_series("Close", sym)
            if closes_1m:
                live_prices[sym] = closes_1m[-1]
    except Exception as exc:
        print(f"[market_data] live 1m fetch error: {exc}")

    # ── Fetch SPY closes for relative-strength signal ─────────────
    spy_closes = series("Close", "SPY")   # already in TICKERS; will be populated

    # ── Main tickers ─────────────────────────────────────────────
    ticker_entries  = []
    _bt_records     = []   # all-ticker walk-forward records
    _bt_per_ticker  = {}   # per-ticker walk-forward records

    for rank, sym in enumerate(request_tickers, 1):
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
                                 volumes=v or None, spy_closes=spy,
                                 live_price=live_prices.get(sym))
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

    # ── Earnings dates (parallel fetch) ──────────────────────────
    earnings_dates = {}
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            future_map = {pool.submit(_fetch_earnings_date, sym): sym for sym in request_tickers}
            for fut in concurrent.futures.as_completed(future_map, timeout=12):
                sym = future_map[fut]
                try:
                    result = fut.result()
                    if result:
                        earnings_dates[sym] = result
                except Exception:
                    pass
    except Exception as exc:
        print(f"[market_data] earnings fetch error: {exc}")

    # Attach earnings date to each ticker entry
    for entry in ticker_entries:
        entry["earningsDate"] = earnings_dates.get(entry["ticker"])

    # ── Index / futures entries ───────────────────────────────────
    index_entries = []
    # SPY and QQQ reuse their already-computed ticker_entries
    for sym in ("SPY", "QQQ"):
        e = next((t for t in ticker_entries if t["ticker"] == sym), None)
        if e:
            index_entries.append(e)

    # VIX — extract as a simple dict (no full entry needed)
    vix_data = None
    for yf_sym, short_key in INDEX_FUTURES:
        try:
            o = series("Open",  yf_sym)
            h = series("High",  yf_sym)
            l = series("Low",   yf_sym)
            c = series("Close", yf_sym)
            if len(c) < 2:
                continue
            if short_key == "VIX":
                # VIX: just expose current level and 1-day change
                live_c = live_prices.get(yf_sym, c[-1])
                prev = c[-2] if len(c) >= 2 else c[-1]
                chg  = round((live_c - prev) / prev * 100, 2) if prev else 0.0
                vix_data = {
                    "price":    round(live_c, 2),
                    "change":   round(live_c - prev, 2),
                    "changePct": chg,
                    "label":    ("Fear" if live_c > 25 else "Calm" if live_c < 15 else "Normal"),
                }
                continue
            if len(c) < 22:
                continue
            entry = _build_entry(0, short_key, TICKER_NAMES.get(short_key, short_key), o, h, l, c,
                                 live_price=live_prices.get(yf_sym))
            if entry:
                index_entries.append(entry)
        except Exception as exc:
            print(f"[market_data] {yf_sym}: {exc}")

    # ── Market breadth ────────────────────────────────────────────
    scores = [e["signalScore"] for e in ticker_entries if e.get("signalScore") is not None]
    bullish_n  = sum(1 for s in scores if s >= 20)
    bearish_n  = sum(1 for s in scores if s <= -20)
    neutral_n  = len(scores) - bullish_n - bearish_n
    avg_score  = round(sum(scores) / len(scores), 1) if scores else 0.0
    if avg_score >= 40:      breadth_label = "Strongly Bullish"
    elif avg_score >= 15:    breadth_label = "Bullish"
    elif avg_score <= -40:   breadth_label = "Strongly Bearish"
    elif avg_score <= -15:   breadth_label = "Bearish"
    else:                    breadth_label = "Mixed"
    market_breadth = {
        "bullish":   bullish_n,
        "bearish":   bearish_n,
        "neutral":   neutral_n,
        "total":     len(scores),
        "avgScore":  avg_score,
        "label":     breadth_label,
    }

    # ── Auto-generate watchlist ───────────────────────────────────
    watchlist = _build_watchlist(ticker_entries, pinned_symbols=extra_symbols)

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
        "vix":              vix_data,
        "marketBreadth":    market_breadth,
        "earningsDates":    earnings_dates,
        "updatedAt":        int(now),
        "liveData":         True,
    }

    with _cache_lock:
        _cache[cache_key] = {
            "payload": payload,
            "expires_at": now + CACHE_TTL_SECONDS,
        }

    return payload
