"""Persistent memory: conversations, facts, and learned lessons.

SQLite + FTS5 keyword recall. No external vector DB, no network, no deps.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from typing import Any

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, started_at REAL, title TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts REAL,
    role TEXT, content TEXT
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT,
    subject TEXT, body TEXT, source TEXT, confidence REAL DEFAULT 0.8
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, depth INTEGER DEFAULT 0,
    trigger TEXT, lesson TEXT, evidence TEXT, uses INTEGER DEFAULT 0,
    score REAL DEFAULT 0.0, retired INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, session_id TEXT,
    tool TEXT, args TEXT, ok INTEGER, ms INTEGER, result_head TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
    ref, kind, text, tokenize='porter'
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def new_session(title: str = "") -> str:
    sid = uuid.uuid4().hex[:12]
    with db() as c:
        c.execute("INSERT INTO sessions (id, started_at, title) VALUES (?,?,?)",
                  (sid, time.time(), title))
    return sid


def log_message(session_id: str, role: str, content: Any) -> None:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    with db() as c:
        cur = c.execute(
            "INSERT INTO messages (session_id, ts, role, content) VALUES (?,?,?,?)",
            (session_id, time.time(), role, text),
        )
        c.execute("INSERT INTO search (ref, kind, text) VALUES (?,?,?)",
                  (f"msg:{cur.lastrowid}", "message", text[:20000]))


def log_tool_run(session_id: str, tool: str, args: dict, ok: bool, ms: int, head: str) -> None:
    with db() as c:
        c.execute(
            "INSERT INTO tool_runs (ts, session_id, tool, args, ok, ms, result_head)"
            " VALUES (?,?,?,?,?,?,?)",
            (time.time(), session_id, tool, json.dumps(args, default=str)[:4000],
             int(ok), ms, head[:2000]),
        )


def remember(subject: str, body: str, kind: str = "fact", source: str = "conversation") -> str:
    """Store a durable fact about the user or the world."""
    with db() as c:
        cur = c.execute(
            "INSERT INTO facts (ts, kind, subject, body, source) VALUES (?,?,?,?,?)",
            (time.time(), kind, subject, body, source),
        )
        c.execute("INSERT INTO search (ref, kind, text) VALUES (?,?,?)",
                  (f"fact:{cur.lastrowid}", "fact", f"{subject}: {body}"))
    return f"remembered [{kind}] {subject}"


def add_lesson(trigger: str, lesson: str, evidence: str = "", depth: int = 0) -> int:
    with db() as c:
        cur = c.execute(
            "INSERT INTO lessons (ts, depth, trigger, lesson, evidence) VALUES (?,?,?,?,?)",
            (time.time(), depth, trigger, lesson, evidence),
        )
        c.execute("INSERT INTO search (ref, kind, text) VALUES (?,?,?)",
                  (f"lesson:{cur.lastrowid}", "lesson", f"{trigger} -> {lesson}"))
        return cur.lastrowid


def score_lesson(lesson_id: int, delta: float) -> None:
    with db() as c:
        c.execute("UPDATE lessons SET uses = uses + 1, score = score + ? WHERE id = ?",
                  (delta, lesson_id))
        c.execute("UPDATE lessons SET retired = 1 WHERE id = ? AND score < -2", (lesson_id,))


def active_lessons(limit: int = 40) -> list[sqlite3.Row]:
    with db() as c:
        return c.execute(
            "SELECT * FROM lessons WHERE retired = 0 ORDER BY score DESC, ts DESC LIMIT ?",
            (limit,),
        ).fetchall()


def recall(query: str, limit: int = 12) -> list[dict]:
    """Keyword recall across messages, facts, and lessons."""
    terms = " OR ".join(re.findall(r"[A-Za-z0-9_]{3,}", query)[:12]) or query
    with db() as c:
        try:
            rows = c.execute(
                "SELECT ref, kind, snippet(search, 2, '[', ']', '…', 24) AS snip"
                " FROM search WHERE search MATCH ? LIMIT ?", (terms, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]


def memory_prompt() -> str:
    """The block injected into every system prompt: who the user is + what was learned."""
    with db() as c:
        facts = c.execute(
            "SELECT subject, body FROM facts ORDER BY ts DESC LIMIT 40").fetchall()
    lessons = active_lessons()
    out = []
    if facts:
        out.append("What you know about the user and their world:")
        out += [f"- {f['subject']}: {f['body']}" for f in facts]
    if lessons:
        out.append("\nLessons you have learned from your own past runs "
                   "(highest-scoring first — apply them):")
        out += [f"- [{l['id']}] when {l['trigger']} -> {l['lesson']}" for l in lessons]
    return "\n".join(out)
