"""POST /api/journal/sync — fetch Flex report from IBKR and import fills.

Body: {"token": "<ibkr_flex_token>", "query_id": "<flex_query_id>"}
Auth: Bearer <supabase_access_token>

Needs Vercel Pro for the extended function timeout — IBKR report generation
can take 30-60 seconds end to end.
"""
import os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import journal_cloud as jc
from api_helpers import bearer, read_body_json, respond, handle_options


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): handle_options(self)

    def do_POST(self):
        token = bearer(self)
        user_id = jc.verify_user(token)
        if not user_id:
            return respond(self, 401, {"error": "unauthorized"})

        body = read_body_json(self)
        ibkr_token = (body.get("token") or "").strip()
        ibkr_qid = (body.get("query_id") or "").strip()
        if not ibkr_token or not ibkr_qid:
            return respond(self, 400, {
                "ok": False,
                "error": "Open Settings and paste your IBKR Flex token and query ID.",
            })

        try:
            result = jc.sync_from_ibkr(token, user_id, ibkr_token, ibkr_qid)
            respond(self, 200, result)
        except Exception as exc:
            respond(self, 500, {"ok": False, "error": str(exc)})
