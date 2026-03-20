#!/usr/bin/env python3
"""
top_watch.py — Cross-source trending ticker detector for Option Riders.

Fetches trending / most-active stocks from four sources:
  • StockTwits  — public trending symbols JSON API
  • MarketWatch — most-active page (via TradingView scanner — MW is geo-blocked)
  • Barchart    — most-active / unusual options (reuses barchart_proxy cache)
  • Finnviz     — top gainers/losers/active from Finviz homepage

Tickers appearing on 2+ sources are flagged as "TOP Watch".
Results are cached for CACHE_TTL_SECONDS to avoid hammering external sites.
"""

import concurrent.futures
import json
import re
import threading
import time
import urllib.request

CACHE_TTL_SECONDS = 300   # 5-minute cache

_cache_lock = threading.Lock()
_cache = {"expires_at": 0.0, "payload": None}

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_TIMEOUT = 12   # per-source network timeout (seconds)

# Broad-market ETFs and volatility products — excluded from cross-source matching
_SKIP = {
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "USO", "TLT", "VXX",
    "UVXY", "SQQQ", "TQQQ", "SPXU", "SPXL", "UPRO", "SH", "SVXY",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLC", "XLU", "XLB", "XLRE",
    "GDX", "GDXJ", "HYG", "LQD", "AGG", "BND", "EEM", "EFA",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url, extra_headers=None, data=None, method="GET"):
    headers = {"User-Agent": _UA, **(extra_headers or {})}
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


# ── Per-source fetchers ───────────────────────────────────────────────────────

def _fetch_stocktwits():
    """Trending symbols from StockTwits public API (no auth required)."""
    try:
        raw = _get("https://api.stocktwits.com/api/2/trending/symbols.json")
        data = json.loads(raw)
        return [s["symbol"].upper() for s in data.get("symbols", [])]
    except Exception as exc:
        print(f"[top_watch] StockTwits: {exc}")
        return []


def _fetch_marketwatch():
    """
    Most-active stocks via TradingView scanner API.
    (MarketWatch.com is geo-blocked/login-gated for server-side fetches.)
    Returns tickers sorted by relative volume — the same "what's moving today"
    signal that MarketWatch's most-active list tracks.
    """
    try:
        payload = json.dumps({
            "filter": [
                {"left": "type",     "operation": "equal",    "right": "stock"},
                {"left": "subtype",  "operation": "in_range", "right": ["common", "foreign-issuer"]},
                {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                {"left": "market_cap_basic", "operation": "greater", "right": 500_000_000},
            ],
            "options": {"lang": "en"},
            "markets": ["america"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "volume", "relative_volume_10d_calc"],
            "sort": {"sortBy": "volume", "sortOrder": "desc"},
            "range": [0, 40],
        }).encode()
        raw = _get(
            "https://scanner.tradingview.com/america/scan",
            extra_headers={"Content-Type": "application/json"},
            data=payload,
            method="POST",
        )
        data = json.loads(raw)
        return [row["d"][0] for row in data.get("data", [])]
    except Exception as exc:
        print(f"[top_watch] MarketWatch/TV: {exc}")
        return []


def _fetch_barchart():
    """Most-active and unusual-options symbols from Barchart (uses cached proxy)."""
    try:
        from barchart_proxy import fetch_options_activity
        data = fetch_options_activity()
        seen = []
        for key in ("mostActive", "unusual"):
            for row in data.get(key, []):
                sym = (row.get("symbol") or row.get("ticker") or "").upper().strip()
                if sym and sym not in seen:
                    seen.append(sym)
        return seen
    except Exception as exc:
        print(f"[top_watch] Barchart: {exc}")
        return []


def _fetch_finnviz():
    """
    Top movers from Finviz homepage (top gainers / losers / most active tables).
    Finviz embeds ticker symbols as data-boxover-ticker attributes on their homepage.
    """
    try:
        raw = _get("https://finviz.com/")
        # Finviz homepage: data-boxover-ticker="NVDA" on each table row
        found = re.findall(r'data-boxover-ticker="([A-Z]{1,5})"', raw)
        return list(dict.fromkeys(found))   # deduplicated, order-preserved
    except Exception as exc:
        print(f"[top_watch] Finviz: {exc}")
        return []


# ── Price enrichment ──────────────────────────────────────────────────────────

def _quick_prices(symbols):
    """
    Return {symbol: {price, changePct}} for a list of symbols via yfinance.
    """
    if not symbols:
        return {}
    try:
        import yfinance as yf
        syms = list(symbols)
        raw = yf.download(syms, period="5d", interval="1d",
                          progress=False, auto_adjust=True)

        def _closes(sym):
            try:
                if hasattr(raw.columns, "levels"):
                    return list(raw["Close"][sym].dropna().astype(float))
                return list(raw["Close"].dropna().astype(float))
            except Exception:
                return []

        result = {}
        for sym in syms:
            vals = _closes(sym)
            if len(vals) >= 2:
                price = round(vals[-1], 2)
                prev  = vals[-2]
                chg   = round((price - prev) / prev * 100, 2) if prev else 0.0
                result[sym] = {"price": price, "changePct": chg}
        return result
    except Exception as exc:
        print(f"[top_watch] price fetch: {exc}")
        return {}


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_top_watch(force_refresh=False):
    """
    Return tickers mentioned on 2+ sources with source attribution and prices.
    Cached for CACHE_TTL_SECONDS.
    """
    now = time.time()
    if not force_refresh:
        with _cache_lock:
            if _cache["payload"] and _cache["expires_at"] > now:
                return _cache["payload"]

    source_fns = {
        "StockTwits":  _fetch_stocktwits,
        "MarketWatch": _fetch_marketwatch,   # powered by TradingView scanner
        "Barchart":    _fetch_barchart,
        "Finviz":      _fetch_finnviz,
    }

    # Fetch all sources in parallel
    results = {name: [] for name in source_fns}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fs = {pool.submit(fn): name for name, fn in source_fns.items()}
        done, _ = concurrent.futures.wait(fs, timeout=16)
        for fut in done:
            name = fs[fut]
            try:
                results[name] = fut.result() or []
            except Exception as exc:
                print(f"[top_watch] {name} future: {exc}")

    # Build ticker → sources map
    ticker_sources = {}
    for source_name, tickers in results.items():
        for sym in tickers:
            sym = sym.upper().strip()
            if not sym or sym in _SKIP:
                continue
            if not (1 < len(sym) <= 5) or not sym.isalpha():
                continue
            ticker_sources.setdefault(sym, [])
            if source_name not in ticker_sources[sym]:
                ticker_sources[sym].append(source_name)

    # Keep only tickers on 2+ sources; sort by count desc, then alpha
    cross = [
        {"ticker": sym, "sources": srcs, "sourceCount": len(srcs)}
        for sym, srcs in ticker_sources.items()
        if len(srcs) >= 2
    ]
    cross.sort(key=lambda x: (-x["sourceCount"], x["ticker"]))

    # Enrich with quick price data
    syms = [item["ticker"] for item in cross]
    prices = _quick_prices(syms)
    for item in cross:
        p = prices.get(item["ticker"])
        if p:
            item["price"]     = p["price"]
            item["changePct"] = p["changePct"]
        else:
            item["price"]     = None
            item["changePct"] = None

    # Enrich with nearest OTM bid-ask spread and put/call ratio from Barchart
    try:
        from barchart_proxy import fetch_otm_spreads_for_symbols
        otm_data = fetch_otm_spreads_for_symbols(syms)
        for item in cross:
            entry = otm_data.get(item["ticker"]) or {}
            item["otmSpread"]    = entry.get("otmSpread")
            item["putCallRatio"] = entry.get("putCallRatio")
    except Exception as exc:
        print(f"[top_watch] OTM spreads: {exc}")
        for item in cross:
            item.setdefault("otmSpread", None)
            item.setdefault("putCallRatio", None)

    source_status = {name: bool(tks) for name, tks in results.items()}

    payload = {
        "topWatch":     cross,
        "sourceStatus": source_status,
        "updatedAt":    time.strftime("%H:%M UTC", time.gmtime()),
        "liveData":     True,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = now + CACHE_TTL_SECONDS

    return payload
