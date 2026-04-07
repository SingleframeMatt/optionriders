#!/usr/bin/env python3
"""
dashboard_server.py — Local Flask server for the main Option Riders dashboard.

Serves:
  GET /                  -> index.html
  GET /api/market-data   -> live market data
  GET /api/options-flow  -> Barchart options activity
  GET /api/top-watch     -> cross-source top watch feed
  GET /api/public-config -> public frontend config
"""

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

HERE = Path(__file__).parent.resolve()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _load_dotenv(dotenv_path: str = ".env"):
    env_file = HERE / dotenv_path
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


_load_dotenv()

from barchart_proxy import fetch_options_activity
from market_data import fetch_market_data
from top_trade_today import fetch_top_trade_today
from top_watch import fetch_top_watch


PORT = int(os.environ.get("DASHBOARD_SERVER_PORT", "8125"))
app = Flask(__name__, static_folder=str(HERE), static_url_path="")


def _public_config():
    return {
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
    }


@app.route("/")
def root():
    return send_from_directory(str(HERE), "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(str(HERE), "index.html")


@app.route("/api/public-config")
def public_config():
    return jsonify(_public_config())


@app.route("/api/market-data")
def market_data():
    try:
        raw_tickers = request.args.get("tickers", "")
        extra_tickers = [part.strip() for part in raw_tickers.split(",") if part.strip()]
        force_refresh = request.args.get("fresh", "0").lower() in {"1", "true", "yes"}
        return jsonify(fetch_market_data(extra_tickers=extra_tickers, force_refresh=force_refresh))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/options-flow")
def options_flow():
    try:
        raw_tickers = request.args.get("tickers", "")
        extra_symbols = [part.strip() for part in raw_tickers.split(",") if part.strip()]
        force_refresh = request.args.get("fresh", "0").lower() in {"1", "true", "yes"}
        return jsonify(fetch_options_activity(extra_symbols=extra_symbols, force_refresh=force_refresh))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/top-watch")
def top_watch():
    try:
        force_refresh = request.args.get("fresh", "0").lower() in {"1", "true", "yes"}
        return jsonify(fetch_top_watch(force_refresh=force_refresh))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/top-trade-today")
def top_trade_today():
    try:
        force_refresh = request.args.get("fresh", "0").lower() in {"1", "true", "yes"}
        return jsonify(fetch_top_trade_today(force_refresh=force_refresh))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(HERE), filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)
