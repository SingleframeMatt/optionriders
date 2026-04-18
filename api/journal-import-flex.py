"""POST /api/journal/import-flex — upload a Flex CSV or XML file."""
import os, sys, json
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc
from api_helpers import bearer, respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_POST(self):
        token = bearer(self)
        user_id = jc.verify_user(token)
        if not user_id:
            return respond(self, 401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            text = raw.decode("utf-8", errors="replace")
            # Accept {"csv": "..."} JSON wrapper for browsers that can't send raw CSV.
            if text.lstrip().startswith("{") and not text.lstrip().startswith("<"):
                try:
                    text = json.loads(text).get("csv", text)
                except json.JSONDecodeError:
                    pass
            rows = jc._parse_flex_and_normalize(text, user_id)
            result = jc.insert_fills(token, user_id, rows)
            respond(self, 200, {"ok": True, **result,
                                "format": "xml" if text.lstrip().startswith("<") else "csv"})
        except Exception as exc:
            respond(self, 500, {"ok": False, "error": str(exc)})
