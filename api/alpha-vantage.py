"""
api/alpha-vantage.py — Vercel serverless handler for Alpha Vantage data.

Query parameters
----------------
symbols : comma-separated tickers  e.g. ?symbols=AAPL,NVDA,TSLA
mode    : one of quote | overview | earnings | options |
                  indicators | intraday | enriched
          defaults to "quote"

Examples
--------
  /api/alpha-vantage?symbols=AAPL&mode=quote
  /api/alpha-vantage?symbols=NVDA&mode=enriched
  /api/alpha-vantage?symbols=AAPL,MSFT&mode=indicators
  /api/alpha-vantage?symbols=TSLA&mode=options
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Make the project root importable when running inside Vercel's /api directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from alpha_vantage import fetch_alpha_vantage_data  # noqa: E402


def _load_dotenv() -> None:
    """Load .env from the project root (mirrors server.py behaviour)."""
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv()


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            params = parse_qs(urlparse(self.path).query)

            # Parse ?symbols=AAPL,NVDA  (also handles repeated ?symbols=A&symbols=B)
            symbols: list[str] = []
            for raw in params.get("symbols", []):
                symbols.extend(
                    part.strip().upper()
                    for part in raw.split(",")
                    if part.strip()
                )

            # Parse ?mode=quote|overview|earnings|options|indicators|intraday|enriched
            mode = params.get("mode", ["quote"])[0].lower()

            payload = fetch_alpha_vantage_data(symbols=symbols, mode=mode)
            body    = json.dumps(payload).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type",   "application/json; charset=utf-8")
            self.send_header("Cache-Control",  "no-store, no-cache, max-age=0, must-revalidate")
            self.send_header("Pragma",         "no-cache")
            self.send_header("Expires",        "0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type",   "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
