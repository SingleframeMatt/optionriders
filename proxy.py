#!/usr/bin/env python3
"""
proxy.py — Reverse proxy that exposes both bots on a single public port.

Routes:
  /crypto/*   → http://127.0.0.1:8125  (crypto bot)
  /options/*  → http://127.0.0.1:8126  (options bot)
  /           → dashboard page with links to both

Run: python proxy.py
Port: 8127
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

CRYPTO_PORT = 8125
OPTIONS_PORT = 8126
FUTURES_PORT = 8128
PROXY_PORT = 8127

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OptionRiders — Bot Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0a0f; color: #e2e8f0; font-family: Inter, sans-serif;
         min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .container { text-align: center; max-width: 600px; padding: 40px 20px; }
  h1 { font-size: 2rem; font-weight: 800; margin-bottom: 8px;
       background: linear-gradient(135deg, #34d399, #22d3ee, #818cf8);
       -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  p { color: #94a3b8; margin-bottom: 40px; }
  .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .card { background: #111827; border: 1px solid #1f2937; border-radius: 12px;
          padding: 24px; text-decoration: none; color: inherit;
          transition: border-color .2s, transform .2s; display: block; }
  .card:hover { border-color: #34d399; transform: translateY(-2px); }
  .card-icon { font-size: 2rem; margin-bottom: 12px; }
  .card-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 6px; }
  .card-desc { font-size: 0.85rem; color: #6b7280; }
</style>
</head>
<body>
<div class="container">
  <h1>OptionRiders</h1>
  <p>Bot Monitor — select a dashboard</p>
  <div class="cards">
    <a class="card" href="/crypto/">
      <div class="card-icon">BTC</div>
      <div class="card-title">Crypto Bot</div>
      <div class="card-desc">BTC scalping on Binance testnet</div>
    </a>
    <a class="card" href="/options/">
      <div class="card-icon">OPT</div>
      <div class="card-title">Options Bot</div>
      <div class="card-desc">SPY/QQQ options via IBKR paper</div>
    </a>
    <a class="card" href="/futures/">
      <div class="card-icon">ES</div>
      <div class="card-title">Futures Bot</div>
      <div class="card-desc">MES/MNQ futures via IBKR paper</div>
    </a>
  </div>
</div>
</body>
</html>""".encode("utf-8")


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access logs

    def _proxy(self, target_port, path, prefix):
        url = f"http://127.0.0.1:{target_port}{path}"
        try:
            req = urllib.request.Request(url, method=self.command)
            # Follow redirects manually so we can rewrite Location headers
            req.add_header("User-Agent", "OptionRiders-Proxy/1.0")
            for h in ("Content-Type", "Content-Length", "Accept", "Accept-Encoding"):
                v = self.headers.get(h)
                if v:
                    req.add_header(h, v)
            # Forward body for POST/PUT
            body = None
            clen = int(self.headers.get("Content-Length", 0))
            if clen:
                body = self.rfile.read(clen)
            with urllib.request.urlopen(req, data=body, timeout=15) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() == "location":
                        # Rewrite absolute redirect paths to include proxy prefix
                        if v.startswith("/") and not v.startswith(prefix):
                            v = prefix + v.lstrip("/")
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.URLError as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Bot unavailable: {e}".encode())

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        path = self.path
        if path == "/" or path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(INDEX_HTML)))
            self.end_headers()
            self.wfile.write(INDEX_HTML)
        elif path.startswith("/crypto"):
            sub = path[len("/crypto"):]
            if not sub:
                # redirect /crypto → /crypto/
                self.send_response(301)
                self.send_header("Location", "/crypto/")
                self.end_headers()
                return
            self._proxy(CRYPTO_PORT, sub if sub else "/", "/crypto/")
        elif path.startswith("/options"):
            sub = path[len("/options"):]
            if not sub:
                self.send_response(301)
                self.send_header("Location", "/options/")
                self.end_headers()
                return
            self._proxy(OPTIONS_PORT, sub if sub else "/", "/options/")
        elif path.startswith("/futures"):
            sub = path[len("/futures"):]
            if not sub:
                self.send_response(301)
                self.send_header("Location", "/futures/")
                self.end_headers()
                return
            self._proxy(FUTURES_PORT, sub if sub else "/", "/futures/")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    print(f"Proxy running on port {PROXY_PORT}")
    print(f"  /crypto/ -> localhost:{CRYPTO_PORT}")
    print(f"  /options/ -> localhost:{OPTIONS_PORT}")
    server.serve_forever()
