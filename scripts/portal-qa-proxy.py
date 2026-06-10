#!/usr/bin/env python3
"""QA proxy for the Foyer Stage portal.

Serves dashboard/clientmcp/ statics and forwards /clientmcp/api/* to the local
Foyer backend (:4000), so an isolated preview browser exercises the full
portal+API loop without touching cloudflared or the live dashboard.

Usage: python3 scripts/portal-qa-proxy.py [port=8771]
"""
import http.server
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard", "clientmcp"))
BACKEND = os.environ.get("FOYER_BACKEND", "http://127.0.0.1:4000")
API_PREFIX = "/clientmcp/api"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def _proxy(self):
        path = self.path[len(API_PREFIX):]
        body = None
        length = int(self.headers.get("content-length") or 0)
        if length:
            body = self.rfile.read(length)
        req = urllib.request.Request(
            BACKEND + path,
            data=body,
            method=self.command,
            headers={"content-type": self.headers.get("content-type") or "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=95) as r:
                data = r.read()
                self.send_response(r.status)
                self.send_header("content-type", r.headers.get("content-type", "application/json"))
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(503)
            self.end_headers()

    def do_GET(self):
        if self.path.startswith(API_PREFIX + "/"):
            return self._proxy()
        # path-parity with the dashboard's /clientmcp mount
        if self.path.startswith("/clientmcp/"):
            self.path = self.path[len("/clientmcp"):] or "/"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith(API_PREFIX + "/"):
            return self._proxy()
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
