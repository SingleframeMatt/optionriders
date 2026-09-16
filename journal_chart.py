"""Historical underlying candles for journal execution markers (UTC seconds)."""
from datetime import date, datetime, timedelta
import math
import re
import time
import os
import tempfile
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_cache = {}
_INTERVALS = {"1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m", "60min": "60m"}


def _clean(bars):
    valid = {}
    for b in bars:
        try:
            row = {k: float(b[k]) for k in ("open", "high", "low", "close")}
            if not all(math.isfinite(v) and v > 0 for v in row.values()):
                continue
            ts = int(b["time"])
            valid[ts] = {"time": ts, **row}
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return [valid[t] for t in sorted(valid)]


def intraday_bars(symbol: str, date_iso: str, interval: str = "5min") -> dict:
    symbol = symbol.strip().upper()
    result = {"symbol": symbol, "date": date_iso, "interval": interval, "bars": []}
    try:
        day = date.fromisoformat(date_iso)
    except ValueError:
        return {**result, "error": "A valid trade date is required."}
    if not re.fullmatch(r"[A-Z0-9.^=/-]{1,32}", symbol) or interval not in _INTERVALS:
        return {**result, "error": "Invalid symbol or candle interval."}
    key = (symbol, date_iso, interval)
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    # Request the actual historical month, rather than silently using today's
    # rolling window for every journal date. The existing AV plan may not
    # include intraday history; Yahoo supplies recent sessions as a fallback.
    bars = []
    source = "Alpha Vantage"
    try:
        import alpha_vantage as av
        data = av.fetch_intraday(symbol, interval=interval, outputsize="full", month=day.strftime("%Y-%m"))
        for b in data.get("bars", []):
            dt = datetime.fromisoformat(b["time"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_NY)
            if dt.astimezone(_NY).date() == day:
                bars.append({**b, "time": int(dt.timestamp())})
        bars = _clean(bars)
    except Exception:
        bars = []
    if not bars and 0 <= (datetime.now(_NY).date() - day).days < (7 if interval == "1min" else 60):
        try:
            import yfinance as yf
            yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), "optionriders-yfinance"))
            frame = yf.Ticker(symbol.replace(".", "-")).history(
                start=day.isoformat(), end=(day + timedelta(days=1)).isoformat(),
                interval=_INTERVALS[interval], auto_adjust=False, prepost=True,
                actions=False, timeout=10, raise_errors=True)
            for ts, row in frame.iterrows():
                if ts.tzinfo is None:
                    ts = ts.tz_localize(_NY)
                if ts.tz_convert(_NY).date() == day:
                    bars.append({"time": int(ts.timestamp()), **{
                        k: row[k.title()] for k in ("open", "high", "low", "close")}})
            bars = _clean(bars)
            source = "Yahoo Finance"
        except Exception:
            bars = []
    result["bars"] = bars
    if bars:
        result["source"] = source
    else:
        result["error"] = "Historical intraday candles are unavailable for this date from the configured data providers."
    # Bound warm-server memory and retry transient failures after one minute.
    if len(_cache) >= 256:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic() + (300 if bars else 60), result)
    return result
