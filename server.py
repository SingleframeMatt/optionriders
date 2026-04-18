#!/usr/bin/env python3

import json
import os
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import importlib.util

from alpha_vantage import fetch_alpha_vantage_data
from barchart_proxy import CACHE_TTL_SECONDS, fetch_options_activity
from market_data import fetch_market_data
from top_trade_today import fetch_top_trade_today
from top_watch import fetch_top_watch
from bot_core import bot as _bot
from scalp_bot_core import bot as _scalp_bot
import trade_journal


def _load_api_handler(name: str):
    """
    Load a Vercel-style handler class from api/<name>.py.
    Filenames may contain dashes, which are not valid Python identifiers,
    so we use importlib rather than a regular import.
    """
    path = Path(__file__).parent / "api" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


def load_dotenv(dotenv_path=".env"):
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
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


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/?"}:
            self.path = "/index.html"
            return super().do_GET()
        if self.path.startswith("/api/options-flow"):
            self.handle_options_flow()
            return
        if self.path.startswith("/api/market-data"):
            self.handle_market_data()
            return
        if self.path.startswith("/api/public-config"):
            self.handle_public_config()
            return
        if self.path.startswith("/api/top-watch"):
            self.handle_top_watch()
            return
        if self.path.startswith("/api/top-trade-today"):
            self.handle_top_trade_today()
            return
        if self.path.startswith("/api/alpha-vantage"):
            self.handle_alpha_vantage()
            return
        if self.path.startswith("/api/bot-status"):
            self.handle_bot_status()
            return
        if self.path.startswith("/api/scalp-bot-status"):
            self.handle_scalp_bot_status()
            return
        if self.path.startswith("/api/journal/"):
            self.handle_journal_get()
            return
        # Subscription / billing endpoints
        if self.path.startswith("/api/subscription-status"):
            self._delegate("subscription-status", "do_GET")
            return
        super().do_GET()

    def do_OPTIONS(self):
        # CORS pre-flight for subscription/billing endpoints
        if any(self.path.startswith(p) for p in (
            "/api/subscription-status",
            "/api/stripe-checkout",
            "/api/stripe-portal",
        )):
            self._delegate(self.path.split("/api/")[1].split("?")[0], "do_OPTIONS")
            return
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/api/bot-control"):
            self.handle_bot_control()
            return
        if self.path.startswith("/api/scalp-bot-control"):
            self.handle_scalp_bot_control()
            return
        if self.path.startswith("/api/journal/"):
            self.handle_journal_post()
            return
        # Subscription / billing endpoints
        if self.path.startswith("/api/stripe-checkout"):
            self._delegate("stripe-checkout", "do_POST")
            return
        if self.path.startswith("/api/stripe-webhook"):
            self._delegate("stripe-webhook", "do_POST")
            return
        if self.path.startswith("/api/stripe-portal"):
            self._delegate("stripe-portal", "do_POST")
            return
        self.send_response(404)
        self.end_headers()

    def _delegate(self, api_name: str, method: str):
        """
        Instantiate a Vercel-style api/<api_name>.py handler and call
        its do_GET / do_POST / do_OPTIONS method using this connection.
        """
        cls = _load_api_handler(api_name)
        h = cls.__new__(cls)
        h.request = self.request
        h.client_address = self.client_address
        h.server = self.server
        h.rfile = self.rfile
        h.wfile = self.wfile
        h.headers = self.headers
        h.command = self.command
        h.path = self.path
        getattr(h, method)()

    def handle_bot_status(self):
        body = json.dumps(_bot.get_state()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_scalp_bot_status(self):
        body = json.dumps(_scalp_bot.get_state()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_bot_control(self):
        try:
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else {}
            action  = payload.get("action", "")
            if action == "start":
                result = _bot.start()
            elif action == "stop":
                result = _bot.stop()
            else:
                result = {"ok": False, "message": f"Unknown action: {action}"}
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"ok": False, "message": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_scalp_bot_control(self):
        try:
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else {}
            action  = payload.get("action", "")
            if action == "start":
                result = _scalp_bot.start()
            elif action == "stop":
                result = _scalp_bot.stop()
            else:
                result = {"ok": False, "message": f"Unknown action: {action}"}
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"ok": False, "message": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_options_flow(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            tickers = []
            for value in params.get("tickers", []):
                tickers.extend(part.strip() for part in value.split(","))
            payload = fetch_options_activity(extra_symbols=tickers)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_market_data(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            tickers = []
            for value in params.get("tickers", []):
                tickers.extend(part.strip() for part in value.split(","))
            payload = fetch_market_data(extra_tickers=tickers)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_top_watch(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            force_refresh = params.get("fresh", ["0"])[0].lower() in {"1", "true", "yes"}
            payload = fetch_top_watch(force_refresh=force_refresh)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_top_trade_today(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            force_refresh = params.get("fresh", ["0"])[0].lower() in {"1", "true", "yes"}
            payload = fetch_top_trade_today(force_refresh=force_refresh)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def handle_alpha_vantage(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            symbols = []
            for value in params.get("symbols", []):
                symbols.extend(part.strip().upper() for part in value.split(",") if part.strip())
            mode = params.get("mode", ["quote"])[0].lower()
            payload = fetch_alpha_vantage_data(symbols=symbols, mode=mode)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _json(self, payload, status=200, cache="no-store"):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _journal_user_id(self):
        """
        Verify the caller's Supabase access token and return their user_id.
        Falls back to a dev user when running locally without auth.
        """
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            # Local dev fallback — single-user mode.
            return os.environ.get("LOCAL_DEV_USER_ID", "local")
        token = auth[7:]
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        anon_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
        if not supabase_url or not anon_key:
            return os.environ.get("LOCAL_DEV_USER_ID", "local")
        try:
            req = urllib.request.Request(
                f"{supabase_url}/auth/v1/user",
                headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())
                return data.get("id") or None
        except Exception:
            return None

    def _journal_filters(self, user_id=None):
        params = parse_qs(urlparse(self.path).query)
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        for key in ("from", "to", "symbol", "asset_class"):
            values = params.get(key)
            if values and values[0]:
                filters[key] = values[0].strip().upper() if key == "symbol" else values[0].strip()
        return filters

    def handle_journal_get(self):
        try:
            user_id = self._journal_user_id()
            if user_id is None:
                self._json({"error": "unauthorized"}, status=401); return
            path = urlparse(self.path).path
            filters = self._journal_filters(user_id=user_id)
            if path == "/api/journal/stats":
                self._json(trade_journal.compute_stats(filters))
            elif path == "/api/journal/fills":
                params = parse_qs(urlparse(self.path).query)
                limit = int(params.get("limit", ["500"])[0])
                self._json(trade_journal.list_fills(filters, limit=limit))
            elif path == "/api/journal/equity":
                self._json(trade_journal.equity_curve(filters))
            elif path == "/api/journal/last-sync":
                self._json(trade_journal.last_sync())
            elif path == "/api/journal/day":
                params = parse_qs(urlparse(self.path).query)
                date = (params.get("date", [""])[0] or "").strip()
                if not date:
                    self._json({"error": "missing date"}, status=400)
                else:
                    self._json(trade_journal.day_detail(date, user_id=user_id))
            elif path == "/api/journal/calendar":
                params = parse_qs(urlparse(self.path).query)
                now = datetime.now()
                year = int(params.get("year", [str(now.year)])[0])
                month = int(params.get("month", [str(now.month)])[0])
                self._json(trade_journal.calendar_month(year, month, filters))
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._json({"error": str(exc)}, status=500)

    def handle_journal_post(self):
        try:
            user_id = self._journal_user_id()
            if user_id is None:
                self._json({"error": "unauthorized"}, status=401); return
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            if path == "/api/journal/import-flex":
                text = body.decode("utf-8", errors="replace")
                # Accept either raw CSV text or JSON {"csv": "..."}
                if text.lstrip().startswith("{") and not text.lstrip().startswith("<"):
                    try:
                        text = json.loads(text).get("csv", text)
                    except json.JSONDecodeError:
                        pass
                result = trade_journal.import_flex_report(text, user_id=user_id)
                self._json(result)
            elif path == "/api/journal/sync":
                token = query_id = None
                if body:
                    try:
                        payload = json.loads(body)
                        token = payload.get("token")
                        query_id = payload.get("query_id")
                    except json.JSONDecodeError:
                        pass
                self._json(trade_journal.sync_from_ibkr(
                    token=token, query_id=query_id, user_id=user_id,
                ))
            elif path == "/api/journal/clear":
                self._json(trade_journal.clear_all(user_id=user_id))
            else:
                self._json({"error": "not found"}, status=404)
        except Exception as exc:
            self._json({"error": str(exc)}, status=500)

    def handle_public_config(self):
        body = json.dumps({
            "supabaseUrl": os.environ.get("SUPABASE_URL", ""),
            "supabaseAnonKey": os.environ.get("SUPABASE_ANON_KEY", ""),
            "googleClientId": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "stripePaymentLink": os.environ.get("STRIPE_PAYMENT_LINK", ""),
            "tradingViewProductName": os.environ.get("TRADINGVIEW_PRODUCT_NAME", "Option Riders TradingView Script"),
            "tradingViewProductDescription": os.environ.get(
                "TRADINGVIEW_PRODUCT_DESCRIPTION",
                "Private TradingView tool for traders who want the same Option Riders signal framework directly on-chart.",
            ),
            "tradingViewProductPriceLabel": os.environ.get("TRADINGVIEW_PRODUCT_PRICE_LABEL", ""),
            "tradingViewMonthlyLink": os.environ.get("TRADINGVIEW_MONTHLY_LINK", ""),
            "tradingViewMonthlyName": os.environ.get("TRADINGVIEW_MONTHLY_NAME", "Monthly Access"),
            "tradingViewMonthlyPrice": os.environ.get("TRADINGVIEW_MONTHLY_PRICE", "$0/mo"),
            "tradingViewMonthlyDescription": os.environ.get(
                "TRADINGVIEW_MONTHLY_DESCRIPTION",
                "Recurring access to the Option Riders TradingView script.",
            ),
            "tradingViewLifetimeLink": os.environ.get("TRADINGVIEW_LIFETIME_LINK", ""),
            "tradingViewLifetimeName": os.environ.get("TRADINGVIEW_LIFETIME_NAME", "Lifetime Access"),
            "tradingViewLifetimePrice": os.environ.get("TRADINGVIEW_LIFETIME_PRICE", "$0 one-time"),
            "tradingViewLifetimeDescription": os.environ.get(
                "TRADINGVIEW_LIFETIME_DESCRIPTION",
                "One payment for lifetime access to the script.",
            ),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    load_dotenv()
    server = ThreadingHTTPServer(("127.0.0.1", 8125), DashboardHandler)
    print("Serving Option Riders at http://127.0.0.1:8125")
    server.serve_forever()


if __name__ == "__main__":
    main()
