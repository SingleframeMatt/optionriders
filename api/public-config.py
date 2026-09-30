import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            # --- Supabase (safe to expose — anon key only) ---
            "supabaseUrl": os.environ.get("SUPABASE_URL", ""),
            "supabaseAnonKey": os.environ.get("SUPABASE_ANON_KEY", ""),
            # --- Legacy Google client ID (kept for fallback display) ---
            "googleClientId": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "stripePaymentLink": os.environ.get("STRIPE_PAYMENT_LINK", ""),
            "tradingViewProductName": os.environ.get("TRADINGVIEW_PRODUCT_NAME", "OptionRiders TradingView Script Bundle"),
            "tradingViewProductDescription": os.environ.get(
                "TRADINGVIEW_PRODUCT_DESCRIPTION",
                "Both private OptionRiders indicators, including ongoing updates.",
            ),
            "tradingViewProductPriceLabel": os.environ.get("TRADINGVIEW_PRODUCT_PRICE_LABEL", ""),
            "tradingViewMonthlyLink": os.environ.get("TRADINGVIEW_MONTHLY_LINK", ""),
            "tradingViewMonthlyName": os.environ.get("TRADINGVIEW_MONTHLY_NAME", "Monthly Access"),
            "tradingViewMonthlyPrice": os.environ.get("TRADINGVIEW_MONTHLY_PRICE", "$39/month"),
            "tradingViewMonthlyDescription": os.environ.get(
                "TRADINGVIEW_MONTHLY_DESCRIPTION",
                "Monthly access to both OptionRiders TradingView scripts, including ongoing updates.",
            ),
            "tradingViewLifetimeLink": os.environ.get("TRADINGVIEW_LIFETIME_LINK", ""),
            "tradingViewLifetimeName": os.environ.get("TRADINGVIEW_LIFETIME_NAME", "Lifetime Access"),
            "tradingViewLifetimePrice": os.environ.get("TRADINGVIEW_LIFETIME_PRICE", "$400 one-time"),
            "tradingViewLifetimeDescription": os.environ.get(
                "TRADINGVIEW_LIFETIME_DESCRIPTION",
                "One payment for lifetime access to both OptionRiders TradingView scripts.",
            ),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
