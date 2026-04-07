"""
POST /api/stripe-checkout
Requires: Authorization: Bearer <supabase_access_token>

Creates a Stripe Checkout Session for the dashboard subscription,
including a free-trial period. Returns { url } for the frontend
to redirect to.

The Stripe customer is looked up or created so that repeat checkouts
reuse the same customer record.
"""

import datetime
import json
import os

import requests as _req
import stripe
from http.server import BaseHTTPRequestHandler

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DASHBOARD_PRICE_ID = os.environ.get("STRIPE_DASHBOARD_PRICE_ID", "")
DASHBOARD_TRIAL_DAYS = int(os.environ.get("DASHBOARD_TRIAL_DAYS", "7"))
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

        user = user_resp.json()
        user_id = user.get("id", "")
        email = user.get("email", "")

        if not DASHBOARD_PRICE_ID:
            self._respond(500, {"error": "Dashboard price not configured"})
            return

        # --- 2. Find or create a Stripe customer for this user ---
        existing = _req.get(
            f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
            headers=_supabase_headers(),
            params={"user_id": f"eq.{user_id}", "limit": "1"},
            timeout=8,
        ).json() or []

        customer_id = existing[0].get("stripe_customer_id") if existing else None

        if not customer_id:
            customer = stripe.Customer.create(
                email=email,
                metadata={"supabase_user_id": user_id},
            )
            customer_id = customer.id

        # --- 3. Create Checkout Session with trial ---
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": DASHBOARD_PRICE_ID, "quantity": 1}],
            mode="subscription",
            subscription_data={
                "trial_period_days": DASHBOARD_TRIAL_DAYS,
                "metadata": {"supabase_user_id": user_id},
            },
            success_url=f"{APP_URL}/?checkout=success",
            cancel_url=f"{APP_URL}/?checkout=canceled",
            metadata={"supabase_user_id": user_id},
        )

        self._respond(200, {"url": session.url})

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
