"""GET /api/journal/calendar — monthly P&L calendar + weekly rollups."""
import os, sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc
from api_helpers import bearer, query_filters, query_param, respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_GET(self):
        token = bearer(self)
        if not token or not jc.verify_user(token):
            return respond(self, 401, {"error": "unauthorized"})
        try:
            now = datetime.now()
            year = int(query_param(self.path, "year", str(now.year)))
            month = int(query_param(self.path, "month", str(now.month)))
            respond(self, 200, jc.calendar_month(token, year, month, query_filters(self.path)))
        except Exception as exc:
            respond(self, 500, {"error": str(exc)})
