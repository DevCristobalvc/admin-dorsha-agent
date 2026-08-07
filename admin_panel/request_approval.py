#!/usr/bin/env python3
"""
request_approval.py — El agente (Dinco/Gero) llama esto ANTES de una accion
sensible pedida por alguien que NO es el super admin (ADMIN_CHAT_ID en .env).

Uso:
  python3 request_approval.py "<chat_id>" "<nombre>" "<descripcion de la accion>"

Bloquea hasta 10 min esperando resolucion desde el panel web. Imprime:
  APPROVED | DENIED | EXPIRED | TIMEOUT
"""
import os, sys, time, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

def _env_value(key, default=None):
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default

SUPER_ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID") or _env_value("ADMIN_CHAT_ID")

def notify_admin_telegram(text):
    token_line = None
    for path in [os.path.expanduser("~/.gero-bridge/config.json")]:
        if os.path.exists(path):
            token_line = json.load(open(path)).get("bot_token")
            break
    if not token_line:
        return
    try:
        data = json.dumps({"chat_id": SUPER_ADMIN_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token_line}/sendMessage",
            data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("warn notify:", e, file=sys.stderr)

def main():
    if len(sys.argv) < 4:
        print("Uso: request_approval.py <chat_id> <nombre> <descripcion>")
        sys.exit(1)
    chat_id, name, desc = sys.argv[1], sys.argv[2], sys.argv[3]

    if chat_id == SUPER_ADMIN_CHAT_ID:
        print("APPROVED")  # el admin nunca necesita autoaprobarse
        return

    db.init_db()
    aid = db.create_pending_action(chat_id, name, desc, ttl_minutes=10)

    panel_url = os.environ.get("ADMIN_PANEL_PUBLIC_URL", "http://localhost:5057")
    notify_admin_telegram(
        f"🔐 {name} ({chat_id}) pidio una accion sensible:\n\n{desc}\n\n"
        f"Aprobar/negar en el panel: {panel_url}/dashboard\n"
        f"(expira en 10 min, id={aid})"
    )

    print(f"Esperando aprobacion (id={aid})...", file=sys.stderr)
    deadline = time.time() + 600
    while time.time() < deadline:
        action = db.get_action(aid)
        if not action:
            print("EXPIRED")
            return
        if action["status"] != "pending":
            print(action["status"].upper())
            return
        time.sleep(3)

    db.resolve_action(aid, "expired")
    print("TIMEOUT")

if __name__ == "__main__":
    main()
