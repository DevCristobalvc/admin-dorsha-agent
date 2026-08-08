#!/usr/bin/env python3
import os, sys, re, json, subprocess, hashlib, hmac, time
from datetime import datetime
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
          <form method='post' action='/system/off' onsubmit="return confirm('¿Apagar TODO el sistema? El bot dejará de responder y los crons se pausan.')">
            <button class='danger-btn' type='submit'>🛑 Apagar sistema</button>
          </form>
          <form method='post' action='/system/on'>
            <button type='submit'>▶ Reactivar</button>
          </form>
        </div>
        <div style='margin-top:18px'>{ev_rows}</div>
      </div>"""
    except Exception:
        system_card = ""

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
        <div class='nav'><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
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
    </div>
    <script>
    function act(url) {{
      fetch(url, {{method:'POST'}}).then(()=>location.reload());
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
    try:
        _cron_restore()
    except Exception:
        pass
    if os.path.exists(EMERGENCY_FLAG):
        os.remove(EMERGENCY_FLAG)
    subprocess.run(["systemctl", "--user", "start", "hermes-gateway.service"], timeout=20)
    db.log_system_event("SYSTEM_ON", "Sistema reactivado: gateway + crons restaurados", SUPER_ADMIN)
    return {"ok": True}


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
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/crons'>Crons</a><a href='/keys'>Claves</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
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
        <span class='idx'>ACTIVIDAD</span>
        <h2>Mensajes por día — últimos 14 días</h2>
        <div class='bars'>{bars}</div>
      </div>

      <div class='card'>
        <span class='idx'>COSTO</span>
        <h2>Costo por día — últimos 14 días</h2>
        <div class='bars'>{cost_bars}</div>
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
    """


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
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/metrics'>Métricas</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
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
            <form method='post' action='/keys/env/delete' onsubmit="return confirm('¿Borrar {escape(k['name'])}?')">
              <input type='hidden' name='name' value='{escape(k['name'])}'>
              <button class='danger' type='submit'>Borrar</button>
            </form></div>
            <form method='post' action='/keys/env/save' style='display:flex;gap:8px'>
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
                <form method='post' action='/keys/pool/remove' onsubmit="return confirm('¿Quitar {escape(c['label'])} del pool?')">
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
            <form method='post' action='/keys/pool/add' style='display:flex;gap:8px;margin-top:16px;flex-wrap:wrap'>
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
        <div class='nav'><a href='/dashboard'>← Panel</a><a href='/crons'>Crons</a><a href='/metrics'>Métricas</a><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
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
    name = request.form.get("name", "").strip()
    if name:
        km.delete_env_key(name)
        db.log_system_event("KEY_DELETE", f"{name} eliminada", SUPER_ADMIN)
    return redirect("/keys")


@app.route("/keys/pool/add", methods=["POST"])
def keys_pool_add():
    if current_role() != "admin":
        abort(403)
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


if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_PANEL_PORT", "5057"))
    app.run(host="127.0.0.1", port=port)
