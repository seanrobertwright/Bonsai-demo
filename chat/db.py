"""SQLite storage for conversations and messages."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone


class ChatDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
        """)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def create_conversation(self, title: str) -> dict:
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )
        self.conn.commit()
        return {"id": cid, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_title(self, conversation_id: str, title: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conversation_id),
        )
        self.conn.commit()

    def delete_conversation(self, conversation_id: str) -> None:
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self.conn.commit()

    def add_message(self, conversation_id: str, role: str, content: str, tool_calls: list | None = None) -> dict:
        mid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        tc_json = json.dumps(tool_calls) if tool_calls else None
        self.conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (mid, conversation_id, role, content, tc_json, now),
        )
        self.conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        self.conn.commit()
        return {"id": mid, "role": role, "content": content, "tool_calls": tool_calls, "created_at": now}

    def get_messages(self, conversation_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tool_calls"] = json.loads(d["tool_calls"]) if d["tool_calls"] else None
            result.append(d)
        return result

    def close(self):
        self.conn.close()
