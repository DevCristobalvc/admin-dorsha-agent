#!/usr/bin/env python3
"""
keymanager.py — Gestión de API keys desde el panel:
  - Keys globales del .env (listar enmascaradas, editar, testear)
  - Pools de auth.json (credential_pool): listar estado, agregar/quitar/reemplazar
  - Asignación por usuario (registro; Hermes no soporta routing por usuario nativo)
Siempre con backup antes de escribir.
"""
import os
import re
import json
import shutil
import urllib.request
import urllib.error
from datetime import datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
AUTH_PATH = os.path.expanduser("~/.hermes/auth.json")

# var -> (proveedor, endpoint de prueba, headers extra)
PROVIDER_PROBE = {
    "deepseek": ("https://api.deepseek.com/user/balance", {}, "Bearer"),
    "openai": ("https://api.openai.com/v1/models", {}, "Bearer"),
    "openrouter": ("https://openrouter.ai/api/v1/models", {}, "Bearer"),
    "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": "{key}"}, ""),
    "vercel": ("https://api.vercel.com/v2/user", {}, "Bearer"),
    "github": ("https://api.github.com/user", {}, "Bearer"),
    "supabase": ("https://api.supabase.com/v1/projects", {}, "Bearer"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": "{key}"}, ""),
}

ENV_KEY_PROVIDERS = [
    (r"^DEEPSEEK_API_KEY$", "deepseek"),
    (r"^OPENAI_API_KEY$|^VOICE_TOOLS_OPENAI_KEY$", "openai"),
    (r"^OPENROUTER_API_KEY$", "openrouter"),
    (r"^ANTHROPIC_API_KEY$", "anthropic"),
    (r"^VERCEL_TOKEN_", "vercel"),
    (r"^GITHUB_TOKEN$|^GH_TOKEN$", "github"),
    (r"^SUPABASE_", "supabase"),
    (r"^GOOGLE_API_KEY$|^GEMINI_API_KEY$", "google"),
]


def _backup(path):
    bak = f"{path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, bak)
    return bak


def _load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _save_env(env):
    _backup(ENV_PATH)
    lines = []
    seen = set()
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                k = stripped.split("=", 1)[0].strip()
                if k in env:
                    seen.add(k)
                    lines.append(f"{k}={env[k]}\n")
                    continue
                if k in seen:
                    continue  # duplicado ya escrito
                continue  # key eliminada del dict -> se omite la línea
            lines.append(line)
    for k, v in env.items():
        if k not in seen:
            lines.append(f"{k}={v}\n")
    open(ENV_PATH, "w", encoding="utf-8").write("".join(lines))


def _mask(value):
    if not value:
        return ""
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}…{value[-4:]}"


def _provider_for_var(name):
    for pattern, provider in ENV_KEY_PROVIDERS:
        if re.match(pattern, name):
            return provider
    return None


def list_env_keys():
    env = _load_env()
    out = []
    for name, value in env.items():
        provider = _provider_for_var(name)
        if provider or re.search(r"(KEY|TOKEN|SECRET|_PASS|PASSWORD)", name, re.I):
            if not value:
                continue
            out.append({
                "name": name,
                "masked": _mask(value),
                "last4": value[-4:],
                "provider": provider or "generic",
                "len": len(value),
            })
    return sorted(out, key=lambda x: x["name"])


def set_env_key(name, value):
    value = value.strip()
    if not value:
        return False, "Valor vacío"
    env = _load_env()
    env[name] = value
    _save_env(env)
    return True, "guardado"


def delete_env_key(name):
    env = _load_env()
    if name not in env:
        return False, "no existe"
    del env[name]
    _save_env(env)
    return True, "eliminado"


# ---------- pools (auth.json) ----------
def _load_auth():
    return json.load(open(AUTH_PATH))


def _save_auth(d):
    _backup(AUTH_PATH)
    json.dump(d, open(AUTH_PATH, "w"), indent=2)


def list_pools():
    d = _load_auth()
    pool = d.get("credential_pool", {})
    out = []
    for provider, creds in pool.items():
        items = []
        for c in creds or []:
            keyval = c.get("api_key") or c.get("token") or c.get("oauth_token") or ""
            items.append({
                "id": c.get("id"),
                "label": c.get("label") or c.get("source") or "?",
                "status": c.get("last_status") or "unknown",
                "error": (c.get("last_error_reason") or c.get("last_error_message") or "")[:60],
                "error_code": c.get("last_error_code") or "",
                "priority": c.get("priority"),
                "masked": _mask(keyval),
                "has_key": bool(keyval),
                "base_url": c.get("base_url") or "",
            })
        out.append({"provider": provider, "creds": items, "count": len(items)})
    return out


def add_pool_key(provider, label, api_key, base_url=None):
    d = _load_auth()
    pool = d.setdefault("credential_pool", {})
    creds = pool.setdefault(provider, [])
    new = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S") + os.urandom(2).hex(),
        "label": label,
        "auth_type": "api_key",
        "priority": 10,
        "source": "admin-panel",
        "api_key": api_key.strip(),
        "base_url": base_url or None,
        "last_status": "unknown",
    }
    creds.append(new)
    _save_auth(d)
    return True, "key agregada al pool"


def remove_pool_key(provider, cred_id):
    d = _load_auth()
    creds = d.get("credential_pool", {}).get(provider, [])
    d["credential_pool"][provider] = [c for c in creds if c.get("id") != cred_id]
    _save_auth(d)
    return True, "key eliminada del pool"


# ---------- testing ----------
def test_key(provider, api_key):
    probe = PROVIDER_PROBE.get(provider)
    if not probe:
        return False, f"sin endpoint de prueba para '{provider}'"
    url, extra_headers, auth_scheme = probe
    headers = {"User-Agent": "dorsha-admin"}
    key = api_key.strip()
    for k, v in extra_headers.items():
        headers[k] = v.replace("{key}", key)
    if auth_scheme:
        headers["Authorization"] = f"{auth_scheme} {key}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read(400).decode("utf-8", errors="replace")
            detail = ""
            if provider == "deepseek":
                try:
                    b = json.loads(body)
                    detail = f" · saldo: {b.get('balance_infos', [{}])[0].get('total_balance', '?')}"
                except Exception:
                    pass
            return True, f"HTTP {resp.status}{detail}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:
        return False, str(e)[:80]


# ---------- asignación por usuario ----------
def assign_user_key(user_id, provider, model, key_label, note=""):
    """Registro de asignación. Hermes no aplica routing por usuario nativamente."""
    import sqlite3
    conn = sqlite3.connect(os.path.expanduser("~/.hermes/admin_panel/admin_panel.db"))
    conn.execute("""CREATE TABLE IF NOT EXISTS user_keys (
        user_id TEXT PRIMARY KEY, provider TEXT, model TEXT, key_label TEXT,
        note TEXT, updated_at TEXT)""")
    conn.execute(
        "INSERT OR REPLACE INTO user_keys (user_id, provider, model, key_label, note, updated_at) VALUES (?,?,?,?,?,?)",
        (user_id, provider, model, key_label, note, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True, "asignación registrada"


def unassign_user_key(user_id):
    import sqlite3
    conn = sqlite3.connect(os.path.expanduser("~/.hermes/admin_panel/admin_panel.db"))
    conn.execute("DELETE FROM user_keys WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return True, "asignación eliminada"


def list_user_keys():
    import sqlite3
    conn = sqlite3.connect(os.path.expanduser("~/.hermes/admin_panel/admin_panel.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM user_keys").fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]
