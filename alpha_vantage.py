#!/usr/bin/env python3
"""
alpha_vantage.py — Alpha Vantage integration for Option Riders
==============================================================
Provides: real-time quotes, company fundamentals, earnings history,
options chain, and technical indicators (RSI, MACD, BBands, ADX).

Free-tier rate limit: 25 requests / day.
All functions cache results aggressively to stay within limits.

Endpoint reference: https://www.alphavantage.co/documentation/
"""

import json
import os
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.alphavantage.co/query"

# Cache TTLs (seconds)
QUOTE_CACHE_TTL        = 60        # 1 min — live price/change
INTRADAY_CACHE_TTL     = 300       # 5 min — intraday bars
INDICATOR_CACHE_TTL    = 300       # 5 min — RSI / MACD / BBands / ADX
OPTIONS_CACHE_TTL      = 300       # 5 min — options chain
FUNDAMENTALS_CACHE_TTL = 86_400    # 24 h  — OVERVIEW + EARNINGS

# In-memory cache: { key: (data, timestamp) }
_cache: dict = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not key:
        raise ValueError(
            "ALPHA_VANTAGE_API_KEY is not set. "
            "Add it to your .env file: ALPHA_VANTAGE_API_KEY=<your_key>"
        )
    return key


def _cache_get(key: str, ttl: int):
    """Return cached value if still fresh, else None."""
    entry = _cache.get(key)
    if entry and (time.time() - entry[1]) < ttl:
        return entry[0]
    return None


def _cache_set(key: str, data) -> None:
    _cache[key] = (data, time.time())


def _fetch(params: dict) -> dict:
    """Make a single authenticated GET request to Alpha Vantage."""
    params["apikey"] = _get_api_key()
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OptionRiders/1.3"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")

    data = json.loads(raw)

    # Surface API-level error / info messages
    if "Information" in data:
        raise RuntimeError(f"Alpha Vantage: {data['Information']}")
    if "Note" in data:
        raise RuntimeError(f"Alpha Vantage rate-limit: {data['Note']}")
    if "Error Message" in data:
        raise RuntimeError(f"Alpha Vantage error: {data['Error Message']}")

    return data


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_quote(symbol: str) -> dict:
    """
    GLOBAL_QUOTE — real-time price, change, volume.
    1 API call per symbol. Cached 1 min.
    """
    key = f"quote:{symbol}"
    cached = _cache_get(key, QUOTE_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({"function": "GLOBAL_QUOTE", "symbol": symbol})
    q = data.get("Global Quote", {})

    result = {
        "symbol":           symbol,
        "price":            float(q.get("05. price", 0) or 0),
        "open":             float(q.get("02. open", 0) or 0),
        "high":             float(q.get("03. high", 0) or 0),
        "low":              float(q.get("04. low", 0) or 0),
        "volume":           int(q.get("06. volume", 0) or 0),
        "prevClose":        float(q.get("08. previous close", 0) or 0),
        "change":           float(q.get("09. change", 0) or 0),
        "changePct":        float((q.get("10. change percent", "0%") or "0%").replace("%", "")),
        "latestTradingDay": q.get("07. latest trading day", ""),
    }

    _cache_set(key, result)
    return result


def fetch_overview(symbol: str) -> dict:
    """
    OVERVIEW — fundamentals: sector, market cap, P/E, 52-week range, analyst target, etc.
    1 API call per symbol. Cached 24 h.
    """
    key = f"overview:{symbol}"
    cached = _cache_get(key, FUNDAMENTALS_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({"function": "OVERVIEW", "symbol": symbol})

    def _f(field):
        v = data.get(field, "")
        return v if v not in ("None", "-", "") else None

    result = {
        "symbol":              symbol,
        "name":                _f("Name"),
        "description":         _f("Description"),
        "sector":              _f("Sector"),
        "industry":            _f("Industry"),
        "exchange":            _f("Exchange"),
        "currency":            _f("Currency"),
        "country":             _f("Country"),
        "marketCap":           _f("MarketCapitalization"),
        "peRatio":             _f("PERatio"),
        "forwardPE":           _f("ForwardPE"),
        "pegRatio":            _f("PEGRatio"),
        "eps":                 _f("EPS"),
        "bookValue":           _f("BookValue"),
        "priceToBook":         _f("PriceToBookRatio"),
        "dividendYield":       _f("DividendYield"),
        "dividendDate":        _f("DividendDate"),
        "exDividendDate":      _f("ExDividendDate"),
        "profitMargin":        _f("ProfitMargin"),
        "operatingMargin":     _f("OperatingMarginTTM"),
        "returnOnEquity":      _f("ReturnOnEquityTTM"),
        "returnOnAssets":      _f("ReturnOnAssetsTTM"),
        "revenueGrowthYoY":    _f("RevenueGrowthYOY"),
        "beta":                _f("Beta"),
        "week52High":          _f("52WeekHigh"),
        "week52Low":           _f("52WeekLow"),
        "sma50":               _f("50DayMovingAverage"),
        "sma200":              _f("200DayMovingAverage"),
        "analystTargetPrice":  _f("AnalystTargetPrice"),
        "sharesOutstanding":   _f("SharesOutstanding"),
        "shareFloat":          _f("SharesFloat"),
        "shortRatio":          _f("ShortRatio"),
        "shortPctFloat":       _f("ShortPercentFloat"),
        "shortPctOutstanding": _f("ShortPercentOutstanding"),
        "sharesShort":         _f("SharesShort"),
        "fiscalYearEnd":       _f("FiscalYearEnd"),
        "latestQuarter":       _f("LatestQuarter"),
    }

    _cache_set(key, result)
    return result


def fetch_earnings(symbol: str) -> dict:
    """
    EARNINGS — annual + quarterly EPS history with beat/miss data.
    1 API call per symbol. Cached 24 h.
    """
    key = f"earnings:{symbol}"
    cached = _cache_get(key, FUNDAMENTALS_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({"function": "EARNINGS", "symbol": symbol})

    def _parse_earnings(records, limit):
        out = []
        for e in (records or [])[:limit]:
            surprise_pct = e.get("surprisePercentage", "")
            try:
                spct = float(surprise_pct) if surprise_pct not in (None, "None", "") else None
            except ValueError:
                spct = None

            beat = None
            if spct is not None:
                beat = spct > 0

            out.append({
                "fiscalDate":    e.get("fiscalDateEnding", ""),
                "reportDate":    e.get("reportedDate", ""),
                "reportedEPS":   e.get("reportedEPS", ""),
                "estimatedEPS":  e.get("estimatedEPS", ""),
                "surprise":      e.get("surprise", ""),
                "surprisePct":   surprise_pct,
                "beat":          beat,
            })
        return out

    result = {
        "symbol":           symbol,
        "annualEarnings":   _parse_earnings(data.get("annualEarnings", []), 4),
        "quarterlyEarnings":_parse_earnings(data.get("quarterlyEarnings", []), 8),
    }

    _cache_set(key, result)
    return result


def fetch_options(symbol: str) -> dict:
    """
    REALTIME_OPTIONS — live options chain with greeks.
    Requires a premium Alpha Vantage plan; returns graceful error on free tier.
    1 API call per symbol. Cached 5 min.
    """
    key = f"options:{symbol}"
    cached = _cache_get(key, OPTIONS_CACHE_TTL)
    if cached:
        return cached

    try:
        data = _fetch({
            "function":        "REALTIME_OPTIONS",
            "symbol":          symbol,
            "require_options": "true",
        })

        raw_contracts = data.get("data", [])
        if not raw_contracts:
            result = {
                "symbol":    symbol,
                "available": False,
                "contracts": [],
                "note":      data.get("message", "No options data returned (may require premium plan)."),
            }
            _cache_set(key, result)
            return result

        contracts = []
        for c in raw_contracts:
            contracts.append({
                "contractID":        c.get("contractID", ""),
                "expiration":        c.get("expiration", ""),
                "strike":            c.get("strike", ""),
                "type":              c.get("type", ""),        # "call" | "put"
                "last":              c.get("last", ""),
                "bid":               c.get("bid", ""),
                "ask":               c.get("ask", ""),
                "volume":            c.get("volume", ""),
                "openInterest":      c.get("open_interest", ""),
                "impliedVolatility": c.get("implied_volatility", ""),
                "delta":             c.get("delta", ""),
                "gamma":             c.get("gamma", ""),
                "theta":             c.get("theta", ""),
                "vega":              c.get("vega", ""),
                "rho":               c.get("rho", ""),
                "inTheMoney":        c.get("in_the_money", ""),
            })

        result = {
            "symbol":    symbol,
            "available": True,
            "contracts": contracts,
            "total":     len(contracts),
        }

    except RuntimeError as exc:
        result = {
            "symbol":    symbol,
            "available": False,
            "contracts": [],
            "note":      str(exc),
        }

    _cache_set(key, result)
    return result


def fetch_rsi(symbol: str, interval: str = "daily", time_period: int = 14) -> dict:
    """
    RSI — Relative Strength Index.
    1 API call. Cached 5 min.
    """
    key = f"rsi:{symbol}:{interval}:{time_period}"
    cached = _cache_get(key, INDICATOR_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({
        "function":    "RSI",
        "symbol":      symbol,
        "interval":    interval,
        "time_period": str(time_period),
        "series_type": "close",
    })

    analysis = data.get("Technical Analysis: RSI", {})
    dates    = sorted(analysis.keys())
    latest_date  = dates[-1] if dates else ""
    latest_rsi   = float(analysis[latest_date]["RSI"]) if latest_date else 0.0
    history      = [{"date": d, "rsi": float(analysis[d]["RSI"])} for d in dates[-20:]]

    result = {
        "symbol":  symbol,
        "rsi":     round(latest_rsi, 2),
        "date":    latest_date,
        "history": history,
        "signal":  (
            "oversold"   if latest_rsi < 30
            else "overbought" if latest_rsi > 70
            else "neutral"
        ),
    }

    _cache_set(key, result)
    return result


def fetch_macd(symbol: str, interval: str = "daily") -> dict:
    """
    MACD — Moving Average Convergence/Divergence.
    1 API call. Cached 5 min.
    """
    key = f"macd:{symbol}:{interval}"
    cached = _cache_get(key, INDICATOR_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({
        "function":    "MACD",
        "symbol":      symbol,
        "interval":    interval,
        "series_type": "close",
    })

    analysis    = data.get("Technical Analysis: MACD", {})
    dates       = sorted(analysis.keys())
    latest_date = dates[-1] if dates else ""

    if latest_date:
        entry      = analysis[latest_date]
        macd_val   = float(entry.get("MACD", 0) or 0)
        signal_val = float(entry.get("MACD_Signal", 0) or 0)
        hist_val   = float(entry.get("MACD_Hist", 0) or 0)
    else:
        macd_val = signal_val = hist_val = 0.0

    result = {
        "symbol":    symbol,
        "macd":      round(macd_val, 4),
        "signal":    round(signal_val, 4),
        "histogram": round(hist_val, 4),
        "date":      latest_date,
        "trend":     "bullish" if hist_val > 0 else "bearish",
        "crossover": (
            "bullish_cross" if macd_val > signal_val and hist_val > 0
            else "bearish_cross" if macd_val < signal_val and hist_val < 0
            else "neutral"
        ),
    }

    _cache_set(key, result)
    return result


def fetch_bbands(symbol: str, interval: str = "daily", time_period: int = 20) -> dict:
    """
    BBANDS — Bollinger Bands (upper / middle / lower).
    1 API call. Cached 5 min.
    """
    key = f"bbands:{symbol}:{interval}:{time_period}"
    cached = _cache_get(key, INDICATOR_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({
        "function":    "BBANDS",
        "symbol":      symbol,
        "interval":    interval,
        "time_period": str(time_period),
        "series_type": "close",
    })

    analysis    = data.get("Technical Analysis: BBANDS", {})
    dates       = sorted(analysis.keys())
    latest_date = dates[-1] if dates else ""

    if latest_date:
        entry  = analysis[latest_date]
        upper  = float(entry.get("Real Upper Band", 0) or 0)
        middle = float(entry.get("Real Middle Band", 0) or 0)
        lower  = float(entry.get("Real Lower Band", 0) or 0)
    else:
        upper = middle = lower = 0.0

    bandwidth = round(upper - lower, 4) if upper and lower else 0.0

    result = {
        "symbol":    symbol,
        "upper":     round(upper, 4),
        "middle":    round(middle, 4),
        "lower":     round(lower, 4),
        "bandwidth": bandwidth,
        "date":      latest_date,
    }

    _cache_set(key, result)
    return result


def fetch_adx(symbol: str, interval: str = "daily", time_period: int = 14) -> dict:
    """
    ADX — Average Directional Index (trend strength).
    1 API call. Cached 5 min.
    """
    key = f"adx:{symbol}:{interval}:{time_period}"
    cached = _cache_get(key, INDICATOR_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({
        "function":    "ADX",
        "symbol":      symbol,
        "interval":    interval,
        "time_period": str(time_period),
    })

    analysis    = data.get("Technical Analysis: ADX", {})
    dates       = sorted(analysis.keys())
    latest_date = dates[-1] if dates else ""
    adx_val     = float(analysis[latest_date]["ADX"]) if latest_date else 0.0

    result = {
        "symbol":       symbol,
        "adx":          round(adx_val, 2),
        "date":         latest_date,
        "trendStrength": (
            "strong"   if adx_val >= 25
            else "moderate" if adx_val >= 20
            else "weak"
        ),
    }

    _cache_set(key, result)
    return result


def fetch_intraday(symbol: str, interval: str = "5min") -> dict:
    """
    TIME_SERIES_INTRADAY — recent intraday OHLCV bars.
    1 API call. Cached 5 min.
    """
    key = f"intraday:{symbol}:{interval}"
    cached = _cache_get(key, INTRADAY_CACHE_TTL)
    if cached:
        return cached

    data = _fetch({
        "function":      "TIME_SERIES_INTRADAY",
        "symbol":        symbol,
        "interval":      interval,
        "outputsize":    "compact",   # ~100 bars
        "extended_hours":"false",
    })

    series_key = f"Time Series ({interval})"
    series     = data.get(series_key, {})

    bars = [
        {
            "time":   ts,
            "open":   float(bar["1. open"]),
            "high":   float(bar["2. high"]),
            "low":    float(bar["3. low"]),
            "close":  float(bar["4. close"]),
            "volume": int(bar["5. volume"]),
        }
        for ts, bar in sorted(series.items())
    ]

    result = {
        "symbol":      symbol,
        "interval":    interval,
        "bars":        bars,
        "latestClose": bars[-1]["close"] if bars else 0,
        "meta":        data.get("Meta Data", {}),
    }

    _cache_set(key, result)
    return result


def fetch_enriched_ticker(symbol: str) -> dict:
    """
    Convenience wrapper: quote + overview + earnings in one call.
    Uses up to 3 API calls (each independently cached).
    """
    key = f"enriched:{symbol}"
    cached = _cache_get(key, INDICATOR_CACHE_TTL)
    if cached:
        return cached

    result: dict = {"symbol": symbol, "errors": {}}

    for field, fn in [("quote", fetch_quote), ("overview", fetch_overview), ("earnings", fetch_earnings)]:
        try:
            result[field] = fn(symbol)
        except Exception as exc:
            result["errors"][field] = str(exc)
            result[field] = {}

    _cache_set(key, result)
    return result


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

_VALID_MODES = frozenset({
    "quote", "overview", "earnings", "options",
    "indicators", "intraday", "enriched",
})


def fetch_alpha_vantage_data(symbols: list = None, mode: str = "quote") -> dict:
    """
    Main entry point called by the API handler.

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols to fetch (e.g. ["AAPL", "NVDA"]).
    mode : str
        One of:
          "quote"      → GLOBAL_QUOTE  (1 req/symbol, 1-min cache)
          "overview"   → OVERVIEW      (1 req/symbol, 24-h cache)
          "earnings"   → EARNINGS      (1 req/symbol, 24-h cache)
          "options"    → REALTIME_OPTIONS (1 req/symbol, premium plan required)
          "indicators" → RSI + MACD + BBands + ADX (4 req/symbol, 5-min cache)
          "intraday"   → TIME_SERIES_INTRADAY (1 req/symbol, 5-min cache)
          "enriched"   → quote + overview + earnings (3 req/symbol, 5-min cache)

    Returns
    -------
    dict with keys: data, errors, mode, symbols, updatedAt, liveData
    """
    symbols = [s.strip().upper() for s in (symbols or []) if s.strip()]
    if mode not in _VALID_MODES:
        mode = "quote"

    results: dict = {}
    errors:  dict = {}

    for sym in symbols:
        try:
            if mode == "quote":
                results[sym] = fetch_quote(sym)
            elif mode == "overview":
                results[sym] = fetch_overview(sym)
            elif mode == "earnings":
                results[sym] = fetch_earnings(sym)
            elif mode == "options":
                results[sym] = fetch_options(sym)
            elif mode == "indicators":
                results[sym] = {
                    "rsi":    fetch_rsi(sym),
                    "macd":   fetch_macd(sym),
                    "bbands": fetch_bbands(sym),
                    "adx":    fetch_adx(sym),
                }
            elif mode == "intraday":
                results[sym] = fetch_intraday(sym)
            elif mode == "enriched":
                results[sym] = fetch_enriched_ticker(sym)
        except Exception as exc:
            errors[sym] = str(exc)

    return {
        "data":      results,
        "errors":    errors,
        "mode":      mode,
        "symbols":   symbols,
        "updatedAt": int(time.time()),
        "liveData":  True,
    }
