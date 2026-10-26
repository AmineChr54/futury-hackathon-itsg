"""Tiny local proxy so the demo page can call the hessian.AI gateway from a browser.

The gateway rejects browser CORS preflight requests, so the page talks to this proxy
instead. The team API key is read from the HAI_API_KEY environment variable and never
leaves this machine except towards the gateway.

    set HAI_API_KEY=<your team key>        (PowerShell: $env:HAI_API_KEY="<your team key>")
    python demo/proxy.py
    -> in the demo: AI settings → Live → base URL http://localhost:8787/v1

Standard library only. Listens on 127.0.0.1 only.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("HAI_BASE_URL", "https://hip-gw.hessian.ai/v1").rstrip("/")
PORT = int(os.environ.get("PROXY_PORT", "8787"))
KEY = os.environ.get("HAI_API_KEY", "")


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _forward(self, method):
        if not self.path.startswith("/v1/"):
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        auth = self.headers.get("Authorization") or (f"Bearer {KEY}" if KEY else "")
        req = urllib.request.Request(UPSTREAM + self.path[3:], data=body, method=method)
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status, data = resp.status, resp.read()
        except urllib.error.HTTPError as err:
            status, data = err.code, err.read()
        except Exception as err:  # network errors become a JSON 502 for the page
            status, data = 502, json.dumps({"error": str(err)}).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self._forward("POST")

    def do_GET(self):
        self._forward("GET")

    def log_message(self, fmt, *args):
        sys.stderr.write("proxy: " + (fmt % args) + "\n")


if __name__ == "__main__":
    if not KEY:
        print("Note: HAI_API_KEY is not set; the page must send the key itself.", file=sys.stderr)
    print(f"Proxy on http://localhost:{PORT}/v1 -> {UPSTREAM}", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
