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
from zoneinfo import ZoneInfo

# IBKR Flex reports timestamps in the account's execution-venue local time,
# which for US brokerage accounts is America/New_York. We display in UK time
# (same as Lisbon) — matches TradeZella's display and the user's locale.
_IBKR_TZ = ZoneInfo("America/New_York")
_DISPLAY_TZ = ZoneInfo("Europe/London")


def _fmt_display_time(iso_str: str | None) -> str:
    """Convert an IBKR-local ISO timestamp to HH:MM:SS in Europe/London."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        # Fallback: return raw HH:MM:SS slice if we can't parse
        return iso_str[11:19]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IBKR_TZ)
    return dt.astimezone(_DISPLAY_TZ).strftime("%H:%M:%S")

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


# Supabase's hosted PostgREST caps responses at 1000 rows per request regardless
# of the `limit` query param. Paginate with Range headers to pull everything.
_PAGE_SIZE = 1000


def _paginated_get(bearer_token: str, params: list[tuple[str, str]],
                   cap: int | None = None, timeout: int = 30) -> list[dict]:
    """GET /journal_fills in 1000-row pages until exhausted (or cap reached)."""
    out: list[dict] = []
    offset = 0
    while True:
        page_end = offset + _PAGE_SIZE - 1
        headers = _rest_headers(bearer_token, {
            "Range-Unit": "items",
            "Range": f"{offset}-{page_end}",
            "Prefer": "count=exact",
        })
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/journal_fills",
            headers=headers,
            params=params,
            timeout=timeout,
        )
        # 200 (exact fit) and 206 (partial content) are both success for Range reads.
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"_paginated_get: {resp.status_code} {resp.text[:200]}")
        batch = resp.json()
        out.extend(_coerce(r) for r in batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
        if cap is not None and len(out) >= cap:
            return out[:cap]
    return out


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
    return _paginated_get(bearer_token, params, cap=limit, timeout=15)


def fetch_all_user_fills(bearer_token: str) -> list[dict]:
    """Whole-history fetch (for round-trip matching). No date filter."""
    return _paginated_get(bearer_token, [("order", "datetime.asc")], timeout=30)


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
        # Upsert on the (user_id, trade_id, datetime, symbol, quantity, trade_price)
        # unique constraint — without on_conflict PostgREST tries the PK (id) and
        # returns 409 when the natural key collides.
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/journal_fills"
            "?on_conflict=user_id,trade_id,datetime,symbol,quantity,trade_price",
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


def _open_positions_opened_on(rows: list[dict], date_iso: str) -> list[dict]:
    """
    Return positions that are still open AND whose current cycle started on
    `date_iso`. Used to list in-progress trades alongside closed ones in the
    day detail view (TradeZella-style — "(open)" rows).

    A cycle is a stretch of fills starting from position=0 going non-zero. If
    the most recent cycle for a (account, symbol) bucket never returns to zero
    by the end of available fills, it's an "open" position. If its first fill
    lands on date_iso, we surface it for that day.
    """
    from collections import defaultdict
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if (r.get("asset_class") or "") == "CASH":
            continue
        key = ((r.get("account") or ""), (r.get("symbol") or r.get("underlying") or ""))
        if not key[1]:
            continue
        buckets[key].append(r)

    out: list[dict] = []
    for (account, symbol), fills in buckets.items():
        fills.sort(key=lambda x: (x.get("datetime") or "", x.get("id") or 0))
        position = 0.0
        cycle_fills: list[dict] = []
        cycle_open_fill = None
        for f in fills:
            qty = f.get("quantity") or 0.0
            if qty == 0:
                continue
            if position == 0:
                cycle_fills = []
                cycle_open_fill = f
            position += qty
            cycle_fills.append(f)
            if abs(position) < 1e-9:
                position = 0.0
                cycle_fills = []
                cycle_open_fill = None
        # After all fills: if position still non-zero, the last cycle is open.
        if cycle_open_fill and abs(position) >= 1e-9:
            open_date = cycle_open_fill.get("trade_date")
            if open_date == date_iso:
                mtm = 0.0
                for f in cycle_fills:
                    fx = f.get("fx_rate_to_base") or 1.0
                    mtm += (f.get("mtm_pnl") or 0.0) * fx
                out.append({
                    "account": account,
                    "symbol": symbol,
                    "underlying": cycle_open_fill.get("underlying") or symbol,
                    "asset_class": cycle_open_fill.get("asset_class"),
                    "open_datetime": cycle_open_fill.get("datetime"),
                    "open_date": open_date,
                    "fill_count": len(cycle_fills),
                    "position_qty": round(position, 4),
                    "floating_pnl": round(mtm, 2),
                })
    return out


def _fills_for_trade(rows: list[dict], account: str, symbol: str,
                     open_iso: str | None, close_iso: str | None) -> list[dict]:
    """Return the individual IBKR fills that make up a single trade cycle."""
    if not symbol:
        return []
    out = []
    for r in rows:
        if (r.get("account") or "") != (account or ""):
            continue
        row_sym = r.get("symbol") or r.get("underlying") or ""
        if row_sym != symbol:
            continue
        dt = r.get("datetime") or ""
        if open_iso and dt and dt < open_iso:
            continue
        if close_iso and dt and dt > close_iso:
            continue
        out.append(r)
    return out


def _fill_summary(fill: dict) -> dict:
    """Trim an IBKR fill down to the fields the trade-detail UI needs."""
    return {
        "datetime": fill.get("datetime"),
        "quantity": fill.get("quantity"),
        "trade_price": fill.get("trade_price"),
        "proceeds": fill.get("proceeds"),
        "commission": fill.get("commission"),
        "realized_pnl": fill.get("realized_pnl"),
        "mtm_pnl": fill.get("mtm_pnl"),
        "buy_sell": fill.get("buy_sell"),
        "open_close": fill.get("open_close"),
    }


def _trade_metrics(fills: list[dict]) -> dict:
    """Average entry / exit price, gross quantity, qty still held (signed)."""
    open_qty = 0.0
    open_notional = 0.0
    close_qty = 0.0
    close_notional = 0.0
    net_qty = 0.0
    for f in fills:
        q = f.get("quantity") or 0.0
        p = f.get("trade_price") or 0.0
        net_qty += q
        # Opens add to position magnitude (same sign as current direction)
        if q > 0:
            open_qty += q
            open_notional += q * p
        else:
            close_qty += abs(q)
            close_notional += abs(q) * p
    avg_entry = (open_notional / open_qty) if open_qty else None
    avg_exit = (close_notional / close_qty) if close_qty else None
    return {
        "avg_entry_price": round(avg_entry, 4) if avg_entry is not None else None,
        "avg_exit_price": round(avg_exit, 4) if avg_exit is not None else None,
        "qty_opened": round(open_qty, 4),
        "qty_closed": round(close_qty, 4),
        "net_qty": round(net_qty, 4),
    }


def day_detail(bearer_token: str, date_iso: str) -> dict:
    rows = fetch_all_user_fills(bearer_token)
    trades = trade_journal._build_trades(rows)
    day_trades = [t for t in trades if t["close_date"] == date_iso]
    day_rows = [r for r in rows if r.get("trade_date") == date_iso and r.get("asset_class") != "CASH"]
    open_positions = _open_positions_opened_on(rows, date_iso)

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
        time_str = _fmt_display_time(open_iso)
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
        trade_fills = _fills_for_trade(
            rows, t.get("account") or "", t["symbol"],
            t.get("open_datetime"), t.get("close_datetime"),
        )
        tmetrics = _trade_metrics(trade_fills)
        trades_out.append({
            "time": time_str,
            "ticker": t["underlying"] or t["symbol"],
            "symbol": t["symbol"],
            "side": side,
            "instrument": instrument,
            "asset_class": meta.get("asset_class"),
            "strike": meta.get("strike"),
            "expiry": meta.get("expiry"),
            "put_call": meta.get("put_call"),
            "multiplier": meta.get("multiplier"),
            "currency": meta.get("currency"),
            "fill_count": t["fill_count"],
            "net_pnl": t["gross_pnl"],
            "gross_pnl": t["gross_pnl"],
            "net_after_comm": t["net_pnl"],
            "realized_pnl": t["realized_pnl"],
            "commission": t["commission"],
            "net_roi": round(roi, 2) if roi is not None else None,
            "is_open": False,
            "open_datetime": t.get("open_datetime"),
            "close_datetime": t.get("close_datetime"),
            "avg_entry_price": tmetrics["avg_entry_price"],
            "avg_exit_price": tmetrics["avg_exit_price"],
            "qty_opened": tmetrics["qty_opened"],
            "qty_closed": tmetrics["qty_closed"],
            "fills": [_fill_summary(f) for f in trade_fills],
        })

    for op in open_positions:
        open_iso = op.get("open_datetime") or ""
        time_str = _fmt_display_time(open_iso)
        meta = meta_by_symbol.get(op["symbol"], {})
        is_opt = op.get("asset_class") in ("OPT", "FOP")
        side = "CALL" if meta.get("put_call") == "C" else "PUT" if meta.get("put_call") == "P" else ""
        if not is_opt:
            side = (meta.get("buy_sell") or "").upper()
        strike = meta.get("strike")
        expiry = meta.get("expiry")
        if is_opt and expiry and strike is not None:
            y, m, d = str(expiry).split("-")
            strike_s = str(int(strike)) if float(strike).is_integer() else f"{strike:.2f}".rstrip("0").rstrip(".")
            instrument = f"{m}-{d}-{y} {strike_s} {side}".strip()
        else:
            instrument = op["underlying"] or op["symbol"]
        open_fills = _fills_for_trade(
            rows, op.get("account") or "", op["symbol"],
            op.get("open_datetime"), None,
        )
        omet = _trade_metrics(open_fills)
        trades_out.append({
            "time": time_str,
            "ticker": op["underlying"] or op["symbol"],
            "symbol": op["symbol"],
            "side": side,
            "instrument": instrument,
            "asset_class": op.get("asset_class"),
            "strike": meta.get("strike"),
            "expiry": meta.get("expiry"),
            "put_call": meta.get("put_call"),
            "multiplier": meta.get("multiplier"),
            "currency": meta.get("currency"),
            "fill_count": op["fill_count"],
            "net_pnl": op["floating_pnl"],
            "gross_pnl": op["floating_pnl"],
            "net_after_comm": op["floating_pnl"],
            "realized_pnl": 0.0,
            "commission": 0.0,
            "net_roi": None,
            "is_open": True,
            "position_qty": op["position_qty"],
            "open_datetime": op.get("open_datetime"),
            "close_datetime": None,
            "avg_entry_price": omet["avg_entry_price"],
            "avg_exit_price": omet["avg_exit_price"],
            "qty_opened": omet["qty_opened"],
            "qty_closed": omet["qty_closed"],
            "fills": [_fill_summary(f) for f in open_fills],
        })

    return {
        "date": date_iso,
        "total_trades": len(day_trades) + len(open_positions),
        "open_count": len(open_positions),
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

def _enumerate_flex_sections(report: str) -> list[dict]:
    """
    Diagnostic helper: return a list of {tag, count, sample_attrs, sample_xml}
    for each distinct element in the root <FlexStatements> tree. Used once to
    discover what MTM / Realized summary rows look like in the user's account
    before writing a parser for them.
    """
    if not report.lstrip().startswith("<"):
        return []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(report)
    except ET.ParseError:
        return []

    tags: dict[str, dict] = {}
    for el in root.iter():
        entry = tags.setdefault(el.tag, {
            "tag": el.tag,
            "count": 0,
            "attr_count": 0,
            "sample_attrs": {},
            "sample_xml": "",
        })
        entry["count"] += 1
        # Capture the first element with any attributes so the frontend can see
        # field names. Fall back to first element overall if nothing has attrs.
        if not entry["sample_attrs"]:
            if el.attrib:
                entry["attr_count"] = len(el.attrib)
                entry["sample_attrs"] = dict(list(el.attrib.items())[:60])
            if not entry["sample_xml"]:
                try:
                    xml_str = ET.tostring(el, encoding="unicode")
                    # Truncate huge elements but keep enough for attribute discovery
                    entry["sample_xml"] = xml_str[:1500]
                except Exception:
                    entry["sample_xml"] = ""
    return sorted(tags.values(), key=lambda x: -x["count"])[:60]


def sync_from_ibkr(bearer_token: str, user_id: str,
                   ibkr_token: str, ibkr_query_id: str,
                   diagnose: bool = False) -> dict:
    if not ibkr_token or not ibkr_query_id:
        return {"ok": False, "error": "Missing IBKR credentials"}
    try:
        started = datetime.now(timezone.utc)
        report = trade_journal.fetch_flex_report(ibkr_token, ibkr_query_id)
        rows = _parse_flex_and_normalize(report, user_id)
        result = insert_fills(bearer_token, user_id, rows)
        out = {
            "ok": True,
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "updated": result["updated"],
            "format": "xml" if report.lstrip().startswith("<") else "csv",
            "fetched_at": started.isoformat(),
        }
        if diagnose:
            out["sections_found"] = _enumerate_flex_sections(report)
        return out
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
