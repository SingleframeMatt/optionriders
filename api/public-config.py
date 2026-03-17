import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
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
