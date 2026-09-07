#!/usr/bin/env python3
"""
discipline_alert.py — same-day discipline watchdog.

Syncs the local journal DB from IBKR, checks today's closed round-trips
against the locked rules (see memory/feedback_trading_rules.md), and fires a
macOS notification the moment one breaks — instead of finding out in a
review three months later. Also fires a one-time "target hit, consider
stopping" notification once today's CLEAN pnl clears the daily goal, since
the goal is ~GBP1k/clean-day, not a home run.

Meant to run on a timer during market hours (see
com.optionriders.disciplinealert.plist) — it no-ops silently outside
Mon-Fri 14:30-21:00 Lisbon so it's safe to schedule every 15 min all day.

Usage:
  .venv/bin/python discipline_alert.py            # normal run (used by launchd)
  .venv/bin/python discipline_alert.py --force     # skip the market-hours gate
  .venv/bin/python discipline_alert.py --no-sync   # skip the IBKR sync (use local db as-is)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
import discipline_check as dc
import trade_journal as tj

STATE_FILE = Path(__file__).parent / ".discipline_alert_state.json"
LISBON = ZoneInfo("Europe/Lisbon")

# Same caps as TWS Precautionary Settings and the sizing calculator — keep these three in sync.
MAX_POSITION_GBP = 2900.0
MAX_LOSS_GBP = 730.0
STOP_PCT = 0.25
FIRST_15_CUTOFF = (9, 45)  # ET, matches the underlying exchange clock in fill timestamps
ADD_DOWN_TRIGGER = 0.98
DAILY_TARGET_GBP = 1000.0


def in_market_hours(now: datetime) -> bool:
    local = now.astimezone(LISBON)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return 14 * 60 + 30 <= minutes <= 21 * 60


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"seen_trades": [], "target_hit_date": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def notify(title: str, message: str, sound: str = "Basso") -> None:
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)} sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"[{title}] {message}")


def rate_of(fill: dict) -> float:
    fx = fill.get("fx_rate_to_base")
    return fx if fx else 1.0


def build_trades_gbp(fills: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in fills:
        key = (r.get("underlying") or r.get("symbol"), r.get("put_call"), r.get("strike"), r.get("expiry"))
        groups[key].append(r)

    trades = []
    for (ul, pc, strike, expiry), rows in groups.items():
        rows.sort(key=lambda r: r.get("datetime") or "")
        opens = [r for r in rows if (r.get("open_close") or "").upper() == "O"]
        closes = [r for r in rows if (r.get("open_close") or "").upper() == "C"]
        if not opens or not closes:
            continue
        entry_cost = sum(abs(dc._f(r["quantity"])) * dc._f(r["trade_price"]) * (dc._f(r["multiplier"]) or 100.0) * rate_of(r) for r in opens)
        pnl = sum(dc._f(r.get("realized_pnl")) * rate_of(r) for r in closes)
        open_dts = [d for d in (dc._parse_dt(r.get("datetime")) for r in opens) if d]
        close_dts = [d for d in (dc._parse_dt(r.get("datetime")) for r in closes) if d]
        open_prices = [dc._f(r["trade_price"]) * rate_of(r) for r in opens]
        dates = sorted({r.get("trade_date") for r in rows if r.get("trade_date")})
        trades.append({
            "key": f"{ul}|{pc}|{strike}|{expiry}|{min(open_dts) if open_dts else ''}",
            "ul": ul, "pc": pc, "strike": strike, "expiry": expiry,
            "entry_cost": entry_cost, "pnl": pnl,
            "first_open": min(open_dts) if open_dts else None,
            "open_prices": open_prices, "n_opens": len(opens), "dates": dates,
        })
    return trades


def check_gbp(t: dict) -> list[str]:
    flags = []
    prices = t["open_prices"]
    if t["n_opens"] > 1:
        running_max = prices[0]
        for p in prices[1:]:
            if p <= running_max * ADD_DOWN_TRIGGER:
                flags.append("ADDED-DOWN"); break
            running_max = max(running_max, p)
    if t["entry_cost"] > MAX_POSITION_GBP:
        flags.append(f"OVERSIZED(£{t['entry_cost']:,.0f})")
    if t["pnl"] < -MAX_LOSS_GBP:
        flags.append(f"LOSS>£{MAX_LOSS_GBP:,.0f}(£{t['pnl']:,.0f})")
    if t["entry_cost"] > 0 and t["pnl"] < -STOP_PCT * t["entry_cost"]:
        flags.append(f"STOP-BLOWN({100.0 * t['pnl'] / t['entry_cost']:.0f}%)")
    if len(t["dates"]) > 1:
        flags.append(f"HELD-{len(t['dates'])}DAYS")
    fo = t["first_open"]
    if fo and (fo.hour, fo.minute) < FIRST_15_CUTOFF:
        flags.append(f"OPEN-CHASE({fo:%H:%M})")
    return flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="skip the market-hours gate")
    ap.add_argument("--no-sync", action="store_true", help="skip the IBKR resync")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    if not args.force and not in_market_hours(now):
        return

    dc.load_dotenv(str(Path(__file__).parent / ".env"))

    if not args.no_sync:
        result = tj.sync_from_ibkr()
        if not result.get("ok"):
            notify("Discipline alert — sync failed", str(result.get("error", "unknown error")), sound="Basso")
            return

    today = now.astimezone(LISBON).date().isoformat()
    rows = tj.list_fills({"from": today, "to": today}, limit=5000)
    fills = [r for r in rows if r.get("put_call")]
    if not fills:
        return

    trades = build_trades_gbp(fills)
    state = load_state()
    seen = set(state.get("seen_trades", []))

    new_violations = []
    for t in trades:
        if t["key"] in seen:
            continue
        flags = check_gbp(t)
        seen.add(t["key"])
        if flags:
            new_violations.append((t, flags))

    for t, flags in new_violations:
        tag = f"{t['ul']} {t['strike']:g}{t['pc']}"
        notify(
            f"Rule broken — {tag}",
            f"£{t['pnl']:+,.0f}  ·  {', '.join(flags)}",
        )

    clean_pnl_today = sum(t["pnl"] for t in trades if not check_gbp(t))
    if clean_pnl_today >= DAILY_TARGET_GBP and state.get("target_hit_date") != today:
        notify(
            "Target hit — consider stopping",
            f"Clean P&L today: £{clean_pnl_today:,.0f}. The goal is ~£1k/day. Nothing wrong with walking away now.",
            sound="Glass",
        )
        state["target_hit_date"] = today

    state["seen_trades"] = list(seen)[-2000:]  # cap growth
    save_state(state)


if __name__ == "__main__":
    main()
