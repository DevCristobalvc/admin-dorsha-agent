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
body{font-family:-apple-system,Arial,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:24px}
.card{max-width:520px;margin:40px auto;background:#181b21;border:1px solid #2a2f3a;border-radius:10px;padding:28px}
h1{font-size:20px;margin:0 0 18px}
input[type=password],input[type=text]{width:100%;padding:10px;margin:8px 0 16px;background:#0f1115;
  border:1px solid #333;border-radius:6px;color:#fff;box-sizing:border-box}
button{background:#3b82f6;color:#fff;border:none;padding:10px 18px;border-radius:6px;cursor:pointer;font-size:14px}
button.danger{background:#ef4444}
button.ghost{background:#2a2f3a}
.row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #23262e}
.tag{font-size:11px;padding:2px 8px;border-radius:10px;background:#2a2f3a}
.tag.blocked{background:#7f1d1d}
.tag.active{background:#14532d}
.wrap{max-width:720px;margin:30px auto}
.muted{color:#9aa0aa;font-size:13px}
a{color:#60a5fa}
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
            return BASE_CSS + "<div class='card'><h1>Error</h1><p>Contraseña muy corta (min 6).</p><a href='/setup'>Volver</a></div>"
        if p1 != p2:
            return BASE_CSS + "<div class='card'><h1>Error</h1><p>No coinciden.</p><a href='/setup'>Volver</a></div>"
        db.set_password(p1)
        token = db.create_session()
        resp = make_response(redirect("/dashboard"))
        resp.set_cookie("session", token, httponly=True, samesite="Lax", max_age=3600*12)
        return resp
    return BASE_CSS + """
    <div class='card'>
      <h1>🔐 Crear contraseña de administrador</h1>
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
        return BASE_CSS + "<div class='card'><h1>❌ Contraseña incorrecta</h1><a href='/login'>Reintentar</a></div>"
    return BASE_CSS + """
    <div class='card'>
      <h1>🔐 Panel de administración — Gero/Dinco</h1>
      <form method='post'>
        <input type='password' name='password' placeholder='Contraseña' required autofocus>
        <button type='submit'>Entrar</button>
      </form>
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
        return BASE_CSS + "<div class='card'><h1>❌ Ticket no configurado</h1><p class='muted'>Falta PRIVY_TICKET_SECRET en ~/.hermes/.env</p></div>", 500
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
        return BASE_CSS + "<div class='card'><h1>❌ Email no configurado</h1><p class='muted'>Falta PRIVY_ALLOWED_EMAIL en ~/.hermes/.env</p></div>", 500
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
            </div><div>
            <button onclick="act('/actions/{a['id']}/approve')">✅ Aprobar</button>
            <button class='danger' onclick="act('/actions/{a['id']}/deny')">❌ Negar</button>
            </div></div>"""
    if not act_rows:
        act_rows = "<p class='muted'>No hay acciones pendientes.</p>"

    return BASE_CSS + f"""
    <div class='wrap'>
      <div style='display:flex;justify-content:space-between'><h1>Panel de administración</h1><div><a href='/history'>📜 Historial</a> &nbsp;|&nbsp; <a href='/logout'>Salir</a></div></div>

      <div class='card' style='margin-left:0'>
        <h1 style='font-size:16px'>⏳ Acciones sensibles pendientes</h1>
        {act_rows}
      </div>

      <div class='card' style='margin-left:0'>
        <h1 style='font-size:16px'>👥 Usuarios autorizados</h1>
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
          <div class='muted'>{r['created_at'][:16]} · <b>{name}</b> · {r['platform']}</div>
          <div style='margin-top:4px'>👤 {(r['message'] or '').replace('<','&lt;').replace('>','&gt;')[:600]}</div>
          <div style='margin-top:4px;color:#93c5fd'>🤖 {(r['response'] or '(sin respuesta aun)').replace('<','&lt;').replace('>','&gt;')[:600]}</div>
        </div>"""
    if not items:
        items = "<p class='muted'>Sin mensajes registrados todavia.</p>"

    return BASE_CSS + f"""
    <div class='wrap'>
      <div style='display:flex;justify-content:space-between'><h1>📜 Historial de mensajes</h1><a href='/dashboard'>&larr; Panel</a></div>
      <form method='get' class='card' style='margin-left:0;padding:14px'>
        <select name='user_id' onchange='this.form.submit()' style='width:100%;padding:8px;background:#0f1115;color:#fff;border:1px solid #333;border-radius:6px'>
          {opts}
        </select>
      </form>
      <div class='card' style='margin-left:0'>{items}</div>
    </div>
    """

if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_PANEL_PORT", "5057"))
    app.run(host="127.0.0.1", port=port)
