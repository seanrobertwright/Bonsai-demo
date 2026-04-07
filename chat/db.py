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
        # Add columns if missing (migrations)
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            self.conn.execute("ALTER TABLE conversations ADD COLUMN system_prompt TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        try:
            self.conn.execute(
                "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'user'"
            )
        except sqlite3.OperationalError:
            pass
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
            "SELECT * FROM conversations ORDER BY pinned DESC, updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def toggle_pin(self, conversation_id: str) -> bool:
        row = self.conn.execute("SELECT pinned FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        new_val = 0 if row and row["pinned"] else 1
        self.conn.execute("UPDATE conversations SET pinned = ? WHERE id = ?", (new_val, conversation_id))
        self.conn.commit()
        return bool(new_val)

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

    def search_conversations(self, query: str) -> list[dict]:
        """Full-text search across conversation titles and message content."""
        like_query = f"%{query}%"
        rows = self.conn.execute("""
            SELECT DISTINCT c.id, c.title, c.updated_at, m.content as snippet
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.title LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC
            LIMIT 20
        """, (like_query, like_query)).fetchall()

        results = []
        seen = set()
        for r in rows:
            if r["id"] not in seen:
                seen.add(r["id"])
                results.append({
                    "id": r["id"],
                    "title": r["title"],
                    "snippet": r["snippet"][:120] if r["snippet"] else "",
                    "updated_at": r["updated_at"],
                })
        return results

    def delete_last_assistant_message(self, conversation_id: str) -> str | None:
        """Delete the last assistant message. Returns the last user message content for re-sending."""
        row = self.conn.execute(
            "SELECT id FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        if row:
            self.conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            self.conn.commit()

        # Return last user message for re-send
        user_row = self.conn.execute(
            "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        return user_row["content"] if user_row else None

    def delete_messages_after_last_user(self, conversation_id: str) -> None:
        """Delete the last user message and all messages after it."""
        row = self.conn.execute(
            "SELECT created_at FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        if row:
            self.conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND created_at >= ?",
                (conversation_id, row["created_at"]),
            )
            self.conn.commit()

    def add_memory(self, content: str, source: str = "user") -> dict:
        mid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO memories (id, content, created_at, source) VALUES (?, ?, ?, ?)",
            (mid, content, now, source),
        )
        # Auto-prune to 50 (FIFO across all sources)
        self.conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT id FROM memories ORDER BY created_at DESC LIMIT 50
            )
        """)
        self.conn.commit()
        return {"id": mid, "content": content, "created_at": now, "source": source}

    def list_memories(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, memory_id: str) -> None:
        self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()

    def delete_all_memories(self) -> None:
        self.conn.execute("DELETE FROM memories")
        self.conn.commit()

    def get_system_prompt(self, conversation_id: str) -> str:
        row = self.conn.execute("SELECT system_prompt FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return row["system_prompt"] if row and row["system_prompt"] else ""

    def set_system_prompt(self, conversation_id: str, prompt: str) -> None:
        self.conn.execute("UPDATE conversations SET system_prompt = ? WHERE id = ?", (prompt, conversation_id))
        self.conn.commit()

    def close(self):
        self.conn.close()
