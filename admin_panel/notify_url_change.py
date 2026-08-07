#!/usr/bin/env python3
"""
notify_url_change.py — sigue el log del tunel Serveo y avisa por Telegram
al super admin cada vez que la URL publica cambia.
"""
import json, os, re, time, urllib.request

LOG_PATH = os.path.expanduser("~/.hermes/admin_panel/tunnel.log")
STATE_PATH = os.path.expanduser("~/.hermes/admin_panel/.last_url")
ENV_PATH = os.path.expanduser("~/.hermes/.env")

def _env_value(key, default=None):
    try:
        for line in open(ENV_PATH):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default

SUPER_ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID") or _env_value("ADMIN_CHAT_ID")
URL_RE = re.compile(r"Forwarding HTTP traffic from (https://\S+)")

GIST_ID = "21a187027af69a8d8f4c5e19079e8d62"
GIST_FILE = "panel_url.txt"

def update_gist(url):
    """Publica la URL actual del panel en el gist para la landing (dorsha.devcristobalvc.com/api/panel)."""
    try:
        hosts_path = os.path.expanduser("~/.config/gh/hosts.yml")
        token = None
        with open(hosts_path) as f:
            for line in f:
                m = re.match(r"\s*oauth_token:\s*['\"]?([^\s'\"]+)", line)
                if m:
                    token = m.group(1)
                    break
        if not token:
            print("warn gist: token gh no encontrado", flush=True)
            return
        body = json.dumps({"files": {GIST_FILE: {"content": url}}}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/gists/{GIST_ID}",
            data=body, method="PATCH",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json",
                     "User-Agent": "dorsha-notifier"})
        urllib.request.urlopen(req, timeout=10)
        print("gist actualizado:", url, flush=True)
    except Exception as e:
        print("warn gist:", e, flush=True)

def bot_token():
    path = os.path.expanduser("~/.gero-bridge/config.json")
    if os.path.exists(path):
        return json.load(open(path)).get("bot_token")
    return None

def send_telegram(text):
    token = bot_token()
    if not token:
        return
    data = json.dumps({"chat_id": SUPER_ADMIN_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("warn send:", e, flush=True)

def last_url():
    if os.path.exists(STATE_PATH):
        return open(STATE_PATH).read().strip()
    return None

def save_url(u):
    open(STATE_PATH, "w").write(u)

def main():
    print("notify_url_change: watching", LOG_PATH, flush=True)
    pos = 0
    while True:
        try:
            if os.path.exists(LOG_PATH):
                with open(LOG_PATH, "r", errors="ignore") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for m in URL_RE.finditer(chunk):
                    url = m.group(1)
                    if url != last_url():
                        save_url(url)
                        print("Nueva URL:", url, flush=True)
                        update_gist(url)
                        send_telegram(
                            f"Panel de administracion — nueva URL (el tunel anterior expiro):\n\n"
                            f"{url}/login"
                        )
        except Exception as e:
            print("error loop:", e, flush=True)
        time.sleep(3)

if __name__ == "__main__":
    main()
