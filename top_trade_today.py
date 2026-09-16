#!/usr/bin/env python3
"""
top_trade_today.py — Daily options setup engine for Option Riders.

Builds up to four screened watchlist setups for the current U.S. trading session
from live market data, macro events, options flow, and cross-source momentum.
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from barchart_proxy import fetch_options_activity
from market_data import fetch_market_data
from premarket import fetch_premarket
from top_watch import fetch_top_watch


CACHE_TTL_SECONDS = 300
MAX_BAR_AGE_SECONDS = 600  # Last completed 2-minute candle; excludes stale sessions.
MAX_SOURCE_AGE_SECONDS = 900
MAX_OPTION_SPREAD_PCT = 10.0  # Screening policy, not an empirically optimized threshold.
# Minimum current-session pre-market gap (vs prior close) for a name to survive
# the pre-market scan. Below this it chops after the open — no move, no trade.
PREMARKET_GAP_MIN = 0.5
NY_TZ = ZoneInfo("America/New_York")
# Published NYSE equity-session calendar, verified 2026-09-16:
# https://www.nyse.com/trade/hours-calendars
# Unknown years fail closed until the published schedule is updated.
_SESSION_HOLIDAYS = {
    2026: {"01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"},
    2027: {"01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"},
    2028: {"01-17", "02-21", "04-14", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"},
}
_EARLY_CLOSE_DATES = {"2026-11-27", "2026-12-24", "2027-11-26", "2028-07-03", "2028-11-24"}
PRIMARY_UNIVERSE = ["SPY", "QQQ", "NVDA", "TSLA", "AMD", "SMCI", "META", "AAPL", "MSFT", "AMZN"]
CALENDAR_SOURCES = [
    "https://api.allorigins.win/raw?url=https%3A%2F%2Fnfs.faireconomy.media%2Fff_calendar_thisweek.json",
    "https://r.jina.ai/http://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
]
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_cache_lock = threading.Lock()
_cache = {"expires_at": 0.0, "payload": None, "session_key": None}


@dataclass
class TimeframeSnapshot:
    label: str
    direction: str
    trend_score: float
    momentum: float
    above_fast: bool
    above_slow: bool


def _now_ny() -> datetime:
    return datetime.now(tz=NY_TZ)


def _session_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _market_session_label(now: datetime) -> str:
    now = now.astimezone(NY_TZ)
    if now.year not in _SESSION_HOLIDAYS:
        return "Calendar unavailable"
    if now.strftime("%m-%d") in _SESSION_HOLIDAYS[now.year]:
        return "Market closed"
    open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_dt = now.replace(hour=13 if now.date().isoformat() in _EARLY_CLOSE_DATES else 16, minute=0, second=0, microsecond=0)
    if now.weekday() >= 5 or now.hour < 4:
        return "Market closed"
    if now < open_dt:
        return "Pre-market"
    if now < close_dt:
        return "Regular session"
    return "Post-close"


def _json_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_calendar_payload(raw_text: str) -> str:
    trimmed = raw_text.strip()
    if trimmed.startswith("["):
        return trimmed
    marker = "Markdown Content:"
    if marker in trimmed:
        return trimmed.split(marker, 1)[1].strip()
    array_start = trimmed.find("[{")
    if array_start >= 0:
        return trimmed[array_start:].strip()
    raise ValueError("Calendar payload was not JSON.")


def _fetch_macro_events() -> Dict[str, List[dict]]:
    events = []
    errors = []
    for url in CALENDAR_SOURCES:
        try:
            raw = _json_get(url)
            payload = json.loads(_extract_calendar_payload(raw))
            events = payload if isinstance(payload, list) else []
            if events:
                break
        except Exception as exc:
            errors.append(str(exc))

    today = _now_ny().date()
    todays_events = []
    next_events = []
    for event in events:
        try:
            if event.get("country") != "USD" or event.get("impact") != "High" or not event.get("date"):
                continue
            event_dt = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00")).astimezone(NY_TZ)
            entry = {
                "timestamp": int(event_dt.timestamp()),
                "title": event.get("title") or "Unnamed event",
                "time": event_dt.strftime("%-I:%M %p ET"),
                "date": event_dt.date().isoformat(),
                "forecast": event.get("forecast") or "",
                "previous": event.get("previous") or "",
                "actual": event.get("actual") or "",
            }
            if event_dt.date() == today:
                todays_events.append(entry)
            elif event_dt.date() > today and len(next_events) < 3:
                next_events.append(entry)
        except Exception:
            continue

    return {
        "today": todays_events,
        "next": next_events,
        "error": errors[-1] if errors and not events else "",
    }


def _sma(values: Iterable[float], period: int) -> float:
    values = list(values)
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period


def _safe_pct_move(current: Optional[float], previous: Optional[float]) -> float:
    if current in (None, 0) or previous in (None, 0):
        return 0.0
    try:
        return ((float(current) - float(previous)) / float(previous)) * 100.0
    except Exception:
        return 0.0


def _parse_trigger_number(text: str) -> Optional[float]:
    if not text:
        return None
    allowed = set("0123456789.")
    for token in text.replace(",", "").split():
        cleaned = "".join(ch for ch in token if ch in allowed)
        if cleaned.count(".") <= 1 and cleaned and cleaned != ".":
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _frame_bars(frame, now: datetime, minutes: int) -> dict:
    """Keep aligned OHLCV rows and their actual timestamps; omit forming bars."""
    result = {key: [] for key in ("time", "open", "high", "low", "close", "volume")}
    if frame is None or frame.empty:
        return result
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for stamp, row in frame.iterrows():
        if stamp.tzinfo is None:
            continue  # Intraday timezone must be known, not guessed.
        ts = int(stamp.timestamp())
        if ts + minutes * 60 > now.timestamp():
            continue
        try:
            values = {field: float(row[field.title()]) for field in ("open", "high", "low", "close", "volume")}
            if not all(math.isfinite(v) for v in values.values()):
                continue
            if min(values[k] for k in ("open", "high", "low", "close")) <= 0 or values["volume"] < 0:
                continue
            if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        result["time"].append(ts)
        for field, value in values.items():
            result[field].append(value)
    return result


def _download_multiframe(symbols: List[str]) -> Dict[str, dict]:
    if not symbols:
        return {}
    try:
        import yfinance as yf
    except Exception:
        return {}
    settings = {"1h": ("60d", "60m", 60), "15m": ("10d", "15m", 15), "2m": ("5d", "2m", 2)}
    result = {symbol: {} for symbol in symbols}
    for label, (period, interval, minutes) in settings.items():
        try:
            raw = yf.download(symbols, period=period, interval=interval, progress=False,
                              auto_adjust=True, prepost=(label != "1h"), timeout=10)
        except Exception:
            continue
        now = _now_ny()
        for symbol in symbols:
            try:
                frame = raw.xs(symbol, level=1, axis=1) if hasattr(raw.columns, "levels") else raw
                result[symbol][label] = _frame_bars(frame, now, minutes)
            except (KeyError, ValueError):
                continue
    return result


def _collapse_to_4h(one_hour: dict) -> dict:
    # Only aggregate four contiguous RTH hours from one session, anchored at
    # 09:30 ET. Never join the end of yesterday to the start of today.
    result = {key: [] for key in ("time", "open", "high", "low", "close", "volume")}
    times = one_hour.get("time") or []
    for idx, ts in enumerate(times):
        start = datetime.fromtimestamp(ts, NY_TZ)
        if (start.hour, start.minute) != (9, 30) or start.date().isoformat() in _EARLY_CLOSE_DATES:
            continue
        chunk = times[idx:idx + 4]
        if chunk != [ts + n * 3600 for n in range(4)]:
            continue
        result["time"].append(ts)
        result["open"].append(one_hour["open"][idx])
        result["close"].append(one_hour["close"][idx + 3])
        result["high"].append(max(one_hour["high"][idx:idx + 4]))
        result["low"].append(min(one_hour["low"][idx:idx + 4]))
        result["volume"].append(sum(one_hour["volume"][idx:idx + 4]))
    return result


def _fresh_intraday(two_min: dict, now: datetime, minutes: int = 2) -> bool:
    times = two_min.get("time") or []
    if not times or len(two_min.get("close") or []) < 21:
        return False
    last = datetime.fromtimestamp(times[-1], NY_TZ)
    return last.date() == now.date() and minutes * 60 <= now.timestamp() - times[-1] <= minutes * 60 + MAX_BAR_AGE_SECONDS - 120


def _number(value) -> Optional[float]:
    try:
        number = float(str(value).replace("$", "").replace(",", ""))
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _option_quote(row: Optional[dict], direction: str) -> Optional[dict]:
    quote = (row or {}).get("call" if direction == "Call" else "put") or {}
    bid, ask = _number(quote.get("bid")), _number(quote.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2
    return {**quote, "spread": ask - bid, "spreadPct": (ask - bid) / mid * 100}


def _trade_levels(item: dict, direction: str) -> Optional[dict]:
    trigger = _parse_trigger_number(str(item.get("bullTrigger" if direction == "Call" else "bearTrigger") or ""))
    if trigger is None or not math.isfinite(trigger) or trigger <= 0:
        return None
    support = sorted({n for v in (item.get("support") or []) if (n := _number(v)) is not None and n > 0})
    resistance = sorted({n for v in (item.get("resistance") or []) if (n := _number(v)) is not None and n > 0})
    stops = [n for n in (support if direction == "Call" else resistance) if (n < trigger if direction == "Call" else n > trigger)]
    targets = [n for n in (resistance if direction == "Call" else support) if (n > trigger if direction == "Call" else n < trigger)]
    if not stops or not targets:
        return None  # Do not manufacture profit targets from ATR.
    stop = max(stops) if direction == "Call" else min(stops)
    targets.sort(reverse=direction == "Put")
    risk = abs(trigger - stop)
    return {"trigger": trigger, "stop": stop, "targets": targets[:2],
            "rewardRisk": round(abs(targets[0] - trigger) / risk, 2)}


def _snapshot_from_closes(label: str, closes: List[float]) -> TimeframeSnapshot:
    if len(closes) < 21:
        return TimeframeSnapshot(label=label, direction="neutral", trend_score=0.0, momentum=0.0, above_fast=False, above_slow=False)

    fast = _sma(closes, 8)
    slow = _sma(closes, 21)
    current = closes[-1]
    prev_3 = closes[-4] if len(closes) >= 4 else closes[0]
    prev_8 = closes[-9] if len(closes) >= 9 else closes[0]
    momentum_short = _safe_pct_move(current, prev_3)
    momentum_med = _safe_pct_move(current, prev_8)
    trend_score = (momentum_short * 0.55) + (momentum_med * 0.45)
    above_fast = current >= fast
    above_slow = current >= slow

    if current > fast > slow and trend_score > 0:
        direction = "bullish"
    elif current < fast < slow and trend_score < 0:
        direction = "bearish"
    else:
        direction = "neutral"

    return TimeframeSnapshot(
        label=label,
        direction=direction,
        trend_score=round(trend_score, 2),
        momentum=round(momentum_short, 2),
        above_fast=above_fast,
        above_slow=above_slow,
    )


def _build_timeframe_snapshots(symbol: str, intraday: Dict[str, dict]) -> Dict[str, TimeframeSnapshot]:
    one_hour = intraday.get(symbol, {}).get("1h", {})
    fifteen = intraday.get(symbol, {}).get("15m", {})
    two_min = intraday.get(symbol, {}).get("2m", {})
    four_hour = _collapse_to_4h(one_hour)
    return {
        "4h": _snapshot_from_closes("4h", list(four_hour.get("close") or [])),
        "1h": _snapshot_from_closes("1h", list(one_hour.get("close") or [])),
        "15m": _snapshot_from_closes("15m", list(fifteen.get("close") or [])),
        "2m": _snapshot_from_closes("2m", list(two_min.get("close") or [])),
    }


def _build_setup_type(direction: str, item: dict, tf: Dict[str, TimeframeSnapshot]) -> str:
    bias = str(item.get("bias") or "")
    signal_score = item.get("signalScore") or 0
    short_tf = tf["15m"].direction
    fast_tf = tf["2m"].direction
    if direction == "Call":
        if "Bullish" in bias and short_tf == "bullish" and fast_tf == "bullish":
            return "Momentum breakout"
        if signal_score > 0:
            return "Reclaim and go"
        return "Range breakout"
    if "Bearish" in bias and short_tf == "bearish" and fast_tf == "bearish":
        return "Breakdown continuation"
    if signal_score < 0:
        return "Failed bounce short"
    return "Range rejection"


def _summarize_why(symbol: str, direction: str, item: dict, top_watch_item: Optional[dict], unusual_bias: Optional[str], macro_events: Dict[str, List[dict]], tf: Dict[str, TimeframeSnapshot]) -> str:
    parts = []
    gap_pct = float(item.get("_gapPct") or 0.0)
    if abs(gap_pct) >= PREMARKET_GAP_MIN:
        parts.append(f"{gap_pct:+.1f}% pre-market gap")
    rel = item.get("relStrength")
    if rel is not None:
        label = "relative strength" if rel > 0 else "relative weakness"
        if direction == "Call" and rel > 0:
            parts.append(f"{rel:+.1f}% five-day {label} vs SPY")
        elif direction == "Put" and rel < 0:
            parts.append(f"{rel:+.1f}% five-day {label} vs SPY")
    move_pct = item.get("_expectedMovePct") or 0
    if move_pct:
        parts.append(f"{move_pct:.1f}% historical daily ATR")
    if top_watch_item and top_watch_item.get("sourceCount", 0) >= 2:
        parts.append(f"cross-source interest ({top_watch_item['sourceCount']}/4)")
    if unusual_bias:
        parts.append(f"unusual options flow skew {unusual_bias}")
    aligned = [label for label, snap in tf.items() if snap.direction == ("bullish" if direction == "Call" else "bearish")]
    if aligned:
        parts.append(f"{'/'.join(aligned)} structure aligned")
    if macro_events.get("today"):
        parts.append("headline risk still matters")
    return f"{symbol} has " + ", ".join(parts[:4]) + "." if parts else f"{symbol} is one of the few names with a clean {direction.lower()} trigger."


def _build_risk_line(symbol: str, direction: str, item: dict, macro_events: Dict[str, List[dict]], unusual_bias: Optional[str]) -> str:
    risks = []
    if macro_events.get("today"):
        risks.append("scheduled macro volatility")
    if item.get("earningsDate") == _now_ny().date().isoformat():
        risks.append("same-day earnings catalyst")
    spread = item.get("_spreadDollars")
    if spread is not None and spread > 0.12:
        risks.append("spread expansion")
    if unusual_bias:
        opposite = (direction == "Call" and unusual_bias == "bearish") or (direction == "Put" and unusual_bias == "bullish")
        if opposite:
            risks.append("flow is fighting the setup")
    return ", ".join(risks) if risks else "failed trigger and broad tape reversal"


def _build_macro_risks(macro_events: Dict[str, List[dict]]) -> List[str]:
    risks = []
    for event in macro_events.get("today", [])[:3]:
        risks.append(f"{event['time']} {event['title']}")
    if not risks:
        for event in macro_events.get("next", [])[:2]:
            risks.append(f"Upcoming: {event['date']} {event['time']} {event['title']}")
    if macro_events.get("error") and not risks:
        risks.append("Macro calendar feed unavailable")
    return risks


def _classify_session(market_payload: dict, macro_events: Dict[str, List[dict]]) -> dict:
    breadth = market_payload.get("marketBreadth") or {}
    vix = market_payload.get("vix") or {}
    avg_score = float(breadth.get("avgScore") or 0.0)
    vix_price = float(vix.get("price") or 0.0)
    has_macro = bool(macro_events.get("today"))
    if has_macro or (vix_price >= 24 and abs(avg_score) < 16):
        return {"label": "Choppy / headline-driven", "choppy": True}
    if abs(avg_score) >= 20 and vix_price < 26:
        return {"label": "Trending", "choppy": False}
    return {"label": "Rotational", "choppy": True if abs(avg_score) < 10 else False}


def _build_candidate_universe(market_payload: dict, flow_payload: dict, top_watch_payload: dict) -> List[str]:
    symbols = list(PRIMARY_UNIVERSE)
    liquid_secondary = []

    for row in (top_watch_payload.get("topWatch") or []):
        symbol = str(row.get("ticker") or "").upper()
        spread = (((row.get("otmSpread") or {}).get("spread")) if isinstance(row.get("otmSpread"), dict) else None)
        if symbol and row.get("sourceCount", 0) >= 2 and (spread is None or spread <= 0.15):
            liquid_secondary.append(symbol)

    for row in (flow_payload.get("mostActive") or []):
        symbol = str(row.get("baseSymbol") or "").upper()
        if symbol:
            liquid_secondary.append(symbol)

    for row in (flow_payload.get("unusual") or []):
        symbol = str(row.get("baseSymbol") or "").upper()
        if symbol:
            liquid_secondary.append(symbol)

    seen = set()
    ordered = []
    for symbol in symbols + liquid_secondary:
        if not symbol or symbol in seen or len(symbol) > 5 or not symbol.isalnum():
            continue
        ordered.append(symbol)
        seen.add(symbol)
    return ordered


def _score_candidate(symbol: str, item: dict, atm_spread_row: Optional[dict], top_watch_item: Optional[dict], unusual_rows: List[dict], tf: Dict[str, TimeframeSnapshot], session: dict, pm: Optional[dict], is_premarket: bool) -> Optional[dict]:
    price = float(item.get("price") or 0.0)
    if price <= 0:
        return None

    signal_score = float(item.get("signalScore") or 0.0)
    rel_strength = float(item.get("relStrength") or 0.0)
    expected_move_pct = float(item.get("_expectedMovePct") or 0.0)
    if not all(math.isfinite(v) for v in (price, signal_score, rel_strength, expected_move_pct)):
        return None
    ratio = None
    leader = "balanced"
    if atm_spread_row:
        ratio = ((atm_spread_row.get("putCallRatio") or {}).get("ratio")) if isinstance(atm_spread_row.get("putCallRatio"), dict) else None
        leader = ((atm_spread_row.get("putCallRatio") or {}).get("leader")) if isinstance(atm_spread_row.get("putCallRatio"), dict) else "balanced"

    bullish_flow = sum(1 for row in unusual_rows if str(row.get("sentiment") or "").lower() == "bullish")
    bearish_flow = sum(1 for row in unusual_rows if str(row.get("sentiment") or "").lower() == "bearish")
    unusual_bias = "bullish" if bullish_flow > bearish_flow else "bearish" if bearish_flow > bullish_flow else None

    bullish_tfs = sum(1 for snap in tf.values() if snap.direction == "bullish")
    bearish_tfs = sum(1 for snap in tf.values() if snap.direction == "bearish")

    call_score = 0.0
    put_score = 0.0
    call_score += max(0.0, signal_score) * 0.55
    put_score += max(0.0, -signal_score) * 0.55
    call_score += max(0.0, rel_strength) * 4.0
    put_score += max(0.0, -rel_strength) * 4.0
    call_score += bullish_tfs * 6.5
    put_score += bearish_tfs * 6.5
    call_score += expected_move_pct * 5.2
    put_score += expected_move_pct * 5.2
    if top_watch_item:
        call_score += top_watch_item.get("sourceCount", 0) * 2.5
        put_score += top_watch_item.get("sourceCount", 0) * 2.5
    if unusual_bias == "bullish":
        call_score += 8.0
        put_score -= 4.0
    elif unusual_bias == "bearish":
        put_score += 8.0
        call_score -= 4.0
    if leader == "calls":
        call_score += 4.0
    elif leader == "puts":
        put_score += 4.0
    if session.get("choppy"):
        call_score -= 3.0
        put_score -= 3.0

    # ── Current-session pre-market gap filter ──────────────────────────────
    # Requires current-session pre-market data. Yahoo zeroes 1-min volume, so the
    # confirmation is gap magnitude + presence of today's pre-market bars, not
    # reported volume.
    gap_pct = float((pm or {}).get("gapPct") or 0.0)
    abs_gap = abs(gap_pct)
    has_pm = bool((pm or {}).get("hasPremarket"))
    pm_stale = bool((pm or {}).get("stale"))

    if is_premarket:
        if not pm or pm_stale or not has_pm or abs_gap < PREMARKET_GAP_MIN:
            return None
        if gap_pct > 0:
            call_score += min(abs_gap, 4.0) * 4.0
            put_score -= min(abs_gap, 4.0) * 2.0
        else:
            put_score += min(abs_gap, 4.0) * 4.0
            call_score -= min(abs_gap, 4.0) * 2.0

    if call_score == put_score:
        return None
    direction = "Call" if call_score >= put_score else "Put"
    quote = _option_quote(atm_spread_row, direction)
    if quote is None or quote["spreadPct"] > MAX_OPTION_SPREAD_PCT:
        return None
    spread = quote["spread"]
    penalty = 0.0 if spread <= 0.08 else 4.0 if spread <= 0.15 else 12.0
    best_score = max(call_score, put_score) - penalty
    if best_score < 26:
        return None

    bias = str(item.get("bias") or "").lower()
    if direction == "Call" and "bearish" in bias and bullish_tfs < 3:
        return None
    if direction == "Put" and "bullish" in bias and bearish_tfs < 3:
        return None

    return {
        "ticker": symbol,
        "direction": direction,
        "score": round(best_score, 1),
        "quote": quote,
        "spread": spread,
        "putCallRatio": ratio,
        "putCallLeader": leader,
        "unusualBias": unusual_bias,
        "bullishTfs": bullish_tfs,
        "bearishTfs": bearish_tfs,
    }


def fetch_top_trade_today(force_refresh: bool = False) -> dict:
    now = _now_ny()
    today_key = f"{_session_key(now)}:{_market_session_label(now)}"

    if not force_refresh:
        with _cache_lock:
            if _cache["payload"] and _cache["expires_at"] > time.time() and _cache["session_key"] == today_key:
                return _cache["payload"]

    session_label = _market_session_label(now)
    if session_label in {"Market closed", "Post-close", "Calendar unavailable"}:
        return {"marketDate": now.date().isoformat(), "generatedAt": int(now.timestamp()),
                "sessionLabel": session_label, "sessionType": "Outside scan hours", "picks": [],
                "bestOverallPick": "", "summary": "Intraday screening resumes during the next weekday session. No active picks outside verified scan hours.",
                "liveData": False, "dataWarnings": ["Update the exchange calendar before screening this year."] if session_label == "Calendar unavailable" else []}
    warnings = []
    market_payload = fetch_market_data(force_refresh=force_refresh)
    try:
        flow_payload = fetch_options_activity(force_refresh=force_refresh)
    except Exception:
        flow_payload = {}
        warnings.append("Options quotes unavailable; no contract-qualified picks.")
    try:
        top_watch_payload = fetch_top_watch(force_refresh=force_refresh)
    except Exception:
        top_watch_payload = {}
        warnings.append("Cross-source interest unavailable.")
    macro_events = _fetch_macro_events()
    # A refresh timestamp is not a quote timestamp. Reject old source snapshots
    # and disclose the absence of exchange quote timestamps on the cards.
    flow_age = _now_ny().timestamp() - (_number(flow_payload.get("updatedAt")) or 0)
    if not 0 <= flow_age <= MAX_SOURCE_AGE_SECONDS:
        flow_payload = {}
        warnings.append("Options snapshot missing or stale; refresh required.")
    session = _classify_session(market_payload, macro_events)

    candidate_symbols = _build_candidate_universe(market_payload, flow_payload, top_watch_payload)
    ticker_lookup = {item["ticker"]: item for item in (market_payload.get("tickers") or [])}
    index_lookup = {item["ticker"]: item for item in (market_payload.get("indexes") or [])}
    watch_lookup = {item["ticker"]: item for item in (market_payload.get("watchlist") or [])}
    top_watch_lookup = {item["ticker"]: item for item in (top_watch_payload.get("topWatch") or [])}
    atm_lookup = {item["ticker"]: item for item in (flow_payload.get("atmSpreads") or []) if item.get("ticker")}
    unusual_by_symbol: Dict[str, List[dict]] = {}
    for row in (flow_payload.get("unusual") or []):
        symbol = str(row.get("baseSymbol") or "").upper()
        if symbol:
            unusual_by_symbol.setdefault(symbol, []).append(row)

    # Avoid downloading symbols we cannot score from the market payload.
    candidate_symbols = [symbol for symbol in candidate_symbols if symbol in ticker_lookup or symbol in index_lookup]
    market_age = _now_ny().timestamp() - (_number(market_payload.get("updatedAt")) or 0)
    if not 0 <= market_age <= MAX_SOURCE_AGE_SECONDS:
        candidate_symbols = []
        warnings.append("Market snapshot missing or stale; refresh required.")
    intraday = _download_multiframe(candidate_symbols)
    now = _now_ny()
    is_premarket = _market_session_label(now) == "Pre-market"
    if _market_session_label(now) in {"Market closed", "Post-close", "Calendar unavailable"}:
        return fetch_top_trade_today(force_refresh=True)
    premarket_snaps = fetch_premarket(candidate_symbols, now)
    picks = []
    excluded = {"staleBars": 0, "screening": 0, "invalidLevels": 0, "expiredContract": 0}

    for symbol in candidate_symbols:
        market_item = ticker_lookup.get(symbol) or index_lookup.get(symbol)
        if not market_item:
            continue

        two_min = intraday.get(symbol, {}).get("2m", {})
        if not _fresh_intraday(two_min, now) or not _fresh_intraday(intraday.get(symbol, {}).get("15m", {}), now, 15):
            excluded["staleBars"] += 1
            continue
        item = dict(market_item)
        item.update(watch_lookup.get(symbol) or {})
        item["price"] = two_min["close"][-1]
        item["_expectedMovePct"] = 0.0
        expected_move = str(item.get("expectedMove") or "")
        if "(" in expected_move and "%" in expected_move:
            try:
                item["_expectedMovePct"] = float(expected_move.split("(")[-1].split("%")[0].replace("+", "").replace("-", ""))
            except Exception:
                item["_expectedMovePct"] = float(item.get("atrPct") or 0.0)
        else:
            item["_expectedMovePct"] = float(item.get("atrPct") or 0.0)

        atm_row = atm_lookup.get(symbol)
        top_watch_item = top_watch_lookup.get(symbol)
        tf = _build_timeframe_snapshots(symbol, intraday)
        pm_snap = premarket_snaps.get(symbol)
        pm_dict = pm_snap.as_dict() if pm_snap is not None else None
        item["_gapPct"] = float((pm_dict or {}).get("gapPct") or 0.0)
        scored = _score_candidate(symbol, item, atm_row, top_watch_item, unusual_by_symbol.get(symbol, []), tf, session, pm_dict, is_premarket)
        if not scored:
            excluded["screening"] += 1
            continue

        direction = scored["direction"]
        setup_type = _build_setup_type(direction, item, tf)
        support = list(item.get("support") or [])
        resistance = list(item.get("resistance") or [])
        bull_trigger = str(item.get("bullTrigger") or "")
        bear_trigger = str(item.get("bearTrigger") or "")
        levels = _trade_levels(item, direction)
        if not levels:
            excluded["invalidLevels"] += 1
            continue
        trigger_level, stop_level, targets = levels["trigger"], levels["stop"], levels["targets"]
        quote = scored["quote"]
        try:
            expiry_date = datetime.fromisoformat(str(quote.get("expirationDate"))).date()
        except (ValueError, TypeError):
            excluded["expiredContract"] += 1
            continue
        if expiry_date < now.date():
            excluded["expiredContract"] += 1
            continue
        spread_value = scored["spread"]
        item["_spreadDollars"] = spread_value

        pick = {
            "ticker": symbol,
            "direction": direction,
            "setupType": setup_type,
            "why": _summarize_why(symbol, direction, item, top_watch_item, scored["unusualBias"], macro_events, tf),
            "keyLevels": {
                "support": support[:2],
                "resistance": resistance[:2],
                "trigger": trigger_level,
                "premarketHigh": (pm_dict or {}).get("pmh"),
                "premarketLow": (pm_dict or {}).get("pml"),
            },
            "premarket": pm_dict or {},
            "triggerToEnter": bull_trigger if direction == "Call" else bear_trigger,
            "stopInvalidation": f"Back through {stop_level}" if stop_level is not None else "Failed break back inside range",
            "profitTargets": targets,
            "bestContractIdea": {
                "strike": quote.get("contract") or "Unavailable",
                "expiry": quote.get("expirationDate"),
            },
            "spreadPct": round(quote["spreadPct"], 2),
            "rewardRisk": levels["rewardRisk"],
            "barAsOf": two_min["time"][-1],
            "quoteFetchedAt": flow_payload.get("updatedAt"),
            "status": "Pre-market watch" if is_premarket else "Watch for confirmation",
            "bottomLine": "Watchlist setup only. Confirm the trigger and live option bid/ask; source quote timestamps and delta are unavailable.",
            "ruinRisk": _build_risk_line(symbol, direction, item, macro_events, scored["unusualBias"]),
            "score": scored["score"],
            "expectedMovePct": round(item["_expectedMovePct"], 1),
            "spread": spread_value,
            "sessionAlignment": {
                "4h": tf["4h"].direction,
                "1h": tf["1h"].direction,
                "15m": tf["15m"].direction,
                "2m": tf["2m"].direction,
            },
            "earningsDate": item.get("earningsDate"),
        }
        picks.append(pick)

    picks.sort(key=lambda item: (-item["score"], item["spreadPct"], item["ticker"]))
    picks = picks[:4]  # Never pad the board with candidates that failed screening.
    if excluded["staleBars"]:
        warnings.append(f"{excluded['staleBars']} symbols excluded: missing or stale completed intraday candles.")
    if excluded["screening"]:
        warnings.append(f"{excluded['screening']} candidates excluded by direction, quote, spread or score checks.")
    if excluded["expiredContract"]:
        warnings.append(f"{excluded['expiredContract']} contracts excluded: missing or expired expiry dates.")
    if excluded["invalidLevels"]:
        warnings.append(f"{excluded['invalidLevels']} setups excluded: no valid stop or target beyond the entry.")

    avoid = []
    for symbol, row in atm_lookup.items():
        for direction in ("Call", "Put"):
            quote = _option_quote(row, direction)
            if quote and quote["spreadPct"] > MAX_OPTION_SPREAD_PCT:
                avoid.append(f"{symbol} {direction}")
    avoid = sorted(set(avoid))[:5]

    best_pick = picks[0]["ticker"] if picks else ""
    summary = (
        f"{best_pick} ranks highest among the screened watchlist setups. Confirm entry conditions before considering a trade."
    ) if picks else "No qualifying setups right now. Missing data or failed screening does not produce a fallback trade."

    payload = {
        "marketDate": now.date().isoformat(),
        "generatedAt": int(time.time()),
        "sessionType": session["label"],
        "sessionLabel": _market_session_label(now),
        "choppyDayWarning": session["choppy"],
        "macroRisks": _build_macro_risks(macro_events),
        "todaysEvents": macro_events.get("today", []),
        "bestOverallPick": best_pick,
        "namesToAvoid": avoid,
        "summary": summary,
        "picks": picks[:4],
        "liveData": bool(picks),
        "dataWarnings": warnings,
        "excluded": excluded,
        "scoreMethod": "Heuristic ranking points; success rate unmeasured.",
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = time.time() + CACHE_TTL_SECONDS
        _cache["session_key"] = today_key

    return payload
