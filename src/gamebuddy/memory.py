"""SQLite persistence: continuous conversation, long-term notes, coach log."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from gamebuddy.llm.base import Message
from gamebuddy.paths import db_file, ensure_dirs

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at REAL NOT NULL,
  game TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  role TEXT NOT NULL,
  record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  game TEXT DEFAULT '',
  note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pins (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  title TEXT, markdown TEXT, kind TEXT, updated_at REAL
);
CREATE TABLE IF NOT EXISTS coach_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  game TEXT DEFAULT '',
  stage TEXT NOT NULL,
  decision TEXT DEFAULT '',
  detail TEXT DEFAULT ''
);
"""


class Store:
    def __init__(self, path: Path | None = None):
        if path is None:
            ensure_dirs()
            path = db_file()
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self.conversation_id = self._current_conversation()

    # ---- conversations ---------------------------------------------------
    def _current_conversation(self) -> int:
        row = self._conn.execute("SELECT id FROM conversations ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return int(row[0])
        return self.new_conversation()

    def new_conversation(self, game: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO conversations(started_at, game) VALUES (?, ?)", (time.time(), game)
            )
            self._conn.commit()
            self.conversation_id = int(cur.lastrowid)
            return self.conversation_id

    def add_message(self, msg: Message) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages(conversation_id, created_at, role, record) VALUES (?, ?, ?, ?)",
                (
                    self.conversation_id,
                    time.time(),
                    msg.role,
                    json.dumps(msg.to_record(), ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def recent_messages(self, limit: int = 30) -> list[Message]:
        rows = self._conn.execute(
            "SELECT record FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (self.conversation_id, limit),
        ).fetchall()
        msgs = [Message.from_record(json.loads(r[0])) for r in reversed(rows)]
        return _trim_dangling_tools(msgs)

    def clear_conversation(self) -> None:
        self.new_conversation()

    # ---- memories --------------------------------------------------------
    def remember(self, note: str, game: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memories(created_at, game, note) VALUES (?, ?, ?)", (time.time(), game, note)
            )
            self._conn.commit()

    def memories(self, limit: int = 40, game: str = "") -> list[str]:
        if game:
            rows = self._conn.execute(
                "SELECT note FROM memories WHERE game = ? OR game = '' ORDER BY id DESC LIMIT ?",
                (game, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT note FROM memories ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    def search_memories(self, query: str, limit: int = 10) -> list[str]:
        words = [w for w in query.lower().split() if len(w) > 2]
        rows = self._conn.execute("SELECT note FROM memories ORDER BY id DESC LIMIT 500").fetchall()
        scored = []
        for (note,) in rows:
            low = note.lower()
            score = sum(1 for w in words if w in low)
            if score or not words:
                scored.append((score, note))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:limit]]

    def forget_all(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories")
            self._conn.commit()

    # ---- pin -------------------------------------------------------------
    def save_pin(self, title: str, markdown: str, kind: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO pins(id, title, markdown, kind, updated_at) VALUES (1, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, markdown=excluded.markdown, "
                "kind=excluded.kind, updated_at=excluded.updated_at",
                (title, markdown, kind, time.time()),
            )
            self._conn.commit()

    def load_pin(self) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT title, markdown, kind FROM pins WHERE id = 1").fetchone()
        if not row or not row[1]:
            return None
        return {"title": row[0], "markdown": row[1], "kind": row[2]}

    def clear_pin(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM pins")
            self._conn.commit()

    # ---- coach log -------------------------------------------------------
    def log_coach(self, stage: str, decision: str = "", detail: str = "", game: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO coach_log(created_at, game, stage, decision, detail) VALUES (?, ?, ?, ?, ?)",
                (time.time(), game, stage, decision, detail[:2000]),
            )
            self._conn.commit()

    def coach_stats(self, since: float = 0.0) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT stage || ':' || decision, COUNT(*) FROM coach_log WHERE created_at >= ? GROUP BY 1",
            (since,),
        ).fetchall()
        return {k: int(v) for k, v in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _trim_dangling_tools(msgs: list[Message]) -> list[Message]:
    """Drop a leading tool result without its assistant call, and a trailing call without result."""
    while msgs and msgs[0].role == "tool":
        msgs.pop(0)
    if msgs and msgs[-1].role == "assistant" and msgs[-1].tool_calls:
        msgs.pop()
    return msgs
