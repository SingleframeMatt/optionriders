#!/usr/bin/env python3
"""
premarket_scan.py — Pre-market gap scanner for Option Riders.

Hits TradingView's public scanner endpoint (no auth, free) to pull every
US-listed equity with meaningful pre-market action, filters for option-
tradable liquidity, and ranks for day-trade setups.

Output is tuned for your style: long-debit weeklies, ATM, ~10 DTE, sold
same day. So the ranking favors:
  * Mega-cap liquid names (penny-wide ATM spreads)
  * Pre-market volume confirmation (real move, not stale tick)
  * Gap size vs ATR (movement worth paying premium for)
  * Avoids names with massive earnings gaps (IV crush trap)

Usage:
    python premarket_scan.py                     # default scan
    python premarket_scan.py --min-gap 1.5       # gap threshold (%)
    python premarket_scan.py --top 25            # show top N
    python premarket_scan.py --side up           # gappers up only
    python premarket_scan.py --side down         # gappers down only
    python premarket_scan.py --json              # machine-readable
    python premarket_scan.py --confluence        # add confluence scoring
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


TV_SCAN_URL = "https://scanner.tradingview.com/america/scan"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Curated whitelist of names with genuinely tight ATM weekly option spreads.
# Market cap alone is a poor liquidity proxy — many mega-caps (SNDK, VRT, LRCX)
# have $0.20-1.00 ATM spreads that destroy day-trade math. Only names below
# have penny-wide or near-penny ATM weeklies.

# CORE 5 — user's named priority list. Always surfaced in the report
# regardless of score, as long as there's any meaningful pre-market move.
CORE_TICKERS = {"AMD", "NVDA", "TSLA", "MSFT", "TSM"}

LIQUID_OPTIONS_TICKERS = {
    # Tier 1 — penny-wide ATM (ETFs + mega-cap tech)
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA",
    "META", "AMZN", "GOOGL", "GOOG", "TSM",
    "MU", "INTC",
    # Tier 2 — tight $0.05-ish ATM, usually fine
    "NFLX", "COST", "AVGO", "QCOM", "AMAT",
    "ORCL", "DIS", "BA", "BAC", "JPM",
    "COIN", "MSTR", "PLTR", "BABA", "UBER",
    "CRM", "SHOP", "GS", "MS", "V", "MA", "WMT",
    "SMCI", "MARA", "RIOT", "RBLX", "SOFI", "HOOD",
    "F", "GE", "T", "VZ", "XOM", "CVX",
    "GLD", "SLV", "USO", "TLT",
}

# Columns we ask TradingView for. Order matters — index used below.
COLUMNS = [
    "name",                          # 0  ticker
    "description",                   # 1  company name
    "close",                         # 2  prev close
    "premarket_close",               # 3  pre-market last
    "premarket_change",              # 4  $ change pre-market
    "premarket_change_abs",          # 5  |change| pre-market
    "premarket_change_from_open",    # 6  % change pre-market
    "premarket_volume",              # 7  pre-market volume
    "premarket_gap",                 # 8  pre-market gap %
    "volume",                        # 9  prev session volume
    "average_volume_30d_calc",       # 10 30d avg volume
    "market_cap_basic",              # 11 market cap
    "ATR",                           # 12 ATR(14)
    "Recommend.All",                 # 13 TV technical rating
    "earnings_release_next_date",    # 14 next earnings (epoch ms)
]


def _tv_request(min_gap_pct: float, side: str, universe: set[str] | None,
                max_results: int = 100) -> list:
    """Query TradingView scanner for premarket movers."""
    sort_col = "premarket_change" if side == "up" else (
        "premarket_change" if side == "down" else "premarket_change_abs"
    )
    sort_order = "asc" if side == "down" else "desc"

    filters: list[dict] = [
        {"left": "type",     "operation": "equal",    "right": "stock"},
        {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
        {"left": "is_primary", "operation": "equal", "right": True},
        # Pre-market volume must be meaningful (not a single tick)
        {"left": "premarket_volume", "operation": "greater", "right": 1_000},
    ]
    # When filtering to a hand-picked liquidity whitelist, skip subtype/cap
    # filters — they reject ETFs (SPY/QQQ) which we want.
    if not universe:
        filters.append({"left": "subtype",  "operation": "in_range",
                        "right": ["common", "foreign-issuer"]})
        filters.append({"left": "market_cap_basic", "operation": "greater",
                        "right": 5_000_000_000})
        filters.append({"left": "close", "operation": "in_range", "right": [5, 2000]})
    if side == "up":
        filters.append({"left": "premarket_change", "operation": "greater",
                        "right": min_gap_pct})
    elif side == "down":
        filters.append({"left": "premarket_change", "operation": "less",
                        "right": -min_gap_pct})
    else:  # both
        filters.append({"left": "premarket_change_abs", "operation": "greater",
                        "right": min_gap_pct})

    payload: dict = {
        "filter": filters,
        "options": {"lang": "en"},
        "markets": ["america"],
        "columns": COLUMNS,
        "sort": {"sortBy": sort_col, "sortOrder": sort_order},
        "range": [0, max_results],
    }
    if universe:
        # Hand-picked liquidity whitelist — explicitly request these tickers.
        payload["symbols"] = {"tickers": [f"NASDAQ:{t}" for t in universe]
                                       + [f"NYSE:{t}"  for t in universe]
                                       + [f"AMEX:{t}"  for t in universe]}
    else:
        payload["symbols"] = {"query": {"types": []}, "tickers": []}

    req = urllib.request.Request(
        TV_SCAN_URL,
        data=json.dumps(payload).encode(),
        headers={"User-Agent": _UA, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data.get("data", [])


def _score(row: dict) -> int:
    """
    Day-trade quality score, 0-100. Tuned for long-debit ATM weeklies.
    Higher = better candidate.
    """
    score = 0
    gap_pct = abs(row.get("gap_pct") or 0)
    pm_vol = row.get("pm_volume") or 0
    avg_vol = row.get("avg_vol_30d") or 1
    mcap_b = (row.get("market_cap") or 0) / 1e9
    atr = row.get("atr") or 0.01
    price = row.get("price") or 1
    days_to_earn = row.get("days_to_earnings")
    tv_rating = row.get("tv_rating") or 0  # -1..1

    # Gap size, sweet spot 1-5%. Above 8% = earnings gap trap.
    if 1.0 <= gap_pct <= 5.0:
        score += 30
    elif 5.0 < gap_pct <= 8.0:
        score += 15
    elif gap_pct > 8.0:
        score += 5  # earnings gap zone — IV crush risk
    else:
        score += 10

    # Pre-market volume relative to typical: 5%+ of 30d avg = strong
    pm_to_avg = pm_vol / avg_vol if avg_vol else 0
    if pm_to_avg >= 0.10:
        score += 25
    elif pm_to_avg >= 0.05:
        score += 18
    elif pm_to_avg >= 0.02:
        score += 10
    else:
        score += 3

    # Market cap → option liquidity proxy
    if mcap_b >= 100:
        score += 20
    elif mcap_b >= 25:
        score += 15
    elif mcap_b >= 10:
        score += 10
    else:
        score += 5

    # Move is meaningful vs ATR
    move_atr = abs(row.get("pm_change_dollar") or 0) / atr if atr else 0
    if 0.5 <= move_atr <= 2.0:
        score += 15
    elif 2.0 < move_atr <= 3.0:
        score += 8  # extended
    elif move_atr > 3.0:
        score += 2  # parabolic, IV crush territory
    else:
        score += 5

    # Earnings within 2 days = IV crush trap
    if days_to_earn is not None and 0 <= days_to_earn <= 2:
        score -= 25  # heavy penalty
    elif days_to_earn is not None and 0 <= days_to_earn <= 7:
        score -= 5

    # TV's technical rating as tiebreaker (range -1..1)
    score += int(tv_rating * 5)

    return max(0, min(100, score))


def _normalize(rows: list) -> list[dict]:
    """Convert TradingView rows to clean dicts. Compute $/% changes from
    prices directly to dodge ambiguous field semantics in the scanner API."""
    import time
    now_s = time.time()
    out = []
    for r in rows:
        d = r.get("d") or []
        if len(d) < len(COLUMNS):
            continue
        ticker = d[0]
        prev_close = d[2] or 0
        pm_close = d[3] or 0
        # Trust price diff over the API's pm-change field — sign was wrong on gap-down.
        pm_change_dollar = (pm_close - prev_close) if (pm_close and prev_close) else 0
        pm_change_pct = (pm_change_dollar / prev_close * 100) if prev_close else 0
        pm_vol = d[7] or 0
        avg_vol = d[10] or 0
        mcap = d[11] or 0
        atr = d[12] or 0
        tv_rating = d[13] or 0
        # earnings_release_next_date returns seconds (or 0/None if unknown).
        next_earn_s = d[14]
        if next_earn_s and next_earn_s > now_s:
            days_to_earn = int((next_earn_s - now_s) / 86400)
        else:
            days_to_earn = None
        out.append({
            "ticker": ticker,
            "name": d[1],
            "prev_close": prev_close,
            "price": pm_close or prev_close,
            "pm_change_dollar": pm_change_dollar,
            "gap_pct": pm_change_pct,
            "pm_volume": pm_vol,
            "avg_vol_30d": avg_vol,
            "market_cap": mcap,
            "atr": atr,
            "tv_rating": tv_rating,
            "days_to_earnings": days_to_earn,
        })
    for r in out:
        r["score"] = _score(r)
    return out


# ── Trend scan (ADX trend / early-pop hunter) ────────────────────────────────
# The gap scan above needs a pre-market move. This path finds names already in
# a clean directional trend (what SNDK was) — regardless of a gap — using ADX
# for trend strength, ±DI for direction, and the SMA stack for alignment.

TREND_COLUMNS = [
    "name",                        # 0  ticker
    "description",                 # 1  company
    "close",                       # 2  last price
    "change",                      # 3  day % change
    "volume",                      # 4  session volume
    "average_volume_10d_calc",     # 5  10d avg volume
    "relative_volume_10d_calc",    # 6  today vs typical (RVOL)
    "market_cap_basic",            # 7  market cap
    "ATR",                         # 8  ATR(14)
    "ADX",                         # 9  trend strength (14)
    "ADX+DI",                      # 10 bullish directional
    "ADX-DI",                      # 11 bearish directional
    "SMA20",                       # 12
    "SMA50",                       # 13
    "SMA200",                      # 14
    "Perf.W",                      # 15 1-week performance %
    "Recommend.All",               # 16 TV rating -1..1
    "earnings_release_next_date",  # 17 next earnings (epoch s)
]


def _tv_trend_request(universe: set[str] | None, min_adx: float,
                      max_results: int = 100) -> list:
    """Query TradingView for names with ADX above `min_adx` (a real trend)."""
    filters: list[dict] = [
        {"left": "type",     "operation": "equal",    "right": "stock"},
        {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
        {"left": "is_primary", "operation": "equal", "right": True},
        {"left": "ADX", "operation": "greater", "right": min_adx},
    ]
    if not universe:
        filters.append({"left": "subtype",  "operation": "in_range",
                        "right": ["common", "foreign-issuer"]})
        filters.append({"left": "market_cap_basic", "operation": "greater",
                        "right": 5_000_000_000})
        filters.append({"left": "close", "operation": "in_range", "right": [5, 5000]})
        # Broad scan still needs tradable liquidity in the shares themselves.
        filters.append({"left": "average_volume_10d_calc", "operation": "greater",
                        "right": 1_000_000})

    payload: dict = {
        "filter": filters,
        "options": {"lang": "en"},
        "markets": ["america"],
        "columns": TREND_COLUMNS,
        "sort": {"sortBy": "ADX", "sortOrder": "desc"},
        "range": [0, max_results],
    }
    if universe:
        payload["symbols"] = {"tickers": [f"NASDAQ:{t}" for t in universe]
                                       + [f"NYSE:{t}"  for t in universe]
                                       + [f"AMEX:{t}"  for t in universe]}
    else:
        payload["symbols"] = {"query": {"types": []}, "tickers": []}

    req = urllib.request.Request(
        TV_SCAN_URL,
        data=json.dumps(payload).encode(),
        headers={"User-Agent": _UA, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data.get("data", [])


def _trend_score(row: dict) -> int:
    """Trend-quality score, 0-100. Rewards a clean, confirmed, not-yet-exhausted
    trend with real volume; penalises over-extension (late chase) and earnings."""
    score = 0
    adx = row["adx"]
    # Trend strength — the sweet spot is strong but not blown-out.
    if 25 <= adx <= 40:
        score += 35
    elif 20 <= adx < 25:
        score += 30           # fresh/early trend — often the best entry
    elif 40 < adx <= 50:
        score += 20           # strong but extended
    elif adx > 50:
        score += 8            # very extended — reversal risk
    else:
        score += 5

    # Directional cleanliness — how one-sided is the trend (DI spread).
    di_spread = abs(row["di_plus"] - row["di_minus"])
    if di_spread >= 15:
        score += 20
    elif di_spread >= 8:
        score += 13
    elif di_spread >= 4:
        score += 6

    # Moving-average stack alignment (0..3 stacked in trend direction).
    score += row["ma_stack"] * 7          # up to +21

    # Relative volume — is the move real participation?
    rv = row["rel_vol"] or 0
    if rv >= 1.5:
        score += 15
    elif rv >= 1.1:
        score += 10
    elif rv >= 0.8:
        score += 5

    # Over-extension penalty — price too far from SMA20 in ATRs = late chase.
    if row["ext_atr"] > 5:
        score -= 12
    elif row["ext_atr"] > 3.5:
        score -= 5

    # Earnings trap (IV crush / gap risk).
    d2e = row["days_to_earnings"]
    if d2e is not None and 0 <= d2e <= 2:
        score -= 25
    elif d2e is not None and 0 <= d2e <= 7:
        score -= 5

    # Penny-wide options names are easier for you to actually trade.
    if row["in_whitelist"]:
        score += 8

    return max(0, min(100, score))


def _normalize_trend(rows: list) -> list[dict]:
    """Convert TradingView trend rows to clean dicts + score them."""
    import time
    now_s = time.time()
    out = []
    for r in rows:
        d = r.get("d") or []
        if len(d) < len(TREND_COLUMNS):
            continue
        price = d[2] or 0
        atr = d[8] or 0.01
        di_plus = d[10] or 0
        di_minus = d[11] or 0
        sma20, sma50, sma200 = d[12] or 0, d[13] or 0, d[14] or 0
        direction = "up" if di_plus >= di_minus else "down"
        if direction == "up":
            stack = int(price > sma20) + int(sma20 > sma50) + (int(sma50 > sma200) if sma200 else 0)
        else:
            stack = int(price < sma20) + int(sma20 < sma50) + (int(sma50 < sma200) if sma200 else 0)
        ext_atr = abs(price - sma20) / atr if (atr and sma20) else 0
        next_earn_s = d[17]
        days_to_earn = (int((next_earn_s - now_s) / 86400)
                        if (next_earn_s and next_earn_s > now_s) else None)
        out.append({
            "ticker": d[0], "name": d[1], "price": price,
            "change_pct": d[3] or 0, "volume": d[4] or 0,
            "avg_vol_10d": d[5] or 0, "rel_vol": d[6] or 0,
            "market_cap": d[7] or 0, "atr": atr,
            "adx": d[9] or 0, "di_plus": di_plus, "di_minus": di_minus,
            "direction": direction, "ma_stack": stack, "ext_atr": ext_atr,
            "perf_w": d[15] or 0, "tv_rating": d[16] or 0,
            "days_to_earnings": days_to_earn,
            "in_whitelist": d[0] in LIQUID_OPTIONS_TICKERS,
            "fresh": 20 <= (d[9] or 0) <= 30,   # early trend = pop candidate
        })
    for r in out:
        r["score"] = _trend_score(r)
    return out


# ── CLI output ─────────────────────────────────────────────────────────────────

# Only emit ANSI when writing to a real terminal — keeps the saved daily
# report (redirected to a file) clean plain-text.
if sys.stdout.isatty():
    _GREEN, _RED, _YEL, _DIM, _BOLD, _RST = (
        "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[2m", "\x1b[1m", "\x1b[0m"
    )
else:
    _GREEN = _RED = _YEL = _DIM = _BOLD = _RST = ""


def _color(text: str, code: str) -> str:
    return f"{code}{text}{_RST}" if sys.stdout.isatty() else text


def _fmt_volume(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(int(v))


def _fmt_mcap(v: float) -> str:
    if v >= 1e12:
        return f"{v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{v / 1e9:.0f}B"
    if v >= 1e6:
        return f"{v / 1e6:.0f}M"
    return str(int(v))


def _print_table(rows: list[dict], top: int) -> None:
    rows = sorted(rows, key=lambda r: -r["score"])[:top]
    if not rows:
        print("\n  No pre-market movers match the filter.\n")
        return

    print()
    print(f"  {_BOLD}{'':<2}{'TICKER':<7}{'PRICE':>9}{'GAP%':>9}{'$MOVE':>9}"
          f"{'PM VOL':>9}{'%30D':>7}{'MCAP':>7}{'ATR':>7}"
          f"{'EARN':>7}{'SCORE':>9}{_RST}")
    print(f"  {'─' * 88}")

    for r in rows:
        gap = r["gap_pct"]
        gap_col = _GREEN if gap > 0 else _RED
        score = r["score"]
        score_col = (_GREEN if score >= 65 else _YEL if score >= 45 else _RED)
        pm_to_avg = (r["pm_volume"] / r["avg_vol_30d"] * 100) if r["avg_vol_30d"] else 0
        earn = r["days_to_earnings"]
        if earn is None:
            earn_disp, earn_col = "—", _DIM
        elif earn <= 2:
            earn_disp, earn_col = f"{earn}d", _RED
        elif earn <= 7:
            earn_disp, earn_col = f"{earn}d", _YEL
        else:
            earn_disp, earn_col = f"{earn}d", _DIM

        is_core = r["ticker"] in CORE_TICKERS
        marker = _color("★ ", _BOLD) if is_core else "  "

        # Format raw strings first, then color-wrap (so width specifiers don't fight the ANSI codes).
        gap_s   = f"{gap:+.2f}%"
        score_s = f"{score:>3}/100"
        print(
            f"  {marker}"
            f"{r['ticker']:<7}"
            f"{r['price']:>9.2f}"
            f"{_color(gap_s, gap_col):>9}"
            + (f"{r['pm_change_dollar']:>+9.2f}"
               f"{_fmt_volume(r['pm_volume']):>9}"
               f"{pm_to_avg:>6.1f}%"
               f"{_fmt_mcap(r['market_cap']):>7}"
               f"{r['atr']:>7.2f}"
               f"  {_color(earn_disp, earn_col):>5}"
               f"  {_color(score_s, score_col):>9}")
        )

    print()
    # Core 5 watch — always shown when they have any meaningful pre-market move,
    # regardless of score. These are the user's named priority tickers.
    core_rows = sorted([r for r in rows if r["ticker"] in CORE_TICKERS],
                       key=lambda r: -abs(r["gap_pct"]))
    if core_rows:
        print(f"  {_BOLD}★ CORE 5 watch (AMD, NVDA, TSLA, MSFT, TSM):{_RST}")
        for r in core_rows:
            arrow = "▲" if r["gap_pct"] > 0 else "▼"
            side = "calls" if r["gap_pct"] > 0 else "puts"
            warn = ""
            if r["days_to_earnings"] is not None and 0 <= r["days_to_earnings"] <= 7:
                warn = _color(f"  ⚠ earnings in {r['days_to_earnings']}d — IV ramp risk", _YEL)
            print(f"    {arrow} {r['ticker']:<5} ATM {side:<5}  "
                  f"{r['gap_pct']:+.2f}%  ${r['price']:.2f}  "
                  f"score {r['score']}/100{warn}")
        print()

    # Score-based standouts — separate from Core 5 visibility
    actionable = sorted([r for r in rows if r["score"] >= 65],
                        key=lambda r: -r["score"])
    if actionable:
        print(f"  {_BOLD}High-conviction setups (score ≥ 65):{_RST}")
        for r in actionable[:5]:
            arrow = "▲" if r["gap_pct"] > 0 else "▼"
            side = "calls" if r["gap_pct"] > 0 else "puts"
            warn = ""
            if r["days_to_earnings"] is not None and 0 <= r["days_to_earnings"] <= 2:
                warn = _color("  ⚠ EARNINGS — IV crush risk", _YEL)
            print(f"    {arrow} {r['ticker']:<5} ATM {side:<5}  "
                  f"{r['gap_pct']:+.2f}%  ${r['price']:.2f}  "
                  f"score {r['score']}/100{warn}")
        print()


def _print_trend_table(rows: list[dict], top: int) -> None:
    rows = sorted(rows, key=lambda r: -r["score"])[:top]
    if not rows:
        print("\n  No trending names match the filter — market's likely chop today. "
              "That's a sit-out signal, not a reason to force one.\n")
        return

    print()
    print(f"  {_BOLD}{'':<2}{'TICKER':<7}{'PRICE':>9}{'DAY%':>8}{'ADX':>6}"
          f"{'DIR':>6}{'DI±':>6}{'MA':>4}{'RVOL':>7}{'WK%':>8}{'EARN':>7}{'SCORE':>10}{_RST}")
    print(f"  {'─' * 90}")

    for r in rows:
        up = r["direction"] == "up"
        dir_s = "▲ up" if up else "▼ dn"
        dir_col = _GREEN if up else _RED
        score = r["score"]
        score_col = _GREEN if score >= 65 else _YEL if score >= 45 else _RED
        di_spread = abs(r["di_plus"] - r["di_minus"])
        earn = r["days_to_earnings"]
        if earn is None:
            earn_disp, earn_col = "—", _DIM
        else:
            earn_disp = f"{earn}d"
            earn_col = _RED if earn <= 2 else _YEL if earn <= 7 else _DIM
        star = _color("★ ", _BOLD) if r["in_whitelist"] else "  "

        chg_s = f"{r['change_pct']:+.1f}%"
        chg_col = _GREEN if r["change_pct"] >= 0 else _RED
        wk_s = f"{r['perf_w']:+.1f}%"
        score_s = f"{score:>3}/100"
        print(
            f"  {star}{r['ticker']:<7}{r['price']:>9.2f}"
            f"{_color(chg_s, chg_col):>8}"
            f"{r['adx']:>6.0f}"
            f"{_color(dir_s, dir_col):>6}"
            f"{di_spread:>6.0f}"
            f"{r['ma_stack']:>3}/3"
            f"{r['rel_vol']:>6.1f}x"
            f"{wk_s:>8}"
            f"  {_color(earn_disp, earn_col):>5}"
            f"  {_color(score_s, score_col):>10}"
        )

    print()
    # Fresh trends = the "about to run / early" ones (ADX 20-30, real volume,
    # aligned MAs, not extended). Your best entries live here, not in the
    # blown-out ADX>45 names you'd be chasing.
    fresh = sorted([r for r in rows if r["fresh"] and r["ma_stack"] >= 2
                    and (r["rel_vol"] or 0) >= 1.0 and r["ext_atr"] <= 3.5
                    and r["score"] >= 55],
                   key=lambda r: -r["score"])
    if fresh:
        print(f"  {_BOLD}🔥 Fresh trends — early ADX + real volume (best R:R, not a chase):{_RST}")
        for r in fresh[:5]:
            arrow = "▲" if r["direction"] == "up" else "▼"
            side = "calls" if r["direction"] == "up" else "puts"
            liq = "" if r["in_whitelist"] else _color("  (check option spread — off whitelist)", _YEL)
            print(f"    {arrow} {r['ticker']:<5} ATM {side:<5}  ADX {r['adx']:.0f}  "
                  f"RVOL {r['rel_vol']:.1f}x  score {r['score']}/100{liq}")
        print()

    strong = sorted([r for r in rows if r["adx"] > 40 and r["score"] >= 55],
                    key=lambda r: -r["adx"])
    if strong:
        print(f"  {_BOLD}Mature trends (ADX>40 — strong but extended, wait for a pullback):{_RST}")
        for r in strong[:5]:
            arrow = "▲" if r["direction"] == "up" else "▼"
            print(f"    {arrow} {r['ticker']:<5}  ADX {r['adx']:.0f}  "
                  f"{r['ext_atr']:.1f} ATR from SMA20  score {r['score']}/100")
        print()


# ── Confluence enrichment ─────────────────────────────────────────────────────

def _enrich_confluence(rows: list[dict]) -> list[dict]:
    """Optionally run confluence_scan on the top candidates."""
    try:
        import confluence_scan
    except Exception as exc:
        print(f"# confluence_scan import failed: {exc}", file=sys.stderr)
        return rows
    tickers = [r["ticker"] for r in rows[:20]]
    enriched = {t: confluence_scan._score_ticker(t) for t in tickers}
    for r in rows:
        c = enriched.get(r["ticker"])
        if c and not c.error:
            r["confluence"] = c.total
            r["bias"] = c.bias
            r["regime"] = c.regime
            # Boost score if confluence aligns with gap direction
            if (r["gap_pct"] > 0 and c.total >= 7) or (r["gap_pct"] < 0 and c.total <= 3):
                r["score"] = min(100, r["score"] + 15)
            elif (r["gap_pct"] > 0 and c.total <= 3) or (r["gap_pct"] < 0 and c.total >= 7):
                r["score"] = max(0, r["score"] - 15)  # gap fights bias
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--min-gap", type=float, default=1.0,
                   help="Minimum |gap %%| to include (default 1.0)")
    p.add_argument("--top", type=int, default=20,
                   help="Number of rows to display (default 20)")
    p.add_argument("--side", choices=["up", "down", "both"], default="both",
                   help="Direction filter (default both)")
    p.add_argument("--json", action="store_true",
                   help="JSON output instead of table")
    p.add_argument("--confluence", action="store_true",
                   help="Add confluence scoring (slower, ~10s)")
    p.add_argument("--all", action="store_true",
                   help="Scan ALL liquid stocks instead of the curated "
                        "penny-wide-options whitelist (default: whitelist only)")
    p.add_argument("--trend", action="store_true",
                   help="Hunt trending / early-breakout names (ADX-based) "
                        "instead of pre-market gaps — finds SNDK-style movers")
    p.add_argument("--min-adx", type=float, default=20.0,
                   help="Minimum ADX for --trend mode (default 20)")
    args = p.parse_args()

    universe = None if args.all else LIQUID_OPTIONS_TICKERS

    # Trend-hunting path — find names already in a clean directional trend.
    if args.trend:
        try:
            raw = _tv_trend_request(universe, args.min_adx, max_results=100)
        except Exception as exc:
            print(f"Trend scan request failed: {exc}", file=sys.stderr)
            return 1
        rows = _normalize_trend(raw)
        if args.side in ("up", "down"):
            rows = [r for r in rows if r["direction"] == args.side]
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            _print_trend_table(rows, args.top)
        return 0

    try:
        raw = _tv_request(args.min_gap, args.side, universe, max_results=100)
    except Exception as exc:
        print(f"Scanner request failed: {exc}", file=sys.stderr)
        return 1

    rows = _normalize(raw)

    if args.confluence and rows:
        rows = _enrich_confluence(rows)

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        _print_table(rows, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
