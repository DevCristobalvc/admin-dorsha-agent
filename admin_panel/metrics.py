#!/usr/bin/env python3
"""
metrics.py — Estadísticas del sistema desde state.db (solo lectura).
Soporta métricas de sesiones, tokens, costo, errores, actividad, modelos,
plataformas y herramientas.
"""
import os
import re
import json
import sqlite3
from datetime import datetime, timedelta, timezone

STATE_DB = os.path.expanduser("~/.hermes/state.db")
PANEL_DB = os.path.expanduser("~/.hermes/admin_panel/admin_panel.db")
CRON_JOBS = os.path.expanduser("~/.hermes/cron/jobs.json")
GATEWAY_LOG = os.path.expanduser("~/.hermes/logs/gateway.log")

SID_DATE_RE = re.compile(r"(\d{8})")

# Tarifas USD por millón de tokens para modelos sin pricing en Hermes
# (deepseek-v4-flash no estaba en la tabla oficial; precios oficiales 2026-05)
FALLBACK_RATES = {
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.0028},
}


def _fallback_cost(conn, in_clause=None, params=None):
    """Costo adicional para modelos con estimated_cost_usd = 0 (sin pricing en Hermes)."""
    q = ("SELECT model, COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o, "
         "COALESCE(SUM(cache_read_tokens),0) cr, COALESCE(SUM(estimated_cost_usd),0) e "
         "FROM session_model_usage")
    if in_clause:
        q += f" WHERE session_id IN {in_clause}"
    q += " GROUP BY model"
    rows = conn.execute(q, params or []).fetchall()
    extra = 0.0
    for r in rows:
        rates = FALLBACK_RATES.get(r["model"])
        if not rates or (r["e"] and r["e"] > 0):
            continue
        extra += (r["i"] * rates["input"] + r["o"] * rates["output"] + r["cr"] * rates["cache_read"]) / 1_000_000
    return extra


def _state_conn():
    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _user_names():
    try:
        conn = sqlite3.connect(PANEL_DB)
        names = {str(r[0]): r[1] for r in conn.execute("SELECT chat_id, name FROM users")}
        conn.close()
        return names
    except Exception:
        return {}


def _sid_date(session_id):
    """Extrae YYYYMMDD del id de sesión (20260710_223347_x o cron_x_20260710_..)."""
    m = SID_DATE_RE.search(session_id or "")
    return m.group(1) if m else None


def _cutoff_days(days):
    """Devuelve (cutoff_sid_date, cutoff_epoch) según days (7/30/None=all)."""
    if not days:
        return None, None
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return d.strftime("%Y%m%d"), d.timestamp()


def _period_filter(conn, days):
    sid_cutoff, ts_cutoff = _cutoff_days(days)
    if not sid_cutoff:
        return ""
    return f" AND created >= {sid_cutoff}"


def overview(days=None):
    """Totales: sesiones, mensajes, tokens, llamadas, costo. (days=None = todo)"""
    conn = _state_conn()
    sid_cutoff, ts_cutoff = _cutoff_days(days)

    # sesiones (filtro por fecha en el id)
    if sid_cutoff:
        sessions = [r["id"] for r in conn.execute("SELECT id FROM sessions")]
        sessions = [s for s in sessions if (_sid_date(s) or "") >= sid_cutoff]
        n_sessions = len(sessions)
        in_ = "(" + ",".join("?" for _ in sessions) + ")" if sessions else "('')"
        usage = conn.execute(
            f"SELECT COALESCE(SUM(api_call_count),0) c, COALESCE(SUM(input_tokens),0) i, "
            f"COALESCE(SUM(output_tokens),0) o, COALESCE(SUM(estimated_cost_usd),0) e "
            f"FROM session_model_usage WHERE session_id IN {in_}", sessions).fetchone()
    else:
        n_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        usage = conn.execute(
            "SELECT COALESCE(SUM(api_call_count),0) c, COALESCE(SUM(input_tokens),0) i, "
            "COALESCE(SUM(output_tokens),0) o, COALESCE(SUM(estimated_cost_usd),0) e "
            "FROM session_model_usage").fetchone()

    extra = _fallback_cost(conn, in_ if sid_cutoff else None, sessions if sid_cutoff else None)

    if ts_cutoff:
        n_messages = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp >= ?", (ts_cutoff,)).fetchone()[0]
    else:
        n_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    return {
        "sessions": n_sessions,
        "messages": n_messages,
        "api_calls": usage["c"],
        "input_tokens": usage["i"],
        "output_tokens": usage["o"],
        "total_tokens": usage["i"] + usage["o"],
        "cost_usd": round(usage["e"] + extra, 4),
    }


def spend_by_user(days=None):
    """Ranking de gasto por usuario: sesiones, llamadas, tokens, costo (con fallback)."""
    conn = _state_conn()
    sid_cutoff, _ = _cutoff_days(days)
    names = _user_names()
    base = ("FROM session_model_usage u JOIN sessions s ON s.id = u.session_id")
    cols = ("SELECT s.user_id, u.model, COUNT(DISTINCT s.id) ses, "
            "COALESCE(SUM(u.api_call_count),0) calls, COALESCE(SUM(u.input_tokens),0) inp, "
            "COALESCE(SUM(u.output_tokens),0) out, COALESCE(SUM(u.cache_read_tokens),0) cr, "
            "COALESCE(SUM(u.estimated_cost_usd),0) e ")
    if sid_cutoff:
        keep = [s for s in (r[0] for r in conn.execute("SELECT id FROM sessions"))
                if (_sid_date(s) or "") >= sid_cutoff]
        in_ = "(" + ",".join("?" for _ in keep) + ")" if keep else "('')"
        rows = conn.execute(f"{cols} {base} WHERE u.session_id IN {in_} GROUP BY s.user_id, u.model",
                            keep).fetchall()
    else:
        rows = conn.execute(f"{cols} {base} GROUP BY s.user_id, u.model").fetchall()

    agg = {}
    for r in rows:
        uid = str(r["user_id"]) if r["user_id"] is not None else None
        key = uid or "cron"
        a = agg.setdefault(key, {
            "user": names.get(uid, uid) if uid else "cron",
            "chat_id": uid or "—",
            "sessions": 0, "calls": 0, "tokens": 0, "cost": 0.0,
        })
        a["sessions"] += r["ses"]
        a["calls"] += r["calls"]
        a["tokens"] += r["inp"] + r["out"]
        rates = FALLBACK_RATES.get(r["model"])
        if rates and not r["e"]:
            a["cost"] += (r["inp"] * rates["input"] + r["out"] * rates["output"]
                          + r["cr"] * rates["cache_read"]) / 1_000_000
        else:
            a["cost"] += r["e"] or 0
    conn.close()
    for a in agg.values():
        a["cost"] = round(a["cost"], 4)
    return sorted(agg.values(), key=lambda x: x["cost"], reverse=True)[:12]


def errors_by_user(days=None):
    """Tool-errors por usuario (resultados de tools que fallaron)."""
    conn = _state_conn()
    ts_cutoff = _cutoff_days(days)[1]
    names = _user_names()
    q = ("SELECT s.user_id, COUNT(*) n FROM messages m JOIN sessions s ON s.id = m.session_id "
         "WHERE m.role='tool' AND lower(m.content) LIKE '%error%'")
    params = []
    if ts_cutoff:
        q += " AND m.timestamp >= ?"
        params.append(ts_cutoff)
    q += " GROUP BY s.user_id ORDER BY n DESC LIMIT 12"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [{"user": names.get(str(r["user_id"]), r["user_id"] or "cron") or "cron",
             "errors": r["n"]} for r in rows]


def cron_failures():
    """Crons con último estado error."""
    try:
        d = json.load(open(CRON_JOBS))
        jobs = d.get("jobs", [])
        fails = [{"name": j.get("name") or j.get("id"), "last_status": j.get("last_status"),
                  "last_error": (j.get("last_error") or "")[:80],
                  "last_run": (j.get("last_run_at") or "")[:16]} for j in jobs
                 if j.get("last_status") == "error"]
        return fails, len(jobs)
    except Exception as e:
        return [], 0


def gateway_errors(hours=24):
    """Conteo de errores en el log del gateway (últimas N horas)."""
    try:
        stat = os.stat(GATEWAY_LOG)
        if not stat.st_size:
            return 0
        with open(GATEWAY_LOG, "rb") as f:
            f.seek(max(0, stat.st_size - 400_000))
            tail = f.read().decode("utf-8", errors="ignore")
        return sum(1 for line in tail.splitlines()
                   if re.search(r"\berror\b", line, re.IGNORECASE))
    except Exception:
        return 0


def activity(days=14):
    """Mensajes por día (últimos N días)."""
    conn = _state_conn()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    rows = conn.execute(
        "SELECT date(timestamp,'unixepoch','localtime') d, COUNT(*) n FROM messages "
        "WHERE timestamp >= ? GROUP BY d ORDER BY d", (since,)).fetchall()
    conn.close()
    return [{"date": r["d"], "count": r["n"]} for r in rows]


def models():
    conn = _state_conn()
    rows = conn.execute(
        "SELECT model, COUNT(*) sessions, COALESCE(SUM(input_tokens),0) inp, "
        "COALESCE(SUM(output_tokens),0) out, COALESCE(SUM(cache_read_tokens),0) cr, "
        "COALESCE(SUM(estimated_cost_usd),0) cost "
        "FROM session_model_usage GROUP BY model ORDER BY inp+out DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        cost = r["cost"] or 0
        rates = FALLBACK_RATES.get(r["model"])
        if rates and not cost:
            cost = (r["inp"] * rates["input"] + r["out"] * rates["output"]
                    + r["cr"] * rates["cache_read"]) / 1_000_000
        out.append({"model": r["model"], "sessions": r["sessions"],
                    "tokens": r["inp"] + r["out"], "cost": round(cost, 4)})
    return out


def platforms():
    conn = _state_conn()
    rows = conn.execute(
        "SELECT source, COUNT(*) n FROM sessions GROUP BY source ORDER BY n DESC").fetchall()
    conn.close()
    return [{"platform": r["source"] or "?", "sessions": r["n"]} for r in rows]


def top_tools(limit=10):
    conn = _state_conn()
    rows = conn.execute(
        "SELECT tool_name, COUNT(*) n FROM messages WHERE tool_name IS NOT NULL "
        "GROUP BY tool_name ORDER BY n DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [{"tool": r["tool_name"], "calls": r["n"]} for r in rows]
