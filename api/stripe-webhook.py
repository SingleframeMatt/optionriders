"""
POST /api/stripe-webhook
No auth header — verified via Stripe-Signature.

Handles subscription lifecycle events from Stripe and syncs the
current status into the dashboard_subscriptions table.

Required Stripe events to forward:
  - checkout.session.completed
  - customer.subscription.created
  - customer.subscription.updated
  - customer.subscription.deleted
"""

import datetime
import json
import os

import requests as _req
import stripe
from http.server import BaseHTTPRequestHandler

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _ts_to_iso(ts):
    """Convert a Unix timestamp (int/None) to ISO-8601 UTC string."""
    if ts:
        return datetime.datetime.utcfromtimestamp(int(ts)).isoformat() + "Z"
    return None


def _upsert_subscription(*, user_id, email, customer_id, sub_id, status,
                          trial_end_ts, period_end_ts):
    """
    Upsert a row into dashboard_subscriptions.
    Conflicts on stripe_subscription_id (set on initial checkout).
    On conflict, updates all mutable columns.
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"
    payload = {
        "user_id": user_id,
        "email": email,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": sub_id,
        "product_key": "dashboard",
        "status": status,
        "trial_ends_at": _ts_to_iso(trial_end_ts),
        "current_period_ends_at": _ts_to_iso(period_end_ts),
        "updated_at": now,
    }
    _req.post(
        f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
        headers={**_supabase_headers(), "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "stripe_subscription_id"},
        json=payload,
        timeout=10,
    )


def _update_status_by_sub_id(sub_id, status):
    """Update only the status (and updated_at) for a known subscription_id."""
    now = datetime.datetime.utcnow().isoformat() + "Z"
    _req.patch(
        f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
        headers={**_supabase_headers(), "Prefer": "return=minimal"},
        params={"stripe_subscription_id": f"eq.{sub_id}"},
        json={"status": status, "updated_at": now},
        timeout=10,
    )


def _lookup_user_id_by_customer(customer_id):
    """Find supabase user_id from an existing subscription row."""
    resp = _req.get(
        f"{SUPABASE_URL}/rest/v1/dashboard_subscriptions",
        headers=_supabase_headers(),
        params={"stripe_customer_id": f"eq.{customer_id}", "limit": "1"},
        timeout=8,
    )
    rows = resp.json() if resp.status_code == 200 else []
    return rows[0].get("user_id", "") if rows else ""


def _sync_subscription(sub, user_id="", email=""):
    """Pull the canonical fields off a Stripe Subscription object and upsert."""
    customer_id = sub.get("customer", "")
    sub_id = sub.get("id", "")
    status = sub.get("status", "")
    trial_end = sub.get("trial_end")
    period_end = sub.get("current_period_end")

    # Resolve user_id when it wasn't passed in (e.g., subscription.updated events)
    if not user_id:
        # Try metadata first (set at Checkout time)
        user_id = sub.get("metadata", {}).get("supabase_user_id", "")
    if not user_id:
        user_id = _lookup_user_id_by_customer(customer_id)
    if not user_id:
        return  # Cannot associate — skip

    # Resolve email if not passed in
    if not email:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            email = customer.get("email", "")
        except Exception:
            email = ""

    _upsert_subscription(
        user_id=user_id,
        email=email,
        customer_id=customer_id,
        sub_id=sub_id,
        status=status,
        trial_end_ts=trial_end,
        period_end_ts=period_end,
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # --- 1. Read raw body (required for signature verification) ---
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        sig_header = self.headers.get("Stripe-Signature", "")

        # --- 2. Verify the webhook signature ---
        try:
            event = stripe.Webhook.construct_event(raw_body, sig_header, WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            self._respond(400, {"error": "Invalid webhook signature"})
            return

        event_type = event["type"]
        obj = event["data"]["object"]

        # --- 3. Dispatch ---
        if event_type == "checkout.session.completed":
            self._handle_checkout_completed(obj)

        elif event_type in ("customer.subscription.created",
                            "customer.subscription.updated"):
            _sync_subscription(obj)

        elif event_type == "customer.subscription.deleted":
            # Mark canceled — keeps the row for audit; status blocks access.
            _update_status_by_sub_id(obj.get("id", ""), "canceled")

        self._respond(200, {"received": True})

    def _handle_checkout_completed(self, session):
        """On a completed subscription checkout, fetch the full sub and sync it."""
        if session.get("mode") != "subscription":
            return  # Not a subscription checkout — ignore

        sub_id = session.get("subscription", "")
        if not sub_id:
            return

        user_id = session.get("metadata", {}).get("supabase_user_id", "")
        email = (session.get("customer_details") or {}).get("email", "")

        try:
            sub = stripe.Subscription.retrieve(sub_id)
        except Exception:
            return

        _sync_subscription(sub, user_id=user_id, email=email)

    # ------------------------------------------------------------------
    def _respond(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass
