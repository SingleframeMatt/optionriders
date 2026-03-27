#!/usr/bin/env python3
"""
crypto_server.py — HTTP server for the crypto bot dashboard on port 8125.
Serves static files and wraps bot_core.py API endpoints.
"""
import json
import logging
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger("crypto_server")

PORT = 8125
BASE_DIR = Path(__file__).parent
os.chdir(BASE_DIR)

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Import bot ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(BASE_DIR))
try:
    import bot_core
    _bot = bot_core.bot
    log.info("bot_core loaded — strategy: %s", bot_core.STRATEGY)
except Exception as e:
    log.warning("bot_core import failed: %s — running in display-only mode", e)
    _bot = None


class CryptoHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/bot-status":
            self._json(self._status())
        elif path == "/api/bot-control":
            self._json({"error": "use POST"}, 405)
        elif path in ("/", ""):
            self._redirect("/bot.html")
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/bot-control":
            action = body.get("action", "")
            if _bot is None:
                self._json({"error": "bot not available"}, 503)
                return
            if action == "start":
                _bot.start()
                self._json({"ok": True, "status": "started"})
            elif action == "stop":
                _bot.stop()
                self._json({"ok": True, "status": "stopped"})
            else:
                self._json({"error": f"unknown action: {action}"}, 400)
        else:
            self.send_response(404)
            self.end_headers()

    def _status(self):
        if _bot is None:
            return {"status": "unavailable", "error": "bot_core not loaded"}
        try:
            return _bot.get_status()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), CryptoHandler)
    log.info("Crypto bot dashboard: http://0.0.0.0:%d/bot.html", PORT)
    server.serve_forever()
