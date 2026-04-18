"""GET /api/journal/equity — cumulative equity curve points."""
import os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc
from api_helpers import bearer, query_filters, respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_GET(self):
        token = bearer(self)
        if not token or not jc.verify_user(token):
            return respond(self, 401, {"error": "unauthorized"})
        try:
            respond(self, 200, jc.equity_curve(token, query_filters(self.path)))
        except Exception as exc:
            respond(self, 500, {"error": str(exc)})
