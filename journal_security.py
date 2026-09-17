"""Journal security boundaries. No credentials or upstream response bodies in errors."""
import base64
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import date
from urllib.parse import urlsplit

import requests

MAX_BODY = 2 * 1024 * 1024
_LOCK = threading.Lock()
_BUCKETS = {}

class SecurityError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def trusted_origin(origin):
    if not origin:
        return True  # CLI/server requests still require a valid bearer token.
    allowed = {"https://optionriders.com", "https://www.optionriders.com"}
    configured = os.getenv("APP_URL", "")
    if configured:
        p = urlsplit(configured)
        if p.scheme == "https" and p.netloc:
            allowed.add(f"{p.scheme}://{p.netloc}")
    if os.getenv("VERCEL_ENV") != "production":
        for name in ("VERCEL_URL", "VERCEL_BRANCH_URL"):
            if os.getenv(name):
                allowed.add("https://" + os.environ[name])
    return origin in allowed


def json_payload(raw):
    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, UnicodeError):
        raise SecurityError("Invalid JSON request.") from None
    if not isinstance(payload, dict):
        raise SecurityError("Expected a JSON object.")
    return payload


def valid_date(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise SecurityError("Invalid date.") from None


def credentials(payload):
    token, query = payload.get("token"), payload.get("query_id")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,512}", token):
        raise SecurityError("Enter a valid IBKR Flex reporting token.")
    if not isinstance(query, str) or not re.fullmatch(r"\d{1,32}", query):
        raise SecurityError("Enter a numeric Flex query ID.")
    return {"token": token, "query_id": query}


def storage_enabled():
    return os.getenv("JOURNAL_SECURITY_STORAGE") == "1"


def vault_enabled():
    return storage_enabled() and bool(os.getenv("JOURNAL_VAULT_KEY")) and bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def _key():
    try:
        key = base64.b64decode(os.environ["JOURNAL_VAULT_KEY"], validate=True)
        if len(key) != 32:
            raise ValueError()
        return key
    except (KeyError, ValueError):
        raise SecurityError("Secure broker storage is unavailable.", 503) from None


def seal(user_id, value):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, json.dumps(value).encode(), f"journal-ibkr:{user_id}:v1".encode())
    return base64.b64encode(nonce + ciphertext).decode()


def unseal(user_id, value):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.b64decode(value, validate=True)
        plaintext = AESGCM(_key()).decrypt(raw[:12], raw[12:], f"journal-ibkr:{user_id}:v1".encode())
        return credentials(json.loads(plaintext))
    except Exception:
        raise SecurityError("Reconnect IBKR in Settings to restore access.", 503) from None


def _rest(method, resource, bearer=None, admin=False, **kwargs):
    api_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY" if admin else "SUPABASE_ANON_KEY", "")
    if not api_key:
        raise SecurityError("Journal storage is unavailable.", 503)
    extra = kwargs.pop("headers", {})
    headers = {"apikey": api_key, "Authorization": "Bearer " + (api_key if admin else bearer or ""),
               "Content-Type": "application/json", **extra}
    try:
        response = requests.request(method, os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + resource,
                                    headers=headers, timeout=15, **kwargs)
        if not response.ok:
            raise SecurityError("Journal storage is unavailable. Please try again.", 503)
        return response.json() if response.content else None
    except (requests.RequestException, ValueError, KeyError):
        raise SecurityError("Journal storage is unavailable. Please try again.", 503) from None


def connection(user_id):
    if not vault_enabled():
        return {"enabled": False, "connected": False}
    _key()  # Validate configuration without returning key or ciphertext.
    rows = _rest("GET", "journal_connections", admin=True,
                 params={"user_id": "eq." + user_id, "select": "user_id", "limit": 1})
    return {"enabled": True, "connected": bool(rows)}


def save_connection(user_id, payload):
    if not vault_enabled():
        raise SecurityError("Secure storage is not configured.", 503)
    if payload.get("disconnect") is True:
        _rest("DELETE", "journal_connections", admin=True, params={"user_id": "eq." + user_id})
    else:
        encrypted = seal(user_id, credentials(payload))
        _rest("POST", "journal_connections", admin=True, params={"on_conflict": "user_id"},
              headers={"Prefer": "resolution=merge-duplicates"}, json={"user_id": user_id, "encrypted_credentials": encrypted})
    return {"ok": True}


def load_connection(user_id):
    if not vault_enabled():
        raise SecurityError("Reconnect IBKR in Settings.")
    rows = _rest("GET", "journal_connections", admin=True,
                 params={"user_id": "eq." + user_id, "select": "encrypted_credentials", "limit": 1})
    if not rows:
        raise SecurityError("Reconnect IBKR in Settings.")
    return unseal(user_id, rows[0]["encrypted_credentials"])


def rate_limit(user_id, action, bearer):
    # Distributed, atomic enforcement after the migration is enabled. During
    # rollout the bounded per-process limiter reduces abuse but is not global.
    bucket = "sync" if action in ("sync", "import-flex") else "read" if action == "read" else "write"
    if storage_enabled():
        if not _rest("POST", "rpc/journal_consume_budget", bearer, json={"bucket_name": bucket}):
            raise SecurityError("Too many requests. Please wait before trying again.", 429)
        return
    window, maximum = {"sync": (60, 2), "read": (60, 120), "write": (60, 30)}[bucket]
    now = time.monotonic()
    with _LOCK:
        for key, (end, _) in list(_BUCKETS.items()):
            if end <= now:
                _BUCKETS.pop(key, None)
        key = (user_id, bucket)
        if key not in _BUCKETS and len(_BUCKETS) >= 10000:
            raise SecurityError("Please retry shortly.", 429)
        end, count = _BUCKETS.get(key, (now + window, 0))
        if count >= maximum:
            raise SecurityError("Too many requests. Please wait before trying again.", 429)
        _BUCKETS[key] = (end, count + 1)


def read_profile(bearer, user_id):
    if not storage_enabled():
        return {"enabled": False}
    goals = _rest("GET", "journal_preferences", bearer, params={"user_id": "eq." + user_id, "select": "currency,monthly_target,trading_days"})
    rules = []
    while True:
        page = _rest("GET", "journal_discipline", bearer, params={"user_id": "eq." + user_id, "select": "day,followed_rules", "order": "day.desc", "limit": "1000", "offset": str(len(rules))})
        rules.extend(page)
        if len(page) < 1000: break
        if len(rules) >= 50000:
            raise SecurityError("Daily review history exceeds the supported limit.", 413)
    return {"enabled": True, "goals": {g["currency"]: {"monthlyTarget": float(g["monthly_target"]), "tradingDays": g["trading_days"]} for g in goals},
            "rules": {r["day"]: r["followed_rules"] for r in rules}}


def write_profile(bearer, user_id, payload):
    if not storage_enabled():
        raise SecurityError("Journal storage is not configured.", 503)
    kind = payload.get("kind")
    if kind == "goal":
        currency, target, days = payload.get("currency"), payload.get("monthlyTarget"), payload.get("tradingDays")
        if currency not in ("USD", "GBP", "EUR") or type(target) not in (int, float) or not math.isfinite(target) or not 0.01 <= target <= 999999999.99 or type(days) is not int or not 1 <= days <= 31:
            raise SecurityError("Invalid monthly plan.")
        table, row = "journal_preferences", {"user_id": user_id, "currency": currency, "monthly_target": round(target, 2), "trading_days": days}
        conflict = "user_id,currency"
    elif kind == "rules":
        day = valid_date(payload.get("day"))
        # Permit all time zones' current local dates; the UI uses the user's day.
        from datetime import timedelta
        if day > (date.today() + timedelta(days=1)).isoformat() or type(payload.get("followed")) is not bool:
            raise SecurityError("Invalid daily review.")
        table, row = "journal_discipline", {"user_id": user_id, "day": day, "followed_rules": payload["followed"]}
        conflict = "user_id,day"
    else:
        raise SecurityError("Invalid journal preference.")
    prefer = "resolution=ignore-duplicates" if payload.get("migrate") is True else "resolution=merge-duplicates"
    _rest("POST", table, bearer, params={"on_conflict": conflict}, headers={"Prefer": prefer}, json=row)
    return {"ok": True}
