import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from barchart_proxy import fetch_options_activity


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            tickers = []
            for value in params.get("tickers", []):
                tickers.extend(part.strip() for part in value.split(","))
            force_refresh = params.get("fresh", ["0"])[0].lower() in {"1", "true", "yes"}
            payload = fetch_options_activity(extra_symbols=tickers, force_refresh=force_refresh)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, max-age=0, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
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
