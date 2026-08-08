#!/usr/bin/env python3
import os, sys, re, json, io, sqlite3, zipfile, tempfile, subprocess, hashlib, hmac, time
from datetime import datetime, timedelta
from html import escape
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import metrics as metrics_mod
import keymanager as km

from flask import Flask, request, redirect, make_response, abort

app = Flask(__name__)
db.init_db()
db.sync_users_from_channel_directory()

ENV_PATH = os.path.expanduser("~/.hermes/.env")
CONFIG_PATH = os.path.expanduser("~/.hermes/config.yaml")

def _read_env(key, default=None):
    try:
        for line in open(ENV_PATH):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default


def _tail_log(n=400):
    """Últimas N líneas del log del gateway (lectura segura de archivo grande)."""
    path = os.path.expanduser("~/.hermes/logs/gateway.log")
    try:
        stat = os.stat(path)
        if not stat.st_size:
            return ["(log vacío)"]
        with open(path, "rb") as f:
            if stat.st_size > 300_000:
                f.seek(stat.st_size - 300_000)
                f.readline()  # descarta línea parcial
            tail = f.read().decode("utf-8", errors="ignore")
        lines = tail.splitlines()[-n:]
        return lines or ["(log vacío)"]
    except FileNotFoundError:
        return ["(no existe ~/.hermes/logs/gateway.log)"]
    except Exception as e:
        return [f"(error leyendo log: {e})"]

SUPER_ADMIN = os.environ.get("ADMIN_CHAT_ID") or _read_env("ADMIN_CHAT_ID")

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');
:root{--bg:#ffffff;--ink:#0a0a0a;--muted:#5a5a5a;--line:#e4e4e4;--danger:#dc2626;--ok:#15803d}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;font-weight:400;min-height:100vh}
h1,h2,h3,h4{font-family:'Space Grotesk',sans-serif;font-weight:500;letter-spacing:-.02em}
.brand{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:18px;letter-spacing:-.02em}
.idx{font-family:'Space Grotesk',sans-serif;font-size:11.5px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase}
.wrap{max-width:760px;margin:0 auto;padding:48px 24px}
.top{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:36px}
.top .brand a{color:var(--ink);text-decoration:none}
.nav a{color:var(--muted);text-decoration:none;font-size:13.5px;margin-left:18px}
.nav a:hover{color:var(--ink)}
.card{border:1px solid var(--line);padding:28px;margin-bottom:32px}
.card h2{font-size:17px;margin-bottom:6px}
.card .idx{margin-bottom:18px;display:block}
.row{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:none}
.row .who b{font-family:'Space Grotesk',sans-serif;font-weight:500;font-size:14.5px}
.muted{color:var(--muted);font-size:13px;line-height:1.55}
input[type=password],input[type=text],select{width:100%;padding:11px 13px;margin:8px 0 16px;background:#fff;border:1px solid var(--line);border-radius:0;color:var(--ink);font-family:'Inter',sans-serif;font-size:14px;box-sizing:border-box}
input:focus,select:focus{outline:none;border-color:var(--ink)}
button{font-family:'Space Grotesk',sans-serif;font-size:13.5px;font-weight:500;letter-spacing:.02em;padding:10px 20px;border:1px solid var(--ink);border-radius:0;background:var(--ink);color:#fff;cursor:pointer;transition:background .15s}
button:hover{background:#262626}
button.ghost{background:#fff;color:var(--ink)}
button.ghost:hover{background:#f5f5f5}
button.danger{background:#fff;color:var(--danger);border-color:var(--danger)}
button.danger:hover{background:var(--danger);color:#fff}
.tag{font-family:'Space Grotesk',sans-serif;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;padding:4px 10px;border:1px solid var(--line);color:var(--muted);margin-right:10px;white-space:nowrap}
.tag.active{border-color:var(--ok);color:var(--ok)}
.tag.blocked{border-color:var(--danger);color:var(--danger)}
a{color:var(--ink)}
.msg{max-width:520px;margin:60px auto;padding:32px;border:1px solid var(--line)}
.msg h1{font-size:20px;margin-bottom:12px}
.bar{height:3px;background:var(--ink);width:56px;margin-bottom:26px}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:26px}
.mcard{border:1px solid var(--line);padding:18px 16px}
.mcard .v{font-family:'Space Grotesk',sans-serif;font-size:23px;font-weight:500;letter-spacing:-.02em}
.mcard .l{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{font-family:'Space Grotesk',sans-serif;font-weight:500;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:8px 10px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:none}
.bars{display:flex;align-items:flex-end;gap:5px;height:110px;margin-top:12px}
.bar{flex:1;background:var(--ink);min-width:6px;position:relative}
.bar .bt{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);font-size:9.5px;color:var(--muted);white-space:nowrap}
.bar .bd{position:absolute;top:100%;left:50%;transform:translateX(-50%);font-size:9.5px;color:var(--muted);white-space:nowrap;margin-top:4px}
.pill{display:inline-block;font-family:'Space Grotesk',sans-serif;font-size:12px;letter-spacing:.08em;text-transform:uppercase;padding:7px 16px;border:1px solid var(--line);margin-right:8px;color:var(--muted);text-decoration:none}
.pill:hover{border-color:var(--ink)}
.pill.on{border-color:var(--ink);color:var(--ink);background:#f5f5f5}
.pill.ok{border-color:var(--ok);color:var(--ok)}
.pill.bad{border-color:var(--danger);color:var(--danger)}
.health{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:26px}
.health .pill{padding:8px 14px;margin-right:0}
.visitor-banner{border:1px solid var(--line);background:#fafafa;padding:12px 16px;font-size:13px;color:var(--muted);margin-bottom:24px}
.badge{display:inline-block;font-family:'Space Grotesk',sans-serif;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;padding:6px 14px;border:1px solid var(--ok);color:var(--ok)}
.badge.off{border-color:var(--danger);color:var(--danger)}
.danger-btn{background:#fff;color:var(--danger);border-color:var(--danger)}
.danger-btn:hover{background:var(--danger);color:#fff}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:26px}
@media(max-width:720px){.two-col{grid-template-columns:1fr}}
</style>
"""

def cookie_ok():
    return db.session_valid(request.cookies.get("session"))

def current_role():
    return db.session_role(request.cookies.get("session"))

def _visitor_emails():
    raw = _env_value("PRIVY_VISITOR_EMAILS") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]

def require_login():
    if not cookie_ok():
        abort(redirect("/login"))

@app.route("/")
def index():
    if cookie_ok():
        return redirect("/dashboard")
    return redirect("/login")

# ---------- LOGIN ----------
# El acceso por contraseña fue ELIMINADO (decisión de seguridad, 2026-08).
# La única puerta es Privy: landing -> email + OTP -> ticket -> sesión.
# Emergencias: SSH al servidor.
@app.route("/login", methods=["GET", "POST"])
def login():
    return BASE_CSS + """
    <div class='msg'>
      <div class='bar'></div>
      <div class='idx'>DORSHA · ADMIN</div>
      <h1>🔒 Acceso con email y código</h1>
      <p class='muted' style='margin-bottom:20px'>El login por contraseña fue eliminado. El acceso al panel es solo con email + código desde la landing.</p>
      <a href='https://dorsha.devcristobalvc.com/login'><button type='button'>Entrar con email y código →</button></a>
      <p class='muted' style='margin-top:18px;font-size:12px'>¿Emergencia? Accede por SSH al servidor (<code>127.0.0.1:5057</code>).</p>
    </div>"""


@app.route("/setup", methods=["GET", "POST"])
def setup():
    return redirect("/login")

@app.route("/logout")
def logout():
    resp = make_response(redirect("/login"))
    resp.delete_cookie("session")
    return resp

# ---------- AUTO-LOGIN vía ticket (landing Privy -> Vercel) ----------
def _env_value(key, default=None):
    try:
        for line in open(ENV_PATH):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default

@app.route("/auth/ticket")
def auth_ticket():
    t = request.args.get("t", "")
    e = request.args.get("e", "")
    m = request.args.get("m", "")
    secret = _env_value("PRIVY_TICKET_SECRET")
    if not secret:
        return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div><h1>❌ Ticket no configurado</h1><p class='muted'>Falta PRIVY_TICKET_SECRET en ~/.hermes/.env</p></div>", 500
    try:
        exp = int(e)
    except ValueError:
        abort(403)
    expected = hmac.new(secret.encode(), f"{m}:{e}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, t):
        abort(403)
    if exp < time.time() * 1000:
        abort(403)
    allowed = _env_value("PRIVY_ALLOWED_EMAIL")
    if not allowed:
        return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div><h1>❌ Email no configurado</h1><p class='muted'>Falta PRIVY_ALLOWED_EMAIL en ~/.hermes/.env</p></div>", 500
    visitors = _visitor_emails()
    if m != allowed and m not in visitors:
        abort(403)
    role = "admin" if m == allowed else "visitor"
    token = db.create_session(role)
    resp = make_response(redirect("/dashboard"))
    resp.set_cookie("session", token, httponly=True, samesite="Lax", max_age=3600*12)
    return resp

# ---------- helpers de allowlist ----------
def get_env_allowed():
    if not os.path.exists(ENV_PATH):
        return []
    content = open(ENV_PATH, encoding="utf-8").read()
    m = re.search(r"^TELEGRAM_ALLOWED_USERS=(.*)$", content, re.MULTILINE)
    if not m:
        return []
    return [x.strip() for x in m.group(1).split(",") if x.strip()]

def set_env_allowed(ids):
    content = open(ENV_PATH, encoding="utf-8").read()
    new_line = "TELEGRAM_ALLOWED_USERS=" + ",".join(ids)
    if re.search(r"^TELEGRAM_ALLOWED_USERS=.*$", content, re.MULTILINE):
        content = re.sub(r"^TELEGRAM_ALLOWED_USERS=.*$", new_line, content, flags=re.MULTILINE)
    else:
        content += f"\n{new_line}\n"
    open(ENV_PATH, "w", encoding="utf-8").write(content)
    # tambien en config.yaml -> telegram.allow_from (segun pitfall documentado)
    try:
        import yaml
        cfg = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
        cfg.setdefault("telegram", {})["allow_from"] = [int(x) for x in ids]
        yaml.safe_dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    except Exception as e:
        print("warn config.yaml:", e, file=sys.stderr)

def restart_gateway():
    # cron trick documentado en la skill telegram-user-access
    script = "/tmp/gateway_restart.sh"
    open(script, "w").write("#!/bin/bash\nsystemctl --user restart hermes-gateway.service\n")
    os.chmod(script, 0o755)
    subprocess.run(["bash", script], timeout=20)
    try:
        os.remove(script)
    except OSError:
        pass

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if not cookie_ok():
        return redirect("/login")
    db.sync_users_from_channel_directory()
    db.expire_stale_actions()
    users = db.list_users()
    env_allowed = set(get_env_allowed())
    actions = db.list_pending_actions()
    role = current_role()
    is_visitor = role != "admin"

    rows = ""
    for u in users:
        cid = u["chat_id"]
        is_admin = cid == SUPER_ADMIN
        blocked = cid not in env_allowed
        tag = f"<span class='tag blocked'>BLOQUEADO</span>" if blocked else "<span class='tag active'>activo</span>"
        btn = "" if (is_admin or is_visitor) else (
            f"<button class='ghost' onclick=\"act('/users/{cid}/unblock')\">Desbloquear</button>"
            if blocked else
            f"<button class='danger' onclick=\"act('/users/{cid}/block')\">Bloquear</button>"
        )
        admin_tag = " 👑 admin" if is_admin else ""
        rows += f"<div class='row'><div>{u['name'] or cid}{admin_tag}<br><span class='muted'>{cid}</span></div><div>{tag} {btn}</div></div>"

    act_rows = ""
    for a in actions:
        act_btns = "" if is_visitor else (
            f"<div class='btnrow'><button onclick=\"act('/actions/{a['id']}/approve')\">Aprobar</button>"
            f"<button class='danger' onclick=\"act('/actions/{a['id']}/deny')\">Negar</button></div>")
        act_rows += f"""<div class='row'><div>
            <b>{a['chat_name'] or a['chat_id']}</b> pidió:<br>
            <span class='muted'>{a['action_desc']}</span><br>
            <span class='muted'>expira: {a['expires_at'][:16]}</span>
            </div>{act_btns}</div>"""
    if not act_rows:
        act_rows = "<p class='muted'>No hay acciones pendientes.</p>"

    # ---- MÉTRICAS (mini, 7d) ----
    try:
        ov7 = metrics_mod.overview(7)
        m_cards = "".join(
            f"<div class='mcard'><div class='v'>{_fmt(ov7[k])}</div><div class='l'>{lbl}</div></div>"
            for k, lbl in [("sessions", "Sesiones"), ("messages", "Mensajes"),
                           ("total_tokens", "Tokens"), ("cost_usd", "Costo $")])
        metrics_card = f"""
      <div class='card'>
        <span class='idx'>03 — MÉTRICAS</span>
        <h2>Últimos 7 días</h2>
        <div class='cards' style='margin:14px 0 6px'>{m_cards}</div>
        <p style='margin-top:10px'><a href='/metrics'>Ver métricas completas →</a></p>
      </div>"""
    except Exception:
        metrics_card = ""

    # ---- SISTEMA / KILL SWITCH ----
    try:
        off, gw = system_status()
        events = db.list_system_events(5)
        ev_rows = "".join(
            f"<div class='row'><div><b>{e['event']}</b><br><span class='muted'>{e['detail'][:70]}</span></div>"
            f"<div class='muted'>{e['created_at'][11:19]}</div></div>"
            for e in events) or "<p class='muted'>Sin eventos registrados.</p>"
        badge = ("<span class='badge off'>⛔ APAGADO</span>"
                 if off else f"<span class='badge'>● ACTIVO · gateway {gw}</span>")
        if is_visitor:
            system_card = f"""
      <div class='card'>
        <span class='idx'>04 — SISTEMA</span>
        <h2>Kill switch</h2>
        <div style='margin:14px 0 18px'>{badge}</div>
        <p class='muted'>Modo visitante: solo lectura. Contacta al administrador para apagar/reactivar.</p>
      </div>"""
        else:
            system_card = f"""
      <div class='card'>
        <span class='idx'>04 — SISTEMA</span>
        <h2>Kill switch</h2>
        <div style='margin:14px 0 18px'>{badge}</div>
        <div class='btnrow' style='justify-content:flex-start'>
          <form method='post' action='/system/off' onsubmit="return confirm('¿Apagar TODO el sistema? El bot dejará de responder y los crons se pausan.') && withMaster(this)">
            <button class='danger-btn' type='submit'>🛑 Apagar sistema</button>
          </form>
          <form method='post' action='/system/on' onsubmit="return withMaster(this)">
            <button type='submit'>▶ Reactivar</button>
          </form>
        </div>
        <div style='margin-top:18px'>{ev_rows}</div>
      </div>"""
    except Exception:
        system_card = ""

    # ---- SESIONES ACTIVAS ----
    try:
        sess = db.list_sessions()
        my_token = request.cookies.get("session")
        sess_rows = ""
        for s in sess:
            tag = ("<span class='tag active'>activa</span>" if s["active"] else "<span class='tag'>expirada</span>")
            mine = " <span class='muted'>(esta)</span>" if s["token"] == my_token else ""
            revoke = "" if (is_visitor or not s["active"]) else (
                f"<form method='post' action='/sessions/{s['token']}/revoke' "
                f"onsubmit=\"return confirm('¿Revocar esta sesión? Se cerrará en ese dispositivo.')\">"
                f"<button class='danger' type='submit'>Revocar</button></form>")
            sess_rows += f"""<div class='row'><div><b>{s['token_masked']}</b>{mine} {tag}<br>
                <span class='muted'>{s['role']} · creada {s['created_at']} · expira {s['expires_at']}</span></div>{revoke}</div>"""
        if not sess_rows:
            sess_rows = "<p class='muted'>Sin sesiones.</p>"
        sessions_card = f"""
      <div class='card'>
        <span class='idx'>05 — SESIONES</span>
        <h2>Sesiones activas</h2>
        {sess_rows}
      </div>"""
    except Exception:
        sessions_card = ""

    # ---- SEMÁFORO DE SALUD ----
    try:
        gw = metrics_mod.gateway_status()
        tun_state, tun_url = metrics_mod.tunnel_status()
        bal, bal_status = metrics_mod.balance()
        bal_num = 0.0
        m = re.search(r"[\d.]+", bal or "")
        if m:
            bal_num = float(m.group(0))
        fails_n, total_n = metrics_mod.cron_failures()

        def hpill(label, ok):
            return f"<span class='pill {'ok' if ok else 'bad'}'>{label}</span>"
        health = ("<div class='health'>"
                  + hpill("Gateway " + ("🟢" if gw == "active" else "🔴 " + gw), gw == "active")
                  + hpill("Túnel " + ("🟢" if tun_state == "ok" else "🔴 " + tun_state), tun_state == "ok")
                  + hpill("Saldo $" + (f"{bal_num:.2f}" if bal_num else "?") + (" ⚠️" if bal_num < 2 else " ✅"), bal_num >= 2)
                  + hpill(f"Crons {fails_n}/{total_n}" + ("" if fails_n == 0 else " 🔴"), fails_n == 0)
                  + "</div>")
    except Exception:
        health = ""

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/secrets'>Secretos</a><a href='/logs'>Logs</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>

      {('<p class="visitor-banner">👁 <b>Modo visitante</b> — solo lectura: puedes ver todo, pero no modificar nada.</p>' if is_visitor else '')}

      {health}

      <div class='card'>
        <span class='idx'>01 — PENDIENTES</span>
        <h2>Acciones sensibles</h2>
        {act_rows}
      </div>

      <div class='card'>
        <span class='idx'>02 — ACCESO</span>
        <h2>Usuarios</h2>
        {rows}
      </div>

      {metrics_card}

      {system_card}

      {sessions_card}
    </div>
    <script>
    function act(url) {{
      fetch(url, {{method:'POST'}}).then(()=>location.reload());
    }}
    function withMaster(form){{
      const pw = prompt('🔐 Master password (vault):');
      if(pw === null) return false;
      let inp = form.querySelector('input[name="master_pw"]');
      if(!inp){{ inp = document.createElement('input'); inp.type='hidden'; inp.name='master_pw'; form.appendChild(inp); }}
      inp.value = pw;
      return true;
    }}
    </script>
    """

@app.route("/users/<chat_id>/block", methods=["POST"])
def block_user(chat_id):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    if chat_id == SUPER_ADMIN:
        abort(400)
    ids = [i for i in get_env_allowed() if i != chat_id]
    set_env_allowed(ids)
    db.set_blocked(chat_id, True)
    restart_gateway()
    return {"ok": True}

@app.route("/users/<chat_id>/unblock", methods=["POST"])
def unblock_user(chat_id):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    ids = get_env_allowed()
    if chat_id not in ids:
        ids.append(chat_id)
    set_env_allowed(ids)
    db.set_blocked(chat_id, False)
    restart_gateway()
    return {"ok": True}

@app.route("/actions/<aid>/approve", methods=["POST"])
def approve_action(aid):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    db.resolve_action(aid, "approved")
    return {"ok": True}

@app.route("/actions/<aid>/deny", methods=["POST"])
def deny_action(aid):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    db.resolve_action(aid, "denied")
    return {"ok": True}

# ---------- HISTORIAL DE MENSAJES (silencioso, via hook) ----------
@app.route("/history")
def history():
    if not cookie_ok():
        return redirect("/login")
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    filt = request.args.get("user_id", "")
    users = db.list_users()
    id_to_name = {u["chat_id"]: u["name"] for u in users}

    q = "SELECT * FROM message_log"
    params = []
    if filt:
        q += " WHERE user_id=?"
        params.append(filt)
    q += " ORDER BY id DESC LIMIT 200"
    rows = conn.execute(q, params).fetchall()
    conn.close()

    opts = "<option value=''>-- todos --</option>" + "".join(
        f"<option value='{u['chat_id']}' {'selected' if u['chat_id']==filt else ''}>{u['name'] or u['chat_id']}</option>"
        for u in users
    )

    items = ""
    for r in rows:
        name = id_to_name.get(r["user_id"], r["user_id"])
        items += f"""<div class='row' style='display:block'>
          <div class='muted'>{r['created_at'][:16]} · <b style='color:var(--ink)'>{name}</b> · {r['platform']}</div>
          <div style='margin-top:6px;font-size:14px'>{(r['message'] or '').replace('<','&lt;').replace('>','&gt;')[:600]}</div>
          <div style='margin-top:6px;font-size:13.5px;color:var(--muted);border-left:2px solid var(--line);padding-left:10px'>🤖 {(r['response'] or '(sin respuesta aun)').replace('<','&lt;').replace('>','&gt;')[:600]}</div>
        </div>"""
    if not items:
        items = "<p class='muted'>Sin mensajes registrados todavia.</p>"

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='card'>
        <span class='idx'>03 — HISTORIAL</span>
        <h2>Mensajes</h2>
        <form method='get' style='margin:14px 0 8px'>
          <select name='user_id' onchange='this.form.submit()'>
            {opts}
          </select>
        </form>
      </div>
      <div class='card'>{items}</div>
    </div>
    """

# ---------- KILL SWITCH ----------
EMERGENCY_FLAG = os.path.expanduser("~/.hermes/EMERGENCY_OFF")
CRON_STATE_BACKUP = os.path.expanduser("~/.hermes/emergency_cron_backup.json")
CRON_JOBS_PATH = os.path.expanduser("~/.hermes/cron/jobs.json")


def system_status():
    off = os.path.exists(EMERGENCY_FLAG)
    gw = "inactive"
    try:
        gw = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway.service"],
                            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        pass
    return off, gw


def _cron_pause_all(backup=True):
    d = json.load(open(CRON_JOBS_PATH))
    if backup:
        json.dump({j.get("id"): bool(j.get("enabled")) for j in d.get("jobs", [])},
                  open(CRON_STATE_BACKUP, "w"))
    for j in d.get("jobs", []):
        j["enabled"] = False
        j["state"] = "paused"
    json.dump(d, open(CRON_JOBS_PATH, "w"), indent=2, ensure_ascii=False)


def _cron_restore():
    try:
        backup = json.load(open(CRON_STATE_BACKUP))
    except Exception:
        backup = {}
    d = json.load(open(CRON_JOBS_PATH))
    for j in d.get("jobs", []):
        en = backup.get(j.get("id"), True)
        j["enabled"] = en
        j["state"] = "scheduled" if en else "paused"
    json.dump(d, open(CRON_JOBS_PATH, "w"), indent=2, ensure_ascii=False)


@app.route("/system/off", methods=["POST"])
def system_off():
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    try:
        _cron_pause_all()
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    open(EMERGENCY_FLAG, "w").write(datetime.now().isoformat())
    subprocess.run(["systemctl", "--user", "stop", "hermes-gateway.service"], timeout=20)
    db.log_system_event("SYSTEM_OFF", "Kill switch: gateway detenido + crons pausados", SUPER_ADMIN)
    return {"ok": True}


@app.route("/system/on", methods=["POST"])
def system_on():
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    try:
        _cron_restore()
    except Exception:
        pass
    if os.path.exists(EMERGENCY_FLAG):
        os.remove(EMERGENCY_FLAG)
    subprocess.run(["systemctl", "--user", "start", "hermes-gateway.service"], timeout=20)
    db.log_system_event("SYSTEM_ON", "Sistema reactivado: gateway + crons restaurados", SUPER_ADMIN)
    return {"ok": True}


@app.route("/sessions/<token>/revoke", methods=["POST"])
def session_revoke(token):
    if not cookie_ok() or current_role() != "admin":
        abort(403)
    db.delete_session(token)
    db.log_system_event("SESSION_REVOKE", f"sesión {token[:8]}… revocada", SUPER_ADMIN)
    return redirect("/dashboard")


# ---------- MÉTRICAS ----------
def _fmt(n):
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


@app.route("/metrics")
def metrics_page():
    if not cookie_ok():
        return redirect("/login")
    days_param = request.args.get("days", "7")
    days = {"7": 7, "30": 30}.get(days_param)  # None = todo

    ov = metrics_mod.overview(days)
    spend = metrics_mod.spend_by_user(days)
    errs = metrics_mod.errors_by_user(days)
    cron_fails, cron_total = metrics_mod.cron_failures()
    gw_err = metrics_mod.gateway_errors()
    act = metrics_mod.activity(14)
    cd = metrics_mod.cost_by_day(14)
    models = metrics_mod.models()
    plats = metrics_mod.platforms()
    tools = metrics_mod.top_tools(10)

    # ---- datos para Chart.js (14 días) ----
    series = metrics_mod.daily_series(14)
    ch_dates = json.dumps([s["date"][5:] for s in series])
    ch_msgs = json.dumps([s["messages"] for s in series])
    ch_sess = json.dumps([s["sessions"] for s in series])
    ch_cost = json.dumps([s["cost"] for s in series])
    ch_tin = json.dumps([s["tokens_in"] for s in series])
    ch_tout = json.dumps([s["tokens_out"] for s in series])
    ch_plats = json.dumps([p["platform"] for p in plats])
    ch_plat_n = json.dumps([p["sessions"] for p in plats])
    ch_tools = json.dumps([t["tool"] for t in tools][::-1])
    ch_tools_n = json.dumps([t["calls"] for t in tools][::-1])
    top_models = models[:6]
    ch_models = json.dumps([m["model"] for m in top_models][::-1])
    ch_models_n = json.dumps([round(m["cost"], 4) for m in top_models][::-1])

    # ---- diagrama de ejecución (pipeline vivo) ----
    gw = metrics_mod.gateway_status()
    tun_state, tun_url = metrics_mod.tunnel_status()
    bal, _ = metrics_mod.balance()
    bal_num = 0.0
    mm = re.search(r"[\d.]+", bal or "")
    if mm:
        bal_num = float(mm.group(0))
    fails_list, total_n = metrics_mod.cron_failures()
    fails_n = len(fails_list)

    def box(x, title, sub, ok):
        color = "#15803d" if ok else "#dc2626"
        return (f"<g><rect x='{x}' y='18' width='150' height='54' rx='8' fill='#fff' stroke='#e4e4e4'/>"
                f"<circle cx='{x+14}' cy='30' r='4' fill='{color}'/>"
                f"<text x='{x+24}' y='34' font-family='Space Grotesk,monospace' font-size='12' fill='#0a0a0a'>{title}</text>"
                f"<text x='{x+14}' y='54' font-family='monospace' font-size='9.5' fill='#5a5a5a'>{sub}</text></g>")

    def arrow(x1, x2, y=45):
        return (f"<line x1='{x1}' y1='{y}' x2='{x2}' y2='{y}' stroke='#0a0a0a' stroke-width='1.5'/>"
                f"<polygon points='{x2},{y} {x2-7},{y-3.5} {x2-7},{y+3.5}' fill='#0a0a0a'/>")

    diagram = f"""
    <svg viewBox='0 0 950 130' style='width:100%;max-width:950px' xmlns='http://www.w3.org/2000/svg'>
      {box(10, 'ENTRADA', 'Telegram · Webhook', True)}
      {arrow(160, 188)}
      {box(188, 'GATEWAY', 'puente de mensajes', gw == 'active')}
      {arrow(338, 366)}
      {box(366, 'AGENTE', 'razona + ejecuta', True)}
      {arrow(516, 544, 36)}
      {arrow(516, 544, 80)}
      {box(544, 'MODELO', 'DeepSeek API', bal_num >= 2)}
      {box(544, 'HERRAMIENTAS', 'term · web · cron · imgs', True)}
      <text x='550' y='105' font-family='monospace' font-size='9' fill='#5a5a5a'>
        saldo ${'%.2f' % bal_num} {'✅' if bal_num >= 2 else '⚠️'} · crons {fails_n}/{total_n} {'✅' if fails_n == 0 else '🔴'} · túnel {'ok' if tun_state == 'ok' else tun_state}</text>
    </svg>"""

    maxc = max([a["count"] for a in act] or [1])
    bars = "".join(
        f"<div class='bar' style='height:{max(4, int(a['count']/maxc*100))}%'>"
        f"<span class='bt'>{a['count']}</span><span class='bd'>{a['date'][5:]}</span></div>"
        for a in act) or "<p class='muted'>Sin actividad.</p>"

    maxcost = max([c["cost"] for c in cd] or [0.01])
    cost_bars = "".join(
        f"<div class='bar' style='height:{max(4, int(c['cost']/maxcost*100))}%'>"
        f"<span class='bt'>${c['cost']}</span><span class='bd'>{c['date'][5:]}</span></div>"
        for c in cd)

    spend_rows = "".join(
        f"<tr><td>{s['user']}</td><td class='muted'>{s['chat_id']}</td><td>{s['sessions']}</td>"
        f"<td>{s['calls']}</td><td>{_fmt(s['tokens'])}</td><td>${s['cost']}</td></tr>"
        for s in spend) or "<tr><td colspan='6' class='muted'>Sin datos</td></tr>"

    err_rows = "".join(
        f"<tr><td>{e['user']}</td><td>{e['errors']}</td></tr>" for e in errs) or "<tr><td colspan='2' class='muted'>Sin errores</td></tr>"

    cron_rows = "".join(
        f"<tr><td>{c['name']}</td><td class='muted'>{c['last_run']}</td><td class='muted'>{c['last_error']}</td></tr>"
        for c in cron_fails) or "<tr><td colspan='3' class='muted'>Sin fallos recientes</td></tr>"

    model_rows = "".join(
        f"<tr><td>{m['model']}</td><td>{m['sessions']}</td><td>{_fmt(m['tokens'])}</td><td>${m['cost']}</td></tr>"
        for m in models)
    plat_rows = "".join(
        f"<tr><td>{p['platform']}</td><td>{p['sessions']}</td></tr>" for p in plats)
    tool_rows = "".join(
        f"<tr><td>{t['tool']}</td><td>{t['calls']}</td></tr>" for t in tools)

    period_tabs = "".join(
        f"<a class='pill {'on' if days_param == k else ''}' href='/metrics?days={k}'>{lbl}</a>"
        for k, lbl in [("7", "7 días"), ("30", "30 días"), ("all", "Todo")])

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/secrets'>Secretos</a><a href='/logs'>Logs</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='idx'>03 — MÉTRICAS</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Métricas del sistema</h1>
      <p class='muted' style='margin-bottom:22px'>Gasto por usuario · errores · actividad</p>
      <div style='margin-bottom:24px'>{period_tabs}</div>

      <div class='cards'>
        <div class='mcard'><div class='v'>{ov['sessions']}</div><div class='l'>Sesiones</div></div>
        <div class='mcard'><div class='v'>{_fmt(ov['messages'])}</div><div class='l'>Mensajes</div></div>
        <div class='mcard'><div class='v'>{_fmt(ov['api_calls'])}</div><div class='l'>Llamadas API</div></div>
        <div class='mcard'><div class='v'>{_fmt(ov['total_tokens'])}</div><div class='l'>Tokens</div></div>
        <div class='mcard'><div class='v'>${ov['cost_usd']}</div><div class='l'>Costo est.</div></div>
      </div>

      <div class='card'>
        <span class='idx'>DIAGRAMA DE EJECUCIÓN</span>
        <h2>Cómo fluye un mensaje — estado en vivo</h2>
        <div style='margin-top:16px'>{diagram}</div>
        <p class='muted' style='margin-top:10px'>Cada punto indica salud en vivo: verde = ok, rojo = problema. El modelo se marca ⚠️ si el saldo baja de $2.</p>
      </div>

      <div class='card'>
        <span class='idx'>ACTIVIDAD</span>
        <h2>Mensajes y sesiones por día — últimos 14 días</h2>
        <canvas id='chActivity' height='110'></canvas>
      </div>

      <div class='card'>
        <span class='idx'>COSTO</span>
        <h2>Costo estimado por día (USD) — últimos 14 días</h2>
        <canvas id='chCost' height='110'></canvas>
      </div>

      <div class='two-col'>
        <div class='card'>
          <span class='idx'>TOKENS</span>
          <h2>Tokens in/out por día</h2>
          <canvas id='chTokens' height='150'></canvas>
        </div>
        <div class='card'>
          <span class='idx'>PLATAFORMAS</span>
          <h2>Sesiones por origen</h2>
          <canvas id='chPlats' height='150'></canvas>
        </div>
      </div>

      <div class='two-col'>
        <div class='card'>
          <span class='idx'>HERRAMIENTAS</span>
          <h2>Top 10 herramientas</h2>
          <canvas id='chTools' height='170'></canvas>
        </div>
        <div class='card'>
          <span class='idx'>MODELOS</span>
          <h2>Costo por modelo (USD)</h2>
          <canvas id='chModels' height='170'></canvas>
        </div>
      </div>

      <div class='two-col'>
        <div class='card'>
          <span class='idx'>GASTO</span>
          <h2>Por usuario</h2>
          <table><tr><th>Usuario</th><th>ID</th><th>Ses.</th><th>Llam.</th><th>Tokens</th><th>Costo</th></tr>{spend_rows}</table>
        </div>
        <div class='card'>
          <span class='idx'>ERRORES</span>
          <h2>Tool-errors por usuario</h2>
          <table><tr><th>Usuario</th><th>Errores</th></tr>{err_rows}</table>
        </div>
      </div>

      <div class='card'>
        <span class='idx'>AUTOMATIZACIONES</span>
        <h2>Crons con fallo ({len(cron_fails)} de {cron_total}) · errores gateway 24h: {gw_err}</h2>
        <table><tr><th>Job</th><th>Último run</th><th>Error</th></tr>{cron_rows}</table>
      </div>

      <div class='two-col'>
        <div class='card'>
          <span class='idx'>MODELOS</span>
          <h2>Tokens por modelo</h2>
          <table><tr><th>Modelo</th><th>Ses.</th><th>Tokens</th><th>Costo</th></tr>{model_rows}</table>
        </div>
        <div class='card'>
          <span class='idx'>PLATAFORMAS</span>
          <h2>Sesiones por origen</h2>
          <table><tr><th>Plataforma</th><th>Sesiones</th></tr>{plat_rows}</table>
        </div>
      </div>

      <div class='card'>
        <span class='idx'>HERRAMIENTAS</span>
        <h2>Top 10</h2>
        <table><tr><th>Tool</th><th>Llamadas</th></tr>{tool_rows}</table>
      </div>
    </div>
    <script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'></script>
    <script>
    Chart.defaults.font.family = "'Inter',sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = '#5a5a5a';
    const INK = '#0a0a0a', MUT = '#5a5a5a', LINE = '#e4e4e4';
    const GREEN = '#15803d', RED = '#dc2626', AMBER = '#b45309', BLUE = '#2563eb';
    function mk(id, cfg){{ const c = document.getElementById(id); if(!c || typeof Chart === 'undefined') return; new Chart(c, cfg); }}
    mk('chActivity', {{
      type:'line',
      data:{{ labels:{ch_dates}, datasets:[
        {{label:'Mensajes', data:{ch_msgs}, borderColor:INK, backgroundColor:'rgba(10,10,10,.08)', fill:true, tension:.3, pointRadius:2}},
        {{label:'Sesiones', data:{ch_sess}, borderColor:BLUE, tension:.3, pointRadius:2}}
      ]}},
      options:{{ scales:{{ y:{{ beginAtZero:true, grid:{{color:LINE}} }}, x:{{ grid:{{display:false}} }} }} }}
    }});
    mk('chCost', {{
      type:'bar',
      data:{{ labels:{ch_dates}, datasets:[{{label:'USD', data:{ch_cost}, backgroundColor:AMBER, borderRadius:3}}] }},
      options:{{ plugins:{{ legend:{{display:false}} }}, scales:{{ y:{{ beginAtZero:true, grid:{{color:LINE}} }}, x:{{ grid:{{display:false}} }} }} }}
    }});
    mk('chTokens', {{
      type:'bar',
      data:{{ labels:{ch_dates}, datasets:[
        {{label:'Input', data:{ch_tin}, backgroundColor:'rgba(10,10,10,.75)', borderRadius:3}},
        {{label:'Output', data:{ch_tout}, backgroundColor:'rgba(37,99,235,.75)', borderRadius:3}}
      ]}},
      options:{{ scales:{{ x:{{stacked:true, grid:{{display:false}} }}, y:{{stacked:true, beginAtZero:true, grid:{{color:LINE}}}} }} }}
    }});
    mk('chPlats', {{
      type:'doughnut',
      data:{{ labels:{ch_plats}, datasets:[{{data:{ch_plat_n}, backgroundColor:['#0a0a0a','#2563eb','#15803d','#b45309','#7c3aed','#dc2626','#0891b2'], borderWidth:0}}] }},
      options:{{ plugins:{{ legend:{{position:'bottom'}} }} }}
    }});
    mk('chTools', {{
      type:'bar',
      data:{{ labels:{ch_tools}, datasets:[{{label:'Llamadas', data:{ch_tools_n}, backgroundColor:INK, borderRadius:3}}] }},
      options:{{ indexAxis:'y', plugins:{{ legend:{{display:false}} }}, scales:{{ x:{{ beginAtZero:true, grid:{{color:LINE}} }}, y:{{ grid:{{display:false}} }} }} }}
    }});
    mk('chModels', {{
      type:'bar',
      data:{{ labels:{ch_models}, datasets:[{{label:'USD', data:{ch_models_n}, backgroundColor:RED, borderRadius:3}}] }},
      options:{{ indexAxis:'y', plugins:{{ legend:{{display:false}} }}, scales:{{ x:{{ beginAtZero:true, grid:{{color:LINE}} }}, y:{{ grid:{{display:false}} }} }} }}
    }});
    </script>
    """


@app.route("/logs")
def logs_page():
    if not cookie_ok():
        return redirect("/login")
    return BASE_CSS + """
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/logs'>Logs</a><a href='/secrets'>Secretos</a><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='idx'>07 — LOGS</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Logs del gateway</h1>
      <p class='muted' style='margin-bottom:22px'>Últimas líneas de ~/.hermes/logs/gateway.log — auto-refresh cada 10s.</p>
      <div style='display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap'>
        <span class='tag'>autorefresh</span>
        <button class='ghost' type='button' onclick='refreshLog()'>⟳ Refrescar ahora</button>
        <span class='muted' id='logmeta'></span>
      </div>
      <div class='card' style='padding:0;overflow:hidden'>
        <pre id='logbox' style='margin:0;padding:16px;font-family:monospace;font-size:11.5px;line-height:1.6;max-height:70vh;overflow:auto;white-space:pre-wrap;word-break:break-word'></pre>
      </div>
    </div>
    <script>
    function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function paint(lines){
      const box = document.getElementById('logbox');
      box.innerHTML = lines.map(l => {
        let c = '#5a5a5a';
        if (/error|traceback|exception/i.test(l)) c = '#dc2626';
        else if (/warn/i.test(l)) c = '#b45309';
        else if (/info/i.test(l)) c = '#15803d';
        else if (/http|POST|GET/i.test(l)) c = '#2563eb';
        return `<div style='color:${c}'>${esc(l)}</div>`;
      }).join('');
    }
    async function refreshLog(){
      try{
        const r = await fetch('/logs/api?n=400');
        const d = await r.json();
        paint(d.lines);
        const meta = document.getElementById('logmeta');
        meta.textContent = d.lines.length + ' líneas · ' + new Date().toLocaleTimeString();
      }catch(e){ document.getElementById('logbox').textContent = '❌ no pude leer el log'; }
    }
    refreshLog();
    setInterval(refreshLog, 10000);
    </script>
    """


@app.route("/logs/api")
def logs_api():
    if not cookie_ok():
        abort(403)
    try:
        n = min(int(request.args.get("n", "400")), 2000)
    except (TypeError, ValueError):
        n = 400
    lines = _tail_log(n)
    return {"lines": lines}


# ---------- CRONS (gestión desde el panel) ----------
def _load_crons():
    return json.load(open(CRON_JOBS_PATH))


def _save_crons(d):
    json.dump(d, open(CRON_JOBS_PATH, "w"), indent=2, ensure_ascii=False)


@app.route("/crons")
def crons_page():
    if not cookie_ok():
        return redirect("/login")
    is_visitor = current_role() != "admin"
    d = _load_crons()
    jobs = d.get("jobs", [])
    rows = ""
    for j in sorted(jobs, key=lambda x: (not x.get("enabled"), (x.get("name") or "").lower())):
        jid = j.get("id")
        name = j.get("name") or jid or "?"
        sched = (j.get("schedule") or {}).get("display") or j.get("schedule_display") or "-"
        last_run = (j.get("last_run_at") or "-")[:16]
        status = j.get("last_status") or "-"
        st_badge = ("<span class='badge'>scheduled</span>" if j.get("enabled")
                    else "<span class='badge off'>paused</span>")
        status_html = (f"<span class='pill {'ok' if status == 'ok' else 'bad'}'>"
                       + escape(status) + "</span>" if status != "-" else "<span class='muted'>-</span>")
        toggle_btn = "" if is_visitor else (
            f"<form method='post' action='/crons/{jid}/toggle'><button class='ghost' type='submit'>"
            + ("⏸ Pausar" if j.get("enabled") else "▶ Reanudar") + "</button></form>")
        run_btn = "" if is_visitor else f"<form method='post' action='/crons/{jid}/run'><button type='submit'>Ejecutar</button></form>"
        out_btn = f"<a href='/crons/{jid}/output'><button class='ghost' type='button'>Log</button></a>"
        rows += (f"<div class='row'><div style='min-width:0'><b>{escape(name)}</b><br>"
                 f"<span class='muted'>{escape(sched)} · último: {escape(last_run)}</span></div>"
                 f"<div class='btnrow'>{st_badge}{status_html}{toggle_btn}{run_btn}{out_btn}</div></div>")
    if not rows:
        rows = "<p class='muted'>Sin jobs.</p>"
    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/metrics'>Métricas</a><a href='/secrets'>Secretos</a><a href='/logs'>Logs</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>
      {('<p class="visitor-banner">👁 <b>Modo visitante</b> — solo lectura.</p>' if is_visitor else '')}
      <div class='idx'>02 — AUTOMATIZACIONES</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Crons</h1>
      <p class='muted' style='margin-bottom:22px'>{len(jobs)} jobs · pausar, reanudar, ejecutar y ver logs</p>
      <div class='card'>{rows}</div>
    </div>"""


@app.route("/crons/<jid>/toggle", methods=["POST"])
def cron_toggle(jid):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    d = _load_crons()
    for j in d.get("jobs", []):
        if j.get("id") == jid:
            en = not j.get("enabled")
            j["enabled"] = en
            j["state"] = "scheduled" if en else "paused"
            if en:
                j["paused_at"] = None
                j["paused_reason"] = None
            else:
                j["paused_at"] = datetime.now().isoformat()
                j["paused_reason"] = "admin panel"
            db.log_system_event("CRON_TOGGLE", f"{j.get('name')}: {'reanudado' if en else 'pausado'}", SUPER_ADMIN)
    _save_crons(d)
    return redirect("/crons")


@app.route("/crons/<jid>/run", methods=["POST"])
def cron_run(jid):
    if not cookie_ok():
        abort(403)
    if current_role() != "admin":
        abort(403)
    d = _load_crons()
    for j in d.get("jobs", []):
        if j.get("id") == jid and j.get("enabled"):
            j["fire_claim"] = {"at": datetime.now().isoformat(), "by": "admin-panel"}
            db.log_system_event("CRON_RUN", f"Ejecución forzada: {j.get('name')}", SUPER_ADMIN)
    _save_crons(d)
    return redirect("/crons")


@app.route("/crons/<jid>/output")
def cron_output(jid):
    if not cookie_ok():
        return redirect("/login")
    path = os.path.expanduser(f"~/.hermes/cron/output/{jid}")
    try:
        content = open(path, encoding="utf-8", errors="replace").read()
        lines = content.splitlines()[-80:]
        body = "<br>".join(escape(l) for l in lines) or "<span class='muted'>Sin output.</span>"
    except Exception:
        body = "<span class='muted'>Sin archivo de output.</span>"
    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/crons'>← Crons</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='idx'>LOG DE CRON</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Últimas 80 líneas</h1>
      <p class='muted' style='margin-bottom:22px'>{escape(jid)}</p>
      <div class='card' style='font-family:monospace;font-size:12px;white-space:pre-wrap;line-height:1.5'>{body}</div>
    </div>"""


# ---------- GESTOR DE KEYS ----------
def _admin_only():
    if not cookie_ok():
        return redirect("/login")
    if current_role() != "admin":
        return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div><h1>🔒 Solo administrador</h1><p class='muted'>El gestor de claves es exclusivo del rol admin.</p></div>"
    return None


def _require_master(form):
    """Valida la master password del vault para acciones destructivas.
    Devuelve None si OK, o (html_error, 403) si falta el vault o la password no coincide."""
    if not db.password_is_set():
        return (BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div>"
                "<h1>🔐 Vault requerido</h1><p class='muted'>Primero configura la master password en "
                "<a href='/secrets'>Secretos</a>. Las acciones destructivas la exigen.</p></div>", 403)
    if not db.check_password((form or {}).get("master_pw", "")):
        db.log_system_event("VAULT_FAIL", "Master password incorrecta en acción sensible", SUPER_ADMIN)
        return (BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div>"
                "<h1>🔒 Master password incorrecta</h1>"
                "<p class='muted'>Acción cancelada. <a href='/dashboard'>← Panel</a></p></div>", 403)
    return None


@app.route("/keys")
def keys_page():
    denied = _admin_only()
    if denied:
        return denied
    env_keys = km.list_env_keys()
    pools = km.list_pools()
    user_keys = km.list_user_keys()
    users = db.list_users()

    env_rows = ""
    for k in env_keys:
        test_btn = f"<button class='ghost' type='button' onclick=\"testKey('env','{k['name']}',this)\">Test</button>"
        env_rows += f"""<div class='row'><div style='min-width:0'>
            <b>{escape(k['name'])}</b> <span class='tag'>{k['provider']}</span><br>
            <span class='muted' style='font-family:monospace;font-size:12px'>{escape(k['masked'])}</span></div>
            <div style='display:flex;flex-direction:column;gap:8px;align-items:flex-end'>
            <div class='btnrow'>{test_btn}
            <form method='post' action='/keys/env/delete' onsubmit="return confirm('¿Borrar {escape(k['name'])}?') && withMaster(this)">
              <input type='hidden' name='name' value='{escape(k['name'])}'>
              <button class='danger' type='submit'>Borrar</button>
            </form></div>
            <form method='post' action='/keys/env/save' style='display:flex;gap:8px' onsubmit="return withMaster(this)">
              <input type='hidden' name='name' value='{escape(k['name'])}'>
              <input type='text' name='value' placeholder='nuevo valor…' style='margin:0;padding:7px 10px;width:260px'>
              <button class='ghost' type='submit'>Guardar</button>
            </form></div></div>"""
    if not env_rows:
        env_rows = "<p class='muted'>Sin claves detectadas.</p>"

    pool_html = ""
    for p in pools:
        cred_rows = ""
        for c in p["creds"]:
            st_class = {"ok": "ok", "error": "bad", "exhausted": "bad", "unauthorized": "bad"}.get(c["status"], "")
            st = f"<span class='pill {st_class}'>{c['status']}</span>" if c["status"] != "unknown" else "<span class='pill'>?</span>"
            err = f"<span class='muted'>{escape(c['error'])}</span>" if c["error"] else ""
            cred_rows += f"""<div class='row'><div style='min-width:0'>
                <b>{escape(c['label'])}</b> {st}<br>
                <span class='muted'>{escape(c['masked'])}{' · ' + escape(c['base_url']) if c['base_url'] else ''}</span><br>{err}</div>
                <div class='btnrow'>
                <button class='ghost' type='button' onclick="testKey('pool','{c['id']}',this)">Test</button>
                <form method='post' action='/keys/pool/remove' onsubmit="return confirm('¿Quitar {escape(c['label'])} del pool?') && withMaster(this)">
                  <input type='hidden' name='provider' value='{escape(p['provider'])}'>
                  <input type='hidden' name='id' value='{c['id']}'>
                  <button class='danger' type='submit'>Quitar</button>
                </form></div></div>"""
        if not cred_rows:
            cred_rows = "<p class='muted'>Pool vacío.</p>"
        pool_html += f"""<div class='card'>
            <span class='idx'>POOL</span>
            <h2>{escape(p['provider'])} · {p['count']} credenciales</h2>
            {cred_rows}
            <form method='post' action='/keys/pool/add' style='display:flex;gap:8px;margin-top:16px;flex-wrap:wrap' onsubmit="return withMaster(this)">
              <input type='hidden' name='provider' value='{escape(p['provider'])}'>
              <input type='text' name='label' placeholder='etiqueta (ej: key-extra-1)' style='margin:0;padding:7px 10px;flex:1;min-width:160px'>
              <input type='text' name='api_key' placeholder='sk-…' style='margin:0;padding:7px 10px;flex:2;min-width:220px'>
              <button class='ghost' type='submit'>+ Agregar al pool</button>
            </form></div>"""

    uk_map = {u["user_id"]: u for u in user_keys}
    user_rows = ""
    for u in users:
        cid = u["chat_id"]
        uk = uk_map.get(cid)
        if uk:
            user_rows += f"""<div class='row'><div><b>{u['name'] or cid}</b><br>
                <span class='muted'>{cid} · {escape(uk.get('provider','?'))} / {escape(uk.get('model','?'))} · key: {escape(uk.get('key_label','?'))}</span></div>
                <form method='post' action='/keys/user/unassign'><input type='hidden' name='user_id' value='{cid}'>
                <button class='danger' type='submit'>Quitar asignación</button></form></div>"""
        else:
            user_rows += f"""<div class='row'><div><b>{u['name'] or cid}</b><br><span class='muted'>{cid} · global</span></div></div>"""
    if not user_rows:
        user_rows = "<p class='muted'>Sin usuarios registrados.</p>"

    user_select = "".join(f"<option value='{u['chat_id']}'>{escape(u['name'] or u['chat_id'])} ({u['chat_id']})</option>" for u in users)
    provider_select = "".join(f"<option value='{p}'>{p}</option>" for p in ["deepseek", "openai", "openrouter", "anthropic", "google", "vercel", "github", "supabase"])

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/crons'>Crons</a><a href='/metrics'>Métricas</a><a href='/secrets'>Secretos</a><a href='/logs'>Logs</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='idx'>05 — CLAVES</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Gestor de API keys</h1>
      <p class='muted' style='margin-bottom:22px'>Globales (.env), pools (auth.json) y asignación por usuario.
      Los cambios en .env aplican tras reiniciar el gateway; los pools aplican al siguiente uso.</p>

      <div class='card'>
        <span class='idx'>GLOBALES</span>
        <h2>Claves del entorno — todos los usuarios</h2>
        {env_rows}
      </div>

      {pool_html}

      <div class='card'>
        <span class='idx'>POR USUARIO</span>
        <h2>Asignación de claves</h2>
        <p class='muted' style='margin-bottom:14px'>Registro de asignación por usuario. Nota: Hermes hoy enruta a todos por la key global; la asignación queda documentada para gestión y futuro soporte BYOK.</p>
        {user_rows}
        <form method='post' action='/keys/user/assign' style='display:flex;gap:8px;margin-top:18px;flex-wrap:wrap'>
          <select name='user_id' style='margin:0;padding:8px 10px;flex:1;min-width:180px'>{user_select}</select>
          <select name='provider' style='margin:0;padding:8px 10px'>{provider_select}</select>
          <input type='text' name='model' placeholder='modelo (ej: deepseek-v4-flash)' style='margin:0;padding:8px 10px;flex:1;min-width:180px'>
          <input type='text' name='key_label' placeholder='key / pool a usar' style='margin:0;padding:8px 10px;flex:1;min-width:140px'>
          <button type='submit'>Asignar</button>
        </form>
      </div>
    </div>
    <script>
    async function testKey(source, ref, btn){{
      btn.textContent='…';
      try{{
        const r = await fetch('/keys/test', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{source, ref}})}});
        const d = await r.json();
        btn.textContent = d.ok ? '✅ '+d.detail : '❌ '+d.detail;
        btn.style.borderColor = d.ok ? '#15803d' : '#dc2626';
      }}catch(e){{ btn.textContent='❌ err'; }}
    }}
    function withMaster(form){{
      const pw = prompt('🔐 Master password (vault):');
      if(pw === null) return false;
      let inp = form.querySelector('input[name="master_pw"]');
      if(!inp){{ inp = document.createElement('input'); inp.type='hidden'; inp.name='master_pw'; form.appendChild(inp); }}
      inp.value = pw;
      return true;
    }}
    </script>
    """


@app.route("/keys/test", methods=["POST"])
def keys_test():
    if current_role() != "admin":
        abort(403)
    data = request.get_json(silent=True) or {}
    source, ref = data.get("source"), data.get("ref", "")
    key, provider = "", ""
    if source == "env":
        env = km._load_env()
        key = env.get(ref, "")
        provider = km._provider_for_var(ref) or "generic"
    elif source == "pool":
        d = km._load_auth()
        for prov, creds in d.get("credential_pool", {}).items():
            for c in creds or []:
                if c.get("id") == ref:
                    provider = prov
                    key = c.get("api_key") or c.get("token") or c.get("oauth_token") or ""
    if not key:
        return {"ok": False, "detail": "clave no encontrada"}
    ok, det = km.test_key(provider, key)
    return {"ok": ok, "detail": det}


@app.route("/keys/env/save", methods=["POST"])
def keys_env_save():
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    name = request.form.get("name", "").strip()
    value = request.form.get("value", "").strip()
    if name and value:
        km.set_env_key(name, value)
        db.log_system_event("KEY_EDIT", f"{name} actualizada", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/env/delete", methods=["POST"])
def keys_env_delete():
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    name = request.form.get("name", "").strip()
    if name:
        km.delete_env_key(name)
        db.log_system_event("KEY_DELETE", f"{name} eliminada", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/pool/add", methods=["POST"])
def keys_pool_add():
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    provider = request.form.get("provider", "").strip()
    label = request.form.get("label", "").strip() or "key-extra"
    api_key = request.form.get("api_key", "").strip()
    if provider and api_key:
        km.add_pool_key(provider, label, api_key)
        db.log_system_event("POOL_ADD", f"{provider}: {label}", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/pool/remove", methods=["POST"])
def keys_pool_remove():
    if current_role() != "admin":
        abort(403)
    denied = _require_master(request.form)
    if denied:
        return denied
    provider = request.form.get("provider", "").strip()
    cid = request.form.get("id", "").strip()
    if provider and cid:
        km.remove_pool_key(provider, cid)
        db.log_system_event("POOL_REMOVE", f"{provider}: {cid[:10]}", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/user/assign", methods=["POST"])
def keys_user_assign():
    if current_role() != "admin":
        abort(403)
    uid = request.form.get("user_id", "").strip()
    provider = request.form.get("provider", "").strip()
    model = request.form.get("model", "").strip()
    key_label = request.form.get("key_label", "").strip()
    if uid and provider:
        km.assign_user_key(uid, provider, model, key_label)
        db.log_system_event("KEY_ASSIGN", f"{uid} -> {provider}/{model}", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/user/unassign", methods=["POST"])
def keys_user_unassign():
    if current_role() != "admin":
        abort(403)
    uid = request.form.get("user_id", "").strip()
    if uid:
        km.unassign_user_key(uid)
        db.log_system_event("KEY_UNASSIGN", f"{uid}", SUPER_ADMIN)
    return redirect("/keys")


# ---------- VAULT DE SECRETOS ----------
# Pestaña /secrets (solo admin): muestra los .env reales protegidos por una
# master password propia (segundo factor, separada del login Privy).
# La password se guarda SOLO hasheada (PBKDF2+salt) en admin_panel.db.
# Anti fuerza bruta: 5 fallos -> bloqueo 15 min (persistido en vault_guard).
# Auto-lock: 10 min de inactividad; lock manual con botón. Todo se audita.
VAULT_LOCK_MIN = 10
VAULT_MAX_FAILS = 5
VAULT_LOCKOUT_MIN = 15
_VAULT_UNLOCKED = {}  # session token -> time.time()


def _vault_unlocked(token):
    ts = _VAULT_UNLOCKED.get(token)
    if not ts:
        return False
    if time.time() - ts > VAULT_LOCK_MIN * 60:
        _VAULT_UNLOCKED.pop(token, None)
        return False
    return True


def _vault_touch(token):
    _VAULT_UNLOCKED[token] = time.time()


def _vault_lock(token):
    _VAULT_UNLOCKED.pop(token, None)


def _env_files():
    files = [{"id": "default", "label": "default", "path": ENV_PATH}]
    base = os.path.expanduser("~/.hermes/profiles")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name, ".env")
            if os.path.isfile(p):
                files.append({"id": name, "label": name, "path": p})
    return files


def _load_env_file(path):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _mask_value(v):
    if len(v) <= 8:
        return "•" * len(v)
    return v[:4] + "…" + v[-4:]


def _vault_msg(err, extra=""):
    return BASE_CSS + f"""<div class='msg'>
      <div class='bar'></div>
      <div class='idx'>DORSHA · ADMIN</div>
      <h1>🔐 Vault de secretos</h1>
      <p class='muted' style='margin:14px 0 22px'>{extra}</p>
      {'<p style="color:var(--danger);margin-bottom:18px;font-size:14px">⚠️ ' + escape(err) + '</p>' if err else ''}
      <form method='post' action='/secrets/unlock'>
        <input type='password' name='p' placeholder='Master password' required autofocus>
        <button type='submit'>🔓 Desbloquear vault</button>
      </form>
      <p class='muted' style='margin-top:16px;font-size:12px'>Solo lectura de archivos .env reales del servidor.
      ¿Olvidaste la contraseña? Resetea por SSH:
      <code style='font-size:11px'>python3 -c "import sys;sys.path.insert(0,chr(126)+'/.hermes/admin_panel');import db;db.set_password('nueva')"</code></p>
    </div>"""


@app.route("/secrets")
def secrets_page():
    denied = _admin_only()
    if denied:
        return denied
    token = request.cookies.get("session")
    err = request.args.get("err", "")
    file_id = request.args.get("file", "default")
    files = _env_files()
    cur = next((f for f in files if f["id"] == file_id), files[0])
    unlocked = _vault_unlocked(token)

    if not db.password_is_set():
        return BASE_CSS + f"""<div class='msg'>
      <div class='bar'></div>
      <div class='idx'>DORSHA · ADMIN</div>
      <h1>🔐 Crear vault</h1>
      <p class='muted' style='margin:14px 0 22px'>Primera vez: define la <b>master password</b> del vault.
      Se guarda <b>hasheada</b> en la BD del panel (nunca en claro). Con ella verás las .env completas.</p>
      {'<p style="color:var(--danger);margin-bottom:18px;font-size:14px">⚠️ ' + escape(err) + '</p>' if err else ''}
      <form method='post' action='/secrets/setup'>
        <input type='password' name='p1' placeholder='Master password (mínimo 8 caracteres)' required minlength='8'>
        <input type='password' name='p2' placeholder='Repite la master password' required minlength='8'>
        <button type='submit'>Crear vault</button>
      </form>
      <p class='muted' style='margin-top:16px;font-size:12px'>El login del panel sigue siendo solo Privy (email + OTP). Esta contraseña es una capa extra para leer secretos.</p>
    </div>"""

    if not unlocked:
        g = db.vault_guard_status()
        lockout = ""
        if g["locked_until"]:
            try:
                left = (datetime.fromisoformat(g["locked_until"]) - datetime.utcnow()).total_seconds()
            except Exception:
                left = 0
            if left > 0:
                lockout = (f"🔒 <b>Vault bloqueado</b> por intentos fallidos. "
                           f"Espera {int(left // 60) + 1} min. Fallos acumulados: {g['fail_count']}.")
        return _vault_msg(err, lockout)

    env = _load_env_file(cur["path"])
    rows = ""
    for k, v in sorted(env.items()):
        masked = _mask_value(v)
        rows += f"""<div class='row' data-key='{escape(k)}' data-masked='{escape(masked)}' style='align-items:flex-start'>
          <div style='min-width:0;flex:1'>
            <b>{escape(k)}</b><br>
            <span class='muted mono' style='font-family:monospace;font-size:12px;word-break:break-all'>{escape(masked)}</span>
          </div>
          <div class='btnrow' style='flex-shrink:0'>
            <button class='ghost' type='button' onclick='reveal(this)'>👁 Mostrar</button>
            <button class='ghost copy' type='button' onclick='copyVal(this)' disabled title='Revela el valor primero'>📋</button>
          </div>
        </div>"""
    if not rows:
        rows = "<p class='muted'>Archivo vacío o solo comentarios.</p>"

    file_opts = "".join(
        f"<option value='{f['id']}' {'selected' if f['id'] == cur['id'] else ''}>{escape(f['label'])}</option>"
        for f in files)

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/secrets'>Secretos</a><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/logs'>Logs</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>
      <div class='idx'>06 — SECRETOS</div>
      <h1 style='font-size:26px;margin-bottom:6px'>Vault de secretos</h1>
      <p class='muted' style='margin-bottom:22px'>Archivos .env reales del servidor. Se auto-bloquea a los {VAULT_LOCK_MIN} min de inactividad; cada revelación queda auditada.</p>

      <div style='display:flex;gap:10px;align-items:center;margin-bottom:22px;flex-wrap:wrap'>
        <select id='fileSel' onchange="location='?file='+this.value" style='margin:0;padding:8px 10px;width:auto'>{file_opts}</select>
        <span class='tag'>{len(env)} vars</span>
        <span class='tag active'>🔓 desbloqueado</span>
        <form method='post' action='/secrets/lock' style='margin-left:auto'>
          <button class='ghost' type='submit'>🔒 Bloquear ahora</button>
        </form>
      </div>

      <div class='card'>
        <span class='idx'>{escape(cur['label'].upper())}</span>
        <h2 style='font-family:monospace;font-size:14px;word-break:break-all'>{escape(cur['path'])}</h2>
        <input type='text' id='filter' placeholder='Filtrar variables… (escribe el nombre)' style='margin:14px 0 8px' oninput='filterRows(this.value)'>
        {rows}
      </div>

      <div class='card'>
        <span class='idx'>BACKUP</span>
        <h2>Backup cifrado descargable</h2>
        <p class='muted' style='margin:10px 0 16px'>Genera un .zip con los .env de <b>todos los perfiles</b>, la BD del panel y los crons — todo cifrado <b>AES-256</b> con tu master password (pide la password de nuevo para confirmar). Restaurar: instrucciones dentro del zip.</p>
        <form method='post' action='/secrets/backup' onsubmit="return withMaster(this)">
          <button type='submit'>📦 Descargar backup cifrado</button>
        </form>
      </div>
    </div>
    <script>
    function reveal(btn){{
      const row = btn.closest('.row');
      const span = row.querySelector('.mono');
      const file = document.getElementById('fileSel').value;
      if(btn.dataset.on === '1'){{
        span.textContent = row.dataset.masked;
        span.style.background = 'transparent';
        btn.textContent = '👁 Mostrar';
        btn.dataset.on = '';
        row.querySelector('.copy').disabled = true;
        return;
      }}
      btn.textContent = '…';
      fetch('/secrets/reveal', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{file, key: row.dataset.key}})}})
        .then(r=>r.json()).then(d=>{{
          if(d.ok){{
            span.textContent = d.value;
            span.style.background = '#fafafa';
            btn.textContent = '🙈 Ocultar';
            btn.dataset.on = '1';
            row.querySelector('.copy').disabled = false;
          }} else {{
            btn.textContent = '❌ ' + d.detail;
            setTimeout(()=>btn.textContent='👁 Mostrar', 2500);
          }}
        }}).catch(()=>btn.textContent='❌ err');
    }}
    function copyVal(btn){{
      const txt = btn.closest('.row').querySelector('.mono').textContent;
      navigator.clipboard.writeText(txt).then(()=>{{
        btn.textContent = '✅';
        setTimeout(()=>btn.textContent='📋', 1200);
      }});
    }}
    function filterRows(q){{
      q = q.toLowerCase();
      document.querySelectorAll('.row[data-key]').forEach(r => {{
        r.style.display = r.dataset.key.toLowerCase().includes(q) ? '' : 'none';
      }});
    }}
    function withMaster(form){{
      const pw = prompt('🔐 Master password (vault):');
      if(pw === null) return false;
      let inp = form.querySelector('input[name="master_pw"]');
      if(!inp){{ inp = document.createElement('input'); inp.type='hidden'; inp.name='master_pw'; form.appendChild(inp); }}
      inp.value = pw;
      return true;
    }}
    </script>
    """


@app.route("/secrets/setup", methods=["POST"])
def secrets_setup():
    denied = _admin_only()
    if denied:
        return denied
    p1 = request.form.get("p1", "")
    p2 = request.form.get("p2", "")
    if len(p1) < 8:
        return redirect("/secrets?err=" + "La contraseña debe tener al menos 8 caracteres")
    if p1 != p2:
        return redirect("/secrets?err=" + "Las contraseñas no coinciden")
    db.set_password(p1)
    token = request.cookies.get("session")
    _vault_touch(token)
    db.vault_clear_fails()
    db.log_system_event("VAULT_SETUP", "Master password del vault creada", SUPER_ADMIN)
    return redirect("/secrets")


@app.route("/secrets/unlock", methods=["POST"])
def secrets_unlock():
    denied = _admin_only()
    if denied:
        return denied
    token = request.cookies.get("session")
    g = db.vault_guard_status()
    if g["locked_until"]:
        try:
            left = (datetime.fromisoformat(g["locked_until"]) - datetime.utcnow()).total_seconds()
        except Exception:
            left = 0
        if left > 0:
            return redirect(f"/secrets?err=Vault bloqueado por intentos fallidos. Espera {int(left // 60) + 1} min.")
    p = request.form.get("p", "")
    if db.check_password(p):
        _vault_touch(token)
        db.vault_clear_fails()
        db.log_system_event("VAULT_UNLOCK", "Vault desbloqueado", SUPER_ADMIN)
        return redirect("/secrets")
    db.vault_register_fail()
    g = db.vault_guard_status()
    db.log_system_event("VAULT_FAIL", f"Intento fallido {g['fail_count']}/{VAULT_MAX_FAILS}", SUPER_ADMIN)
    if g["fail_count"] >= VAULT_MAX_FAILS:
        until = datetime.utcnow() + timedelta(minutes=VAULT_LOCKOUT_MIN)
        db.vault_lock_until(until.isoformat())
        db.log_system_event("VAULT_LOCKOUT", f"{VAULT_LOCKOUT_MIN} min por intentos fallidos", SUPER_ADMIN)
        return redirect("/secrets?err=" + f"Demasiados intentos. Vault bloqueado {VAULT_LOCKOUT_MIN} min.")
    return redirect("/secrets?err=" + f"Contraseña incorrecta ({g['fail_count']}/{VAULT_MAX_FAILS} intentos)")


@app.route("/secrets/lock", methods=["POST"])
def secrets_lock():
    if current_role() != "admin":
        abort(403)
    token = request.cookies.get("session")
    _vault_lock(token)
    db.log_system_event("VAULT_LOCK", "Vault bloqueado manualmente", SUPER_ADMIN)
    return redirect("/secrets")


@app.route("/secrets/backup", methods=["POST"])
def secrets_backup():
    """Backup descargable: .env (todos los perfiles) + admin_panel.db + crons,
    TODO cifrado AES-256-CBC con la master password del vault (openssl)."""
    if current_role() != "admin":
        abort(403)
    token = request.cookies.get("session")
    if not _vault_unlocked(token):
        return {"ok": False, "detail": "Vault bloqueado"}, 403
    pw = (request.form.get("master_pw") or "").strip()
    if not db.check_password(pw):
        db.log_system_event("VAULT_FAIL", "Backup denegado: master password incorrecta", SUPER_ADMIN)
        return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div>" \
               "<h1>🔒 Master password incorrecta</h1><p class='muted'>El backup se cancela. " \
               "<a href='/secrets'>← Secretos</a></p></div>", 403

    def enc(data: bytes, name: str) -> bytes:
        with tempfile.NamedTemporaryFile("w", delete=False) as pf:
            pf.write(pw)
            pw_path = pf.name
        try:
            p = subprocess.run(
                ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "100000",
                 "-salt", "-pass", f"file:{pw_path}"],
                input=data, capture_output=True, timeout=60)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.decode()[:200])
            return p.stdout
        finally:
            os.unlink(pw_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _env_files():
            if os.path.exists(f["path"]):
                raw = open(f["path"], "rb").read()
                z.writestr(f"env-{f['id']}.enc", enc(raw, f["id"]))
        # BD del panel (copia consistente vía sqlite backup API)
        tmp_db = tempfile.mktemp(suffix=".db")
        try:
            src = db.get_conn()
            dst = sqlite3.connect(tmp_db)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            z.writestr("admin-panel.db.enc", enc(open(tmp_db, "rb").read(), "db"))
        finally:
            if os.path.exists(tmp_db):
                os.unlink(tmp_db)
        # crons
        if os.path.exists(CRON_JOBS_PATH):
            z.writestr("cron-jobs.json.enc", enc(open(CRON_JOBS_PATH, "rb").read(), "crons"))
        z.writestr("README.txt", (
            "BACKUP DORSHA — descargado desde el panel admin\n"
            "================================================\n"
            "Todo está cifrado AES-256-CBC (PBKDF2 100k iteraciones) con la\n"
            "master password del vault.\n\n"
            "Restaurar un archivo:\n"
            "  openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \\\n"
            "    -in env-default.enc -out .env -pass pass:'TU_MASTER_PASSWORD'\n\n"
            "Restaurar la BD del panel:\n"
            "  1) openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \\\n"
            "       -in admin-panel.db.enc -out admin_panel.db -pass pass:'TU_MASTER_PASSWORD'\n"
            "  2) systemctl --user stop admin-panel\n"
            "  3) cp admin_panel.db ~/.hermes/admin_panel/admin_panel.db\n"
            "  4) systemctl --user start admin-panel\n\n"
            "No compartas este archivo: contiene credenciales cifradas.\n"
        ))
    buf.seek(0)
    db.log_system_event("VAULT_BACKUP", "Backup cifrado descargado", SUPER_ADMIN)
    fname = "dorsha-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
    from flask import send_file
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=fname)


@app.route("/secrets/reveal", methods=["POST"])
def secrets_reveal():
    if current_role() != "admin":
        abort(403)
    token = request.cookies.get("session")
    if not _vault_unlocked(token):
        return {"ok": False, "detail": "Vault bloqueado"}, 403
    data = request.get_json(silent=True) or {}
    file_id = data.get("file", "default")
    key = data.get("key", "")
    files = _env_files()
    cur = next((f for f in files if f["id"] == file_id), None)
    if not cur:
        return {"ok": False, "detail": "Archivo no encontrado"}, 404
    env = _load_env_file(cur["path"])
    if key not in env:
        return {"ok": False, "detail": "Variable no encontrada"}, 404
    _vault_touch(token)
    db.log_system_event("VAULT_REVEAL", f"{key} ({cur['id']})", SUPER_ADMIN)
    return {"ok": True, "key": key, "value": env[key]}


if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_PANEL_PORT", "5057"))
    app.run(host="127.0.0.1", port=port)
