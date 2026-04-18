"""
Option Riders — Trade Journal (cloud backend)

Postgres-backed version of the analytics engine, used by the Vercel function
handlers under `api/journal-*.py`. The pure-Python analytics (trade building,
stats, calendar) live in trade_journal.py and are reused here.

Storage goes through Supabase PostgREST with the caller's Bearer token, so
Row-Level Security policies enforce per-user isolation automatically.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

import trade_journal  # pure-Python analytics helpers


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


# ---------- auth ----------

def verify_user(bearer_token: str) -> str | None:
    """
    Resolve a Supabase access token to a user ID. Returns None on failure.
    """
    if not bearer_token or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {bearer_token}",
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("id") or None
    except Exception:
        return None


def _rest_headers(bearer_token: str, extra: dict | None = None) -> dict:
    """Headers for PostgREST calls. Uses the caller's JWT so RLS applies."""
    h = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


# ---------- storage ----------

# All NUMERIC columns come back as strings from PostgREST; coerce on read.
_NUMERIC_COLUMNS = (
    "quantity", "trade_price", "proceeds", "commission",
    "realized_pnl", "mtm_pnl", "multiplier", "strike",
    "cost_basis", "fx_rate_to_base",
)


def _coerce(row: dict) -> dict:
    for f in _NUMERIC_COLUMNS:
        v = row.get(f)
        if isinstance(v, str):
            try:
                row[f] = float(v)
            except ValueError:
                row[f] = None
    return row


def fetch_user_fills(bearer_token: str, filters: dict | None = None,
                     limit: int | None = None) -> list[dict]:
    """Read user's fills via PostgREST. RLS enforces user scoping."""
    params: list[tuple[str, str]] = []
    filters = filters or {}
    if filters.get("from"):
        params.append(("trade_date", f"gte.{filters['from']}"))
    if filters.get("to"):
        params.append(("trade_date", f"lte.{filters['to']}"))
    if filters.get("asset_class"):
        params.append(("asset_class", f"eq.{filters['asset_class']}"))
    if filters.get("symbol"):
        # underlying match OR symbol match
        params.append(("or", f"(symbol.eq.{filters['symbol']},underlying.eq.{filters['symbol']})"))
    params.append(("order", "datetime.desc"))
    if limit:
        params.append(("limit", str(limit)))

    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/journal_fills",
        headers=_rest_headers(bearer_token),
        params=params,
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"fetch_user_fills: {resp.status_code} {resp.text[:200]}")
    return [_coerce(r) for r in resp.json()]


def fetch_all_user_fills(bearer_token: str) -> list[dict]:
    """Whole-history fetch (for round-trip matching). No date filter."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/journal_fills",
        headers=_rest_headers(bearer_token),
        params=[("order", "datetime.asc"), ("limit", "50000")],
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"fetch_all_user_fills: {resp.status_code} {resp.text[:200]}")
    return [_coerce(r) for r in resp.json()]


def insert_fills(bearer_token: str, user_id: str, rows: list[dict]) -> dict:
    """
    Bulk insert with upsert semantics. Returns {inserted, skipped, updated}.

    PostgREST upsert via ON CONFLICT requires the Prefer header. We also
    request the inserted rows back in compact form so we can count.
    """
    if not rows:
        return {"inserted": 0, "skipped": 0, "updated": 0}

    # Tag every row with the authenticated user_id (RLS also checks this).
    for r in rows:
        r["user_id"] = user_id

    # Chunk large uploads (Supabase has request size limits)
    CHUNK = 500
    inserted = 0
    updated = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        # PostgREST (PGRST102) requires every row in a bulk insert to have the
        # exact same set of keys. Build the union and fill missing keys with None.
        all_keys: set[str] = set()
        for r in chunk:
            all_keys.update(r.keys())
        chunk = [{k: r.get(k) for k in all_keys} for r in chunk]
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/journal_fills",
            headers=_rest_headers(bearer_token, {
                "Prefer": "return=representation,resolution=merge-duplicates",
            }),
            data=json.dumps(chunk),
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"insert_fills: {resp.status_code} {resp.text[:300]}")
        returned = resp.json()
        inserted += len(returned)

    return {"inserted": inserted, "skipped": max(0, len(rows) - inserted), "updated": updated}


def delete_all_user_fills(bearer_token: str, user_id: str) -> int:
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/journal_fills",
        headers=_rest_headers(bearer_token, {"Prefer": "return=representation"}),
        params=[("user_id", f"eq.{user_id}")],
        timeout=30,
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"delete_all_user_fills: {resp.status_code} {resp.text[:200]}")
    return len(resp.json()) if resp.content else 0


# ---------- analytics (reuse pure-Python helpers from trade_journal.py) ----------

def _normalize_row_for_insert(raw: dict, user_id: str) -> dict:
    """Run IBKR's raw row through the shared normalizer and tag with user_id."""
    row = trade_journal._normalize_row(raw)
    row["user_id"] = user_id
    row["source"] = row.get("source") or "ibkr_flex"
    row["imported_at"] = datetime.now(timezone.utc).isoformat()
    return row


def _parse_flex_and_normalize(raw_text: str, user_id: str) -> list[dict]:
    """Auto-detect CSV vs XML, extract rows, normalize each for insertion."""
    stripped = raw_text.lstrip()
    out: list[dict] = []
    if stripped.startswith("<"):
        for raw in trade_journal._parse_flex_xml(raw_text):
            nr = _normalize_row_for_insert(raw, user_id)
            if nr.get("symbol") or nr.get("underlying"):
                out.append(nr)
    else:
        for raw in trade_journal._iter_csv_rows(raw_text):
            nr = _normalize_row_for_insert(raw, user_id)
            if nr.get("symbol") or nr.get("underlying"):
                out.append(nr)
    return out


def compute_stats(bearer_token: str, filters: dict | None = None) -> dict:
    rows = fetch_user_fills(bearer_token, filters or {}, limit=100000)
    return _compute_stats_from_rows(rows)


def _compute_stats_from_rows(rows: list[dict]) -> dict:
    if not rows:
        return {
            "net_pnl": 0.0, "net_pnl_after_comm": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0,
            "commissions": 0.0, "fill_count": 0, "trade_count": 0, "close_count": 0,
            "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "by_symbol": [], "by_day": [], "by_asset_class": [],
            "base_currency_applied": False,
        }
    trades = trade_journal._build_trades(rows)
    has_fx = any((r.get("fx_rate_to_base") or 0) for r in rows)
    pnls = [t["gross_pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    commissions = sum(t["commission"] for t in trades)

    by_symbol: dict[str, dict[str, float]] = {}
    by_day: dict[str, float] = {}
    by_class: dict[str, float] = {}
    for t in trades:
        sym = t["underlying"] or t["symbol"] or "UNKNOWN"
        d = t["close_date"] or ""
        ac = t["asset_class"] or "UNKNOWN"
        pnl = t["gross_pnl"]
        bucket = by_symbol.setdefault(sym, {"pnl": 0.0, "count": 0, "wins": 0})
        bucket["pnl"] += pnl
        bucket["count"] += 1
        if pnl > 0:
            bucket["wins"] += 1
        by_day[d] = by_day.get(d, 0.0) + pnl
        by_class[ac] = by_class.get(ac, 0.0) + pnl

    return {
        "net_pnl": round(sum(pnls), 2),
        "net_pnl_after_comm": round(sum(pnls) + commissions, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "commissions": round(commissions, 2),
        "fill_count": len(rows),
        "trade_count": len(trades),
        "close_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / abs(gross_loss), 3) if gross_loss else 0.0,
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0.0,
        "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "by_symbol": sorted(
            [{"symbol": k, **v, "pnl": round(v["pnl"], 2)} for k, v in by_symbol.items()],
            key=lambda x: x["pnl"], reverse=True,
        ),
        "by_day": sorted(
            [{"date": k, "pnl": round(v, 2)} for k, v in by_day.items() if k],
            key=lambda x: x["date"],
        ),
        "by_asset_class": sorted(
            [{"asset_class": k, "pnl": round(v, 2)} for k, v in by_class.items()],
            key=lambda x: x["pnl"], reverse=True,
        ),
        "base_currency_applied": has_fx,
    }


def equity_curve(bearer_token: str, filters: dict | None = None) -> list[dict]:
    stats = compute_stats(bearer_token, filters)
    running = 0.0
    curve = []
    for pt in stats["by_day"]:
        running += pt["pnl"]
        curve.append({"date": pt["date"], "pnl": pt["pnl"], "equity": round(running, 2)})
    return curve


def calendar_month(bearer_token: str, year: int, month: int,
                   filters: dict | None = None) -> dict:
    import calendar as cal
    rows = fetch_all_user_fills(bearer_token)
    trades = trade_journal._build_trades(rows)

    first_day = datetime(year, month, 1).date().isoformat()
    last_day_num = cal.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num).date().isoformat()

    per_day: dict[str, dict] = {}
    for t in trades:
        d = t["close_date"] or ""
        if not d or not (first_day <= d <= last_day):
            continue
        bucket = per_day.setdefault(d, {"pnl": 0.0, "trades": 0, "wins": 0})
        bucket["pnl"] += t["gross_pnl"]
        bucket["trades"] += 1
        if t["is_win"]:
            bucket["wins"] += 1

    days = []
    for day in range(1, last_day_num + 1):
        date_iso = datetime(year, month, day).date().isoformat()
        b = per_day.get(date_iso)
        if b:
            win_rate = (b["wins"] / b["trades"] * 100) if b["trades"] else 0.0
            days.append({
                "date": date_iso, "day": day,
                "pnl": round(b["pnl"], 2),
                "trades": b["trades"],
                "win_rate": round(win_rate, 2),
            })
        else:
            days.append({"date": date_iso, "day": day, "pnl": 0.0, "trades": 0, "win_rate": 0.0})

    weeks: list[dict] = []
    cal.setfirstweekday(cal.SUNDAY)
    for week in cal.monthcalendar(year, month):
        pnl = 0.0
        active = 0
        for d in week:
            if d == 0:
                continue
            b = per_day.get(datetime(year, month, d).date().isoformat())
            if b and b["trades"]:
                pnl += b["pnl"]
                active += 1
        weeks.append({"pnl": round(pnl, 2), "active_days": active})

    first_weekday = datetime(year, month, 1).weekday()
    lead_blank = (first_weekday + 1) % 7

    month_pnl = round(sum(d["pnl"] for d in days), 2)
    month_active = sum(1 for d in days if d["trades"])

    return {
        "year": year, "month": month,
        "month_name": cal.month_name[month],
        "days": days, "weeks": weeks,
        "month_pnl": month_pnl, "active_days": month_active,
        "lead_blank": lead_blank,
    }


def day_detail(bearer_token: str, date_iso: str) -> dict:
    rows = fetch_all_user_fills(bearer_token)
    trades = trade_journal._build_trades(rows)
    day_trades = [t for t in trades if t["close_date"] == date_iso]
    day_rows = [r for r in rows if r.get("trade_date") == date_iso and r.get("asset_class") != "CASH"]

    pnls = [t["gross_pnl"] for t in day_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    commissions = sum(t["commission"] for t in day_trades)
    volume = sum(abs(r.get("quantity") or 0.0) for r in day_rows)

    intraday = []
    running = 0.0
    for t in sorted(day_trades, key=lambda x: x["close_datetime"] or ""):
        running += t["gross_pnl"]
        intraday.append({"t": t["close_datetime"], "equity": round(running, 2)})

    meta_by_symbol = {}
    for r in day_rows:
        meta_by_symbol.setdefault(r.get("symbol"), r)

    trades_out = []
    for t in day_trades:
        open_iso = t["open_datetime"] or t["close_datetime"] or ""
        time_str = ""
        if open_iso:
            try:
                time_str = datetime.fromisoformat(open_iso).strftime("%H:%M:%S")
            except ValueError:
                time_str = open_iso[11:19]
        meta = meta_by_symbol.get(t["symbol"], {})
        is_opt = meta.get("asset_class") in ("OPT", "FOP")
        side = (meta.get("put_call") or "").upper() if is_opt else ""
        if is_opt and side == "C":
            side = "CALL"
        elif is_opt and side == "P":
            side = "PUT"
        if not is_opt:
            side = (meta.get("buy_sell") or "").upper()
        strike = meta.get("strike")
        expiry = meta.get("expiry")
        if is_opt and expiry and strike is not None:
            y, m, d = str(expiry).split("-")
            strike_s = str(int(strike)) if float(strike).is_integer() else f"{strike:.2f}".rstrip("0").rstrip(".")
            pc = "PUT" if meta.get("put_call") == "P" else "CALL" if meta.get("put_call") == "C" else ""
            instrument = f"{m}-{d}-{y} {strike_s} {pc}".strip()
        else:
            instrument = t["underlying"] or t["symbol"]
        roi = None
        basis = meta.get("cost_basis")
        if not basis:
            qty = abs(meta.get("quantity") or 0.0)
            mult = meta.get("multiplier") or 1.0
            price = meta.get("trade_price") or 0.0
            basis = qty * mult * price if price else None
        if basis:
            roi = t["gross_pnl"] / abs(basis) * 100.0
        trades_out.append({
            "time": time_str,
            "ticker": t["underlying"] or t["symbol"],
            "side": side,
            "instrument": instrument,
            "asset_class": meta.get("asset_class"),
            "fill_count": t["fill_count"],
            "net_pnl": t["gross_pnl"],
            "gross_pnl": t["gross_pnl"],
            "net_after_comm": t["net_pnl"],
            "realized_pnl": t["realized_pnl"],
            "commission": t["commission"],
            "net_roi": round(roi, 2) if roi is not None else None,
        })

    return {
        "date": date_iso,
        "total_trades": len(day_trades),
        "fill_count": len(day_rows),
        "close_count": len(day_trades),
        "gross_pnl": round(sum(pnls), 2),
        "net_pnl": round(sum(pnls), 2),
        "net_after_commissions": round(sum(pnls) + commissions, 2),
        "commissions": round(commissions, 2),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(day_trades) * 100, 2) if day_trades else 0.0,
        "profit_factor": round(gross_profit / abs(gross_loss), 3) if gross_loss else 0.0,
        "volume": round(volume, 2),
        "intraday": intraday,
        "trades": trades_out,
    }


# ---------- IBKR sync ----------

def sync_from_ibkr(bearer_token: str, user_id: str,
                   ibkr_token: str, ibkr_query_id: str) -> dict:
    if not ibkr_token or not ibkr_query_id:
        return {"ok": False, "error": "Missing IBKR credentials"}
    try:
        started = datetime.now(timezone.utc)
        report = trade_journal.fetch_flex_report(ibkr_token, ibkr_query_id)
        rows = _parse_flex_and_normalize(report, user_id)
        result = insert_fills(bearer_token, user_id, rows)
        return {
            "ok": True,
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "updated": result["updated"],
            "format": "xml" if report.lstrip().startswith("<") else "csv",
            "fetched_at": started.isoformat(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
