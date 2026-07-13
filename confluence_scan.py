#!/usr/bin/env python3
"""
confluence_scan.py — Pre-market confluence ranker for Option Riders.

Replicates the Bias Dashboard scoring from OptionRiders_SnD_Pro_V36.pine
(Weekly/Daily/Intraday factors + ADX regime) across a watchlist via yfinance,
then ranks tickers by conviction strength so the strongest setups float to the
top — long-bias and short-bias setups both surface (long debits and put debits).

Usage:
    python confluence_scan.py
    python confluence_scan.py NVDA TSLA META
    python confluence_scan.py --include-trending
    python confluence_scan.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

NY_TZ = ZoneInfo("America/New_York")

DEFAULT_WATCHLIST = [
    "SPY", "QQQ", "IWM",
    "NVDA", "TSLA", "META", "AAPL", "MSFT", "AMZN", "GOOGL",
    "AMD", "AVGO", "SMCI", "PLTR", "COIN", "MSTR", "NFLX",
]


# ── Indicators ────────────────────────────────────────────────────────────────

def _rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    return float((100 - (100 / (1 + rs))).iloc[-1])


def _ema(closes: pd.Series, period: int) -> float:
    return float(closes.ewm(span=period, adjust=False).mean().iloc[-1])


def _adx(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    up = high.diff()
    dn = -low.diff()
    plus_dm  = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, 1e-12)
    plus_di  = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-12)
    return float(dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def _session_vwap(intraday: pd.DataFrame) -> float | None:
    """RTH-anchored VWAP for the most recent trading session."""
    if intraday.empty:
        return None
    idx_ny = intraday.index.tz_convert(NY_TZ)
    rth = intraday[(idx_ny.time >= pd.Timestamp("09:30").time()) &
                   (idx_ny.time <  pd.Timestamp("16:00").time())]
    if rth.empty:
        return None
    last_date = rth.index.tz_convert(NY_TZ)[-1].date()
    sess = rth[rth.index.tz_convert(NY_TZ).date == last_date]
    if sess.empty:
        return None
    tp = (sess["High"] + sess["Low"] + sess["Close"]) / 3
    pv = (tp * sess["Volume"]).sum()
    vv = sess["Volume"].sum()
    if vv <= 0:
        return None
    return float(pv / vv)


# ── Per-ticker analysis ───────────────────────────────────────────────────────

@dataclass
class Confluence:
    ticker: str
    price: float = 0.0
    weekly: int = 0          # 0-3 bull factors
    daily: int = 0           # 0-4
    intra: int = 0           # 0-3
    total: int = 0           # 0-10
    bias: str = "?"
    direction: str = "—"     # LONG / SHORT / —
    adx: float = 0.0
    regime: str = "?"        # trend / weak / chop
    factors: dict = field(default_factory=dict)
    error: str | None = None


def _score_ticker(ticker: str) -> Confluence:
    out = Confluence(ticker=ticker)
    try:
        tk = yf.Ticker(ticker)
        d = tk.history(period="120d", interval="1d", auto_adjust=False)
        if d.empty or len(d) < 25:
            out.error = "insufficient daily data"
            return out

        i = tk.history(period="7d", interval="5m", auto_adjust=False, prepost=False)
        if i.empty or len(i) < 60:
            out.error = "insufficient intraday data"
            return out
        if i.index.tz is None:
            i.index = i.index.tz_localize("UTC")

        price = float(d["Close"].iloc[-1])
        out.price = round(price, 2)

        # ── Weekly (3 factors) ──
        d_local = d.copy()
        d_local.index = d_local.index.tz_localize(None) if d_local.index.tz is not None else d_local.index
        d_local["wk"] = d_local.index.to_period("W")
        weeks = list(d_local.groupby("wk"))
        if len(weeks) >= 2:
            tw, pw = weeks[-1][1], weeks[-2][1]
            tw_mid = (tw["High"].max() + tw["Low"].min()) / 2
            pw_mid = (pw["High"].max() + pw["Low"].min()) / 2
        else:
            tw_mid = pw_mid = None

        d_local["mo"] = d_local.index.to_period("M")
        months = list(d_local.groupby("mo"))
        pm_mid = None
        if len(months) >= 2:
            pm = months[-2][1]
            pm_mid = (pm["High"].max() + pm["Low"].min()) / 2

        f_pw = pw_mid is not None and price > pw_mid
        f_tw = tw_mid is not None and price > tw_mid
        f_pm = pm_mid is not None and price > pm_mid
        out.weekly = sum([f_pw, f_tw, f_pm])

        # ── Daily (4 factors) ──
        closes_d = d["Close"]
        recent_hi = float(d["High"].iloc[-21:-1].max())
        recent_lo = float(d["Low"].iloc[-21:-1].min())
        if price > recent_hi:
            f_struct = True
        elif price < recent_lo:
            f_struct = False
        else:
            ema_now  = _ema(closes_d, 20)
            ema_prev = _ema(closes_d.iloc[:-5], 20)
            f_struct = ema_now > ema_prev

        vwap = _session_vwap(i)
        f_vwap = vwap is not None and price > vwap
        f_rsi  = _rsi(closes_d, 14) > 50
        f_ema  = price > _ema(closes_d, 20)
        out.daily = sum([f_struct, f_vwap, f_rsi, f_ema])

        # ── Intraday (3 factors) ──
        ic = i["Close"]
        f_fast = _ema(ic, 5)  > _ema(ic, 12)
        f_slow = _ema(ic, 34) > _ema(ic, 50)
        recent = i.tail(min(80, len(i) - 1))
        below = int((recent["Low"]  < price).sum())
        above = int((recent["High"] > price).sum())
        f_zones = below >= above
        out.intra = sum([f_fast, f_slow, f_zones])

        # ── Aggregate ──
        out.total = out.weekly + out.daily + out.intra
        if out.total >= 7:
            out.bias, out.direction = "Bullish", "LONG"
        elif out.total <= 3:
            out.bias, out.direction = "Bearish", "SHORT"
        else:
            out.bias, out.direction = "Neutral", "—"

        adx_val = _adx(i.tail(300), 14)
        out.adx = round(adx_val, 1)
        out.regime = "chop" if adx_val < 20 else "weak" if adx_val < 25 else "trend"

        out.factors = {
            "above_pw_mid":      bool(f_pw),
            "above_tw_mid":      bool(f_tw),
            "above_pm_mid":      bool(f_pm),
            "structure_bull":    bool(f_struct),
            "above_vwap":        bool(f_vwap),
            "rsi_above_50":      bool(f_rsi),
            "above_ema20":       bool(f_ema),
            "fast_cloud_bull":   bool(f_fast),
            "slow_cloud_bull":   bool(f_slow),
            "more_demand_below": bool(f_zones),
        }
        return out
    except Exception as exc:
        out.error = f"{type(exc).__name__}: {exc}"
        return out


# ── Output ────────────────────────────────────────────────────────────────────

_GREEN, _RED, _YEL, _DIM, _RST = "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[2m", "\x1b[0m"

def _color(text: str, code: str) -> str:
    return f"{code}{text}{_RST}" if sys.stdout.isatty() else text


def _print_table(rows: list[Confluence]) -> None:
    # Strongest conviction first (distance from neutral 5), then total bullish
    rows = sorted(rows, key=lambda r: (-abs((r.total or 5) - 5), -r.total))
    print()
    print(f"  {'TICKER':<8}{'PRICE':>10}{'WK':>6}{'DAY':>6}{'INTRA':>7}{'TOTAL':>8}{'BIAS':>10}{'DIR':>7}{'ADX':>7}  REGIME")
    print(f"  {'─' * 86}")
    for r in rows:
        if r.error:
            print(f"  {r.ticker:<8}  {_color('error: ' + r.error, _DIM)}")
            continue
        bias_c = _GREEN if r.bias == "Bullish" else _RED if r.bias == "Bearish" else _DIM
        reg_c  = _GREEN if r.regime == "trend" else _YEL if r.regime == "weak" else _RED
        dir_c  = _GREEN if r.direction == "LONG" else _RED if r.direction == "SHORT" else _DIM
        print(
            f"  {r.ticker:<8}"
            f"{r.price:>10.2f}"
            f"{r.weekly:>4}/3"
            f"{r.daily:>4}/4"
            f"{r.intra:>5}/3"
            f"{r.total:>6}/10"
            f"  {_color(f'{r.bias:>8}', bias_c)}"
            f"  {_color(f'{r.direction:>5}', dir_c)}"
            f"{r.adx:>7.1f}"
            f"  {_color(r.regime, reg_c)}"
        )

    actionable = [r for r in rows if not r.error and r.regime != "chop"
                                  and r.bias != "Neutral"]
    print()
    print(f"  Top setups (non-chop, conviction ≥ Bullish/Bearish): {len(actionable)}")
    for r in actionable[:5]:
        arrow = "▲" if r.direction == "LONG" else "▼"
        print(f"    {arrow} {r.ticker:<6} {r.direction:<5} {r.total}/10  ADX {r.adx:.1f} ({r.regime})")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tickers", nargs="*", help="Tickers (default: built-in watchlist)")
    p.add_argument("--json", action="store_true", help="JSON output instead of table")
    p.add_argument("--include-trending", action="store_true",
                   help="Append cross-source trending tickers from top_watch.py")
    args = p.parse_args()

    universe = [t.upper() for t in args.tickers] or list(DEFAULT_WATCHLIST)
    if args.include_trending:
        try:
            from top_watch import fetch_top_watch
            extras = [item["ticker"] for item in fetch_top_watch().get("topWatch", [])]
            for t in extras:
                if t not in universe:
                    universe.append(t)
        except Exception as exc:
            print(f"# top_watch fetch failed: {exc}", file=sys.stderr)

    rows = [_score_ticker(t) for t in universe]

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2, default=str))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
