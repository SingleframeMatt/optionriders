#!/usr/bin/env python3
"""
watchlist.py — Dynamic watchlist manager for Option Riders options bot.

Responsibilities:
  1. Maintain a CURATED_FALLBACK list of consistently trending, liquid stocks.
  2. Dynamically scan for additional trending equities using yfinance data and
     TradingView scanner (same source used by top_watch.py).
  3. Score each symbol for "trendiness" using ADX (pure Python, no TA-Lib).
  4. Gate symbols on: relative volume > 1.5x, ATR > 1% of price, and options
     open interest > 1000 on ATM strikes.
  5. Return a prioritised list: SPY + QQQ first, then scored symbols.

This module is intentionally free of ib_insync so it can be unit-tested or run
offline (yfinance only).  IBKR is only used by options_bot.py itself.
"""

import logging
import threading
import time
from typing import Optional

log = logging.getLogger("watchlist")

# ── Constants ─────────────────────────────────────────────────────────────────

# Primary symbols — always scanned first
PRIMARY_SYMBOLS = ["SPY", "QQQ"]

# Curated fallback — liquid, well-trending equities with active options chains
CURATED_FALLBACK = [
    "NVDA", "AAPL", "TSLA", "META", "AMZN",
    "MSFT", "AMD",  "GOOGL", "NFLX", "CRM",
]

# Thresholds for dynamic scan admission
MIN_RELATIVE_VOLUME   = 1.5     # relative to 20-day average daily volume
MIN_ATR_PCT           = 0.01    # ATR must be at least 1% of price
MIN_OI_ATM            = 1000    # ATM options open interest (calls OR puts)
MIN_ADX               = 20.0    # ADX threshold — anything above is "trending"

# How long to cache a full scan result (seconds)
SCAN_CACHE_TTL = 300   # 5 minutes

# ADX period
ADX_PERIOD = 14

# ── Thread-safe cache ─────────────────────────────────────────────────────────

_cache_lock   = threading.Lock()
_watchlist_cache: dict = {
    "expires_at": 0.0,
    "entries":    [],   # list of WatchlistEntry dicts
}


# ── Pure-Python indicator helpers ─────────────────────────────────────────────

def _compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """
    Wilder's Average True Range.
    Returns ATR value (not percentage).  Returns 0.0 if insufficient data.
    """
    n = len(closes)
    if n < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return 0.0
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        trs.append(tr)
    # Wilder smoothing
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return round(atr, 4)


def _compute_adx(highs: list, lows: list, closes: list, period: int = ADX_PERIOD) -> float:
    """
    Wilder's ADX (pure Python).
    ADX > 20 = trending, > 25 = strong trend, > 40 = very strong.
    Returns 0.0 if insufficient data.
    """
    n = len(closes)
    need = period * 2 + 1
    if n < need:
        return 0.0

    # True Range and directional movement
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        ph, pl   = highs[i - 1], lows[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up   = h - ph
        down = pl - l
        p_dm = up   if (up > down and up > 0)   else 0.0
        m_dm = down if (down > up and down > 0) else 0.0
        trs.append(tr)
        plus_dm.append(p_dm)
        minus_dm.append(m_dm)

    def _wilder_smooth(series, p):
        if len(series) < p:
            return []
        smoothed = [sum(series[:p])]
        for i in range(p, len(series)):
            smoothed.append(smoothed[-1] - smoothed[-1] / p + series[i])
        return smoothed

    str_  = _wilder_smooth(trs,      period)
    spdm  = _wilder_smooth(plus_dm,  period)
    smdm  = _wilder_smooth(minus_dm, period)

    dx_vals = []
    for i in range(len(str_)):
        if str_[i] == 0:
            continue
        pdi = 100.0 * spdm[i] / str_[i]
        mdi = 100.0 * smdm[i] / str_[i]
        diff = abs(pdi - mdi)
        summ = pdi + mdi
        if summ == 0:
            continue
        dx_vals.append(100.0 * diff / summ)

    if len(dx_vals) < period:
        return 0.0

    # ADX = Wilder-smoothed DX
    adx = sum(dx_vals[:period]) / period
    for i in range(period, len(dx_vals)):
        adx = (adx * (period - 1) + dx_vals[i]) / period
    return round(adx, 2)


def _compute_relative_volume(volumes: list, lookback: int = 20) -> float:
    """
    Latest bar volume divided by the 20-day average.
    Returns 0.0 if insufficient data.
    """
    if len(volumes) < lookback + 1:
        return 0.0
    avg = sum(volumes[-lookback - 1 : -1]) / lookback
    if avg <= 0:
        return 0.0
    return round(volumes[-1] / avg, 2)


def _is_choppy(closes: list, lookback: int = 20) -> bool:
    """
    Simple choppiness filter: if price oscillates around the mean more than
    it trends, we consider it choppy.
    Uses a basic ratio of total path length vs net displacement.
    Returns True if choppy/sideways, False if directional.
    """
    if len(closes) < lookback:
        return True
    window = closes[-lookback:]
    net_move = abs(window[-1] - window[0])
    total_path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    if total_path == 0:
        return True
    efficiency = net_move / total_path
    # Efficiency ratio < 0.3 = choppy (direction reverses too often)
    return efficiency < 0.30


# ── Options OI check ─────────────────────────────────────────────────────────

def _check_options_oi(symbol: str, price: float) -> bool:
    """
    Return True if the ATM strike on the nearest expiry has OI >= MIN_OI_ATM
    on at least the call or put side.  Uses yfinance options chain.
    Falls back to True for SPY/QQQ (always liquid) and for any errors.
    """
    if symbol in ("SPY", "QQQ"):
        return True  # always liquid
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        exps = t.options
        if not exps:
            return False
        # Check nearest expiry
        chain = t.option_chain(exps[0])
        atm_strike = round(price)
        calls = chain.calls
        puts  = chain.puts
        # Find rows near ATM
        for df in (calls, puts):
            near = df[abs(df["strike"] - atm_strike) <= 5]
            if not near.empty:
                max_oi = near["openInterest"].max()
                if max_oi >= MIN_OI_ATM:
                    return True
        return False
    except Exception as exc:
        log.debug("OI check failed for %s: %s", symbol, exc)
        # Default True so we don't accidentally exclude otherwise-good symbols
        return True


# ── Per-symbol scoring ────────────────────────────────────────────────────────

def score_symbol(symbol: str) -> Optional[dict]:
    """
    Download recent daily bars for `symbol` and compute:
      - ADX (trendiness score 0–100)
      - Relative volume vs 20-day average
      - ATR as % of price
      - Whether it's choppy
      - Whether ATM options OI meets threshold

    Returns a dict (WatchlistEntry) or None on error / fails gates.

    Dict keys:
      symbol, adx, rel_vol, atr_pct, choppy, oi_ok, trend_score,
      price, status   ("primary" | "curated" | "dynamic" | "excluded")
    """
    try:
        import yfinance as yf
        # 60 days of daily bars — enough for ADX(14) with buffer
        t = yf.Ticker(symbol)
        hist = t.history(period="60d", interval="1d", auto_adjust=True)
        if hist is None or len(hist) < ADX_PERIOD * 2 + 5:
            return None

        highs   = list(hist["High"].astype(float))
        lows    = list(hist["Low"].astype(float))
        closes  = list(hist["Close"].astype(float))
        volumes = list(hist["Volume"].astype(float))

        price   = closes[-1]
        if price <= 0:
            return None

        atr     = _compute_atr(highs, lows, closes)
        atr_pct = round(atr / price, 4) if price > 0 else 0.0
        adx     = _compute_adx(highs, lows, closes)
        rel_vol = _compute_relative_volume(volumes)
        choppy  = _is_choppy(closes)
        oi_ok   = _check_options_oi(symbol, price)

        # Composite trend_score: 0–100, higher = better candidate
        # Weighted: ADX 60%, inverse-choppiness 20%, ATR_pct 20%
        adx_component     = min(adx / 50.0, 1.0) * 60.0       # 0–60
        chop_component    = 0.0 if choppy else 20.0            # 0 or 20
        atr_component     = min(atr_pct / 0.03, 1.0) * 20.0   # 0–20 (capped at 3%)
        trend_score       = round(adx_component + chop_component + atr_component, 1)

        entry = {
            "symbol":      symbol,
            "price":       round(price, 2),
            "adx":         adx,
            "rel_vol":     rel_vol,
            "atr_pct":     round(atr_pct * 100, 2),  # stored as percentage
            "choppy":      choppy,
            "oi_ok":       oi_ok,
            "trend_score": trend_score,
            "active_scan": False,  # set by options_bot.py
            "status":      "excluded",  # will be updated below
        }

        # Admission gate
        passes = (
            rel_vol  >= MIN_RELATIVE_VOLUME
            and atr_pct >= MIN_ATR_PCT
            and oi_ok
            and not choppy
        )
        entry["passes_gate"] = passes

        if symbol in PRIMARY_SYMBOLS:
            entry["status"] = "primary"
        elif symbol in CURATED_FALLBACK:
            entry["status"] = "curated"
        else:
            entry["status"] = "dynamic" if passes else "excluded"

        return entry

    except Exception as exc:
        log.warning("score_symbol failed for %s: %s", symbol, exc)
        return None


# ── Dynamic candidate fetch ───────────────────────────────────────────────────

def _fetch_dynamic_candidates() -> list:
    """
    Use the TradingView scanner (same as top_watch._fetch_marketwatch) to get
    a list of high-volume US equities that may qualify.  Returns up to 30
    symbols (excluding ETFs, SPY, QQQ, and the curated list).
    """
    import json
    import urllib.request

    skip = set(PRIMARY_SYMBOLS) | set(CURATED_FALLBACK) | {
        "SPX", "IWM", "DIA", "GLD", "SLV", "USO", "TLT", "VXX",
        "UVXY", "SQQQ", "TQQQ", "SPXU", "SPXL", "UPRO", "SH", "SVXY",
        "XLF", "XLE", "XLK", "XLV", "XLI", "XLC", "XLU", "XLB", "XLRE",
        "GDX", "GDXJ", "HYG", "LQD", "AGG", "BND", "EEM", "EFA",
    }
    try:
        payload = json.dumps({
            "filter": [
                {"left": "type",            "operation": "equal",    "right": "stock"},
                {"left": "subtype",         "operation": "in_range", "right": ["common", "foreign-issuer"]},
                {"left": "exchange",        "operation": "in_range", "right": ["NYSE", "NASDAQ"]},
                {"left": "market_cap_basic","operation": "greater",  "right": 5_000_000_000},
                {"left": "relative_volume_10d_calc", "operation": "greater", "right": MIN_RELATIVE_VOLUME},
                {"left": "average_volume_10d_calc",  "operation": "greater", "right": 1_000_000},
            ],
            "options": {"lang": "en"},
            "markets": ["america"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name", "volume", "relative_volume_10d_calc", "average_volume_10d_calc"],
            "sort":    {"sortBy": "relative_volume_10d_calc", "sortOrder": "desc"},
            "range":   [0, 50],
        }).encode()
        req = urllib.request.Request(
            "https://scanner.tradingview.com/america/scan",
            headers={
                "User-Agent":   "Mozilla/5.0",
                "Content-Type": "application/json",
            },
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        candidates = []
        for row in data.get("data", []):
            sym = row["d"][0].upper().strip()
            if sym and sym not in skip and 1 < len(sym) <= 5 and sym.isalpha():
                candidates.append(sym)
                if len(candidates) >= 30:
                    break
        return candidates
    except Exception as exc:
        log.warning("Dynamic candidate fetch failed: %s", exc)
        return []


# ── Full watchlist build ──────────────────────────────────────────────────────

def build_watchlist(force_refresh: bool = False) -> list:
    """
    Build and return the full watchlist as a list of entry dicts sorted by:
      1. primary symbols first (SPY, QQQ)
      2. then by trend_score descending

    Results are cached for SCAN_CACHE_TTL seconds.

    Each entry dict contains:
      symbol, price, adx, rel_vol, atr_pct, choppy, oi_ok,
      trend_score, passes_gate, active_scan, status
    """
    now = time.time()
    if not force_refresh:
        with _cache_lock:
            if _watchlist_cache["entries"] and _watchlist_cache["expires_at"] > now:
                return list(_watchlist_cache["entries"])

    log.info("Building watchlist — scanning primaries + curated + dynamic candidates …")

    # 1. Always include primary symbols
    all_symbols = list(PRIMARY_SYMBOLS)

    # 2. Include curated fallback
    for s in CURATED_FALLBACK:
        if s not in all_symbols:
            all_symbols.append(s)

    # 3. Fetch dynamic candidates (best-effort; skip if network fails)
    try:
        dynamic = _fetch_dynamic_candidates()
        for s in dynamic:
            if s not in all_symbols:
                all_symbols.append(s)
        log.info("Dynamic candidates fetched: %d symbols", len(dynamic))
    except Exception as exc:
        log.warning("Could not fetch dynamic candidates: %s", exc)

    # 4. Score each symbol (parallel using threads for speed)
    import concurrent.futures
    entries = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(score_symbol, sym): sym for sym in all_symbols}
        done, _ = concurrent.futures.wait(futs, timeout=120)
        for fut in done:
            sym = futs[fut]
            try:
                entry = fut.result()
                if entry is not None:
                    entries.append(entry)
            except Exception as exc:
                log.warning("Score future error for %s: %s", sym, exc)

    # 5. For symbols that failed to score, add a minimal placeholder so they
    #    still appear in the dashboard (primaries are never dropped)
    scored_syms = {e["symbol"] for e in entries}
    for sym in PRIMARY_SYMBOLS + CURATED_FALLBACK:
        if sym not in scored_syms:
            entries.append({
                "symbol":      sym,
                "price":       None,
                "adx":         0.0,
                "rel_vol":     0.0,
                "atr_pct":     0.0,
                "choppy":      True,
                "oi_ok":       False,
                "trend_score": 0.0,
                "passes_gate": False,
                "active_scan": False,
                "status":      "primary" if sym in PRIMARY_SYMBOLS else "curated",
            })

    # 6. Sort: primaries first, then by trend_score descending
    priority = {sym: i for i, sym in enumerate(PRIMARY_SYMBOLS)}

    def _sort_key(e):
        pri = priority.get(e["symbol"], len(PRIMARY_SYMBOLS))
        return (pri, -e.get("trend_score", 0.0))

    entries.sort(key=_sort_key)

    log.info(
        "Watchlist built: %d total (%d primaries, %d curated, %d dynamic)",
        len(entries),
        sum(1 for e in entries if e["status"] == "primary"),
        sum(1 for e in entries if e["status"] == "curated"),
        sum(1 for e in entries if e["status"] == "dynamic"),
    )

    with _cache_lock:
        _watchlist_cache["entries"]    = entries
        _watchlist_cache["expires_at"] = now + SCAN_CACHE_TTL

    return list(entries)


def get_active_scan_symbols(
    entries: list,
    first_hour_elapsed: bool,
    max_symbols: int = 10,
) -> list:
    """
    Decide which symbols are actively scanned this cycle.

    Logic:
      - Always include SPY + QQQ (primary).
      - If first_hour_elapsed is False (within the first hour of market open):
          only scan SPY + QQQ.
      - If first_hour_elapsed is True (no signal on primaries within first hour):
          expand to curated + any dynamic symbols that pass_gate,
          sorted by trend_score, up to max_symbols total.

    Returns a list of symbol strings in priority order.
    """
    primaries  = [e["symbol"] for e in entries if e["status"] == "primary"]
    if not first_hour_elapsed:
        return primaries

    # Expand: add curated + qualifying dynamic symbols
    expansion = [
        e for e in entries
        if e["status"] in ("curated", "dynamic") and e.get("passes_gate", False)
    ]
    expansion.sort(key=lambda e: -e.get("trend_score", 0.0))

    active = list(primaries)
    for e in expansion:
        if len(active) >= max_symbols:
            break
        if e["symbol"] not in active:
            active.append(e["symbol"])

    return active


def mark_active(entries: list, active_symbols: list) -> list:
    """Return a new list of entries with active_scan field updated."""
    active_set = set(active_symbols)
    updated = []
    for e in entries:
        e2 = dict(e)
        e2["active_scan"] = e2["symbol"] in active_set
        updated.append(e2)
    return updated
