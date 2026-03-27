#!/usr/bin/env python3
"""
server.py — Flask web server for the Option Riders Options Bot dashboard.

Serves the options bot UI on port 8126 (separate from any other server on 8125).

Endpoints:
  GET  /                   → serves static/options.html
  GET  /api/options        → full bot state (positions, trades, levels, P&L)
  POST /api/options/start  → start the bot background thread
  POST /api/options/stop   → request bot shutdown
  GET  /static/<path>      → static files

Run directly:
    python server.py
"""

import logging
import os
import sys
import threading
from pathlib import Path

# Ensure the optionriders directory is on sys.path so imports work
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ── .env loader (runs before Flask import so env vars are set) ────────────────
def _load_dotenv(dotenv_path: str = ".env"):
    env_file = _HERE / dotenv_path
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

from flask import Flask, jsonify, request, send_from_directory

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = int(os.environ.get("OPTIONS_SERVER_PORT", "8126"))
STATIC_DIR = _HERE / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("options_server")

# ── Bot thread management ─────────────────────────────────────────────────────
_bot_thread: threading.Thread | None = None
_bot_thread_lock = threading.Lock()


def _get_bot_state() -> dict:
    try:
        from options_bot import get_state
        return get_state()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def _start_bot_thread() -> dict:
    """Launch options_bot.run() in a daemon thread if not already running."""
    global _bot_thread
    with _bot_thread_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            return {"ok": False, "message": "Bot thread already running"}
        try:
            from options_bot import run as _run_bot
            _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="options-bot")
            _bot_thread.start()
            log.info("Options bot thread started.")
            return {"ok": True, "message": "Bot started"}
        except Exception as exc:
            log.error("Failed to start bot thread: %s", exc)
            return {"ok": False, "message": str(exc)}


def _stop_bot() -> dict:
    """Signal the bot to stop (best-effort via state flag)."""
    try:
        import options_bot as _ob
        with _ob._state_lock:
            _ob._state["status"] = "stopped"
            _ob._state["halted"] = True   # prevents new entries
        return {"ok": True, "message": "Stop requested — bot will finish current cycle"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# Disable Flask request logging noise (only log errors)
log_func = logging.getLogger("werkzeug")
log_func.setLevel(logging.ERROR)


@app.route("/")
def index():
    """Serve the main UI."""
    return send_from_directory(str(STATIC_DIR), "options.html")


@app.route("/options.html")
def options_html():
    return send_from_directory(str(STATIC_DIR), "options.html")


@app.route("/api/options", methods=["GET"])
def api_state():
    """Return the full bot state as JSON."""
    return jsonify(_get_bot_state())


@app.route("/api/options/start", methods=["POST"])
def api_start():
    """Start the bot background thread."""
    result = _start_bot_thread()
    return jsonify(result)


@app.route("/api/options/stop", methods=["POST"])
def api_stop():
    """Request the bot to stop."""
    result = _stop_bot()
    return jsonify(result)


@app.route("/api/options/status", methods=["GET"])
def api_status():
    """Lightweight status check."""
    state = _get_bot_state()
    return jsonify({
        "status":    state.get("status", "unknown"),
        "connected": state.get("connected", False),
        "halted":    state.get("halted", False),
        "daily_pnl": state.get("daily_pnl", 0.0),
        "positions": len(state.get("positions", {})),
    })


# Serve any other static files (js, css, etc.) from static/
@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(str(_HERE), filename)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Auto-start the bot when the server launches
    result = _start_bot_thread()
    log.info("Bot auto-start: %s", result["message"])

    log.info("Option Riders Options Bot dashboard: http://0.0.0.0:%d", PORT)
    log.info("API: http://0.0.0.0:%d/api/options", PORT)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,    # reloader breaks background threads
        threaded=True,
    )


if __name__ == "__main__":
    main()
