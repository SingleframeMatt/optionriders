"""Tiny helpers shared by every /api/journal-* Vercel handler."""
import json
from urllib.parse import parse_qs, urlparse


def bearer(h) -> str:
    a = h.headers.get("Authorization", "")
    return a[7:] if a.startswith("Bearer ") else ""


def query_filters(path: str) -> dict:
    qs = parse_qs(urlparse(path).query)
    out = {}
    for k in ("from", "to", "symbol", "asset_class"):
        v = qs.get(k)
        if v and v[0]:
            out[k] = v[0].strip().upper() if k == "symbol" else v[0].strip()
    return out


def query_param(path: str, name: str, default: str = "") -> str:
    qs = parse_qs(urlparse(path).query)
    v = qs.get(name)
    return (v[0].strip() if v and v[0] else default)


def cors_headers(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")


def respond(h, code: int, data):
    body = json.dumps(data).encode("utf-8")
    h.send_response(code)
    cors_headers(h)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def handle_options(h):
    h.send_response(204)
    cors_headers(h)
    h.end_headers()


def read_body_json(h) -> dict:
    length = int(h.headers.get("Content-Length", 0))
    if not length:
        return {}
    raw = h.rfile.read(length)
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"_raw": raw.decode("utf-8", errors="replace")}
