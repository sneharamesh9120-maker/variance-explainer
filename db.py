"""Step 8: store every report so it can be reopened and reviewed in the admin dashboard."""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join("data", "reports.db"))


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                period TEXT NOT NULL,
                currency TEXT NOT NULL,
                line_count INTEGER,
                material_count INTEGER,
                net_variance REAL,
                overall_confidence INTEGER,
                overall_band TEXT,
                ai_used INTEGER,
                ai_error TEXT,
                model TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                flags_count INTEGER DEFAULT 0,
                removed_count INTEGER DEFAULT 0,
                input_json TEXT,
                analysis_json TEXT,
                result_json TEXT,
                feedback TEXT,
                feedback_note TEXT
            )
        """)


def save_report(data, analysis, result, meta):
    flags = sum(len(d["flags"]) for d in result["drivers"])
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO reports (created_at, title, period, currency, line_count, material_count,
               net_variance, overall_confidence, overall_band, ai_used, ai_error, model,
               prompt_tokens, completion_tokens, latency_ms, flags_count, removed_count,
               input_json, analysis_json, result_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                data["title"], data["period"], data["currency"],
                len(analysis["rows"]), len(analysis["material"]),
                analysis["totals"]["net_variance"],
                result["overall_confidence"], result["overall_band"],
                1 if result["ai_used"] else 0, result.get("ai_error"),
                meta.get("model"), meta.get("prompt_tokens", 0), meta.get("completion_tokens", 0),
                meta.get("latency_ms", 0), flags, len(result["removed"]),
                json.dumps(data), json.dumps(analysis), json.dumps(result),
            ),
        )
        return cur.lastrowid


def get_report(report_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        return None
    rec = dict(row)
    rec["input"] = json.loads(rec.pop("input_json"))
    rec["analysis"] = json.loads(rec.pop("analysis_json"))
    rec["result"] = json.loads(rec.pop("result_json"))
    return rec


def list_reports(limit=100):
    with _conn() as c:
        rows = c.execute(
            """SELECT id, created_at, title, period, currency, line_count, material_count,
                      net_variance, overall_confidence, overall_band, ai_used, ai_error,
                      flags_count, removed_count, latency_ms, feedback
               FROM reports ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_feedback(report_id, value, note):
    with _conn() as c:
        c.execute("UPDATE reports SET feedback = ?, feedback_note = ? WHERE id = ?",
                  (value, note[:500], report_id))


def delete_report(report_id):
    with _conn() as c:
        c.execute("DELETE FROM reports WHERE id = ?", (report_id,))
