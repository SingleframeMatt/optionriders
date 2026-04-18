"""GET /api/journal/day?date=YYYY-MM-DD — full breakdown for a single day."""
import os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc
from api_helpers import bearer, query_param, respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_GET(self):
        token = bearer(self)
        if not token or not jc.verify_user(token):
            return respond(self, 401, {"error": "unauthorized"})
        date = query_param(self.path, "date")
        if not date:
            return respond(self, 400, {"error": "missing date"})
        try:
            respond(self, 200, jc.day_detail(token, date))
        except Exception as exc:
            respond(self, 500, {"error": str(exc)})
