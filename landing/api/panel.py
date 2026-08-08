"""
/api/panel — Redirige al panel de administración de Dorsha.
La URL del túnel (Cloudflared) cambia periódicamente; el notifier local la publica
en un gist. Esta función lee el gist vía API de GitHub (sin cache de CDN)
y hace 302 al panel actual. Si el gist no responde -> 503 (sin fallback con IP).
"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.request

GIST_API = "https://api.github.com/gists/21a187027af69a8d8f4c5e19079e8d62"


def _current_panel_url():
    try:
        req = urllib.request.Request(GIST_API, headers={"User-Agent": "dorsha-landing"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.load(r)
            u = d["files"]["panel_url.txt"]["content"].strip()
            if u.startswith("https://"):
                return u
    except Exception:
        pass
    return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = _current_panel_url()
        if not url:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"panel url no disponible")
            return
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, format, *args):
        pass
