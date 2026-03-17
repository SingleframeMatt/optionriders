import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from barchart_proxy import CACHE_TTL_SECONDS, fetch_options_activity


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            tickers = []
            for value in params.get("tickers", []):
                tickers.extend(part.strip() for part in value.split(","))
            payload = fetch_options_activity(extra_symbols=tickers)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", f"public, max-age={CACHE_TTL_SECONDS}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
