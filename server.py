#!/usr/bin/env python3

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from alpha_vantage import fetch_alpha_vantage_data
from barchart_proxy import CACHE_TTL_SECONDS, fetch_options_activity
from market_data import fetch_market_data
from top_watch import fetch_top_watch


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
            self.path = "/landing.html"
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
        if self.path.startswith("/api/alpha-vantage"):
            self.handle_alpha_vantage()
            return
        super().do_GET()

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

    def handle_public_config(self):
        body = json.dumps({
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
