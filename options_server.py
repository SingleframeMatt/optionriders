#!/usr/bin/env python3
"""
options_server.py — Flask web server for the Options Trading Bot dashboard.

Serves the options bot UI on port 8126 (separate from the crypto bot on 8125).

Endpoints:
  GET  /               → redirect to /options_bot.html
  GET  /api/options    → full bot state (positions, trades, levels, P&L)
  POST /api/options/start  → start the bot background thread
  POST /api/options/stop   → request bot shutdown
  GET  /options_bot.html   → static UI file
"""

import json
import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("options_server")

PORT = int(os.environ.get("OPTIONS_SERVER_PORT", "8126"))
BASE_DIR = Path(__file__).parent

# ── Lazy import of options_bot so the server starts even if ib_insync is not yet
#    available. The bot is started in a background thread on demand.
_bot_thread: threading.Thread | None = None
_bot_stop_flag = threading.Event()


def _get_bot_state() -> dict:
    try:
        from options_bot import get_state
        return get_state()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def _start_bot_thread():
    """Launch options_bot.run() in a daemon thread if not already running."""
    global _bot_thread
    if _bot_thread is not None and _bot_thread.is_alive():
        return {"ok": False, "message": "Bot thread already running"}
    try:
        from options_bot import run as _run_bot
        _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="options-bot")
        _bot_thread.start()
        return {"ok": True, "message": "Bot started"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _load_dotenv(dotenv_path: str = ".env"):
    env_file = BASE_DIR / dotenv_path
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


class OptionsHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the options bot dashboard."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # ── Routing ───────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Root redirect
        if path in {"/", ""}:
            self.send_response(302)
            self.send_header("Location", "/options_bot.html")
            self.end_headers()
            return

        if path == "/api/options":
            self._send_json(_get_bot_state())
            return

        # Static files
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/api/options/start":
            result = _start_bot_thread()
            self._send_json(result)
            return

        if path == "/api/options/stop":
            # Signal the bot to stop via its state (best-effort)
            try:
                import options_bot as _ob
                import threading as _t
                # Set halted flag so no new entries; positions will EOD-close
                with _ob._state_lock:
                    _ob._state["status"] = "stopped"
                self._send_json({"ok": True, "message": "Stop requested"})
            except Exception as exc:
                self._send_json({"ok": False, "message": str(exc)})
            return

        self.send_response(404)
        self.end_headers()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Suppress per-request stdout noise; only log errors."""
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)


def main():
    _load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Auto-start the bot in the background when the server launches
    result = _start_bot_thread()
    log.info("Bot auto-start: %s", result)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), OptionsHandler)
    log.info("Options Bot dashboard: http://0.0.0.0:%d", PORT)
    log.info("API endpoint:         http://0.0.0.0:%d/api/options", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
