"""
/api/panel — Redirige al panel de administración de Dorsha.
La URL del túnel (Pinggy) cambia periódicamente; el notifier local la publica
en un gist. Esta función lee el gist vía API de GitHub (sin cache de CDN)
y hace 302 al panel actual.
"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.request

GIST_API = "https://api.github.com/gists/21a187027af69a8d8f4c5e19079e8d62"
FALLBACK = "https://gxttx-191-111-236-71.run.pinggy-free.link"


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
    return FALLBACK


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = _current_panel_url()
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, format, *args):
        pass
