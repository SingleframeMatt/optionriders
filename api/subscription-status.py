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
ADMIN_EMAILS = {
    value.strip().lower()
    for value in os.environ.get("ACCESS_ADMIN_EMAILS", "").split(",")
    if value.strip()
}

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
        if self.path.split("?", 1)[0].rstrip("/") == "/api/script-access":
            self._get_script_access()
            return

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

    def do_PATCH(self):
        if self.path.split("?", 1)[0].rstrip("/") != "/api/script-access":
            self._respond(405, {"error": "Method not allowed"})
            return
        if not self._is_admin():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._respond(400, {"error": "Invalid JSON"})
            return

        request_id = str(data.get("id", "")).strip()
        status = str(data.get("grantStatus", "")).strip()
        if not request_id or status not in {"granted", "removed", "pending"}:
            self._respond(400, {"error": "Invalid access update"})
            return

        response = _req.patch(
            f"{SUPABASE_URL}/rest/v1/script_access_requests",
            headers={**_supabase_headers(), "Prefer": "return=representation"},
            params={"id": f"eq.{request_id}"},
            json={"grant_status": status},
            timeout=10,
        )
        if response.status_code not in {200, 204}:
            self._respond(502, {"error": "Could not update access"})
            return
        self._respond(200, {"ok": True})

    def _get_script_access(self):
        if not self._is_admin():
            return
        response = _req.get(
            f"{SUPABASE_URL}/rest/v1/script_access_requests",
            headers=_supabase_headers(),
            params={
                "select": "id,email,tradingview_username,plan,entitlement_status,grant_status,current_period_ends_at,created_at,updated_at",
                "order": "created_at.desc",
            },
            timeout=10,
        )
        if response.status_code != 200:
            self._respond(502, {"error": "Could not load the access queue"})
            return
        rows = response.json() or []
        for row in rows:
            active = row.get("entitlement_status") in {"active", "trialing"}
            granted = row.get("grant_status") == "granted"
            row["action"] = "grant" if active and not granted else ("remove" if not active and granted else "none")
        self._respond(200, {"requests": rows})

    def _is_admin(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._respond(401, {"error": "Sign in first"})
            return False
        response = _req.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": auth},
            timeout=8,
        )
        email = (response.json().get("email", "") if response.status_code == 200 else "").lower()
        if not ADMIN_EMAILS or email not in ADMIN_EMAILS:
            self._respond(403, {"error": "Owner access required"})
            return False
        return True

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
        self.send_header("Access-Control-Allow-Methods", "GET, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _cors_preflight(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def log_message(self, *_args):
        pass
