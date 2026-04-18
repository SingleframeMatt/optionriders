"""POST /api/journal/clear — wipe the authenticated user's fills."""
import os, sys
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
            n = jc.delete_all_user_fills(token, user_id)
            respond(self, 200, {"ok": True, "deleted": n})
        except Exception as exc:
            respond(self, 500, {"ok": False, "error": str(exc)})
