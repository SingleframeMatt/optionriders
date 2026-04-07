"""
GET /api/subscription-status
Requires: Authorization: Bearer <supabase_access_token>

Verifies the caller's Supabase session server-side, then returns their
current dashboard subscription status from the database.

Returns:
  { hasAccess: bool, status: str, trialEndsAt: str|null, currentPeriodEndsAt: str|null }
"""

import json
import os

import requests as _req
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Dashboard is accessible for these Stripe subscription statuses only.
VALID_STATUSES = {"trialing", "active"}


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._cors_preflight()

    def do_GET(self):
        # --- 1. Extract and verify the caller's Supabase access token ---
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._respond(401, {"error": "Missing or invalid Authorization header"})
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
        if not user_id:
            self._respond(401, {"error": "Could not resolve user identity"})
            return

        # --- 2. Query the subscription row for this user ---
        sub_resp = _req.get(
            f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
            headers=_supabase_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "product_key": "eq.dashboard",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=8,
        )

        rows = sub_resp.json() if sub_resp.status_code == 200 else []

        if not rows:
            self._respond(200, {"hasAccess": False, "status": "none"})
            return

        sub = rows[0]
        status = sub.get("status", "inactive")
        self._respond(200, {
            "hasAccess": status in VALID_STATUSES,
            "status": status,
            "trialEndsAt": sub.get("trial_ends_at"),
            "currentPeriodEndsAt": sub.get("current_period_ends_at"),
        })

    # ------------------------------------------------------------------
    def _respond(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _cors_preflight(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def log_message(self, *_args):
        pass
