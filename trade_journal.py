"""
Option Riders — Trade Journal

A lightweight "mini TradeZella" for Interactive Brokers.

Imports executions from an IBKR Flex Query CSV (Trades section), stores them in
SQLite, and surfaces stats + an equity curve for a journaling dashboard.

How to get the CSV:
  IBKR Client Portal -> Performance & Reports -> Flex Queries ->
    Custom Flex Query (Trades section, CSV format) -> Run -> download.
  The parser is tolerant of optional sections/headers in the export.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DB_PATH = Path(os.environ.get("TRADE_JOURNAL_DB", Path(__file__).parent / "trade_journal.db"))


# ---------- schema ----------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT,
    account         TEXT,
    symbol          TEXT,
    underlying      TEXT,
    asset_class     TEXT,
    datetime        TEXT,
    trade_date      TEXT,
    quantity        REAL,
    trade_price     REAL,
    proceeds        REAL,
    commission      REAL,
    realized_pnl    REAL,
    mtm_pnl         REAL,
    open_close      TEXT,
    buy_sell        TEXT,
    currency        TEXT,
    multiplier      REAL,
    strike          REAL,
    expiry          TEXT,
    put_call        TEXT,
    cost_basis      REAL,
    source          TEXT,
    imported_at     TEXT,
    UNIQUE(trade_id, datetime, symbol, quantity, trade_price)
);

CREATE INDEX IF NOT EXISTS idx_fills_trade_date ON fills(trade_date);
CREATE INDEX IF NOT EXISTS idx_fills_symbol     ON fills(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_datetime   ON fills(datetime);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date  TEXT,
    symbol      TEXT,
    body        TEXT,
    tags        TEXT,
    created_at  TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


# ---------- parsing ----------

# Map IBKR Flex headers -> our column names. Lowercased for robustness.
_FIELD_MAP = {
    "tradeid":              "trade_id",
    "clientaccountid":      "account",
    "accountalias":         "account",
    "symbol":               "symbol",
    "underlyingsymbol":     "underlying",
    "assetclass":           "asset_class",
    "datetime":             "datetime",
    "date/time":            "datetime",
    "tradedate":            "trade_date",
    "quantity":             "quantity",
    "tradeprice":           "trade_price",
    "proceeds":             "proceeds",
    "ibcommission":         "commission",
    "commission":           "commission",
    "fifopnlrealized":      "realized_pnl",
    "realizedpnl":          "realized_pnl",
    "mtmpnl":               "mtm_pnl",
    "openclosedindicator":  "open_close",
    "opencloseindicator":   "open_close",
    "open/closeindicator":  "open_close",
    "buysell":              "buy_sell",
    "buy/sell":             "buy_sell",
    "assetcategory":        "asset_class",
    "currency":             "currency",
    "currencyprimary":      "currency",
    "multiplier":           "multiplier",
    "strike":               "strike",
    "expiry":               "expiry",
    "put/call":             "put_call",
    "putcall":              "put_call",
    "costbasis":            "cost_basis",
    "fxratetobase":         "fx_rate_to_base",
}


_EXPECTED_COLUMNS = {
    "cost_basis": "REAL",
    "fx_rate_to_base": "REAL",
    "user_id": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotently add any columns missing from older DBs."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(fills)")}
    for col, ctype in _EXPECTED_COLUMNS.items():
        if col not in existing:
            try:
                conn.execute(f"ALTER TABLE fills ADD COLUMN {col} {ctype}")
            except sqlite3.OperationalError:
                pass
    # Backfill any pre-auth rows to the local dev owner so they remain visible.
    local = os.environ.get("LOCAL_DEV_USER_ID", "local")
    conn.execute("UPDATE fills SET user_id = ? WHERE user_id IS NULL", [local])
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_user ON fills(user_id)")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "--"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_datetime(value: str) -> str | None:
    """IBKR uses 'YYYYMMDD;HHMMSS' or 'YYYY-MM-DD HH:MM:SS' or 'YYYYMMDD HHMMSS'."""
    if not value:
        return None
    s = str(value).strip().replace(";", " ")
    fmts = ("%Y%m%d %H%M%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return s  # store raw, still better than dropping


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, raw_val in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip().lower().replace(" ", "")
        mapped = _FIELD_MAP.get(key)
        if not mapped:
            continue
        out[mapped] = raw_val

    # Coerce types
    for f in ("quantity", "trade_price", "proceeds", "commission",
              "realized_pnl", "mtm_pnl", "multiplier", "strike",
              "cost_basis", "fx_rate_to_base"):
        if f in out:
            out[f] = _to_float(out[f])

    if "datetime" in out:
        out["datetime"] = _parse_datetime(out["datetime"])
    if "trade_date" in out:
        out["trade_date"] = _parse_date(out["trade_date"])
    if "expiry" in out:
        out["expiry"] = _parse_date(out["expiry"])

    # Derive trade_date from datetime if missing
    if not out.get("trade_date") and out.get("datetime"):
        try:
            out["trade_date"] = datetime.fromisoformat(out["datetime"]).date().isoformat()
        except ValueError:
            pass

    return out


def _iter_csv_rows(text: str) -> Iterable[dict[str, str]]:
    """
    IBKR Flex CSVs can have either a single header row (simple) or a
    multi-section layout where every row is prefixed with a section name.
    Handle both.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return

    first = rows[0]
    # Detect section-prefixed format: first col is the section name (e.g. "Trades")
    if first and first[0].strip().lower() in {"header", "data", "trades", "trade"}:
        # Two flavors: (a) "Trades,Header,Col1,..." / "Trades,Data,Val1,..."
        headers: list[str] | None = None
        for row in rows:
            if len(row) < 2:
                continue
            tag = (row[1] or "").strip().lower()
            section = (row[0] or "").strip().lower()
            if section not in {"trades", "trade"}:
                continue
            if tag == "header":
                headers = row[2:]
            elif tag == "data" and headers:
                yield dict(zip(headers, row[2:]))
        return

    # Simple single-header CSV
    headers = first
    for row in rows[1:]:
        if not row or len(row) == 1 and not row[0].strip():
            continue
        yield dict(zip(headers, row))


_BACKFILL_COLUMNS = ("fx_rate_to_base", "cost_basis")


def _backfill_if_present(cur: sqlite3.Cursor, row: dict[str, Any]) -> None:
    """
    When an incoming row duplicates an existing fill but brings new column
    values (e.g. FXRateToBase added to the Flex query after the initial sync),
    update those specific columns without touching anything else.
    """
    updates = {c: row.get(c) for c in _BACKFILL_COLUMNS if row.get(c) is not None}
    if not updates:
        return
    set_clause = ", ".join(f"{c} = ?" for c in updates)
    params = list(updates.values()) + [
        row.get("trade_id"), row.get("datetime"), row.get("symbol"),
        row.get("quantity"), row.get("trade_price"),
    ]
    cur.execute(
        f"UPDATE fills SET {set_clause} WHERE "
        "trade_id IS ? AND datetime IS ? AND symbol IS ? "
        "AND quantity IS ? AND trade_price IS ?",
        params,
    )


def _parse_flex_xml(xml_text: str) -> list[dict[str, str]]:
    """Extract trade dicts from a Flex Web Service XML response."""
    root = ET.fromstring(xml_text)
    trades: list[dict[str, str]] = []
    for trade in root.iter("Trade"):
        trades.append({k: (v or "") for k, v in trade.attrib.items()})
    return trades


def import_flex_report(raw_text: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Auto-detect CSV vs XML and import. Used by both the file-upload path
    and the Flex Web Service path.
    """
    stripped = raw_text.lstrip()
    if stripped.startswith("<"):
        # XML from Flex Web Service or Flex XML download
        init_db()
        try:
            rows = _parse_flex_xml(raw_text)
        except ET.ParseError as exc:
            return {"ok": False, "error": f"XML parse: {exc}", "inserted": 0, "skipped": 0}
        inserted = skipped = 0
        now = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            cur = conn.cursor()
            for raw in rows:
                norm = _normalize_row(raw)
                if not norm.get("symbol") and not norm.get("underlying"):
                    skipped += 1
                    continue
                norm.setdefault("source", "ibkr_flex_ws")
                norm["imported_at"] = now
                if user_id:
                    norm["user_id"] = user_id
                cols = list(norm.keys())
                placeholders = ",".join("?" for _ in cols)
                cur.execute(
                    f"INSERT OR IGNORE INTO fills ({','.join(cols)}) VALUES ({placeholders})",
                    [norm[c] for c in cols],
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
                    _backfill_if_present(cur, norm)
            conn.commit()
        return {"ok": True, "inserted": inserted, "skipped": skipped, "format": "xml"}
    # Default to CSV
    result = import_flex_csv(raw_text, user_id=user_id)
    result["format"] = "csv"
    return result


# ---------- Flex Web Service ----------

FLEX_BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "OptionRiders/TradeJournal"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_flex_report(token: str, query_id: str,
                      max_wait: int = 60, poll_interval: int = 3) -> str:
    """
    Two-step IBKR Flex Web Service flow:
      1. SendRequest -> reference code
      2. GetStatement(reference) -> report bytes (poll until ready)
    Returns the raw report text (XML or CSV depending on query config).
    """
    if not token or not query_id:
        raise ValueError("missing FLEX_TOKEN or FLEX_QUERY_ID")

    send_url = f"{FLEX_BASE}/SendRequest?t={urllib.parse.quote(token)}&q={urllib.parse.quote(query_id)}&v=3"
    send_xml = _http_get(send_url)
    try:
        send_root = ET.fromstring(send_xml)
    except ET.ParseError as exc:
        raise RuntimeError(f"SendRequest returned non-XML: {exc}\n{send_xml[:200]}") from exc

    status = (send_root.findtext("Status") or "").strip()
    if status.lower() != "success":
        code = send_root.findtext("ErrorCode") or "?"
        msg = send_root.findtext("ErrorMessage") or send_xml
        raise RuntimeError(f"IBKR SendRequest failed ({code}): {msg}")

    reference = (send_root.findtext("ReferenceCode") or "").strip()
    base_url = (send_root.findtext("Url") or f"{FLEX_BASE}/GetStatement").strip()
    if not reference:
        raise RuntimeError("IBKR SendRequest returned no ReferenceCode")

    get_url = f"{base_url}?t={urllib.parse.quote(token)}&q={urllib.parse.quote(reference)}&v=3"

    waited = 0
    while waited <= max_wait:
        body = _http_get(get_url)
        stripped = body.lstrip()
        # If still processing, IBKR returns a small XML with a status code
        if stripped.startswith("<FlexStatementResponse") or stripped.startswith("<Status"):
            try:
                r = ET.fromstring(body)
                code = (r.findtext("ErrorCode") or "").strip()
                # 1019 = statement generation in progress
                if code == "1019":
                    time.sleep(poll_interval)
                    waited += poll_interval
                    continue
                msg = r.findtext("ErrorMessage") or body[:200]
                raise RuntimeError(f"IBKR GetStatement failed ({code}): {msg}")
            except ET.ParseError:
                pass
        return body
    raise TimeoutError(f"IBKR GetStatement timed out after {max_wait}s")


def sync_from_ibkr(token: str | None = None, query_id: str | None = None,
                   user_id: str | None = None) -> dict[str, Any]:
    """
    Convenience: fetch + import in one call. Credentials can be passed directly
    or fall back to env vars IBKR_FLEX_TOKEN / IBKR_FLEX_QUERY_ID.
    """
    token = token or os.environ.get("IBKR_FLEX_TOKEN", "").strip()
    query_id = query_id or os.environ.get("IBKR_FLEX_QUERY_ID", "").strip()
    if not token or not query_id:
        return {"ok": False, "error": "No IBKR credentials — open Settings and paste your token and query ID."}
    try:
        started = datetime.now(timezone.utc)
        report = fetch_flex_report(token, query_id)
        result = import_flex_report(report, user_id=user_id)
        result["fetched_at"] = started.isoformat()
        _write_last_sync(started.isoformat(), result)
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------- last-sync timestamp (persisted) ----------

_LAST_SYNC_FILE = Path(__file__).parent / ".trade_journal_last_sync.json"


def _write_last_sync(when_iso: str, result: dict[str, Any]) -> None:
    try:
        _LAST_SYNC_FILE.write_text(json.dumps({"at": when_iso, "result": result}))
    except OSError:
        pass


def last_sync() -> dict[str, Any]:
    if not _LAST_SYNC_FILE.exists():
        return {"at": None, "result": None}
    try:
        return json.loads(_LAST_SYNC_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"at": None, "result": None}


def import_flex_csv(csv_text: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Parse an IBKR Flex Query Trades CSV and insert rows.
    Returns a summary dict with inserted / skipped counts.
    """
    init_db()
    inserted = 0
    skipped = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        cur = conn.cursor()
        for idx, raw in enumerate(_iter_csv_rows(csv_text), start=1):
            try:
                row = _normalize_row(raw)
                if not row.get("symbol") and not row.get("underlying"):
                    skipped += 1
                    continue
                row.setdefault("source", "ibkr_flex")
                row["imported_at"] = now
                if user_id:
                    row["user_id"] = user_id

                cols = list(row.keys())
                placeholders = ",".join("?" for _ in cols)
                stmt = f"INSERT OR IGNORE INTO fills ({','.join(cols)}) VALUES ({placeholders})"
                cur.execute(stmt, [row[c] for c in cols])
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
                    # Row already exists — backfill any columns that the newer
                    # Flex query now provides (e.g. fx_rate_to_base, cost_basis).
                    _backfill_if_present(cur, row)
            except Exception as exc:
                errors.append(f"row {idx}: {exc}")
        conn.commit()

    return {"ok": True, "inserted": inserted, "skipped": skipped,
            "errors": errors[:10], "error_count": len(errors)}


# ---------- queries ----------

def _build_trades(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fold a stream of fills into round-trip trades, one per
    (account, symbol) position cycle (0 → non-zero → 0).

    Skips CASH/FX conversions — those aren't trades, they're currency moves.
    """
    from collections import defaultdict

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if (r.get("asset_class") or "") == "CASH":
            continue
        key = ((r.get("account") or ""), (r.get("symbol") or r.get("underlying") or ""))
        if not key[1]:
            continue
        buckets[key].append(r)

    trades: list[dict[str, Any]] = []
    for (account, symbol), fills in buckets.items():
        fills.sort(key=lambda x: (x.get("datetime") or "", x.get("id") or 0))
        position = 0.0
        realized = 0.0
        commission = 0.0
        fill_count = 0
        open_fill = None
        last_fill = None
        for f in fills:
            qty = f.get("quantity") or 0.0
            if qty == 0:
                continue
            if position == 0:
                realized = 0.0
                commission = 0.0
                fill_count = 0
                open_fill = f
            position += qty
            # If IBKR gave us an FX-to-base rate, use it — the raw amounts are
            # in the trade's local currency (e.g. USD). Multiplying pulls them
            # into the account's base currency (e.g. GBP). Otherwise keep raw.
            fx = f.get("fx_rate_to_base")
            rate = fx if fx else 1.0
            realized += (f.get("realized_pnl") or 0.0) * rate
            commission += (f.get("commission") or 0.0) * rate
            fill_count += 1
            last_fill = f
            if abs(position) < 1e-9:
                position = 0.0
                trades.append({
                    "account": account,
                    "symbol": symbol,
                    "underlying": open_fill.get("underlying") or symbol,
                    "asset_class": open_fill.get("asset_class"),
                    "open_date": open_fill.get("trade_date"),
                    "open_datetime": open_fill.get("datetime"),
                    "close_date": last_fill.get("trade_date"),
                    "close_datetime": last_fill.get("datetime"),
                    "fill_count": fill_count,
                    "gross_pnl": round(realized, 2),
                    "realized_pnl": round(realized, 2),
                    "commission": round(commission, 2),
                    "net_pnl": round(realized + commission, 2),
                    "is_win": realized > 0,
                })
    return trades


def _where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("user_id"):
        clauses.append("user_id = ?"); params.append(filters["user_id"])
    if filters.get("from"):
        clauses.append("trade_date >= ?"); params.append(filters["from"])
    if filters.get("to"):
        clauses.append("trade_date <= ?"); params.append(filters["to"])
    if filters.get("symbol"):
        clauses.append("(symbol = ? OR underlying = ?)")
        params += [filters["symbol"], filters["symbol"]]
    if filters.get("asset_class"):
        clauses.append("asset_class = ?"); params.append(filters["asset_class"])
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def list_fills(filters: dict[str, Any] | None = None, limit: int = 500) -> list[dict[str, Any]]:
    init_db()
    where, params = _where(filters or {})
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM fills{where} ORDER BY datetime DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return [dict(r) for r in rows]


def compute_stats(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    where, params = _where(filters or {})
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM fills{where}", params).fetchall()]

    if not rows:
        return {
            "net_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
            "commissions": 0.0, "fill_count": 0, "trade_count": 0, "close_count": 0,
            "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "by_symbol": [], "by_day": [], "by_asset_class": [],
        }

    trades = _build_trades(rows)
    has_fx = any((r.get("fx_rate_to_base") or 0) for r in rows)
    # Use gross P&L for headline figures (matches TradeZella's calendar).
    # Net = gross + commission is still exposed separately.
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
        "net_pnl": round(sum(pnls), 2),   # headline (gross, TZ-compatible)
        "net_pnl_after_comm": round(sum(pnls) + commissions, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "commissions": round(commissions, 2),
        "fill_count": len(rows),
        "trade_count": len(trades),
        "base_currency_applied": has_fx,
        "close_count": len(trades),  # kept for UI compat
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
    }


def calendar_month(year: int, month: int, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    TradeZella-style P&L calendar: per-day and per-week rollups for a single month.
    """
    import calendar as cal
    init_db()
    # Clamp window to this month
    first_day = datetime(year, month, 1).date().isoformat()
    last_day_num = cal.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num).date().isoformat()

    f = dict(filters or {})
    f["from"] = max(first_day, f.get("from", first_day))
    f["to"] = min(last_day, f.get("to", last_day))

    # Pull the whole history so round-trip matching sees opens that may predate
    # the month window, then restrict results to the target month. Keep it
    # scoped to the requesting user.
    hist_where, hist_params = _where({"user_id": filters.get("user_id")} if filters else {})
    with _connect() as conn:
        all_rows = [dict(r) for r in conn.execute(f"SELECT * FROM fills{hist_where}", hist_params).fetchall()]
    trades = _build_trades(all_rows)

    per_day: dict[str, dict[str, Any]] = {}
    for t in trades:
        d = t["close_date"] or ""
        if not d or not (first_day <= d <= last_day):
            continue
        bucket = per_day.setdefault(d, {"pnl": 0.0, "trades": 0, "wins": 0})
        # Use gross P&L to match TradeZella's calendar headline
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
                "date": date_iso,
                "day": day,
                "pnl": round(b["pnl"], 2),
                "trades": b["trades"],
                "win_rate": round(win_rate, 2),
            })
        else:
            days.append({"date": date_iso, "day": day, "pnl": 0.0, "trades": 0, "win_rate": 0.0})

    # Weekly rollups (Sun-Sat, matching the screenshot)
    weeks: list[dict[str, Any]] = []
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

    month_pnl = round(sum(d["pnl"] for d in days), 2)
    month_active = sum(1 for d in days if d["trades"])

    # Sunday-first header layout helper
    first_weekday = datetime(year, month, 1).weekday()  # Mon=0..Sun=6
    lead_blank = (first_weekday + 1) % 7  # Sun=0

    return {
        "year": year,
        "month": month,
        "month_name": cal.month_name[month],
        "days": days,
        "weeks": weeks,
        "month_pnl": month_pnl,
        "active_days": month_active,
        "lead_blank": lead_blank,
    }


def day_detail(date_iso: str, user_id: str | None = None) -> dict[str, Any]:
    """Everything needed for the day-drill modal — trade-level, not fill-level."""
    init_db()
    user_clause = " AND user_id = ?" if user_id else ""
    user_params = [user_id] if user_id else []
    with _connect() as conn:
        all_rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM fills WHERE 1=1{user_clause}", user_params
        ).fetchall()]
        day_rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM fills WHERE trade_date = ? AND asset_class != 'CASH'{user_clause} ORDER BY datetime ASC",
            [date_iso, *user_params],
        ).fetchall()]

    all_trades = _build_trades(all_rows)
    day_trades = [t for t in all_trades if t["close_date"] == date_iso]

    pnls = [t["gross_pnl"] for t in day_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    commissions = sum(t["commission"] for t in day_trades)
    volume = sum(abs(r["quantity"] or 0.0) for r in day_rows)

    # Intraday cumulative gross-P&L, timestamped at each trade's close
    intraday: list[dict[str, Any]] = []
    running = 0.0
    for t in sorted(day_trades, key=lambda x: x["close_datetime"] or ""):
        running += t["gross_pnl"]
        intraday.append({"t": t["close_datetime"], "equity": round(running, 2)})

    # Render each trade with its earliest (open) fill for context
    by_symbol_map: dict[str, dict[str, Any]] = {}
    for r in day_rows:
        by_symbol_map.setdefault(r["symbol"], r)

    trades_out: list[dict[str, Any]] = []
    for t in day_trades:
        open_iso = t["open_datetime"] or t["close_datetime"] or ""
        time_str = ""
        if open_iso:
            try:
                time_str = datetime.fromisoformat(open_iso).strftime("%H:%M:%S")
            except ValueError:
                time_str = open_iso[11:19]

        meta = by_symbol_map.get(t["symbol"], {})
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
            y, m, d = expiry.split("-")
            strike_s = str(int(strike)) if float(strike).is_integer() else f"{strike:.2f}".rstrip("0").rstrip(".")
            pc = "PUT" if meta.get("put_call") == "P" else "CALL" if meta.get("put_call") == "C" else ""
            instrument = f"{m}-{d}-{y} {strike_s} {pc}".strip()
        else:
            instrument = t["underlying"] or t["symbol"]

        # Net ROI using opener's cost basis if available
        roi = None
        basis = meta.get("cost_basis")
        if not basis:
            qty = abs(meta.get("quantity") or 0.0)
            mult = meta.get("multiplier") or 1.0
            price = meta.get("trade_price") or 0.0
            basis = qty * mult * price if price else None
        if basis:
            roi = t["net_pnl"] / abs(basis) * 100.0

        trades_out.append({
            "time": time_str,
            "ticker": t["underlying"] or t["symbol"],
            "side": side,
            "instrument": instrument,
            "asset_class": meta.get("asset_class"),
            "fill_count": t["fill_count"],
            "net_pnl": t["gross_pnl"],          # display = gross (TZ-style)
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
        "net_pnl": round(sum(pnls), 2),         # headline = gross (matches TZ)
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


def equity_curve(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Cumulative realized P&L by calendar day."""
    stats = compute_stats(filters)
    curve: list[dict[str, Any]] = []
    running = 0.0
    for point in stats["by_day"]:
        running += point["pnl"]
        curve.append({"date": point["date"], "pnl": point["pnl"], "equity": round(running, 2)})
    return curve


def clear_all(user_id: str | None = None) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        if user_id:
            n = conn.execute("DELETE FROM fills WHERE user_id = ?", [user_id]).rowcount
        else:
            n = conn.execute("DELETE FROM fills").rowcount
        conn.commit()
    return {"ok": True, "deleted": n}


# ---------- CLI ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: trade_journal.py {import <csv>|stats|fills|clear}")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "import":
        with open(sys.argv[2], encoding="utf-8") as f:
            print(json.dumps(import_flex_csv(f.read()), indent=2))
    elif cmd == "stats":
        print(json.dumps(compute_stats(), indent=2))
    elif cmd == "fills":
        print(json.dumps(list_fills(limit=50), indent=2))
    elif cmd == "clear":
        print(json.dumps(clear_all(), indent=2))
    else:
        print(f"unknown: {cmd}")
