"""
POST /api/stripe-webhook
No auth header — verified via Stripe-Signature.

Handles dashboard subscriptions and the two-script TradingView bundle.
Bundle purchases are written to an owner queue keyed by TradingView username.

Required Stripe events to forward:
  - checkout.session.completed
  - customer.subscription.created
  - customer.subscription.updated
  - customer.subscription.deleted
  - charge.refunded
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


def _extract_tradingview_username(session):
    """Return the required custom-field value from a Stripe Payment Link."""
    for field in session.get("custom_fields") or []:
        label = (field.get("label") or {}).get("custom", "").strip().lower()
        if label != "tradingview username (exact)":
            continue
        field_type = field.get("type", "text")
        value = (field.get(field_type) or {}).get("value", "")
        return str(value).strip()
    return ""


def _upsert_script_access(session, *, status="active", period_end_ts=None):
    """Create/update the owner queue for a bundle checkout."""
    username = _extract_tradingview_username(session)
    session_id = session.get("id", "")
    if not username or not session_id:
        return  # Dashboard checkouts do not contain this field.

    mode = session.get("mode", "")
    plan = "monthly" if mode == "subscription" else "lifetime"
    customer_details = session.get("customer_details") or {}
    payload = {
        "stripe_checkout_session_id": session_id,
        "stripe_customer_id": session.get("customer", ""),
        "stripe_subscription_id": session.get("subscription"),
        "stripe_payment_intent_id": session.get("payment_intent"),
        "email": customer_details.get("email", ""),
        "tradingview_username": username,
        "plan": plan,
        "entitlement_status": status,
        "current_period_ends_at": _ts_to_iso(period_end_ts),
    }
    _req.post(
        f"{SUPABASE_URL}/rest/v1/script_access_requests",
        headers={**_supabase_headers(), "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "stripe_checkout_session_id"},
        json=payload,
        timeout=10,
    )


def _update_script_access_by_subscription(sub):
    sub_id = sub.get("id", "")
    if not sub_id:
        return
    _req.patch(
        f"{SUPABASE_URL}/rest/v1/script_access_requests",
        headers={**_supabase_headers(), "Prefer": "return=minimal"},
        params={"stripe_subscription_id": f"eq.{sub_id}"},
        json={
            "entitlement_status": sub.get("status", "inactive"),
            "current_period_ends_at": _ts_to_iso(sub.get("current_period_end")),
        },
        timeout=10,
    )


def _mark_lifetime_refunded(charge):
    payment_intent = charge.get("payment_intent", "")
    if not payment_intent:
        return
    _req.patch(
        f"{SUPABASE_URL}/rest/v1/script_access_requests",
        headers={**_supabase_headers(), "Prefer": "return=minimal"},
        params={"stripe_payment_intent_id": f"eq.{payment_intent}"},
        json={"entitlement_status": "refunded"},
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
        # stripe-python deserializes known event objects (for example a
        # Checkout Session) into StripeObject instances.  The handlers below
        # intentionally use normal dictionary access, so normalize the object
        # before dispatching it.
        to_dict = getattr(obj, "to_dict", None)
        if callable(to_dict):
            obj = to_dict()

        # --- 3. Dispatch ---
        if event_type == "checkout.session.completed":
            self._handle_checkout_completed(obj)

        elif event_type in ("customer.subscription.created",
                            "customer.subscription.updated"):
            _sync_subscription(obj)
            _update_script_access_by_subscription(obj)

        elif event_type == "customer.subscription.deleted":
            # Mark canceled — keeps the row for audit; status blocks access.
            _update_status_by_sub_id(obj.get("id", ""), "canceled")
            _update_script_access_by_subscription({**obj, "status": "canceled"})

        elif event_type == "charge.refunded":
            _mark_lifetime_refunded(obj)

        self._respond(200, {"received": True})

    def _handle_checkout_completed(self, session):
        """Record bundle access and retain the existing dashboard checkout sync."""
        if session.get("mode") == "payment":
            payment_status = session.get("payment_status", "")
            status = "active" if payment_status in {"paid", "no_payment_required"} else "pending_payment"
            _upsert_script_access(session, status=status)
            return

        if session.get("mode") != "subscription":
            return

        sub_id = session.get("subscription", "")
        if not sub_id:
            return

        user_id = session.get("metadata", {}).get("supabase_user_id", "")
        email = (session.get("customer_details") or {}).get("email", "")

        # Payment Link bundle checkouts carry the required TradingView username
        # in the signed event, so no broad Stripe API key is needed to grant.
        if _extract_tradingview_username(session):
            _upsert_script_access(session, status="active")

        # Dashboard subscriptions use a server-created Checkout Session and
        # still need the canonical Subscription object for trial/period fields.
        if not user_id:
            return
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
