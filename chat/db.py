"""SQLite storage for conversations and messages."""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone


_STOPWORDS = {"the", "a", "an", "is", "am", "are", "was", "were",
              "user", "i", "my", "me", "you", "your", "to", "of",
              "in", "on", "at", "and", "or"}


def _prefix_signature(content: str, n: int = 4) -> str:
    """Normalize content and return a prefix signature for dedup.

    Used for catching "User lives in Boston" -> "User lives in Seattle" as
    updates to the same underlying fact. Lowercases, strips punctuation,
    drops stopwords, stems *-s/-es/-ing/-e endings very crudely, takes the
    first N significant words, then drops the trailing word when the
    remainder still has at least one word. Dropping the trailing word is
    what makes "lives in Boston" and "lives in Seattle" collide on "liv"
    without requiring the helper to know anything about proper nouns.
    """
    tokens = re.findall(r"[a-z]+", content.lower())
    significant = []
    for t in tokens:
        if t in _STOPWORDS:
            continue
        # Crude stem: strip trailing ing/es/s/e so "lives"/"live"/"living" match.
        if t.endswith("ing") and len(t) > 4:
            t = t[:-3]
        elif t.endswith("es") and len(t) > 3:
            t = t[:-2]
        elif t.endswith("s") and len(t) > 2:
            t = t[:-1]
        if t.endswith("e") and len(t) > 3:
            t = t[:-1]
        significant.append(t)
        if len(significant) >= n:
            break
    # Drop the trailing significant word when at least one remains. This
    # peels off the "variable" part of a fact (the city, the preference,
    # the value) so that updates collide with their prior statement.
    if len(significant) > 1:
        significant = significant[:-1]
    return " ".join(significant)


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
        now = datetime.now(timezone.utc).isoformat()
        stored = content.strip()
        normalized = stored.lower()

        # 1. Exact-match dedup (case- and whitespace-insensitive)
        existing = self.conn.execute(
            "SELECT id FROM memories WHERE LOWER(TRIM(content)) = ?",
            (normalized,),
        ).fetchone()
        if existing:
            return {"status": "duplicate", "id": existing["id"]}

        # 2. Prefix-signature dedup -- replace an existing memory with the same
        # 4-significant-word prefix (catches "lives in Boston" -> "lives in Seattle").
        new_sig = _prefix_signature(stored)
        replaced_id = None
        replaced_content = None
        if new_sig:  # skip if signature is empty (too few significant words)
            rows = self.conn.execute("SELECT id, content FROM memories").fetchall()
            for r in rows:
                if _prefix_signature(r["content"]) == new_sig:
                    replaced_id = r["id"]
                    replaced_content = r["content"]
                    self.conn.execute("DELETE FROM memories WHERE id = ?", (replaced_id,))
                    break

        # 3. Fresh insert
        mid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO memories (id, content, created_at, source) VALUES (?, ?, ?, ?)",
            (mid, stored, now, source),
        )
        # Auto-prune to 50 (FIFO across all sources). Tiebreak on rowid so
        # rapid inserts with identical ISO timestamps still evict in
        # insertion order rather than implementation-defined order.
        self.conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT id FROM memories ORDER BY created_at DESC, rowid DESC LIMIT 50
            )
        """)
        self.conn.commit()

        if replaced_id:
            return {
                "status": "updated",
                "id": mid,
                "content": stored,
                "created_at": now,
                "source": source,
                "replaced_id": replaced_id,
                "replaced_content": replaced_content,
            }
        return {
            "status": "saved",
            "id": mid,
            "content": stored,
            "created_at": now,
            "source": source,
        }

    def list_memories(self) -> list[dict]:
        # rowid tiebreak makes ordering deterministic when ISO timestamps collide.
        rows = self.conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
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
