"""
POST /api/stripe-portal
Requires: Authorization: Bearer <supabase_access_token>

Creates a Stripe Billing Portal session so authenticated users can
manage their subscription (cancel, update payment method, etc.).
Returns { url } for the frontend to redirect to.
"""

import json
import os

import requests as _req
import stripe
from http.server import BaseHTTPRequestHandler

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8125")


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._cors_preflight()

    def do_POST(self):
        # --- 1. Verify Supabase session ---
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._respond(401, {"error": "Unauthorized"})
            return

        token = auth_header[7:]
        user_resp = _req.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=8,
        )
        if user_resp.status_code != 200:
            self._respond(401, {"error": "Invalid or expired session"})
            return

        user_id = user_resp.json().get("id", "")

        # --- 2. Fetch Stripe customer ID from Supabase ---
        sub_resp = _req.get(
            f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
            headers=_supabase_headers(),
            params={"user_id": f"eq.{user_id}", "limit": "1"},
            timeout=8,
        )
        rows = sub_resp.json() if sub_resp.status_code == 200 else []
        customer_id = rows[0].get("stripe_customer_id") if rows else None

        if not customer_id:
            self._respond(400, {"error": "No billing record found for this account"})
            return

        # --- 3. Create Billing Portal session ---
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_URL}/",
        )

        self._respond(200, {"url": portal.url})

    # ------------------------------------------------------------------
    def _respond(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _cors_preflight(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def log_message(self, *_args):
        pass
