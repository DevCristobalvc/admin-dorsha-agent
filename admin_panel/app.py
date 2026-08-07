#!/usr/bin/env python3
import os, sys, re, json, subprocess, hashlib, hmac, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

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
</style>
"""

def cookie_ok():
    return db.session_valid(request.cookies.get("session"))

def require_login():
    if not cookie_ok():
        abort(redirect("/login"))

@app.route("/")
def index():
    if cookie_ok():
        return redirect("/dashboard")
    return redirect("/login")

# ---------- SETUP (solo si no hay contraseña) ----------
@app.route("/setup", methods=["GET", "POST"])
def setup():
    if db.password_is_set():
        return redirect("/login")
    if request.method == "POST":
        p1 = request.form.get("password", "")
        p2 = request.form.get("password2", "")
        if len(p1) < 6:
            return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · SETUP</div><h1>Error</h1><p class='muted'>Contraseña muy corta (min 6).</p><p style='margin-top:14px'><a href='/setup'>← Volver</a></p></div>"
        if p1 != p2:
            return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · SETUP</div><h1>Error</h1><p class='muted'>No coinciden.</p><p style='margin-top:14px'><a href='/setup'>← Volver</a></p></div>"
        db.set_password(p1)
        token = db.create_session()
        resp = make_response(redirect("/dashboard"))
        resp.set_cookie("session", token, httponly=True, samesite="Lax", max_age=3600*12)
        return resp
    return BASE_CSS + """
    <div class='msg'>
      <div class='bar'></div>
      <div class='idx'>DORSHA · SETUP</div>
      <h1>Crear contraseña de administrador</h1>
      <p class='muted'>Primera vez. Esta contraseña queda hasheada (PBKDF2-SHA256), nadie puede leerla despues.</p>
      <form method='post'>
        <input type='password' name='password' placeholder='Nueva contraseña' required>
        <input type='password' name='password2' placeholder='Repetir contraseña' required>
        <button type='submit'>Crear y entrar</button>
      </form>
    </div>"""

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if not db.password_is_set():
        return redirect("/setup")
    if request.method == "POST":
        p = request.form.get("password", "")
        if db.check_password(p):
            token = db.create_session()
            resp = make_response(redirect("/dashboard"))
            resp.set_cookie("session", token, httponly=True, samesite="Lax", max_age=3600*12)
            return resp
        return BASE_CSS + "<div class='msg'><div class='bar'></div><div class='idx'>DORSHA · ADMIN</div><h1>❌ Contraseña incorrecta</h1><p style='margin-top:14px'><a href='/login'>← Reintentar</a></p></div>"
    return BASE_CSS + """
    <div class='msg'>
      <div class='bar'></div>
      <div class='idx'>DORSHA · ADMIN</div>
      <h1>Panel de administración</h1>
      <p class='muted' style='margin-bottom:18px'>Gero / Dinco · acceso restringido</p>
      <form method='post'>
        <input type='password' name='password' placeholder='Contraseña' required autofocus>
        <button type='submit'>Entrar</button>
      </form>
      <p class='muted' style='margin-top:18px;font-size:12px'><a href='https://dorsha.devcristobalvc.com/login'>← Entrar con email y código (Dorsha)</a></p>
    </div>"""

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
    if m != allowed:
        abort(403)
    token = db.create_session()
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

    rows = ""
    for u in users:
        cid = u["chat_id"]
        is_admin = cid == SUPER_ADMIN
        blocked = cid not in env_allowed
        tag = f"<span class='tag blocked'>BLOQUEADO</span>" if blocked else "<span class='tag active'>activo</span>"
        btn = "" if is_admin else (
            f"<button class='ghost' onclick=\"act('/users/{cid}/unblock')\">Desbloquear</button>"
            if blocked else
            f"<button class='danger' onclick=\"act('/users/{cid}/block')\">Bloquear</button>"
        )
        admin_tag = " 👑 admin" if is_admin else ""
        rows += f"<div class='row'><div>{u['name'] or cid}{admin_tag}<br><span class='muted'>{cid}</span></div><div>{tag} {btn}</div></div>"

    act_rows = ""
    for a in actions:
        act_rows += f"""<div class='row'><div>
            <b>{a['chat_name'] or a['chat_id']}</b> pidió:<br>
            <span class='muted'>{a['action_desc']}</span><br>
            <span class='muted'>expira: {a['expires_at'][:16]}</span>
            </div><div class='btnrow'>
            <button onclick="act('/actions/{a['id']}/approve')">Aprobar</button>
            <button class='danger' onclick="act('/actions/{a['id']}/deny')">Negar</button>
            </div></div>"""
    if not act_rows:
        act_rows = "<p class='muted'>No hay acciones pendientes.</p>"

    return BASE_CSS + f"""
    <div class='wrap'>
      <div class='top'>
        <div class='brand'><a href='/dashboard'>DORSHA</a></div>
        <div class='nav'><a href='/history'>Historial</a><a href='/logout'>Salir</a></div>
      </div>

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
    db.resolve_action(aid, "approved")
    return {"ok": True}

@app.route("/actions/<aid>/deny", methods=["POST"])
def deny_action(aid):
    if not cookie_ok():
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

if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_PANEL_PORT", "5057"))
    app.run(host="127.0.0.1", port=port)
