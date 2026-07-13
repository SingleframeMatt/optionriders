#!/usr/bin/env python3
"""
premarket.py — Current-session pre-market level + gap helper for Option Riders.

Pulls today's 1-minute pre/post bars from Yahoo (via yfinance), isolates the
CURRENT trading day's 04:00-09:30 ET pre-market window, and derives the numbers
that actually matter for same-day ATM weekly debits:

  * gap % vs the prior regular-session close
  * pre-market high / low (PMH / PML)
  * pre-market volume (confirms the move is real, not a stale tick)

Every snapshot is hard-validated against the current date: if Yahoo returns no
bars stamped today, the snapshot is flagged `stale` so the scan never trusts
Friday's tape as if it were this morning's pre-market.

Usage:
    from premarket import fetch_premarket
    snaps = fetch_premarket(["NVDA", "AMD", "TSLA"])
    snaps["NVDA"].gap_pct   # -1.16
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")

_PM_START = dtime(4, 0)
_PM_END = dtime(9, 30)
_RTH_START = dtime(9, 30)
_RTH_END = dtime(16, 0)


@dataclass
class PremarketSnapshot:
    symbol: str
    state: str            # premarket | regular | closed | stale | no_data
    stale: bool
    has_premarket: bool
    gap_pct: float
    pmh: Optional[float]
    pml: Optional[float]
    pm_last: Optional[float]
    pm_volume: float
    prior_close: Optional[float]
    asof: Optional[str]

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "stale": self.stale,
            "hasPremarket": self.has_premarket,
            "gapPct": round(self.gap_pct, 2),
            "pmh": round(self.pmh, 2) if self.pmh is not None else None,
            "pml": round(self.pml, 2) if self.pml is not None else None,
            "pmLast": round(self.pm_last, 2) if self.pm_last is not None else None,
            "pmVolume": self.pm_volume,
            "priorClose": round(self.prior_close, 2) if self.prior_close is not None else None,
            "asOf": self.asof,
        }


def _now_ny() -> datetime:
    return datetime.now(tz=NY_TZ)


def _session_state(now: datetime) -> str:
    """Where the clock is right now, before considering data freshness."""
    if now.weekday() >= 5:
        return "closed"
    t = now.time()
    if _PM_START <= t < _RTH_START:
        return "premarket"
    if _RTH_START <= t < _RTH_END:
        return "regular"
    return "closed"


def _localize_ny(df):
    """Return a copy of df with a tz-aware New-York DatetimeIndex."""
    idx = df.index
    if getattr(idx, "tz", None) is None:
        df = df.tz_localize("UTC")
    return df.tz_convert(NY_TZ)


def _frame_for(raw, symbol: str, multi: bool):
    if multi:
        try:
            return raw[symbol]
        except Exception:
            return None
    return raw


def _empty(symbol: str, state: str, stale: bool) -> PremarketSnapshot:
    return PremarketSnapshot(
        symbol=symbol, state=state, stale=stale, has_premarket=False,
        gap_pct=0.0, pmh=None, pml=None, pm_last=None, pm_volume=0.0,
        prior_close=None, asof=None,
    )


def _snapshot_for(symbol: str, df, now: datetime, clock_state: str) -> PremarketSnapshot:
    if df is None or getattr(df, "empty", True):
        return _empty(symbol, "no_data", stale=(clock_state in ("premarket", "regular")))

    try:
        df = _localize_ny(df)
    except Exception:
        return _empty(symbol, "no_data", stale=(clock_state in ("premarket", "regular")))

    for col in ("High", "Low", "Close", "Volume"):
        if col not in df.columns:
            return _empty(symbol, "no_data", stale=(clock_state in ("premarket", "regular")))

    today = now.date()
    times = [ts.time() for ts in df.index]
    dates = [ts.date() for ts in df.index]

    highs = list(df["High"])
    lows = list(df["Low"])
    closes = list(df["Close"])
    vols = list(df["Volume"])

    def _num(x):
        try:
            v = float(x)
            return v if v == v else None  # drop NaN
        except Exception:
            return None

    # Today's pre-market window (04:00 - 09:30 ET, current date only).
    pm_h: List[float] = []
    pm_l: List[float] = []
    pm_c: List[float] = []
    pm_v = 0.0
    # Today's regular-session bars (used as gap reference once the bell rings).
    rth_today_open: Optional[float] = None
    # Prior regular-session close (last RTH close on any date before today).
    prior_close: Optional[float] = None
    today_any = False

    for i, ts in enumerate(df.index):
        d, t = dates[i], times[i]
        if d == today:
            today_any = True
            if _PM_START <= t < _PM_END:
                h, l, c = _num(highs[i]), _num(lows[i]), _num(closes[i])
                if h is not None:
                    pm_h.append(h)
                if l is not None:
                    pm_l.append(l)
                if c is not None:
                    pm_c.append(c)
                v = _num(vols[i])
                if v is not None:
                    pm_v += v
            elif _RTH_START <= t < _RTH_END and rth_today_open is None:
                rth_today_open = _num(closes[i])
        elif d < today and _RTH_START <= t < _RTH_END:
            c = _num(closes[i])
            if c is not None:
                prior_close = c  # keeps advancing to the latest prior RTH close

    # Data-freshness validation: clock says market is live but Yahoo has no
    # bars stamped today -> treat as stale, never trust yesterday's tape.
    if clock_state in ("premarket", "regular") and not today_any:
        return _empty(symbol, "stale", stale=True)

    has_premarket = len(pm_c) > 0
    pmh = max(pm_h) if pm_h else None
    pml = min(pm_l) if pm_l else None
    pm_last = pm_c[-1] if pm_c else None

    ref_price = pm_last if pm_last is not None else rth_today_open
    gap_pct = 0.0
    if ref_price is not None and prior_close:
        gap_pct = (ref_price - prior_close) / prior_close * 100.0

    asof = df.index[-1].isoformat() if len(df.index) else None

    return PremarketSnapshot(
        symbol=symbol,
        state=clock_state,
        stale=False,
        has_premarket=has_premarket,
        gap_pct=gap_pct,
        pmh=pmh,
        pml=pml,
        pm_last=pm_last,
        pm_volume=round(pm_v, 0),
        prior_close=prior_close,
        asof=asof,
    )


def fetch_premarket(symbols, now: Optional[datetime] = None) -> Dict[str, PremarketSnapshot]:
    """Batch pre-market snapshot for the current session. Keyed by symbol."""
    symbols = [str(s).upper() for s in (symbols or []) if s]
    # de-dupe, preserve order
    seen: set = set()
    symbols = [s for s in symbols if not (s in seen or seen.add(s))]
    if not symbols:
        return {}

    if now is None:
        now = _now_ny()
    clock_state = _session_state(now)

    try:
        import yfinance as yf
    except Exception:
        return {}

    try:
        raw = yf.download(
            symbols,
            period="3d",
            interval="1m",
            prepost=True,
            progress=False,
            auto_adjust=False,
            group_by="ticker",
        )
    except Exception:
        return {}

    try:
        import pandas as pd
        multi = isinstance(raw.columns, pd.MultiIndex)
    except Exception:
        multi = len(symbols) > 1

    out: Dict[str, PremarketSnapshot] = {}
    for symbol in symbols:
        df = _frame_for(raw, symbol, multi)
        try:
            out[symbol] = _snapshot_for(symbol, df, now, clock_state)
        except Exception:
            out[symbol] = _empty(symbol, "no_data", stale=(clock_state in ("premarket", "regular")))
    return out


if __name__ == "__main__":
    import json
    import sys

    tickers = [a.upper() for a in sys.argv[1:]] or ["SPY", "QQQ", "NVDA", "AMD", "TSLA", "MSFT", "TSM"]
    snaps = fetch_premarket(tickers)
    print(json.dumps({s: snap.as_dict() for s, snap in snaps.items()}, indent=2))
