"""
Single Vercel function handling every /api/journal/* route.

Consolidated into one entry point so the whole journal backend counts as
one serverless function instead of nine (Vercel Hobby caps at 12).

The dispatcher reads the `action` path segment (injected via vercel.json
rewrite — /api/journal/<action> → /api/journal.py?action=<action>) and
calls the appropriate function in journal_cloud.py.
"""
import json
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc


def _bearer(h) -> str:
    a = h.headers.get("Authorization", "")
    return a[7:] if a.startswith("Bearer ") else ""


def _query_filters(path: str) -> dict:
    qs = parse_qs(urlparse(path).query)
    out = {}
    for k in ("from", "to", "symbol", "asset_class"):
        v = qs.get(k)
        if v and v[0]:
            out[k] = v[0].strip().upper() if k == "symbol" else v[0].strip()
    return out


def _param(path: str, name: str, default: str = "") -> str:
    qs = parse_qs(urlparse(path).query)
    v = qs.get(name)
    return (v[0].strip() if v and v[0] else default)


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")


def _respond(h, code: int, data):
    body = json.dumps(data).encode("utf-8")
    h.send_response(code); _cors(h)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _read_body(h) -> bytes:
    length = int(h.headers.get("Content-Length", 0))
    return h.rfile.read(length) if length else b""


class handler(BaseHTTPRequestHandler):
    # ------ CORS preflight ------
    def do_OPTIONS(self):
        self.send_response(204); _cors(self); self.end_headers()

    # ------ GET endpoints ------
    def do_GET(self):
        action = _param(self.path, "action", "")
        # Fallback: also honor the literal path (for local dev without rewrites).
        if not action:
            segs = [s for s in urlparse(self.path).path.split("/") if s]
            if len(segs) >= 2 and segs[0] == "api" and segs[1] == "journal":
                action = segs[2] if len(segs) > 2 else ""

        # last-sync is the only GET that doesn't require auth (returns null-ish).
        if action == "last-sync":
            return _respond(self, 200, {"at": None, "result": None})

        token = _bearer(self)
        if not token or not jc.verify_user(token):
            return _respond(self, 401, {"error": "unauthorized"})

        try:
            filters = _query_filters(self.path)
            if action == "stats":
                _respond(self, 200, jc.compute_stats(token, filters))
            elif action == "fills":
                limit = int(_param(self.path, "limit", "500") or 500)
                _respond(self, 200, jc.fetch_user_fills(token, filters, limit=limit))
            elif action == "equity":
                _respond(self, 200, jc.equity_curve(token, filters))
            elif action == "calendar":
                now = datetime.now()
                year = int(_param(self.path, "year", str(now.year)))
                month = int(_param(self.path, "month", str(now.month)))
                _respond(self, 200, jc.calendar_month(token, year, month, filters))
            elif action == "day":
                date = _param(self.path, "date")
                if not date:
                    return _respond(self, 400, {"error": "missing date"})
                _respond(self, 200, jc.day_detail(token, date))
            elif action == "week":
                start = _param(self.path, "start")
                if not start:
                    return _respond(self, 400, {"error": "missing start"})
                _respond(self, 200, jc.week_detail(token, start))
            elif action == "trade-note":
                symbol = _param(self.path, "symbol")
                close_dt = _param(self.path, "close_datetime")
                if not symbol or not close_dt:
                    return _respond(self, 400, {"error": "missing symbol or close_datetime"})
                user_id = jc.verify_user(token)
                _respond(self, 200, jc.get_trade_note(token, user_id, symbol, close_dt))
            elif action == "open-positions":
                _respond(self, 200, jc.current_open_positions(token))
            elif action == "bars":
                symbol = (_param(self.path, "symbol", "") or "").upper().strip()
                date = _param(self.path, "date", "")
                interval = _param(self.path, "interval", "5min") or "5min"
                if not symbol or not date:
                    return _respond(self, 400, {"error": "symbol and date required"})
                _respond(self, 200, jc.intraday_bars(symbol, date, interval))
            else:
                _respond(self, 404, {"error": f"unknown action: {action}"})
        except Exception as exc:
            _respond(self, 500, {"error": str(exc)})

    # ------ POST endpoints ------
    def do_POST(self):
        action = _param(self.path, "action", "")
        if not action:
            segs = [s for s in urlparse(self.path).path.split("/") if s]
            if len(segs) >= 2 and segs[0] == "api" and segs[1] == "journal":
                action = segs[2] if len(segs) > 2 else ""

        token = _bearer(self)
        user_id = jc.verify_user(token)
        if not user_id:
            return _respond(self, 401, {"error": "unauthorized"})

        body = _read_body(self)
        try:
            if action == "sync":
                payload = {}
                if body:
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError:
                        payload = {}
                ibkr_token = (payload.get("token") or "").strip()
                ibkr_qid = (payload.get("query_id") or "").strip()
                diagnose = bool(payload.get("diagnose"))
                if not ibkr_token or not ibkr_qid:
                    return _respond(self, 400, {
                        "ok": False,
                        "error": "Open Settings and paste your IBKR Flex token and query ID.",
                    })
                _respond(self, 200, jc.sync_from_ibkr(token, user_id, ibkr_token, ibkr_qid, diagnose=diagnose))
            elif action == "import-flex":
                text = body.decode("utf-8", errors="replace")
                if text.lstrip().startswith("{") and not text.lstrip().startswith("<"):
                    try:
                        text = json.loads(text).get("csv", text)
                    except json.JSONDecodeError:
                        pass
                rows = jc._parse_flex_and_normalize(text, user_id)
                result = jc.insert_fills(token, user_id, rows)
                _respond(self, 200, {"ok": True, **result,
                                     "format": "xml" if text.lstrip().startswith("<") else "csv"})
            elif action == "clear":
                n = jc.delete_all_user_fills(token, user_id)
                _respond(self, 200, {"ok": True, "deleted": n})
            elif action == "trade-note":
                try:
                    payload = json.loads(body or b"{}")
                except json.JSONDecodeError:
                    payload = {}
                symbol = (payload.get("symbol") or "").strip()
                close_dt = (payload.get("close_datetime") or "").strip()
                body_text = payload.get("body") or ""
                trade_date = payload.get("trade_date") or None
                if not symbol or not close_dt:
                    return _respond(self, 400, {"error": "missing symbol or close_datetime"})
                _respond(self, 200, jc.set_trade_note(
                    token, user_id, symbol, close_dt, body_text, trade_date=trade_date,
                ))
            else:
                _respond(self, 404, {"error": f"unknown action: {action}"})
        except Exception as exc:
            _respond(self, 500, {"ok": False, "error": str(exc)})
