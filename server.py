#!/usr/bin/env python3

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from barchart_proxy import CACHE_TTL_SECONDS, fetch_options_activity
from market_data import fetch_market_data


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/options-flow"):
            self.handle_options_flow()
            return
        if self.path.startswith("/api/market-data"):
            self.handle_market_data()
            return
        if self.path.startswith("/api/public-config"):
            self.handle_public_config()
            return
        super().do_GET()

    def handle_options_flow(self):
        try:
            payload = fetch_options_activity()
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

    def handle_market_data(self):
        try:
            payload = fetch_market_data()
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

    def handle_public_config(self):
        body = json.dumps({
            "googleClientId": os.environ.get("GOOGLE_CLIENT_ID", ""),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8125), DashboardHandler)
    print("Serving Option Riders at http://127.0.0.1:8125")
    server.serve_forever()


if __name__ == "__main__":
    main()
