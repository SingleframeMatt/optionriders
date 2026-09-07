#!/usr/bin/env python3
"""
discipline_check.py — daily discipline scorecard for the trade journal.

Reads journal_fills straight from Supabase (service-role key, read-only),
reconstructs each option round-trip, and flags any trade that broke one of
the locked rules. The point is to surface a $54k mistake the DAY it happens,
not three months later.

Rules checked automatically (the ones the fills can prove):
  R1  Never add to a loser        — a later open filled below an earlier open
  R2  Max $4,000 position         — entry cost over cap  (also flags >$1,000 loss)
  R3  Fixed -25% stop             — realized loss worse than -25% of entry cost
  R4  No overnight holds          — opens and closes span more than one date
  R6  No entry in first 15 min    — first open before 09:45 ET

  R5 (ATM only, <=2% OTM) and R7 (>=65 scan setup) need the underlying spot /
  the scan log, which aren't in the fills — those stay a live/manual check.

Usage:
  .venv/bin/python discipline_check.py                # last 30 days
  .venv/bin/python discipline_check.py --since 2026-04-25
  .venv/bin/python discipline_check.py --days 90 --all   # show clean trades too
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# ---- rule thresholds (mirror memory/feedback_trading_rules.md) ----
MAX_POSITION = 4000.0      # R2  max entry cost, USD
MAX_LOSS = 1000.0          # R2  max realized loss per trade, USD
STOP_PCT = 0.25            # R3  -25% premium stop
FIRST_15_CUTOFF = (9, 45)  # R6  no entries before 09:45 ET
ADD_DOWN_TRIGGER = 0.98    # R1  later open <=98% of an earlier open = adding down

USER_ID = "6c7544b5-6d7f-4e8d-a46d-6110896ab31f"  # thedirectmatt@gmail.com


def load_dotenv(path: str = ".env") -> None:
    f = Path(path)
    if not f.exists():
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def fetch_fills(url: str, key: str, since: str) -> list[dict]:
    """Page through journal_fills for our user since `since` (YYYY-MM-DD)."""
    cols = ("symbol,underlying,asset_class,datetime,trade_date,quantity,"
            "trade_price,proceeds,realized_pnl,open_close,buy_sell,"
            "put_call,strike,expiry,multiplier")
    out: list[dict] = []
    page = 1000
    offset = 0
    while True:
        resp = requests.get(
            f"{url}/rest/v1/journal_fills",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Range-Unit": "items",
                "Range": f"{offset}-{offset + page - 1}",
            },
            params={
                "select": cols,
                "user_id": f"eq.{USER_ID}",
                "put_call": "not.is.null",
                "trade_date": f"gte.{since}",
                "order": "datetime.asc",
            },
            timeout=30,
        )
        if resp.status_code not in (200, 206):
            sys.exit(f"Supabase read failed: {resp.status_code} {resp.text[:200]}")
        batch = resp.json()
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return out


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = s.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d;%H%M%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def build_trades(fills: list[dict]) -> list[dict]:
    """Group fills into one round-trip per option contract."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in fills:
        key = (
            r.get("underlying") or r.get("symbol"),
            r.get("put_call"),
            r.get("strike"),
            r.get("expiry"),
        )
        groups[key].append(r)

    trades = []
    for (ul, pc, strike, expiry), rows in groups.items():
        rows.sort(key=lambda r: r.get("datetime") or "")
        opens = [r for r in rows if (r.get("open_close") or "").upper() == "O"]
        closes = [r for r in rows if (r.get("open_close") or "").upper() == "C"]
        if not opens or not closes:
            continue  # still open, or opened before the window — skip
        entry_cost = sum(abs(_f(r["quantity"])) * _f(r["trade_price"])
                         * (_f(r["multiplier"]) or 100.0) for r in opens)
        pnl = sum(_f(r.get("realized_pnl")) for r in closes)
        open_dts = [_parse_dt(r.get("datetime")) for r in opens]
        open_dts = [d for d in open_dts if d]
        close_dts = [_parse_dt(r.get("datetime")) for r in closes]
        close_dts = [d for d in close_dts if d]
        open_prices = [_f(r["trade_price"]) for r in opens]
        dates = {r.get("trade_date") for r in rows if r.get("trade_date")}
        trades.append({
            "ul": ul, "pc": pc, "strike": strike, "expiry": expiry,
            "entry_cost": entry_cost, "pnl": pnl,
            "first_open": min(open_dts) if open_dts else None,
            "last_close": max(close_dts) if close_dts else None,
            "open_prices": open_prices, "n_opens": len(opens),
            "dates": sorted(dates),
            "contracts": sum(abs(_f(r["quantity"])) for r in opens),
        })
    trades.sort(key=lambda t: t["first_open"] or datetime.min)
    return trades


def check(t: dict) -> list[str]:
    flags = []

    # R1 — added to a loser (a later open filled below an earlier one)
    prices = t["open_prices"]
    if t["n_opens"] > 1:
        running_max = prices[0]
        for p in prices[1:]:
            if p <= running_max * ADD_DOWN_TRIGGER:
                flags.append("ADDED-DOWN")
                break
            running_max = max(running_max, p)

    # R2 — oversized / over max loss
    if t["entry_cost"] > MAX_POSITION:
        flags.append(f"OVERSIZED(${t['entry_cost']:,.0f})")
    if t["pnl"] < -MAX_LOSS:
        flags.append(f"LOSS>${MAX_LOSS:,.0f}(${t['pnl']:,.0f})")

    # R3 — stop not honored (loss worse than -25% of entry)
    if t["entry_cost"] > 0 and t["pnl"] < -STOP_PCT * t["entry_cost"]:
        pct = 100.0 * t["pnl"] / t["entry_cost"]
        flags.append(f"STOP-BLOWN({pct:.0f}%)")

    # R4 — held overnight
    if len(t["dates"]) > 1:
        flags.append(f"HELD-{len(t['dates'])}DAYS")

    # R6 — entered in first 15 minutes
    fo = t["first_open"]
    if fo and (fo.hour, fo.minute) < FIRST_15_CUTOFF:
        flags.append(f"OPEN-CHASE({fo:%H:%M})")

    return flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="start date YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=30, help="lookback if --since omitted")
    ap.add_argument("--all", action="store_true", help="show clean trades too")
    args = ap.parse_args()

    load_dotenv()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")

    since = args.since or (date.today() - timedelta(days=args.days)).isoformat()
    fills = fetch_fills(url, key, since)
    trades = build_trades(fills)

    print(f"\n  DISCIPLINE SCORECARD  ·  since {since}  ·  {len(trades)} closed trades\n")
    print("  Rules: R1 no adding · R2 <=$4k/-$1k · R3 -25% stop · R4 no overnight · R6 no first-15min")
    print("  " + "-" * 72)

    violations = 0
    dirty_pnl = 0.0
    for t in trades:
        flags = check(t)
        if flags:
            violations += 1
            dirty_pnl += t["pnl"]
        elif not args.all:
            continue
        d = t["first_open"].strftime("%b %d") if t["first_open"] else "??"
        tag = f"{t['ul']} {t['strike']:g}{t['pc']}"
        pnl = f"${t['pnl']:+,.0f}"
        mark = "  ".join(f"X {f}" for f in flags) if flags else "OK clean"
        print(f"  {d:>6}  {tag:<16} {pnl:>10}   {mark}")

    print("  " + "-" * 72)
    total_pnl = sum(t["pnl"] for t in trades)
    print(f"  {violations}/{len(trades)} trades broke a rule."
          f"  Rule-breaking P&L: ${dirty_pnl:,.0f}  |  Total: ${total_pnl:,.0f}")
    if trades:
        clean = [t for t in trades if not check(t)]
        clean_pnl = sum(t["pnl"] for t in clean)
        print(f"  Clean trades only: {len(clean)}/{len(trades)}  ·  P&L ${clean_pnl:,.0f}"
              "   <- this is your real edge\n")


if __name__ == "__main__":
    main()
