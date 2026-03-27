#!/usr/bin/env python3
"""
signals.py — Supply & Demand Break+Retest signal detection with full confluence scoring.

Signal Logic:
  LONG:  2 consecutive closes ABOVE a key level → price pulls back to touch/wick
         the level but closes ABOVE it (green bullish bar) → entry if confluence >= 4/7.
  SHORT: 2 consecutive closes BELOW a key level → price pulls back to touch/wick
         the level but closes BELOW it (red bearish bar) → entry if confluence >= 4/7.

Confluence factors (need 4 of 7):
  1. BOS direction bullish (for longs) or bearish (for shorts)
  2. Price above VWAP (longs) or below VWAP (shorts)
  3. Within London (3am–12pm ET) or NY (9:30am–4pm ET) session killzone
  4. At a key level (PDH/PDL/PWH/PWL/ORB high/low/VWAP)
  5. HTF zone aligned (approximate 1-hour trend check matches direction)
  6. BOS or CHoCH structural point (structural break identified in recent bars)
  7. Confirmation close (green candle body closes above level for longs,
                         red candle body closes below level for shorts)
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz

log = logging.getLogger("signals")

ET = pytz.timezone("America/New_York")

# ── Tolerance / thresholds ────────────────────────────────────────────────────
LEVEL_TOLERANCE_PCT  = 0.0015   # 0.15% — price must come within this % of a level
MIN_CONFLUENCE       = 4        # need ≥4 of 7 factors

# Round number step (prices snapping to multiples of this get a confluence point)
ROUND_NUMBER_STEP    = 5.0      # SPX $5 rounds, SPY/QQQ $1 → handled per-symbol below

# Killzone windows (hour, minute) in ET — inclusive start, exclusive end
# London session: 3am–12pm ET
# NY session:     9:30am–4pm ET
KILLZONES = [
    ((3,  0),  (12, 0)),   # London session
    ((9, 30),  (16, 0)),   # NY session
]


# ─────────────────────────────────────────────────────────────────────────────
# RSI (pure Python, no pandas dependency)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rsi(closes: list, period: int = 14) -> float:
    """Wilder's RSI. Returns 50.0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + avg_g / avg_l), 2)


# ─────────────────────────────────────────────────────────────────────────────
# VWAP (intraday, from bar list with .date / .open / .high / .low / .close / .volume)
# ─────────────────────────────────────────────────────────────────────────────

def compute_vwap(bars, et_tz=ET) -> float:
    """Cumulative intraday VWAP using today's bars only."""
    today_str = datetime.now(et_tz).strftime("%Y%m%d")
    total_pv, total_vol = 0.0, 0.0
    for b in bars:
        bar_dt = b.date
        if hasattr(bar_dt, "strftime"):
            if bar_dt.tzinfo is None:
                bar_dt = pytz.utc.localize(bar_dt)
            bar_date_str = bar_dt.astimezone(et_tz).strftime("%Y%m%d")
        else:
            bar_date_str = str(bar_dt)[:8].replace("-", "")
        if bar_date_str != today_str:
            continue
        tp = (b.high + b.low + b.close) / 3.0
        total_pv  += tp * b.volume
        total_vol += b.volume
    return round(total_pv / total_vol, 4) if total_vol > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# ORB (Opening Range Breakout) levels — first 15 min of RTH per spec
# ─────────────────────────────────────────────────────────────────────────────

def compute_orb(bars, et_tz=ET) -> dict:
    """
    Returns {'ORB_H': float, 'ORB_L': float} from the first 15 min of today.
    Bars at 9:30am and 9:35am ET (two 5-min bars) form the opening range.
    """
    today_str = datetime.now(et_tz).strftime("%Y%m%d")
    orb_highs, orb_lows = [], []
    for b in bars:
        bar_dt = b.date
        if hasattr(bar_dt, "strftime"):
            if bar_dt.tzinfo is None:
                bar_dt = pytz.utc.localize(bar_dt)
            bar_et = bar_dt.astimezone(et_tz)
        else:
            continue
        if bar_et.strftime("%Y%m%d") != today_str:
            continue
        h, m = bar_et.hour, bar_et.minute
        # 9:30 and 9:35 = first 15-minute opening range (2 × 5-min bars)
        if (h, m) >= (9, 30) and (h, m) <= (9, 40):
            orb_highs.append(b.high)
            orb_lows.append(b.low)
    if not orb_highs:
        return {}
    return {"ORB_H": round(max(orb_highs), 4), "ORB_L": round(min(orb_lows), 4)}


# ─────────────────────────────────────────────────────────────────────────────
# Prior Day / Week levels (from bar data + yfinance)
# ─────────────────────────────────────────────────────────────────────────────

def compute_pdh_pdl(bars, et_tz=ET) -> dict:
    """PDH / PDL from prior trading day bars."""
    today_et = datetime.now(et_tz).date()
    prev = today_et - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    prev_str = prev.strftime("%Y%m%d")

    highs, lows = [], []
    for b in bars:
        bar_dt = b.date
        if hasattr(bar_dt, "strftime"):
            if bar_dt.tzinfo is None:
                bar_dt = pytz.utc.localize(bar_dt)
            bar_date_str = bar_dt.astimezone(et_tz).strftime("%Y%m%d")
        else:
            bar_date_str = str(bar_dt)[:8].replace("-", "")
        if bar_date_str == prev_str:
            highs.append(b.high)
            lows.append(b.low)
    out = {}
    if highs:
        out["PDH"] = round(max(highs), 4)
    if lows:
        out["PDL"] = round(min(lows), 4)
    return out


def fetch_weekly_levels(symbol: str) -> dict:
    """PWH / PWL via yfinance (prior full calendar week)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        weekly = ticker.history(period="1mo", interval="1wk")
        if len(weekly) >= 2:
            pw = weekly.iloc[-2]
            return {"PWH": round(float(pw["High"]), 4), "PWL": round(float(pw["Low"]), 4)}
    except Exception as exc:
        log.warning("yfinance weekly levels failed for %s: %s", symbol, exc)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Round number proximity
# ─────────────────────────────────────────────────────────────────────────────

def _round_number_step(symbol: str) -> float:
    """Return the round-number grid step for a given symbol."""
    if symbol == "SPX":
        return 5.0
    if symbol in ("SPY", "QQQ"):
        return 1.0
    return 5.0


def near_round_number(price: float, symbol: str) -> bool:
    """True if price is within LEVEL_TOLERANCE_PCT of a round number."""
    step = _round_number_step(symbol)
    nearest = round(price / step) * step
    return abs(price - nearest) / price <= LEVEL_TOLERANCE_PCT


# ─────────────────────────────────────────────────────────────────────────────
# Session / killzone helpers
# ─────────────────────────────────────────────────────────────────────────────

def in_killzone(dt: Optional[datetime] = None, et_tz=ET) -> bool:
    """True if the given time (defaults to now) is inside a London or NY killzone."""
    if dt is None:
        dt = datetime.now(et_tz)
    elif dt.tzinfo is None:
        dt = et_tz.localize(dt)
    h, m = dt.hour, dt.minute
    for (sh, sm), (eh, em) in KILLZONES:
        if (h, m) >= (sh, sm) and (h, m) < (eh, em):
            return True
    return False


def in_rth(dt: Optional[datetime] = None, et_tz=ET) -> bool:
    """True if inside regular trading hours (9:30am–4pm ET, Mon–Fri)."""
    if dt is None:
        dt = datetime.now(et_tz)
    elif dt.tzinfo is None:
        dt = et_tz.localize(dt)
    if dt.weekday() >= 5:
        return False
    h, m = dt.hour, dt.minute
    return (h, m) >= (9, 30) and (h, m) < (16, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Break-of-Structure (BOS) direction — simple trend filter
# ─────────────────────────────────────────────────────────────────────────────

def bos_direction(closes: list, lookback: int = 20) -> str:
    """
    Determine recent BOS direction from closes.
    'long'  if the most recent significant swing high is higher than the prior.
    'short' if the most recent significant swing low is lower than the prior.
    'flat'  if no clear direction.
    """
    if len(closes) < lookback:
        return "flat"
    window = closes[-lookback:]
    mid = lookback // 2
    swing_highs = [window[i] for i in range(1, len(window) - 1)
                   if window[i] > window[i - 1] and window[i] > window[i + 1]]
    swing_lows  = [window[i] for i in range(1, len(window) - 1)
                   if window[i] < window[i - 1] and window[i] < window[i + 1]]

    if len(swing_highs) >= 2 and swing_highs[-1] > swing_highs[-2]:
        return "long"
    if len(swing_lows) >= 2 and swing_lows[-1] < swing_lows[-2]:
        return "short"
    # Fallback: compare first-half avg vs second-half avg
    first  = sum(window[:mid]) / mid
    second = sum(window[mid:]) / (lookback - mid)
    if second > first * 1.001:
        return "long"
    if second < first * 0.999:
        return "short"
    return "flat"


def htf_trend(closes: list) -> str:
    """
    Approximate higher-timeframe (1h) trend from 5-min closes.
    Uses the last 12 closes (= 60 min of 5-min bars) as a proxy for 1h direction.
    Returns 'long', 'short', or 'flat'.
    """
    if len(closes) < 12:
        return "flat"
    # Use last 12 × 5-min bars (~1 hour) and compare first 6 vs last 6
    window = closes[-12:]
    first_half  = sum(window[:6])  / 6
    second_half = sum(window[6:])  / 6
    if second_half > first_half * 1.001:
        return "long"
    if second_half < first_half * 0.999:
        return "short"
    return "flat"


def detect_choch(closes: list, lookback: int = 30) -> str:
    """
    Detect Change of Character (CHoCH) — a structural shift where price
    breaks the most recent significant swing in the opposite direction.
    Returns 'long' (bullish CHoCH), 'short' (bearish CHoCH), or 'none'.
    """
    if len(closes) < lookback:
        return "none"
    window = closes[-lookback:]
    # Find swing highs and lows
    highs = [(i, window[i]) for i in range(1, len(window) - 1)
             if window[i] > window[i - 1] and window[i] > window[i + 1]]
    lows  = [(i, window[i]) for i in range(1, len(window) - 1)
             if window[i] < window[i - 1] and window[i] < window[i + 1]]

    last_close = window[-1]

    # Bullish CHoCH: price breaks above the most recent swing high
    if highs:
        recent_high = max(v for _, v in highs[-3:]) if len(highs) >= 3 else highs[-1][1]
        if last_close > recent_high:
            return "long"

    # Bearish CHoCH: price breaks below the most recent swing low
    if lows:
        recent_low = min(v for _, v in lows[-3:]) if len(lows) >= 3 else lows[-1][1]
        if last_close < recent_low:
            return "short"

    return "none"


# ─────────────────────────────────────────────────────────────────────────────
# Confluence scorer — 7 factors matching the spec exactly
# ─────────────────────────────────────────────────────────────────────────────

def confluence_score(
    direction: str,
    symbol: str,
    price: float,
    vwap: float,
    closes: list,
    levels: dict,
    confirm_bar_bullish: bool,      # True if current bar closed bullish (green)
    current_dt: Optional[datetime] = None,
    et_tz=ET,
) -> tuple:
    """
    Score the 7 confluence factors. Returns (score, breakdown_dict).

    Factors:
      1. bos_aligned    — BOS direction matches trade direction
      2. vwap_side      — Price above VWAP for longs, below for shorts
      3. killzone       — Within London (3am-12pm ET) or NY (9:30am-4pm ET) session
      4. key_level      — At PDH/PDL/PWH/PWL/ORB_H/ORB_L/VWAP or round number
      5. htf_aligned    — Approximate 1h (12-bar) trend matches direction
      6. bos_or_choch   — BOS or CHoCH structural point detected
      7. confirm_bar    — Confirmation bar: green close above level (long),
                          red close below level (short)
    """
    if current_dt is None:
        current_dt = datetime.now(et_tz)

    breakdown = {}

    # 1. BOS direction bullish (longs) or bearish (shorts)
    trend = bos_direction(closes)
    breakdown["bos_aligned"] = (direction == "long"  and trend in ("long",)) or \
                                (direction == "short" and trend in ("short",))

    # 2. Price above VWAP (longs) or below VWAP (shorts)
    if vwap > 0:
        breakdown["vwap_side"] = (direction == "long"  and price > vwap) or \
                                  (direction == "short" and price < vwap)
    else:
        breakdown["vwap_side"] = False

    # 3. Session killzone (London 3am-12pm ET  or  NY 9:30am-4pm ET)
    breakdown["killzone"] = in_killzone(current_dt, et_tz)

    # 4. At a key level (PDH/PDL/PWH/PWL/ORB_H/ORB_L/VWAP or round number)
    at_level = False
    for lvl_name, lvl_val in levels.items():
        if lvl_val is None:
            continue
        tol = float(lvl_val) * LEVEL_TOLERANCE_PCT
        if abs(price - float(lvl_val)) <= tol:
            at_level = True
            break
    if not at_level:
        at_level = near_round_number(price, symbol)
    breakdown["key_level"] = at_level

    # 5. HTF zone aligned (1h trend proxy using last 12 × 5-min bars)
    htf = htf_trend(closes)
    breakdown["htf_aligned"] = (direction == "long"  and htf in ("long",)) or \
                                (direction == "short" and htf in ("short",)) or \
                                htf == "flat"  # flat = neutral, give the benefit of the doubt

    # 6. BOS or CHoCH structural point
    bos  = bos_direction(closes, lookback=10)  # shorter lookback for recent structure
    choch = detect_choch(closes)
    breakdown["bos_or_choch"] = \
        (direction == "long"  and (bos == "long"  or choch == "long"))  or \
        (direction == "short" and (bos == "short" or choch == "short"))

    # 7. Confirmation close (green candle closes above level for longs,
    #                        red candle closes below level for shorts)
    breakdown["confirm_bar"] = (direction == "long"  and confirm_bar_bullish) or \
                                (direction == "short" and not confirm_bar_bullish)

    score = sum(1 for v in breakdown.values() if v)
    return score, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# Signal state machine (per-symbol)
# ─────────────────────────────────────────────────────────────────────────────

class SignalStateMachine:
    """
    Tracks break+retest state for a single symbol.

    States:
      idle         — looking for a 2-bar break of a key level
      break_set    — break confirmed (2 consecutive closes beyond level)
      retest_wait  — waiting for price to pull back and touch the level
      [fired]      — signal emitted; reset back to idle
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._reset()

    def _reset(self):
        self.state       = "idle"
        self.break_level : Optional[float] = None
        self.break_name  : Optional[str]   = None
        self.break_dir   : Optional[str]   = None   # "long" | "short"
        self.break_bars  : int = 0
        self.max_bars_in_retest = 10  # abort retest if price doesn't come back within N bars
        self.bars_since_break   = 0

    def update(
        self,
        bars,
        levels: dict,
        vwap: float,
        symbol: str,
        et_tz=ET,
    ) -> Optional[dict]:
        """
        Feed the latest bars into the state machine.
        Returns a signal dict if a valid entry is detected, otherwise None.

        signal dict keys:
          direction, level_name, level_price, confluence, confluence_breakdown,
          vwap, price, symbol, timestamp
        """
        if len(bars) < 3:
            return None

        cur   = bars[-1]
        prev  = bars[-2]
        prev2 = bars[-3]

        c_open   = float(cur.open)
        c_close  = float(cur.close)
        c_high   = float(cur.high)
        c_low    = float(cur.low)
        p_close  = float(prev.close)
        p2_close = float(prev2.close)

        closes_all = [float(b.close) for b in bars]

        # Determine if current bar is bullish (green) or bearish (red)
        bar_is_bullish = c_close >= c_open

        active_levels = {k: v for k, v in levels.items() if v is not None}

        # ── STATE: idle — look for a 2-bar break ─────────────────────────────
        if self.state == "idle":
            for name, lvl in active_levels.items():
                lvl = float(lvl)
                tol = lvl * LEVEL_TOLERANCE_PCT
                # Bullish break: prev2 AND prev both close above level
                if p2_close > lvl + tol and p_close > lvl + tol:
                    log.debug("%s: LONG break above %s=%.2f", self.symbol, name, lvl)
                    self.state       = "break_set"
                    self.break_level = lvl
                    self.break_name  = name
                    self.break_dir   = "long"
                    self.bars_since_break = 0
                    return None

                if p2_close < lvl - tol and p_close < lvl - tol:
                    log.debug("%s: SHORT break below %s=%.2f", self.symbol, name, lvl)
                    self.state       = "break_set"
                    self.break_level = lvl
                    self.break_name  = name
                    self.break_dir   = "short"
                    self.bars_since_break = 0
                    return None
            return None

        # ── STATE: break_set — wait for retest ────────────────────────────────
        if self.state == "break_set":
            lvl = self.break_level
            tol = lvl * LEVEL_TOLERANCE_PCT
            self.bars_since_break += 1

            # Timeout: too long since break, reset
            if self.bars_since_break > self.max_bars_in_retest:
                log.debug("%s: Break retest timeout — resetting", self.symbol)
                self._reset()
                return None

            # Invalidation: price blows through in opposite direction
            if self.break_dir == "long" and c_close < lvl - tol * 3:
                log.debug("%s: Long break invalidated", self.symbol)
                self._reset()
                return None
            if self.break_dir == "short" and c_close > lvl + tol * 3:
                log.debug("%s: Short break invalidated", self.symbol)
                self._reset()
                return None

            # Retest: wick touched level + confirmation close
            if self.break_dir == "long":
                touched   = c_low <= lvl + tol          # wick came down to level
                confirmed = c_close > lvl + tol          # closed back above
                if touched and confirmed:
                    return self._emit_signal(
                        direction="long",
                        c_close=c_close, vwap=vwap,
                        closes_all=closes_all, levels=active_levels,
                        bar_is_bullish=bar_is_bullish, symbol=symbol, et_tz=et_tz,
                    )

            elif self.break_dir == "short":
                touched   = c_high >= lvl - tol          # wick reached up to level
                confirmed = c_close < lvl - tol           # closed back below
                if touched and confirmed:
                    return self._emit_signal(
                        direction="short",
                        c_close=c_close, vwap=vwap,
                        closes_all=closes_all, levels=active_levels,
                        bar_is_bullish=bar_is_bullish, symbol=symbol, et_tz=et_tz,
                    )
        return None

    def _emit_signal(
        self,
        direction: str,
        c_close: float,
        vwap: float,
        closes_all: list,
        levels: dict,
        bar_is_bullish: bool,
        symbol: str,
        et_tz=ET,
    ) -> Optional[dict]:
        """Run confluence check; emit signal dict if >= MIN_CONFLUENCE."""
        now = datetime.now(et_tz)
        score, breakdown = confluence_score(
            direction           = direction,
            symbol              = symbol,
            price               = c_close,
            vwap                = vwap,
            closes              = closes_all,
            levels              = levels,
            confirm_bar_bullish = bar_is_bullish,
            current_dt          = now,
            et_tz               = et_tz,
        )

        log.info(
            "%s %s retest at %s=%.2f | VWAP=%.2f confluence=%d/7 %s",
            symbol, direction.upper(),
            self.break_name, self.break_level,
            vwap, score, breakdown,
        )

        if score < MIN_CONFLUENCE:
            log.info("%s confluence too low (%d/%d) — no signal", symbol, score, MIN_CONFLUENCE)
            # Don't reset — allow another bar to confirm
            return None

        signal = {
            "symbol":                symbol,
            "direction":             direction,
            "level_name":            self.break_name,
            "level_price":           round(self.break_level, 4),
            "confluence":            score,
            "confluence_breakdown":  breakdown,
            "vwap":                  round(vwap, 4),
            "price":                 round(c_close, 4),
            "timestamp":             now.isoformat(),
        }
        self._reset()
        return signal

    def get_state_dict(self) -> dict:
        """Snapshot of current state machine status for the UI."""
        return {
            "state":       self.state,
            "break_dir":   self.break_dir,
            "break_level": self.break_level,
            "break_name":  self.break_name,
            "bars_since":  self.bars_since_break,
        }
