#!/usr/bin/env python3
"""
top_trade_today.py — Daily options setup engine for Option Riders.

Builds up to three high-conviction setups for the current U.S. trading session
from live market data, macro events, options flow, and cross-source momentum.
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from barchart_proxy import fetch_options_activity
from market_data import fetch_market_data
from top_watch import fetch_top_watch


CACHE_TTL_SECONDS = 300
NY_TZ = ZoneInfo("America/New_York")
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
    open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now < open_dt:
        return "Pre-market"
    if now <= close_dt:
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
    digits = []
    allowed = set("0123456789.")
    for token in text.replace(",", " ").split():
        cleaned = "".join(ch for ch in token if ch in allowed)
        if cleaned.count(".") <= 1 and cleaned and cleaned != ".":
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _download_multiframe(symbols: List[str]) -> Dict[str, dict]:
    if not symbols:
        return {}
    try:
        import yfinance as yf
    except Exception:
        return {}

    settings = {
        "1h": {"period": "60d", "interval": "60m"},
        "15m": {"period": "10d", "interval": "15m"},
        "2m": {"period": "5d", "interval": "2m"},
    }
    result = {symbol: {} for symbol in symbols}

    for label, params in settings.items():
        try:
            raw = yf.download(
                symbols,
                period=params["period"],
                interval=params["interval"],
                progress=False,
                auto_adjust=True,
                prepost=True,
            )
        except Exception:
            continue

        def _series(field: str, symbol: str) -> List[float]:
            try:
                if hasattr(raw.columns, "levels"):
                    return list(raw[field][symbol].dropna().astype(float))
                return list(raw[field].dropna().astype(float))
            except Exception:
                return []

        for symbol in symbols:
            result[symbol][label] = {
                "open": _series("Open", symbol),
                "high": _series("High", symbol),
                "low": _series("Low", symbol),
                "close": _series("Close", symbol),
                "volume": _series("Volume", symbol),
            }

    return result


def _collapse_to_4h(one_hour: dict) -> dict:
    closes = list(one_hour.get("close") or [])
    highs = list(one_hour.get("high") or [])
    lows = list(one_hour.get("low") or [])
    opens = list(one_hour.get("open") or [])
    volumes = list(one_hour.get("volume") or [])
    if len(closes) < 8:
        return {"open": [], "high": [], "low": [], "close": [], "volume": []}

    result = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for idx in range(0, len(closes), 4):
        c_slice = closes[idx:idx + 4]
        if len(c_slice) < 4:
            continue
        o_slice = opens[idx:idx + 4]
        h_slice = highs[idx:idx + 4]
        l_slice = lows[idx:idx + 4]
        v_slice = volumes[idx:idx + 4]
        result["open"].append(o_slice[0])
        result["high"].append(max(h_slice))
        result["low"].append(min(l_slice))
        result["close"].append(c_slice[-1])
        result["volume"].append(sum(v_slice) if v_slice else 0.0)
    return result


def _snapshot_from_closes(label: str, closes: List[float]) -> TimeframeSnapshot:
    if len(closes) < 8:
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


def _next_friday(today: datetime) -> str:
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0 and today.hour >= 12:
        days_until_friday = 7
    expiry = today + timedelta(days=days_until_friday)
    return expiry.strftime("%b %-d, %Y")


def _round_strike(price: float, direction: str) -> float:
    if price >= 500:
        step = 5
    elif price >= 200:
        step = 2.5
    elif price >= 50:
        step = 1
    else:
        step = 0.5
    if direction == "Call":
        return math.ceil(price / step) * step
    return math.floor(price / step) * step


def _format_strike(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _quality_bucket(score: float) -> str:
    if score >= 72:
        return "Low"
    if score >= 56:
        return "Medium"
    return "High"


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
    rel = item.get("relStrength")
    if rel is not None:
        label = "relative strength" if rel > 0 else "relative weakness"
        if direction == "Call" and rel > 0:
            parts.append(f"{rel:+.1f}% {label} vs SPY")
        elif direction == "Put" and rel < 0:
            parts.append(f"{rel:+.1f}% {label} vs SPY")
    move_pct = item.get("_expectedMovePct") or 0
    if move_pct:
        parts.append(f"{move_pct:.1f}% expected move")
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


def _score_candidate(symbol: str, item: dict, atm_spread_row: Optional[dict], top_watch_item: Optional[dict], unusual_rows: List[dict], tf: Dict[str, TimeframeSnapshot], session: dict) -> Optional[dict]:
    price = float(item.get("price") or 0.0)
    if price <= 0:
        return None

    signal_score = float(item.get("signalScore") or 0.0)
    rel_strength = float(item.get("relStrength") or 0.0)
    expected_move_pct = float(item.get("_expectedMovePct") or 0.0)
    spread = None
    ratio = None
    leader = "balanced"
    if atm_spread_row:
        call_spread = (((atm_spread_row.get("call") or {}).get("spread")) if isinstance(atm_spread_row.get("call"), dict) else None)
        put_spread = (((atm_spread_row.get("put") or {}).get("spread")) if isinstance(atm_spread_row.get("put"), dict) else None)
        values = [value for value in (call_spread, put_spread) if isinstance(value, (int, float))]
        spread = min(values) if values else None
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
    if spread is not None:
        penalty = 0.0 if spread <= 0.08 else 4.0 if spread <= 0.15 else 12.0
        call_score -= penalty
        put_score -= penalty
    if session.get("choppy"):
        call_score -= 3.0
        put_score -= 3.0

    direction = "Call" if call_score >= put_score else "Put"
    best_score = max(call_score, put_score)
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
        "confidence": round(min(9.6, max(4.8, 5.0 + (best_score / 18.0))), 1),
        "spread": spread,
        "putCallRatio": ratio,
        "putCallLeader": leader,
        "unusualBias": unusual_bias,
        "bullishTfs": bullish_tfs,
        "bearishTfs": bearish_tfs,
    }


def fetch_top_trade_today(force_refresh: bool = False) -> dict:
    now = _now_ny()
    today_key = _session_key(now)

    if not force_refresh:
        with _cache_lock:
            if _cache["payload"] and _cache["expires_at"] > time.time() and _cache["session_key"] == today_key:
                return _cache["payload"]

    market_payload = fetch_market_data(force_refresh=force_refresh)
    flow_payload = fetch_options_activity(force_refresh=force_refresh)
    top_watch_payload = fetch_top_watch(force_refresh=force_refresh)
    macro_events = _fetch_macro_events()
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

    intraday = _download_multiframe(candidate_symbols)
    picks = []

    for symbol in candidate_symbols:
        market_item = ticker_lookup.get(symbol) or index_lookup.get(symbol)
        if not market_item:
            continue

        item = dict(market_item)
        item.update(watch_lookup.get(symbol) or {})
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
        scored = _score_candidate(symbol, item, atm_row, top_watch_item, unusual_by_symbol.get(symbol, []), tf, session)
        if not scored:
            continue

        direction = scored["direction"]
        setup_type = _build_setup_type(direction, item, tf)
        support = list(item.get("support") or [])
        resistance = list(item.get("resistance") or [])
        bull_trigger = str(item.get("bullTrigger") or "")
        bear_trigger = str(item.get("bearTrigger") or "")
        price = float(item.get("price") or 0.0)
        trigger_level = _parse_trigger_number(bull_trigger if direction == "Call" else bear_trigger)
        stop_level = support[0] if direction == "Call" and support else resistance[0] if resistance else None
        if direction == "Put":
            stop_level = resistance[0] if resistance else None
        targets = resistance[:2] if direction == "Call" else support[:2]
        if not targets:
            atr = float(item.get("atr") or 0.0)
            targets = [round(price + atr, 2)] if direction == "Call" else [round(price - atr, 2)]

        strike_basis = trigger_level or price
        strike = _round_strike(strike_basis, direction)
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
            },
            "triggerToEnter": bull_trigger if direction == "Call" else bear_trigger,
            "stopInvalidation": f"Back through {stop_level}" if stop_level is not None else "Failed break back inside range",
            "profitTargets": targets,
            "bestContractIdea": {
                "strike": f"{_format_strike(strike)}{'C' if direction == 'Call' else 'P'}",
                "expiry": _next_friday(now),
                "deltaPreference": "0.35 to 0.50",
            },
            "riskLevel": _quality_bucket(scored["score"]),
            "confidence": scored["confidence"],
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

    picks.sort(key=lambda item: (-item["score"], -item["confidence"], item["ticker"]))

    confidence_floor = 6.3 if session["choppy"] else 6.0
    preferred_picks = [pick for pick in picks if pick["confidence"] >= confidence_floor]
    fallback_picks = [pick for pick in picks if pick["confidence"] < confidence_floor]
    picks = (preferred_picks + fallback_picks)[:4]

    if not picks and candidate_symbols:
        fallback_symbol = next((symbol for symbol in PRIMARY_UNIVERSE if symbol in ticker_lookup), None)
        if fallback_symbol:
            item = ticker_lookup[fallback_symbol]
            picks = [{
                "ticker": fallback_symbol,
                "direction": "Call" if (item.get("signalScore") or 0) >= 0 else "Put",
                "setupType": "Wait for confirmation",
                "why": "Nothing is clean enough yet. This is only the least-bad liquid name on the board.",
                "keyLevels": {
                    "support": list(item.get("support") or [])[:2],
                    "resistance": list(item.get("resistance") or [])[:2],
                    "trigger": _parse_trigger_number(str(item.get("bullTrigger") or item.get("bearTrigger") or "")),
                },
                "triggerToEnter": str(item.get("bullTrigger") or item.get("bearTrigger") or "Wait for range break"),
                "stopInvalidation": "Stand aside if the trigger does not confirm",
                "profitTargets": list(item.get("resistance") or item.get("support") or [])[:2],
                "bestContractIdea": {
                    "strike": f"{_format_strike(_round_strike(float(item.get('price') or 0.0), 'Call'))}C",
                    "expiry": _next_friday(now),
                    "deltaPreference": "0.30 to 0.40",
                },
                "riskLevel": "High",
                "confidence": 5.4,
                "ruinRisk": "choppy tape and no clean confirmation",
                "score": 24.0,
                "expectedMovePct": round(float(item.get("atrPct") or 0.0), 1),
                "spread": None,
                "sessionAlignment": {},
                "earningsDate": item.get("earningsDate"),
            }]

    if 0 < len(picks) < 4:
        existing = {pick["ticker"] for pick in picks}
        for symbol in candidate_symbols:
            if len(picks) >= 4:
                break
            if symbol in existing or symbol not in ticker_lookup:
                continue
            item = ticker_lookup[symbol]
            direction = "Call" if (item.get("signalScore") or 0) >= 0 else "Put"
            picks.append({
                "ticker": symbol,
                "direction": direction,
                "setupType": "Wait for confirmation",
                "why": "This is a lower-conviction filler idea added to keep the board full. Wait for clean confirmation before acting.",
                "keyLevels": {
                    "support": list(item.get("support") or [])[:2],
                    "resistance": list(item.get("resistance") or [])[:2],
                    "trigger": _parse_trigger_number(str(item.get("bullTrigger") or item.get("bearTrigger") or "")),
                },
                "triggerToEnter": str(item.get("bullTrigger") or item.get("bearTrigger") or "Wait for range break"),
                "stopInvalidation": "Stand aside if the trigger does not confirm",
                "profitTargets": list(item.get("resistance") or item.get("support") or [])[:2],
                "bestContractIdea": {
                    "strike": f"{_format_strike(_round_strike(float(item.get('price') or 0.0), direction))}{'C' if direction == 'Call' else 'P'}",
                    "expiry": _next_friday(now),
                    "deltaPreference": "0.30 to 0.40",
                },
                "riskLevel": "High",
                "confidence": 5.2,
                "ruinRisk": "choppy tape and no clean confirmation",
                "score": 20.0,
                "expectedMovePct": round(float(item.get("atrPct") or 0.0), 1),
                "spread": None,
                "sessionAlignment": {},
                "earningsDate": item.get("earningsDate"),
            })
            existing.add(symbol)

    avoid = []
    for symbol, row in atm_lookup.items():
        call_spread = (((row.get("call") or {}).get("spread")) if isinstance(row.get("call"), dict) else None)
        put_spread = (((row.get("put") or {}).get("spread")) if isinstance(row.get("put"), dict) else None)
        worst = max(value for value in (call_spread, put_spread) if isinstance(value, (int, float))) if any(isinstance(value, (int, float)) for value in (call_spread, put_spread)) else None
        if worst is not None and worst > 0.20:
            avoid.append(symbol)
    avoid = sorted(dict.fromkeys(avoid))[:5]

    best_pick = picks[0]["ticker"] if picks else ""
    summary = (
        f"If I only take one trade today, it should be {picks[0]['ticker']} {picks[0]['direction']} "
        f"because it has the cleanest alignment between technicals, liquidity, and catalyst pressure."
    ) if picks else "No trade. The board is not clean enough yet."

    payload = {
        "marketDate": today_key,
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
        "liveData": True,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = time.time() + CACHE_TTL_SECONDS
        _cache["session_key"] = today_key

    return payload
