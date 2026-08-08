import os, sqlite3, hashlib, hmac, base64, json, secrets
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.hermes/admin_panel/admin_panel.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS admin_auth (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
        chat_id TEXT PRIMARY KEY,
        name TEXT,
        blocked INTEGER DEFAULT 0,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS pending_actions (
        id TEXT PRIMARY KEY,
        chat_id TEXT,
        chat_name TEXT,
        action_desc TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        expires_at TEXT,
        resolved_at TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        created_at TEXT,
        expires_at TEXT,
        role TEXT DEFAULT 'admin'
    );
    CREATE TABLE IF NOT EXISTS message_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turn_key TEXT,
        platform TEXT,
        user_id TEXT,
        chat_id TEXT,
        session_id TEXT,
        message TEXT,
        response TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ml_user ON message_log(user_id);
    CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT,
        detail TEXT,
        actor TEXT,
        created_at TEXT
    );
    """)
    # migración: columna role en sessions (bases antiguas)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    if "role" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN role TEXT DEFAULT 'admin'")
    conn.commit()
    conn.close()

# --- password ---
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return base64.b64encode(salt + h).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        raw = base64.b64decode(stored)
        salt, h = raw[:16], raw[16:]
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(h, expected)
    except Exception:
        return False

def password_is_set() -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM admin_auth WHERE id=1").fetchone()
    conn.close()
    return row is not None

def set_password(password: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO admin_auth (id, password_hash, created_at) VALUES (1, ?, ?)",
        (hash_password(password), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def check_password(password: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM admin_auth WHERE id=1").fetchone()
    conn.close()
    if not row:
        return False
    return verify_password(password, row["password_hash"])

# --- sessions ---
def create_session(role: str = "admin") -> str:
    token = secrets.token_urlsafe(32)
    conn = get_conn()
    now = datetime.utcnow()
    conn.execute("INSERT INTO sessions (token, created_at, expires_at, role) VALUES (?, ?, ?, ?)",
                 (token, now.isoformat(), (now + timedelta(hours=12)).isoformat(), role))
    conn.commit()
    conn.close()
    return token

def session_role(token: str) -> str:
    if not token:
        return "admin"
    conn = get_conn()
    row = conn.execute("SELECT role FROM sessions WHERE token=?", (token,)).fetchone()
    conn.close()
    return (row["role"] if row and "role" in row.keys() else "admin") or "admin"

def session_valid(token: str) -> bool:
    if not token:
        return False
    conn = get_conn()
    row = conn.execute("SELECT expires_at FROM sessions WHERE token=?", (token,)).fetchone()
    conn.close()
    if not row:
        return False
    return datetime.fromisoformat(row["expires_at"]) > datetime.utcnow()

# --- users ---
def sync_users_from_channel_directory():
    path = os.path.expanduser("~/.hermes/channel_directory.json")
    if not os.path.exists(path):
        return
    data = json.load(open(path, encoding="utf-8"))
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    for u in data.get("platforms", {}).get("telegram", []):
        cid, name = u["id"], u.get("name", "")
        existing = conn.execute("SELECT chat_id FROM users WHERE chat_id=?", (cid,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO users (chat_id, name, blocked, updated_at) VALUES (?,?,0,?)",
                         (cid, name, now))
        else:
            conn.execute("UPDATE users SET name=? WHERE chat_id=?", (name, cid))
    conn.commit()
    conn.close()

def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT chat_id, name, blocked, updated_at FROM users ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_blocked(chat_id: str, blocked: bool):
    conn = get_conn()
    conn.execute("UPDATE users SET blocked=?, updated_at=? WHERE chat_id=?",
                 (1 if blocked else 0, datetime.utcnow().isoformat(), chat_id))
    conn.commit()
    conn.close()

# --- pending actions ---
def create_pending_action(chat_id, chat_name, action_desc, ttl_minutes=10):
    aid = secrets.token_hex(8)
    now = datetime.utcnow()
    conn = get_conn()
    conn.execute("""INSERT INTO pending_actions
        (id, chat_id, chat_name, action_desc, status, created_at, expires_at)
        VALUES (?,?,?,?, 'pending', ?, ?)""",
        (aid, chat_id, chat_name, action_desc, now.isoformat(),
         (now + timedelta(minutes=ttl_minutes)).isoformat()))
    conn.commit()
    conn.close()
    return aid

def get_action(aid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM pending_actions WHERE id=?", (aid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_pending_actions():
    conn = get_conn()
    rows = conn.execute("""SELECT * FROM pending_actions
        WHERE status='pending' ORDER BY created_at DESC""").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def resolve_action(aid, status):
    conn = get_conn()
    conn.execute("UPDATE pending_actions SET status=?, resolved_at=? WHERE id=?",
                 (status, datetime.utcnow().isoformat(), aid))
    conn.commit()
    conn.close()

def expire_stale_actions():
    conn = get_conn()
    conn.execute("UPDATE pending_actions SET status='expired', resolved_at=? WHERE status='pending' AND expires_at < ?",
                 (datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# --- eventos del sistema (kill switch, etc.) ---
def log_system_event(event, detail, actor):
    conn = get_conn()
    conn.execute("INSERT INTO system_events (event, detail, actor, created_at) VALUES (?,?,?,?)",
                 (event, detail, actor, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def list_system_events(limit=10):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM system_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
