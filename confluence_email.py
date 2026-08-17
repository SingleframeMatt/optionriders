#!/usr/bin/env python3
"""
confluence_email.py — branded HTML email for the daily confluence scan.

Renders confluence_scan results into an OptionRiders-branded, dark, email-safe
HTML message (table layout, all-inline styles, single committed dark look that
matches style.css). Two entry points:

    render_body(rows, ...)      -> the self-contained content block (inline
                                   styles only; safe to drop into a preview or
                                   an artifact skeleton)
    render_document(rows, ...)  -> a full <!doctype html> email document

`rows` is a list of dicts (or Confluence objects) with:
    ticker, price, weekly, daily, intra, total(0-10),
    bias ("Bullish"/"Neutral"/"Bearish"), direction ("LONG"/"SHORT"/"—"),
    adx, regime ("trend"/"weak"/"chop")

    python confluence_email.py            # writes a sample to output/
"""
from __future__ import annotations

import datetime as _dt
import html as _html

# ── Brand tokens (mirrors style.css) ─────────────────────────────────────────
BG_DEEP   = "#030508"
BG_CARD   = "#0a0d18"
CARD_BG   = "#0b0f1c"
SEG_EMPTY = "#161b2b"
BORDER    = "rgba(255,255,255,0.08)"
GREEN     = "#00ff88"
RED       = "#ff4444"
AMBER     = "#ffaa00"
GOLD      = "#ffd700"
CYAN      = "#00d4ff"
T_PRIMARY = "#e8e8f0"
T_SECOND  = "#9898b0"
T_BRIGHT  = "#ffffff"
MONO = "'JetBrains Mono','SFMono-Regular',Menlo,Consolas,monospace"
SANS = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

DASHBOARD_URL = "https://optionriders.com"
LOGO_URL = "https://optionriders.com/assets/optionriders-horse-transparent.png"


def _as_dict(r) -> dict:
    if isinstance(r, dict):
        return r
    return {
        "ticker": getattr(r, "ticker", ""), "price": getattr(r, "price", 0.0),
        "weekly": getattr(r, "weekly", 0), "daily": getattr(r, "daily", 0),
        "intra": getattr(r, "intra", 0), "total": getattr(r, "total", 0),
        "bias": getattr(r, "bias", "Neutral"), "direction": getattr(r, "direction", "—"),
        "adx": getattr(r, "adx", 0.0), "regime": getattr(r, "regime", "chop"),
        "error": getattr(r, "error", None),
    }


def _bias_color(bias: str) -> str:
    return {"Bullish": GREEN, "Bearish": RED}.get(bias, AMBER)


def _regime_color(regime: str) -> str:
    return {"trend": GREEN, "weak": AMBER}.get(regime, RED)


def _meter(total: int, color: str) -> str:
    """10-segment confluence gauge built from a table (email-safe)."""
    cells = []
    for i in range(10):
        on = i < total
        bg = color if on else SEG_EMPTY
        # subtle glow only on the leading lit segment
        cells.append(
            f'<td width="9" height="7" style="background:{bg};'
            f'border-radius:2px;font-size:0;line-height:0;">&nbsp;</td>'
            '<td width="3" style="font-size:0;line-height:0;">&nbsp;</td>'
        )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        + "".join(cells) + "</tr></table>"
    )


def _pill(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f'background:rgba(255,255,255,0.04);border:1px solid {color};color:{color};'
        f'font-family:{MONO};font-size:11px;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;">{_html.escape(text)}</span>'
    )


def _row_card(r: dict, top: bool) -> str:
    d = _as_dict(r)
    if d.get("error"):
        return (
            f'<tr><td style="padding:10px 20px;font-family:{MONO};font-size:12px;'
            f'color:{T_SECOND};">{_html.escape(d["ticker"])} — data unavailable</td></tr>'
        )
    bias_c = _bias_color(d["bias"])
    reg_c = _regime_color(d["regime"])
    dir_txt = {"LONG": "LONG", "SHORT": "SHORT"}.get(d["direction"], "NEUTRAL")
    dir_c = GREEN if d["direction"] == "LONG" else RED if d["direction"] == "SHORT" else T_SECOND
    ring = f"2px solid {GOLD}" if top else f"1px solid {BORDER}"
    crown = (f'<span style="color:{GOLD};font-family:{MONO};font-size:10px;'
             f'font-weight:700;letter-spacing:0.08em;">★ TOP CONVICTION</span><br>') if top else ""

    return f"""
    <tr><td style="padding:0 0 12px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:{CARD_BG};border:{ring};border-radius:12px;">
        <tr>
          <!-- left: ticker + price -->
          <td width="150" valign="top" style="padding:16px 18px;">
            {crown}
            <div style="font-family:{MONO};font-size:23px;font-weight:700;color:{T_BRIGHT};letter-spacing:0.01em;line-height:1.1;">{_html.escape(d["ticker"])}</div>
            <div style="font-family:{MONO};font-size:13px;color:{T_SECOND};margin-top:3px;">${d["price"]:,.2f}</div>
            <div style="margin-top:10px;">
              <span style="display:inline-block;padding:3px 9px;border-radius:6px;background:rgba(255,255,255,0.03);border:1px solid {reg_c};color:{reg_c};font-family:{MONO};font-size:10px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;">{_html.escape(d["regime"])} · adx {d["adx"]:.0f}</span>
            </div>
          </td>
          <!-- right: score + meter + breakdown -->
          <td valign="top" style="padding:16px 18px;border-left:1px solid {BORDER};">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family:{MONO};font-size:12px;color:{T_SECOND};letter-spacing:0.05em;text-transform:uppercase;">Confluence</td>
                <td align="right">{_pill(dir_txt, dir_c)}</td>
              </tr>
            </table>
            <div style="margin:8px 0 10px 0;">
              <span style="font-family:{MONO};font-size:26px;font-weight:700;color:{bias_c};">{d["total"]}</span><span style="font-family:{MONO};font-size:15px;color:{T_SECOND};">/10</span>
            </div>
            <div style="margin-bottom:12px;">{_meter(d["total"], bias_c)}</div>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-family:{MONO};font-size:11px;color:{T_SECOND};padding-right:14px;">WEEKLY <span style="color:{T_PRIMARY};">{d["weekly"]}/3</span></td>
                <td style="font-family:{MONO};font-size:11px;color:{T_SECOND};padding-right:14px;">DAILY <span style="color:{T_PRIMARY};">{d["daily"]}/4</span></td>
                <td style="font-family:{MONO};font-size:11px;color:{T_SECOND};">INTRA <span style="color:{T_PRIMARY};">{d["intra"]}/3</span></td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td></tr>"""


def render_body(rows, date_str: str | None = None,
                dashboard_url: str = DASHBOARD_URL) -> str:
    """Self-contained content block (inline styles only)."""
    date_str = date_str or _dt.date.today().strftime("%A, %d %B %Y")
    clean = [_as_dict(r) for r in rows]
    # Strongest conviction first (distance from neutral 5), then total.
    ranked = sorted(clean, key=lambda r: (-abs((r.get("total") or 5) - 5),
                                          -(r.get("total") or 0)))
    top_ticker = ranked[0]["ticker"] if ranked else None
    cards = "".join(_row_card(r, top=(r["ticker"] == top_ticker and not r.get("error")))
                    for r in ranked)

    n_long = sum(1 for r in clean if r.get("direction") == "LONG" and r.get("regime") != "chop")
    n_short = sum(1 for r in clean if r.get("direction") == "SHORT" and r.get("regime") != "chop")

    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{BG_DEEP};margin:0;padding:0;">
<tr><td align="center" style="padding:28px 14px;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:{BG_CARD};border:1px solid {BORDER};border-radius:18px;overflow:hidden;">

    <!-- header -->
    <tr><td style="padding:26px 26px 18px 26px;border-bottom:1px solid {BORDER};">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="middle">
          <img src="{LOGO_URL}" width="34" height="34" alt="" style="vertical-align:middle;border:0;display:inline-block;">
          <span style="font-family:{SANS};font-size:19px;font-weight:800;letter-spacing:-0.02em;color:{T_BRIGHT};vertical-align:middle;margin-left:8px;">Option<span style="color:{CYAN};">Riders</span></span>
        </td>
        <td align="right" valign="middle" style="font-family:{MONO};font-size:11px;color:{T_SECOND};letter-spacing:0.05em;text-transform:uppercase;">Confluence Scan</td>
      </tr></table>
      <div style="font-family:{SANS};font-size:13px;color:{T_SECOND};margin-top:14px;">{_html.escape(date_str)} · pre-market</div>
    </td></tr>

    <!-- summary strip -->
    <tr><td style="padding:16px 26px;background:{CARD_BG};border-bottom:1px solid {BORDER};">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="font-family:{MONO};font-size:12px;color:{T_SECOND};padding-right:20px;">LONG BIAS <span style="color:{GREEN};font-weight:700;">{n_long}</span></td>
        <td style="font-family:{MONO};font-size:12px;color:{T_SECOND};padding-right:20px;">SHORT BIAS <span style="color:{RED};font-weight:700;">{n_short}</span></td>
        <td style="font-family:{MONO};font-size:12px;color:{T_SECOND};">SCANNED <span style="color:{T_PRIMARY};font-weight:700;">{len(clean)}</span></td>
      </tr></table>
    </td></tr>

    <!-- ticker cards -->
    <tr><td style="padding:18px 20px 4px 20px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        {cards}
      </table>
    </td></tr>

    <!-- discipline strip -->
    <tr><td style="padding:6px 26px 22px 26px;">
      <div style="font-family:{MONO};font-size:11px;color:{T_SECOND};line-height:1.6;background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.18);border-radius:10px;padding:12px 14px;">
        <span style="color:{CYAN};font-weight:700;">RULES</span>&nbsp; ATM · scanned setup · ≤£4k / £1k-risk · underlying stop · never add · flat 19:00
      </div>
    </td></tr>

    <!-- cta -->
    <tr><td align="center" style="padding:2px 26px 26px 26px;">
      <a href="{dashboard_url}" style="display:inline-block;background:{CYAN};color:{BG_DEEP};font-family:{SANS};font-size:14px;font-weight:700;text-decoration:none;padding:12px 26px;border-radius:10px;">Open the dashboard →</a>
    </td></tr>

    <!-- footer -->
    <tr><td style="padding:18px 26px 24px 26px;border-top:1px solid {BORDER};">
      <div style="font-family:{SANS};font-size:11px;color:{T_SECOND};line-height:1.7;">
        Confluence = weekly (0–3) + daily (0–4) + intraday (0–3) trend factors. Not financial advice — a scan, not a signal. Size every trade to a £1k stop.
      </div>
      <div style="font-family:{SANS};font-size:11px;color:{T_SECOND};margin-top:10px;">
        <a href="{dashboard_url}" style="color:{CYAN};text-decoration:none;">OptionRiders</a> · Trade. Ride. Profit.
      </div>
    </td></tr>

  </table>
</td></tr>
</table>"""


def render_document(rows, date_str: str | None = None,
                    dashboard_url: str = DASHBOARD_URL) -> str:
    """Full email document (use this when actually sending)."""
    body = render_body(rows, date_str, dashboard_url)
    return f"""<!DOCTYPE html>
<html lang="en" style="margin:0;padding:0;">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<title>OptionRiders Confluence Scan</title>
</head>
<body style="margin:0;padding:0;background:{BG_DEEP};">
{body}
</body>
</html>"""


def _sample_rows() -> list[dict]:
    return [
        {"ticker": "NVDA", "price": 226.80, "weekly": 3, "daily": 4, "intra": 2,
         "total": 9, "bias": "Bullish", "direction": "LONG", "adx": 31.2, "regime": "trend"},
        {"ticker": "SNDK", "price": 1658.13, "weekly": 2, "daily": 4, "intra": 2,
         "total": 8, "bias": "Bullish", "direction": "LONG", "adx": 35.4, "regime": "trend"},
        {"ticker": "MU", "price": 979.63, "weekly": 2, "daily": 3, "intra": 2,
         "total": 7, "bias": "Bullish", "direction": "LONG", "adx": 27.1, "regime": "trend"},
        {"ticker": "AMD", "price": 487.50, "weekly": 0, "daily": 1, "intra": 1,
         "total": 2, "bias": "Bearish", "direction": "SHORT", "adx": 29.8, "regime": "trend"},
        {"ticker": "MSFT", "price": 495.40, "weekly": 2, "daily": 3, "intra": 1,
         "total": 6, "bias": "Neutral", "direction": "—", "adx": 22.4, "regime": "weak"},
        {"ticker": "SPY", "price": 772.07, "weekly": 2, "daily": 2, "intra": 1,
         "total": 5, "bias": "Neutral", "direction": "—", "adx": 16.2, "regime": "chop"},
    ]


if __name__ == "__main__":
    import os
    os.makedirs("output", exist_ok=True)
    doc = render_document(_sample_rows())
    path = "output/confluence_email_sample.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Wrote {path}")
