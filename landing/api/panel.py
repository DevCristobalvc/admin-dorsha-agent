"""
/api/panel — Redirige al panel de administración de Dorsha.
La URL del túnel Serveo cambia constantemente; el notifier local la
publica en un gist. Esta función lee el gist y hace 302 al panel actual.
"""
from http.server import BaseHTTPRequestHandler
import urllib.request

GIST_RAW = "https://gist.githubusercontent.com/DevCristobalvc/21a187027af69a8d8f4c5e19079e8d62/raw/panel_url.txt"
FALLBACK = "https://bc3dd97a74b5baac-191-111-236-71.serveousercontent.com"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = FALLBACK
        try:
            with urllib.request.urlopen(GIST_RAW, timeout=6) as r:
                u = r.read().decode("utf-8").strip()
                if u.startswith("https://"):
                    url = u
        except Exception:
            pass
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, format, *args):
        pass
