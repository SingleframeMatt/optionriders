#!/usr/bin/env python3
"""
news_feed.py — Intraday news desk aggregator for Option Riders.

Built for same-day ATM weekly debits on liquid mega-caps: it surfaces the
headlines that actually move price on the day, ranked for tradeability, and
scoped to the penny-wide-option whitelist.

Sources, in priority order:
  1. Yahoo Finance (via yfinance)  — always-on backbone, ~10 fresh items/ticker,
     no hard daily cap. This is the stream you see.
  2. Alpha Vantage NEWS_SENTIMENT  — sentiment scores layered on top when the
     25/day free-tier quota allows; degrades silently to a keyword lexicon.
  3. ForexFactory macro calendar   — today's high-impact USD events + next up.

Every article is scored for intraday relevance (recency, core-name weight,
sentiment magnitude, catalyst topic) so the strongest, freshest, most tradeable
headlines float to the top.
"""

from __future__ import annotations

import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import alpha_vantage as av

NY_TZ = ZoneInfo("America/New_York")
CACHE_TTL_SECONDS = 300  # 5 min — Yahoo backbone refresh cadence

# ── Universe ────────────────────────────────────────────────────────────────
# Named priority list — always weighted highest.
CORE_TICKERS = {"AMD", "NVDA", "TSLA", "MSFT", "TSM"}
# Intraday news universe: core + index proxies + highest news-flow liquid names.
# Kept tight so the Yahoo fan-out stays fast; every name has penny-wide weeklies.
NEWS_UNIVERSE = [
    "SPY", "QQQ",
    "NVDA", "AMD", "TSLA", "MSFT", "TSM",
    "AAPL", "META", "AMZN", "GOOGL", "AVGO",
    "MU", "PLTR", "COIN", "SMCI", "NFLX",
]

# ── Sentiment lexicon (fallback when AV quota is spent) ─────────────────────
_BULL = {
    "beat", "beats", "surge", "surges", "surged", "upgrade", "upgraded", "raises",
    "raised", "record", "jumps", "jumped", "rally", "rallies", "tops", "soars",
    "soared", "outperform", "buyback", "strong", "wins", "win", "approval",
    "approved", "gains", "gain", "climbs", "spike", "spikes", "bullish", "boom",
    "rebound", "beat expectations", "higher", "growth", "expands", "milestone",
}
_BEAR = {
    "miss", "misses", "missed", "plunge", "plunges", "plunged", "downgrade",
    "downgraded", "cuts", "cut", "falls", "fell", "sinks", "sank", "probe",
    "lawsuit", "recall", "warns", "warning", "slumps", "weak", "halts", "halted",
    "layoffs", "drops", "dropped", "tumbles", "tumbled", "slides", "slide",
    "bearish", "selloff", "sell-off", "crash", "crashes", "loss", "losses",
    "lower", "slashes", "slashed", "delays", "delay", "investigation", "fraud",
}

# ── Topic / catalyst detection ──────────────────────────────────────────────
_TOPIC_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("earnings", re.compile(r"\b(earnings|eps|quarterly results|q[1-4] results|beats? estimates|misses? estimates|guidance|profit (?:beat|miss|jump|surge|drop)|raises? (?:outlook|guidance)|cuts? (?:outlook|guidance))\b", re.I)),
    ("analyst", re.compile(r"\b(upgrade|downgrade|price target|initiat|overweight|underweight|buy rating|sell rating|reiterat)\b", re.I)),
    ("m&a", re.compile(r"\b(acqui|merger|buyout|takeover|deal|stake|bid for)\b", re.I)),
    ("halt", re.compile(r"\b(halt|halted|circuit breaker|suspend)\b", re.I)),
    ("legal", re.compile(r"\b(lawsuit|probe|investigat|sec |doj |antitrust|fine|settlement|fraud)\b", re.I)),
    ("product", re.compile(r"\b(launch|unveil|new chip|new model|partnership|contract|order|deploy)\b", re.I)),
    ("macro", re.compile(r"\b(fed|fomc|powell|cpi|inflation|jobs|payroll|rate cut|rate hike|tariff|treasury|yields)\b", re.I)),
    ("insider", re.compile(r"\b(insider|buyback|repurchase|dividend|split)\b", re.I)),
]

_TOPIC_WEIGHT = {
    "earnings": 6.0, "analyst": 5.0, "m&a": 6.0, "halt": 7.0,
    "legal": 4.5, "macro": 4.0, "product": 3.0, "insider": 2.5,
}

_cache_lock = threading.Lock()
_cache: dict = {"expires_at": 0.0, "payload": None}


# ── Helpers ─────────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _market_session(now_ny: datetime) -> str:
    if now_ny.weekday() >= 5:
        return "Closed"
    t = now_ny.time()
    if t < now_ny.replace(hour=9, minute=30, second=0, microsecond=0).time():
        return "Pre-market" if t >= now_ny.replace(hour=4, minute=0).time() else "Closed"
    if t <= now_ny.replace(hour=16, minute=0, second=0, microsecond=0).time():
        return "Regular session"
    if t <= now_ny.replace(hour=20, minute=0, second=0, microsecond=0).time():
        return "Post-close"
    return "Closed"


def _parse_iso(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _parse_av_time(s: str) -> Optional[float]:
    # AV format: 20260714T093000
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _ago(epoch: Optional[float], now: float) -> str:
    if not epoch:
        return ""
    delta = max(0, int(now - epoch))
    if delta < 90:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _lexicon_sentiment(text: str) -> Tuple[str, float]:
    words = re.findall(r"[a-z][a-z'-]+", (text or "").lower())
    if not words:
        return "Neutral", 0.0
    wset = set(words)
    bull = len(wset & _BULL)
    bear = len(wset & _BEAR)
    if bull == 0 and bear == 0:
        return "Neutral", 0.0
    score = (bull - bear) / (bull + bear + 1.5)
    score = max(-1.0, min(1.0, score))
    return _sentiment_label(score), round(score, 3)


def _sentiment_label(score: float) -> str:
    if score >= 0.35:
        return "Bullish"
    if score >= 0.15:
        return "Somewhat-Bullish"
    if score <= -0.35:
        return "Bearish"
    if score <= -0.15:
        return "Somewhat-Bearish"
    return "Neutral"


def _detect_topics(text: str) -> List[str]:
    return [name for name, pat in _TOPIC_PATTERNS if pat.search(text or "")]


def _whitelist_tickers(text: str, seed: Optional[str] = None) -> List[str]:
    found = []
    if seed and seed in NEWS_UNIVERSE:
        found.append(seed)
    upper = f" {text.upper()} " if text else ""
    for sym in NEWS_UNIVERSE:
        if sym in found:
            continue
        if re.search(rf"[\s(${{]{re.escape(sym)}[\s,.:)']", upper):
            found.append(sym)
    return found


def _trade_tag(topics: List[str], sent_score: float) -> str:
    if "macro" in topics:
        return "Macro"
    if "halt" in topics:
        return "Halt"
    if "earnings" in topics:
        return "Earnings"
    if "analyst" in topics:
        return "Analyst"
    if "m&a" in topics or "legal" in topics:
        return "Catalyst"
    if abs(sent_score) >= 0.35:
        return "Momentum"
    return "Watch"


# ── Source fetchers ─────────────────────────────────────────────────────────
def _yahoo_for_symbol(symbol: str) -> List[dict]:
    try:
        import yfinance as yf
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []
    out = []
    for it in items:
        c = it.get("content") or it
        if not isinstance(c, dict):
            continue
        title = (c.get("title") or "").strip()
        if not title:
            continue
        url = ((c.get("clickThroughUrl") or c.get("canonicalUrl") or {}) or {}).get("url") or ""
        provider = ((c.get("provider") or {}) or {}).get("displayName") or "Yahoo Finance"
        epoch = _parse_iso(c.get("pubDate") or c.get("displayTime") or "")
        out.append({
            "title": title,
            "summary": (c.get("summary") or c.get("description") or "").strip(),
            "url": url,
            "source": provider,
            "publishedEpoch": epoch,
            "seedTicker": symbol,
            "editorsPick": bool(((c.get("metadata") or {}) or {}).get("editorsPick")),
            "_origin": "yahoo",
        })
    return out


def _fetch_yahoo(symbols: List[str]) -> List[dict]:
    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(_yahoo_for_symbol, symbols):
            results.extend(chunk)
    return results


def _fetch_av_sentiment(symbols: List[str]) -> Tuple[Dict[str, dict], List[dict], str]:
    """
    Returns (per_ticker_sentiment, av_articles, status).
    status: "ok" | "rate_limited" | "unavailable"
    """
    try:
        data = av.fetch_news_sentiment(tickers=symbols, limit=200)
    except RuntimeError as exc:
        msg = str(exc).lower()
        return {}, [], "rate_limited" if ("rate" in msg or "25 requests" in msg or "sparingly" in msg) else "unavailable"
    except Exception:
        return {}, [], "unavailable"

    feed = data.get("feed") or []
    per_ticker: Dict[str, list] = {}
    articles: List[dict] = []
    universe = set(symbols)

    for a in feed:
        ts = _parse_av_time(a.get("time_published") or "")
        title = (a.get("title") or "").strip()
        rel_tickers = []
        for t in a.get("ticker_sentiment") or []:
            sym = (t.get("ticker") or "").upper()
            if sym not in universe:
                continue
            try:
                rel = float(t.get("relevance_score") or 0)
                score = float(t.get("ticker_sentiment_score") or 0)
            except Exception:
                continue
            if rel >= 0.1:
                per_ticker.setdefault(sym, []).append(score)
                rel_tickers.append(sym)
        if title and rel_tickers:
            try:
                overall = float(a.get("overall_sentiment_score") or 0)
            except Exception:
                overall = 0.0
            articles.append({
                "title": title,
                "summary": (a.get("summary") or "").strip(),
                "url": a.get("url") or "",
                "source": a.get("source") or "Alpha Vantage",
                "publishedEpoch": ts,
                "seedTicker": rel_tickers[0],
                "tickers": rel_tickers,
                "avSentiment": (_sentiment_label(overall), round(overall, 3)),
                "editorsPick": False,
                "_origin": "av",
            })

    net = {}
    for sym, scores in per_ticker.items():
        if scores:
            avg = sum(scores) / len(scores)
            net[sym] = {"score": round(avg, 3), "label": _sentiment_label(avg), "count": len(scores)}
    return net, articles, "ok"


def _fetch_macro() -> dict:
    try:
        from top_trade_today import _fetch_macro_events
        return _fetch_macro_events() or {}
    except Exception:
        return {}


# ── Scoring ─────────────────────────────────────────────────────────────────
def _intraday_score(article: dict, now: float) -> float:
    score = 0.0
    epoch = article.get("publishedEpoch")
    if epoch:
        hours = max(0.0, (now - epoch) / 3600.0)
        score += 14.0 * math.exp(-hours / 3.0)  # heavy recency decay (~3h half-weight)
    else:
        score += 3.0

    tickers = article.get("tickers") or []
    if any(t in CORE_TICKERS for t in tickers):
        score += 6.0
    elif tickers:
        score += 2.5

    label, sscore = article.get("sentiment", ("Neutral", 0.0))
    score += abs(sscore) * 8.0
    if article.get("sentimentSource") == "av":
        score += 1.5  # trust scored sentiment a touch more

    for topic in article.get("topics") or []:
        score += _TOPIC_WEIGHT.get(topic, 0.0)

    if article.get("editorsPick"):
        score += 2.0
    return round(score, 2)


# ── Assembly ────────────────────────────────────────────────────────────────
def _normalize_and_rank(yahoo: List[dict], av_articles: List[dict],
                        av_net: Dict[str, dict], now: float) -> List[dict]:
    merged = yahoo + av_articles
    seen: set = set()
    out: List[dict] = []

    for a in merged:
        title = a.get("title") or ""
        key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
        if not key or key in seen:
            continue
        seen.add(key)

        text = f"{title} {a.get('summary') or ''}"
        tickers = a.get("tickers") or _whitelist_tickers(text, a.get("seedTicker"))
        topics = _detect_topics(text)

        # Sentiment: prefer AV score, else per-ticker AV net, else lexicon.
        if a.get("avSentiment"):
            label, sscore = a["avSentiment"]
            ssource = "av"
        elif tickers and tickers[0] in av_net:
            n = av_net[tickers[0]]
            label, sscore, ssource = n["label"], n["score"], "av"
        else:
            label, sscore = _lexicon_sentiment(text)
            ssource = "lexicon"

        epoch = a.get("publishedEpoch")
        article = {
            "title": title,
            "summary": a.get("summary") or "",
            "url": a.get("url") or "",
            "source": a.get("source") or "",
            "published": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch else None,
            "publishedEpoch": epoch,
            "ago": _ago(epoch, now),
            "tickers": tickers,
            "primaryTicker": tickers[0] if tickers else None,
            "topics": topics,
            "sentiment": (label, sscore),
            "sentimentLabel": label,
            "sentimentScore": sscore,
            "sentimentSource": ssource,
            "tradeTag": _trade_tag(topics, sscore),
            "editorsPick": bool(a.get("editorsPick")),
        }
        article["score"] = _intraday_score(article, now)
        out.append(article)

    out.sort(key=lambda x: (-x["score"], -(x["publishedEpoch"] or 0)))
    return out


def _build_rollup(headlines: List[dict], av_net: Dict[str, dict], now: float) -> List[dict]:
    rollup: Dict[str, dict] = {}
    for h in headlines:
        for sym in h.get("tickers") or []:
            r = rollup.setdefault(sym, {"symbol": sym, "isCore": sym in CORE_TICKERS,
                                        "count": 0, "scores": [], "latest": None})
            r["count"] += 1
            r["scores"].append(h["sentimentScore"])
            if r["latest"] is None or (h.get("publishedEpoch") or 0) > (r["latest"].get("publishedEpoch") or 0):
                r["latest"] = h

    out = []
    for sym, r in rollup.items():
        scores = r["scores"]
        net = round(sum(scores) / len(scores), 3) if scores else 0.0
        # blend in AV net sentiment when present
        if sym in av_net:
            net = round((net + av_net[sym]["score"]) / 2, 3)
        latest = r["latest"] or {}
        out.append({
            "symbol": sym,
            "isCore": r["isCore"],
            "count": r["count"],
            "netSentiment": net,
            "netLabel": _sentiment_label(net),
            "latestTitle": latest.get("title"),
            "latestUrl": latest.get("url"),
            "latestAgo": latest.get("ago"),
            "latestTag": latest.get("tradeTag"),
        })
    out.sort(key=lambda x: (not x["isCore"], -x["count"], x["symbol"]))
    return out


def _market_tilt(headlines: List[dict]) -> dict:
    bull = bear = neutral = 0
    weighted = 0.0
    total_w = 0.0
    for h in headlines[:40]:
        s = h["sentimentScore"]
        w = max(0.5, h["score"] / 10.0)
        weighted += s * w
        total_w += w
        if s >= 0.15:
            bull += 1
        elif s <= -0.15:
            bear += 1
        else:
            neutral += 1
    tilt = round(weighted / total_w, 3) if total_w else 0.0
    return {"label": _sentiment_label(tilt), "score": tilt,
            "bull": bull, "bear": bear, "neutral": neutral}


def fetch_news(force_refresh: bool = False) -> dict:
    if not force_refresh:
        with _cache_lock:
            if _cache["payload"] and _cache["expires_at"] > time.time():
                return _cache["payload"]

    now = time.time()
    now_ny = datetime.now(tz=NY_TZ)

    yahoo = _fetch_yahoo(NEWS_UNIVERSE)
    av_net, av_articles, av_status = _fetch_av_sentiment(NEWS_UNIVERSE)
    macro = _fetch_macro()

    headlines = _normalize_and_rank(yahoo, av_articles, av_net, now)
    rollup = _build_rollup(headlines, av_net, now)
    tilt = _market_tilt(headlines)

    movers = sorted(rollup, key=lambda x: (-x["count"], -abs(x["netSentiment"])))[:6]

    # Next high-impact macro event
    next_high = None
    for ev in (macro.get("today") or []):
        if str(ev.get("impact", "")).lower() == "high":
            next_high = ev
            break
    if not next_high:
        nxt = macro.get("next") or []
        next_high = nxt[0] if nxt else None

    payload = {
        "asOf": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "generatedAt": int(now),
        "marketSession": _market_session(now_ny),
        "marketTilt": tilt,
        "macro": {
            "today": macro.get("today") or [],
            "next": macro.get("next") or [],
            "nextHighImpact": next_high,
        },
        "headlines": headlines[:40],
        "tickerRollup": rollup,
        "movers": movers,
        "universe": NEWS_UNIVERSE,
        "coreTickers": sorted(CORE_TICKERS),
        "sources": {
            "yahoo": len(yahoo),
            "alphaVantage": av_status if av_status != "ok" else len(av_articles),
        },
        "liveData": True,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = now + CACHE_TTL_SECONDS

    return payload


if __name__ == "__main__":
    import json
    import sys
    p = fetch_news(force_refresh="--fresh" in sys.argv)
    if "--json" in sys.argv:
        print(json.dumps(p, indent=2))
    else:
        print(f"Session: {p['marketSession']} | tilt {p['marketTilt']['label']} ({p['marketTilt']['score']:+})"
              f" | sources: yahoo={p['sources']['yahoo']} av={p['sources']['alphaVantage']}")
        print(f"Next macro: {p['macro']['nextHighImpact']}")
        print("\nTop headlines:")
        for h in p["headlines"][:12]:
            tk = ",".join(h["tickers"]) or "—"
            print(f"  [{h['score']:>5}] {h['ago']:>4} {h['tradeTag']:<8} {h['sentimentLabel']:<16} {tk:<12} {h['title'][:70]}")
