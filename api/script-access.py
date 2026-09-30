"""Owner-only TradingView bundle access queue."""

import json
import os
from http.server import BaseHTTPRequestHandler

import requests as _req

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ADMIN_EMAILS = {
    value.strip().lower()
    for value in os.environ.get("ACCESS_ADMIN_EMAILS", "").split(",")
    if value.strip()
}


def _service_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if not self._is_admin():
            return
        response = _req.get(
            f"{SUPABASE_URL}/rest/v1/script_access_requests",
            headers=_service_headers(),
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

    def do_PATCH(self):
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
            headers={**_service_headers(), "Prefer": "return=representation"},
            params={"id": f"eq.{request_id}"},
            json={"grant_status": status},
            timeout=10,
        )
        if response.status_code not in {200, 204}:
            self._respond(502, {"error": "Could not update access"})
            return
        self._respond(200, {"ok": True})

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

    def log_message(self, *_args):
        pass
