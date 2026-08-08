#!/usr/bin/env python3
"""
health_watch.py — Vigilante de salud del sistema.
Se ejecuta por cron (no_agent): imprime SOLO cuando hay algo nuevo que alertar.
Silencio (stdout vacío) = todo bien. Dedupe por estado en ~/.hermes/health_watch_state.json
"""
import json
import os
import re
import sys
import subprocess
import urllib.request

HOME = os.path.expanduser("~")
STATE_PATH = os.path.join(HOME, ".hermes", "health_watch_state.json")
ENV_PATH = os.path.join(HOME, ".hermes", ".env")
LAST_URL = os.path.join(HOME, ".hermes", "admin_panel", ".last_url")
CRON_JOBS = os.path.join(HOME, ".hermes", "cron", "jobs.json")

BALANCE_ALERT_THRESHOLD = 2.0


def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {}


def save_state(state):
    json.dump(state, open(STATE_PATH, "w"), indent=1)


def env_val(key):
    for line in open(ENV_PATH, encoding="utf-8"):
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def gateway_status():
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway.service"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def tunnel_ok():
    try:
        url = open(LAST_URL).read().strip()
        if not url.startswith("https://"):
            return False
        req = urllib.request.Request(url + "/login", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 302, 401)
    except Exception:
        return False


def deepseek_balance():
    try:
        out = subprocess.run([sys.executable, os.path.join(HOME, ".hermes", "scripts", "balance_check.py"),
                              "--json"], capture_output=True, text=True, timeout=40)
        for d in json.loads(out.stdout or "[]"):
            if d.get("api") == "DeepSeek":
                m = re.search(r"[\d.]+", d.get("balance") or "")
                return float(m.group(0)) if m else None
    except Exception:
        pass
    return None


def cron_status_map():
    try:
        d = json.load(open(CRON_JOBS))
        return {j.get("id"): j.get("last_status") for j in d.get("jobs", [])}
    except Exception:
        return {}


def main():
    alerts = []
    state = load_state()

    # 1. Gateway
    gw = gateway_status()
    if gw != "active" and state.get("gw") != gw:
        state["gw"] = gw
        alerts.append(f"🛑 GATEWAY {gw.upper()} — el bot no está respondiendo. Revisa el panel.")

    # 2. Túnel del panel
    tun = tunnel_ok()
    if not tun and not state.get("tun_alerted"):
        state["tun_alerted"] = True
        alerts.append("🕳️ El túnel del panel está caído — /api/panel no redirige bien.")
    if tun:
        state["tun_alerted"] = False

    # 3. Saldo DeepSeek
    bal = deepseek_balance()
    if bal is not None and bal < BALANCE_ALERT_THRESHOLD:
        last = state.get("bal_last")
        # alerta si baja de nuevo el umbral por primera vez o si cae > $0.50 desde la última
        if last is None or (bal < last - 0.5):
            state["bal_last"] = bal
            alerts.append(f"⚠️ SALDO DeepSeek en ${bal:.2f} — por debajo de ${BALANCE_ALERT_THRESHOLD:.0f}. ¡Recarga!")
        elif last is not None and bal > last:
            state["bal_last"] = bal
    elif bal is not None and bal >= BALANCE_ALERT_THRESHOLD:
        state["bal_last"] = bal

    # 4. Crons con fallo (solo nuevos)
    cur = cron_status_map()
    prev = state.get("cron_status", {})
    new_fails = [jid for jid, st in cur.items() if st == "error" and prev.get(jid) != "error"]
    if new_fails:
        try:
            d = json.load(open(CRON_JOBS))
            names = {j.get("id"): j.get("name") for j in d.get("jobs", [])}
        except Exception:
            names = {}
        alerts.append("🔥 CRONS FALLANDO: " + ", ".join(names.get(j, j) for j in new_fails))
    state["cron_status"] = cur

    save_state(state)

    if alerts:
        print("🩺 ALERTA DE SALUD\n" + "\n".join(alerts))


if __name__ == "__main__":
    main()
