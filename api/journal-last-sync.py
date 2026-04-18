"""GET /api/journal/last-sync — most recent successful sync timestamp.

Serverless functions have no persistent filesystem, so "last sync" lives
on the client instead. This endpoint stays for frontend compatibility and
simply returns an empty payload; the client reads its own localStorage.
"""
import os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api_helpers import respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_GET(self):
        respond(self, 200, {"at": None, "result": None})
