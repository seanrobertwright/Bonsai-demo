# Autonomous Memory Implementation Plan

> **For agentic workers:** REQUIRED: Use lril-superpowers:subagent-driven-development (if subagents available) or lril-superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Bonsai chat model decide on its own what's worth remembering about the user, and persist those facts across sessions via a new `remember` tool.

**Architecture:** One new tool (`remember`) wired into the existing agent loop. Server-side dedup on write (exact match + 4-word-prefix heuristic). Cap raised 20 → 50, plain FIFO. All memories dump into every system prompt (no retrieval). Frontend shows a subtle toast with undo when a save happens, via the existing `tool_end` WebSocket event.

**Tech Stack:** Python (FastAPI), SQLite, vanilla JS frontend, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-04-07-autonomous-memory-design.md`

---

## File Structure

**Create:**
- `chat/tools/remember.py` — new tool module following `chat/tools/calculator.py` pattern.
- `chat/tests/test_memory_dedup.py` — unit tests for DB-layer dedup.
- `chat/tests/test_remember_tool.py` — unit tests for the tool.
- `chat/tests/test_agent_memory.py` — integration test for the agent loop + memory injection.

**Modify:**
- `chat/db.py` — add `source` column migration; change `add_memory` to accept `source` and perform dedup; raise cap 20 → 50; add small helpers.
- `chat/tools/__init__.py` — register `RememberTool` in `create_registry()`.
- `chat/agent.py` — update system prompt: describe `remember` rules, add negative+positive examples.
- `chat/app.py` — sort memories oldest-first in `custom_context`, append contradiction tie-breaker instruction.
- `chat/static/js/memory.js` — add `showMemoryToast(result)` + undo handler.
- `chat/static/js/core.js` — in the `tool_end` case, call `showMemoryToast` when `data.name === 'remember'`.
- `chat/static/style.css` — `.memory-toast` class.

No new processes, no new dependencies.

---

## Chunk 1: DB layer — schema, dedup, cap

### Task 1: Add `source` column migration + raise cap

**Files:**
- Modify: `chat/db.py:47-54` (memories table creation) and `:174-185` (`add_memory`)
- Test: `chat/tests/test_memory_dedup.py` (new)

- [ ] **Step 1: Write the failing test for migration + source default**

Create `chat/tests/test_memory_dedup.py`:

```python
import os
import tempfile
import pytest
from chat.db import ChatDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = ChatDB(path)
    yield database
    database.close()
    os.unlink(path)


def test_memory_has_source_column_defaulting_to_user(db):
    mem = db.add_memory("User lives in Boston")
    assert mem["source"] == "user"


def test_memory_add_with_explicit_source(db):
    mem = db.add_memory("User lives in Boston", source="model")
    assert mem["source"] == "model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest chat/tests/test_memory_dedup.py -v`
Expected: FAIL — either `TypeError: add_memory() got unexpected keyword 'source'` or `KeyError: 'source'`.

- [ ] **Step 3: Add migration in `_init_tables`**

In `chat/db.py`, after the `CREATE TABLE IF NOT EXISTS memories` block (around line 53), add an `ALTER TABLE` migration inside a try/except that matches the existing migration style (see lines 34-46):

```python
        try:
            self.conn.execute(
                "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'user'"
            )
        except sqlite3.OperationalError:
            pass
```

Place it after the `memories` table creation and before `self.conn.commit()`.

- [ ] **Step 4: Update `add_memory` signature and insert**

Replace the current `add_memory` (lines 174-185) with:

```python
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
```

Changes from current: extra `source` param, extra column in INSERT, cap `20 → 50`, `source` in return dict.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest chat/tests/test_memory_dedup.py -v`
Expected: both tests PASS.

Also run the existing DB test suite to make sure nothing regressed:

Run: `pytest chat/tests/test_db.py -v`
Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add chat/db.py chat/tests/test_memory_dedup.py
git commit -m "feat(db): add memory source column and raise cap to 50"
```

---

### Task 2: Cap enforcement at 50

**Files:**
- Test: `chat/tests/test_memory_dedup.py` (extend)

Note: the cap change already happened in Task 1. This task adds a test to lock it in.

- [ ] **Step 1: Write the failing test for cap=50**

Add to `chat/tests/test_memory_dedup.py`:

```python
def test_memory_cap_at_50(db):
    for i in range(55):
        db.add_memory(f"fact {i}")
    mems = db.list_memories()
    assert len(mems) == 50
    # Oldest should be evicted; newest kept. list_memories returns newest-first.
    assert mems[0]["content"] == "fact 54"
    # "fact 0" through "fact 4" should be gone.
    contents = {m["content"] for m in mems}
    assert "fact 0" not in contents
    assert "fact 4" not in contents
    assert "fact 5" in contents
```

- [ ] **Step 2: Run test**

Run: `pytest chat/tests/test_memory_dedup.py::test_memory_cap_at_50 -v`
Expected: PASS (already implemented in Task 1).

- [ ] **Step 3: Commit**

```bash
git add chat/tests/test_memory_dedup.py
git commit -m "test(db): lock in memory cap=50 behavior"
```

---

### Task 3: Exact-match dedup

**Files:**
- Modify: `chat/db.py` — extend `add_memory` with dedup
- Test: `chat/tests/test_memory_dedup.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `chat/tests/test_memory_dedup.py`:

```python
def test_exact_duplicate_returns_duplicate_status(db):
    first = db.add_memory("User lives in Boston", source="model")
    assert first["status"] == "saved"
    second = db.add_memory("User lives in Boston", source="model")
    assert second["status"] == "duplicate"
    mems = db.list_memories()
    assert len(mems) == 1


def test_exact_dedup_is_case_and_whitespace_insensitive(db):
    db.add_memory("User lives in Boston", source="model")
    dup = db.add_memory("  USER lives in boston  ", source="model")
    assert dup["status"] == "duplicate"
    assert len(db.list_memories()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest chat/tests/test_memory_dedup.py -v -k duplicate`
Expected: FAIL — no `status` key in return dict.

- [ ] **Step 3: Implement exact-match dedup in `add_memory`**

Replace `add_memory` in `chat/db.py` with:

```python
    def add_memory(self, content: str, source: str = "user") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        normalized = content.strip().lower()

        # 1. Exact-match dedup (case- and whitespace-insensitive)
        existing = self.conn.execute(
            "SELECT id FROM memories WHERE LOWER(TRIM(content)) = ?",
            (normalized,),
        ).fetchone()
        if existing:
            return {"status": "duplicate", "id": existing["id"]}

        # 2. Fresh insert
        mid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO memories (id, content, created_at, source) VALUES (?, ?, ?, ?)",
            (mid, content.strip(), now, source),
        )
        # FIFO cap at 50
        self.conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT id FROM memories ORDER BY created_at DESC LIMIT 50
            )
        """)
        self.conn.commit()
        return {"status": "saved", "id": mid, "content": content.strip(), "created_at": now, "source": source}
```

Note: earlier tests assumed `add_memory` returned `{id, content, created_at, source}` without a `status` key. Update those earlier tests to check `mem["status"] == "saved"` and then `mem["source"]` etc.

- [ ] **Step 4: Update earlier tests to match new return shape**

In `chat/tests/test_memory_dedup.py`, change the first two tests:

```python
def test_memory_has_source_column_defaulting_to_user(db):
    mem = db.add_memory("User lives in Boston")
    assert mem["status"] == "saved"
    assert mem["source"] == "user"


def test_memory_add_with_explicit_source(db):
    mem = db.add_memory("User lives in Boston", source="model")
    assert mem["status"] == "saved"
    assert mem["source"] == "model"
```

Also check `chat/app.py:169-171` — `add_memory(data["content"])` uses the return value as-is in the JSON response. The old return was `{id, content, created_at}`; the new one is `{status, id, content, created_at, source}`. This is additive, so existing frontend code keeps working. No change needed here (verify with grep in Step 6).

- [ ] **Step 5: Run tests**

Run: `pytest chat/tests/test_memory_dedup.py -v`
Expected: all PASS.

- [ ] **Step 6: Verify nothing else broke**

Run: `pytest chat/tests/ -v`
Expected: all existing tests PASS.

Also verify the `/api/memory` POST endpoint still works with the new return shape:

Run: `grep -n "add_memory" chat/app.py`
Expected: one hit at `chat/app.py:171` returning the dict as-is. Additive fields are fine.

- [ ] **Step 7: Commit**

```bash
git add chat/db.py chat/tests/test_memory_dedup.py
git commit -m "feat(db): exact-match dedup in add_memory"
```

---

### Task 4: Prefix dedup (replace on update) — **DROPPED**

> **Status:** Attempted in commit `172a737`, reverted in `8989016`. The heuristic was unworkable at v1 quality — see `docs/superpowers/specs/2026-04-07-autonomous-memory-design.md` § Implementation notes. Exact-match dedup from Task 3 is the only dedup layer in the shipped feature. The rest of this Task 4 section is preserved below as a historical record of the attempted approach; skip directly to Task 5.

**Files:**
- Modify: `chat/db.py` — add prefix-signature helper + replace logic
- Test: `chat/tests/test_memory_dedup.py` (extend)

- [ ] **Step 1: Write failing tests**

Add to `chat/tests/test_memory_dedup.py`:

```python
def test_prefix_dedup_replaces_stale_fact(db):
    first = db.add_memory("User lives in Boston", source="model")
    second = db.add_memory("User lives in Seattle", source="model")
    assert second["status"] == "updated"
    assert second["replaced_id"] == first["id"]
    assert second["replaced_content"] == "User lives in Boston"
    mems = db.list_memories()
    assert len(mems) == 1
    assert mems[0]["content"] == "User lives in Seattle"


def test_prefix_dedup_ignores_stopwords(db):
    # "I live in Boston" and "User lives in Boston" should collide
    # after dropping stopwords (I, user) and normalizing lives/live.
    # We only require: the 4-significant-word prefix signature matches.
    db.add_memory("I live in Boston", source="model")
    dup = db.add_memory("The user lives in Boston", source="model")
    # Exact-match won't catch this; prefix dedup should either UPDATE or mark DUPLICATE.
    # Since content differs, we expect UPDATE (replace first with second).
    assert dup["status"] in ("updated", "duplicate")
    assert len(db.list_memories()) == 1


def test_prefix_dedup_allows_unrelated_facts(db):
    db.add_memory("User lives in Boston", source="model")
    other = db.add_memory("User prefers terse answers", source="model")
    assert other["status"] == "saved"
    assert len(db.list_memories()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest chat/tests/test_memory_dedup.py -v -k prefix`
Expected: FAIL — prefix dedup not implemented.

- [ ] **Step 3: Add prefix signature helper**

In `chat/db.py`, above the `ChatDB` class, add a module-level helper:

```python
import re

_STOPWORDS = {"the", "a", "an", "is", "am", "are", "was", "were",
              "user", "i", "my", "me", "you", "your", "to", "of",
              "in", "on", "at", "and", "or"}


def _prefix_signature(content: str, n: int = 4) -> str:
    """Normalize content and return the first N significant words as a signature.

    Used for catching "User lives in Boston" → "User lives in Seattle" as
    updates to the same underlying fact. Lowercases, strips punctuation,
    drops stopwords, stems *-s/-es/-ing endings very crudely, joins first N.
    """
    tokens = re.findall(r"[a-z]+", content.lower())
    significant = []
    for t in tokens:
        if t in _STOPWORDS:
            continue
        # Crude stem: strip trailing s/es/ing so "lives"/"live"/"living" match.
        if t.endswith("ing") and len(t) > 4:
            t = t[:-3]
        elif t.endswith("es") and len(t) > 3:
            t = t[:-2]
        elif t.endswith("s") and len(t) > 2:
            t = t[:-1]
        significant.append(t)
        if len(significant) >= n:
            break
    return " ".join(significant)
```

- [ ] **Step 4: Use prefix signature in `add_memory`**

Replace `add_memory` in `chat/db.py` with:

```python
    def add_memory(self, content: str, source: str = "user") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        normalized = content.strip()
        lowered = normalized.lower()

        # 1. Exact-match dedup
        existing = self.conn.execute(
            "SELECT id FROM memories WHERE LOWER(TRIM(content)) = ?",
            (lowered,),
        ).fetchone()
        if existing:
            return {"status": "duplicate", "id": existing["id"]}

        # 2. Prefix-signature dedup — replace an existing memory with the same
        # 4-significant-word prefix (catches "lives in Boston" → "lives in Seattle").
        new_sig = _prefix_signature(normalized)
        replaced_id = None
        replaced_content = None
        if new_sig:  # skip if signature is empty (too few significant words)
            rows = self.conn.execute(
                "SELECT id, content FROM memories"
            ).fetchall()
            for r in rows:
                if _prefix_signature(r["content"]) == new_sig:
                    replaced_id = r["id"]
                    replaced_content = r["content"]
                    self.conn.execute("DELETE FROM memories WHERE id = ?", (replaced_id,))
                    break

        # 3. Insert fresh
        mid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO memories (id, content, created_at, source) VALUES (?, ?, ?, ?)",
            (mid, normalized, now, source),
        )
        # FIFO cap at 50
        self.conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT id FROM memories ORDER BY created_at DESC LIMIT 50
            )
        """)
        self.conn.commit()

        if replaced_id:
            return {
                "status": "updated",
                "id": mid,
                "content": normalized,
                "created_at": now,
                "source": source,
                "replaced_id": replaced_id,
                "replaced_content": replaced_content,
            }
        return {
            "status": "saved",
            "id": mid,
            "content": normalized,
            "created_at": now,
            "source": source,
        }
```

- [ ] **Step 5: Run all dedup tests**

Run: `pytest chat/tests/test_memory_dedup.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest chat/tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add chat/db.py chat/tests/test_memory_dedup.py
git commit -m "feat(db): prefix-signature dedup for memory updates"
```

---

## Chunk 2: `remember` tool + agent wiring

### Task 5: Create `RememberTool`

**Files:**
- Create: `chat/tools/remember.py`
- Create: `chat/tests/test_remember_tool.py`

- [ ] **Step 1: Write failing tests**

Create `chat/tests/test_remember_tool.py`:

```python
import os
import tempfile
import pytest
from chat.db import ChatDB
from chat.tools.remember import RememberTool


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    d = ChatDB(path)
    yield d
    d.close()
    os.unlink(path)


@pytest.fixture
def tool(db):
    return RememberTool(db)


def test_definition(tool):
    d = tool.definition
    assert d["name"] == "remember"
    assert "parameters" in d
    assert "content" in d["parameters"]["properties"]


@pytest.mark.asyncio
async def test_save_new_fact(tool, db):
    result = await tool.execute({"content": "User lives in Boston"})
    assert result["status"] == "saved"
    assert result["content"] == "User lives in Boston"
    assert "id" in result
    assert len(db.list_memories()) == 1


@pytest.mark.asyncio
async def test_save_duplicate(tool, db):
    await tool.execute({"content": "User lives in Boston"})
    result = await tool.execute({"content": "User lives in Boston"})
    assert result["status"] == "duplicate"
    assert len(db.list_memories()) == 1


@pytest.mark.asyncio
async def test_save_update(tool, db):
    await tool.execute({"content": "User lives in Boston"})
    result = await tool.execute({"content": "User lives in Seattle"})
    assert result["status"] == "updated"
    assert result["replaced_content"] == "User lives in Boston"
    assert len(db.list_memories()) == 1


@pytest.mark.asyncio
async def test_reject_empty(tool):
    result = await tool.execute({"content": "   "})
    assert "error" in result


@pytest.mark.asyncio
async def test_reject_too_long(tool):
    result = await tool.execute({"content": "x" * 500})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest chat/tests/test_remember_tool.py -v`
Expected: FAIL — `ImportError: cannot import name 'RememberTool'`.

- [ ] **Step 3: Create the tool**

Create `chat/tools/remember.py`:

```python
"""Remember tool — lets the model save durable facts about the user."""

from chat.db import ChatDB


class RememberTool:
    """Saves a durable fact about the user to the memory store.

    The model decides when to call this; server-side dedup in db.add_memory
    handles duplicate and replace-on-update cases.
    """

    def __init__(self, db: ChatDB):
        self.db = db

    @property
    def definition(self) -> dict:
        return {
            "name": "remember",
            "description": (
                "Save a durable fact about the user so you'll know it in future "
                "conversations. ONLY use for stable facts about who the user is "
                "(name, location, job, family, pets), long-running projects or "
                "goals, or explicit preferences about how they want you to behave. "
                "DO NOT use for passing remarks, questions the user asked, "
                "information about topics (only about the user), anything already "
                "in 'Things you know about the user', or anything you're not "
                "confident will still be true next week. When in doubt, don't "
                "save. Save at most one fact per turn. Write content as a short "
                "third-person sentence, e.g. 'User lives in Boston'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "One short third-person sentence describing the fact.",
                    },
                },
                "required": ["content"],
            },
        }

    async def execute(self, params: dict) -> dict:
        content = (params.get("content") or "").strip()
        if not content:
            return {"error": "Empty content — nothing to remember."}
        if len(content) > 200:
            return {"error": "Content too long (max 200 chars)."}

        return self.db.add_memory(content, source="model")
```

- [ ] **Step 4: Run tests**

Run: `pytest chat/tests/test_remember_tool.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tools/remember.py chat/tests/test_remember_tool.py
git commit -m "feat(tools): add remember tool for autonomous memory saves"
```

---

### Task 6: Register `RememberTool` in the registry

**Files:**
- Modify: `chat/tools/__init__.py`
- Modify: `chat/app.py` — pass `db` into registry creation
- Modify: any other caller of `create_registry()` (check with grep)

- [ ] **Step 1: Find all callers of `create_registry`**

Run: `grep -rn "create_registry" chat/`
Expected: hits in `chat/app.py` and possibly tests. Note each one.

- [ ] **Step 2: Update `create_registry` to accept `db`**

In `chat/tools/__init__.py`, change `create_registry`:

```python
def create_registry(db=None) -> ToolRegistry:
    """Create registry with all built-in tools.

    If `db` is provided, registers db-dependent tools (currently: remember).
    """
    from chat.tools.calculator import CalculatorTool
    from chat.tools.file_io import FileIOTool
    from chat.tools.python_exec import PythonExecTool
    from chat.tools.url_fetch import URLFetchTool
    from chat.tools.weather import WeatherTool
    from chat.tools.web_search import WebSearchTool

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(URLFetchTool())
    registry.register(CalculatorTool())
    registry.register(FileIOTool())
    registry.register(WeatherTool())
    registry.register(PythonExecTool())

    if db is not None:
        from chat.tools.remember import RememberTool
        registry.register(RememberTool(db))

    return registry
```

`db=None` default preserves backward compatibility with any caller that doesn't want db-backed tools.

- [ ] **Step 3: Update `chat/app.py` to pass `db`**

Find where `create_registry()` is called in `chat/app.py` (likely near module-level after `db` is created). Change the call:

```python
registry = create_registry(db=db)
```

- [ ] **Step 4: Run the full suite**

Run: `pytest chat/tests/ -v`
Expected: all PASS. Existing tests that call `create_registry()` without args still work.

- [ ] **Step 5: Manual smoke: server boots**

Run: `python -c "from chat.app import app; print('ok')"`
Expected: prints `ok`, no import errors.

- [ ] **Step 6: Commit**

```bash
git add chat/tools/__init__.py chat/app.py
git commit -m "feat(tools): register remember tool in registry"
```

---

### Task 7: Update system prompt with `remember` rules + examples

**Files:**
- Modify: `chat/agent.py:18-93` (`_build_system_prompt`)

- [ ] **Step 1: Add `remember` to the "Specific tool rules" block**

In `chat/agent.py`, locate the "Specific tool rules:" section inside `_build_system_prompt` (around lines 52-66). After the existing rules (web_search, url_fetch, calculator, weather, file_io, python_exec), add:

```python
            "- **remember**: Use sparingly. Most turns should NOT save anything. "
            "Only save when the user has just shared a durable fact about "
            "themselves, a long-running project, or a behavior preference — and "
            "it is not already listed in 'Things you know about the user'. "
            "Never save trivia, passing remarks, or facts about topics the user "
            "asked about.\n\n"
```

Make sure the concatenation lines up with the surrounding string (it's all one big `+`-joined string).

- [ ] **Step 2: Add negative + positive examples to the Examples block**

In the `## Examples` block (lines 75-92), add two new examples just before the final python_exec example:

```python
            "User: what's the capital of France?\n"
            "You: The capital of France is Paris.\n\n"
            "User: I just moved to Seattle last month.\n"
            'You: {"name": "remember", "arguments": {"content": "User lives in Seattle"}}\n\n'
```

The first reinforces "don't save trivia about topics." The second shows a correct save.

- [ ] **Step 3: Sanity-check the prompt builds**

Run:

```bash
python -c "from chat.tools import create_registry; from chat.agent import AgentLoop; \
  r = create_registry(); a = AgentLoop(r); print(a._build_system_prompt()[:500])"
```

Expected: prints the first 500 chars of the system prompt without errors.

- [ ] **Step 4: Verify remember rule is included when db is passed**

Run:

```bash
python -c "from chat.db import ChatDB; from chat.tools import create_registry; \
  from chat.agent import AgentLoop; import tempfile, os; \
  fd, p = tempfile.mkstemp(); os.close(fd); \
  d = ChatDB(p); r = create_registry(db=d); a = AgentLoop(r); \
  sp = a._build_system_prompt(); \
  assert 'remember' in sp.lower(), 'remember missing'; \
  print('ok'); d.close(); os.unlink(p)"
```

Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add chat/agent.py
git commit -m "feat(agent): add remember tool rules and examples to system prompt"
```

---

## Chunk 3: Recall injection + integration test

### Task 8: Sort memories oldest-first and add contradiction tie-breaker

**Files:**
- Modify: `chat/app.py:324-331`

- [ ] **Step 1: Locate the injection block**

In `chat/app.py` around lines 324-331, the current code is:

```python
memories = db.list_memories()
...
if memories:
    custom_context += "Things you know about the user:\n"
    custom_context += "\n".join(f"- {m['content']}" for m in memories)
    custom_context += "\n\n"
```

`db.list_memories()` returns newest-first (`ORDER BY created_at DESC`). We want oldest-first in the prompt so "most recent = last."

- [ ] **Step 2: Reverse ordering and add tie-breaker instruction**

Replace the `if memories:` block with:

```python
            if memories:
                # Show oldest-first so the most recent fact appears last —
                # the tie-breaker instruction below then just means "trust the last one."
                memories_oldest_first = list(reversed(memories))
                custom_context += "Things you know about the user:\n"
                custom_context += "\n".join(f"- {m['content']}" for m in memories_oldest_first)
                custom_context += (
                    "\n\n(If two of the facts above contradict each other, "
                    "trust the most recent one — listed last.)\n\n"
                )
```

- [ ] **Step 3: Smoke-test the server still boots**

Run: `python -c "from chat.app import app; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add chat/app.py
git commit -m "feat(app): inject memories oldest-first with contradiction tie-breaker"
```

---

### Task 9: Integration test — agent loop emits `remember` and it lands in DB

**Files:**
- Create: `chat/tests/test_agent_memory.py`

- [ ] **Step 1: Write the failing test**

Create `chat/tests/test_agent_memory.py`:

```python
"""Integration test: agent loop emits remember tool call, DB is updated,
next turn's custom_context contains the fact."""

import os
import tempfile
import pytest
from unittest.mock import patch

from chat.db import ChatDB
from chat.tools import create_registry
from chat.agent import AgentLoop


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    d = ChatDB(path)
    yield d
    d.close()
    os.unlink(path)


@pytest.fixture
def agent(db):
    return AgentLoop(create_registry(db=db))


@pytest.mark.asyncio
async def test_agent_remember_tool_writes_to_db(agent, db):
    # Fake two-round stream: first round emits a remember tool call,
    # second round emits a normal reply.
    rounds = [
        '{"name": "remember", "arguments": {"content": "User lives in Boston"}}',
        "Got it — I'll remember that.",
    ]
    call_count = {"n": 0}

    async def fake_stream(messages):
        idx = call_count["n"]
        call_count["n"] += 1
        for ch in rounds[idx]:
            yield ch

    with patch.object(agent, "_stream_completion", side_effect=fake_stream):
        result = await agent.run(
            messages=[{"role": "user", "content": "I live in Boston."}],
        )

    mems = db.list_memories()
    assert len(mems) == 1
    assert mems[0]["content"] == "User lives in Boston"
    assert mems[0]["source"] == "model"
    assert result["content"] == "Got it — I'll remember that."


@pytest.mark.asyncio
async def test_agent_remember_duplicate_does_not_insert_twice(agent, db):
    # Seed an existing memory.
    db.add_memory("User lives in Boston", source="user")

    rounds = [
        '{"name": "remember", "arguments": {"content": "User lives in Boston"}}',
        "Noted.",
    ]
    call_count = {"n": 0}

    async def fake_stream(messages):
        idx = call_count["n"]
        call_count["n"] += 1
        for ch in rounds[idx]:
            yield ch

    with patch.object(agent, "_stream_completion", side_effect=fake_stream):
        await agent.run(messages=[{"role": "user", "content": "Boston."}])

    assert len(db.list_memories()) == 1
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `pytest chat/tests/test_agent_memory.py -v`

If they pass on the first try — great, wiring is correct. If they fail, the most likely causes are:
- The tool isn't registered because `create_registry` wasn't called with `db` (check Task 6 was completed).
- The agent loop doesn't pass tool args correctly for `remember` (no expected because remember has a simple string arg; likely not the issue).
- Mocking shape is wrong — `_stream_completion` is an async generator; the fake must also be one. If pytest complains about the fake not being async, adjust.

- [ ] **Step 3: Fix any issues and re-run**

Iterate until both tests PASS.

- [ ] **Step 4: Run the full suite**

Run: `pytest chat/tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tests/test_agent_memory.py
git commit -m "test(agent): integration test for remember tool in the loop"
```

---

## Chunk 4: Frontend toast + undo

### Task 10: Add `.memory-toast` CSS

**Files:**
- Modify: `chat/static/style.css`

- [ ] **Step 1: Append the toast styles**

Append to `chat/static/style.css`:

```css
/* ── Memory save toast (autonomous memory feature) ── */
.memory-toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    max-width: 360px;
    padding: 12px 16px;
    background: var(--bg-elevated, #1f2937);
    color: var(--text-primary, #f3f4f6);
    border: 1px solid var(--border, #374151);
    border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
    font-size: 13px;
    line-height: 1.4;
    z-index: 9999;
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 0.2s ease, transform 0.2s ease;
    pointer-events: auto;
}
.memory-toast.visible {
    opacity: 1;
    transform: translateY(0);
}
.memory-toast .memory-toast-content {
    font-style: italic;
    opacity: 0.9;
}
.memory-toast .memory-toast-undo {
    margin-left: 12px;
    color: #60a5fa;
    cursor: pointer;
    text-decoration: underline;
    font-style: normal;
}
.memory-toast .memory-toast-undo:hover {
    color: #93c5fd;
}
```

If the existing `style.css` doesn't use CSS variables, the fallback colors in the `var(..., fallback)` syntax will take effect.

- [ ] **Step 2: Commit**

```bash
git add chat/static/style.css
git commit -m "style: add memory-toast styles"
```

---

### Task 11: Implement `showMemoryToast` in `memory.js`

**Files:**
- Modify: `chat/static/js/memory.js`

- [ ] **Step 1: Append the toast function**

Append to `chat/static/js/memory.js`:

```javascript
// ── Autonomous memory: save toast + undo ──

function showMemoryToast(result) {
    // result shape: { status: 'saved'|'updated'|'duplicate', id, content, replaced_id?, replaced_content? }
    if (!result || result.status === 'duplicate') return;
    if (result.error) return;

    const verb = result.status === 'updated' ? 'Updated' : 'Remembered';
    const toast = document.createElement('div');
    toast.className = 'memory-toast';
    toast.innerHTML = `
        <span>💾 ${verb}: </span>
        <span class="memory-toast-content"></span>
        <span class="memory-toast-undo">Undo</span>
    `;
    // textContent, not innerHTML, for user content — prevents XSS if the
    // model emits HTML in the memory content.
    toast.querySelector('.memory-toast-content').textContent = `"${result.content}"`;

    const undoEl = toast.querySelector('.memory-toast-undo');
    undoEl.addEventListener('click', async () => {
        try {
            await fetch(`/api/memory/${result.id}`, { method: 'DELETE' });
            // If this was an update, we only delete the new one. Restoring the
            // old one requires a separate POST.
            if (result.status === 'updated' && result.replaced_content) {
                await fetch('/api/memory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: result.replaced_content }),
                });
            }
            toast.querySelector('.memory-toast-content').textContent = ' Forgotten';
            undoEl.remove();
        } catch (e) {
            console.error('undo memory failed', e);
        }
    });

    document.body.appendChild(toast);
    // Next-frame trigger for the CSS transition.
    requestAnimationFrame(() => toast.classList.add('visible'));

    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 6000);
}

// Expose on window so core.js can call it without imports (the existing JS
// files are loaded as globals, not modules).
window.showMemoryToast = showMemoryToast;
```

- [ ] **Step 2: Verify `memory.js` is loaded before `core.js` in index.html**

Run: `grep -n "memory.js\|core.js" chat/static/index.html`

The order in `<script>` tags matters. `memory.js` must appear *before* `core.js` so `window.showMemoryToast` is defined when `core.js` runs.

If the order is wrong, edit `chat/static/index.html` to swap them.

- [ ] **Step 3: Commit**

```bash
git add chat/static/js/memory.js chat/static/index.html
git commit -m "feat(ui): showMemoryToast with undo for autonomous saves"
```

---

### Task 12: Hook `showMemoryToast` into the `tool_end` handler

**Files:**
- Modify: `chat/static/js/core.js:56-59`

- [ ] **Step 1: Add the hook**

In `chat/static/js/core.js`, change the `tool_end` case (lines 56-59):

```javascript
        case 'tool_end':
            updateToolPill(data.name, 'completed');
            updateToolLog(data.name, data.result);
            if (data.name === 'remember' && typeof window.showMemoryToast === 'function') {
                window.showMemoryToast(data.result);
            }
            break;
```

- [ ] **Step 2: Manual smoke test**

Start the app (user runs this; see `scripts/start_chat.ps1`). In the browser:
- Send: `I live in Boston.`
- Expect: toast appears bottom-right: `💾 Remembered: "User lives in Boston"` with Undo link.
- Open the memory panel; expect the new entry visible.
- Start a new conversation. Send: `Where do I live?`
- Expect: the model answers "Boston" without being told.
- Send: `Actually I moved to Seattle last month.`
- Expect: toast reads `💾 Updated: "User lives in Seattle"`; memory panel shows one entry (Seattle), not two.
- Click the toast's Undo link within 6 seconds on a save.
- Expect: the entry disappears from the memory panel.

If any step fails, iterate on the implementation before committing the final piece.

- [ ] **Step 3: Commit**

```bash
git add chat/static/js/core.js
git commit -m "feat(ui): trigger memory toast on remember tool_end event"
```

---

## Chunk 5: Final verification

### Task 13: Full suite + manual regression check

- [ ] **Step 1: Run full pytest suite**

Run: `pytest chat/tests/ -v`
Expected: ALL tests pass.

- [ ] **Step 2: Boot the server and hit every tool once**

User runs `scripts/start_chat.ps1`. In the browser, do a quick smoke pass:
- Ask a general knowledge question — expect a direct reply, no tool call.
- Ask `what's 12 * 8?` — direct reply, no calculator call.
- Ask `what's the weather in Paris?` — expect weather tool to fire.
- Say `I'm vegetarian.` — expect remember tool to fire and a toast to appear.
- Start a new conversation. Ask `Do you know anything about my diet?` — expect the model to reference "vegetarian".

- [ ] **Step 3: Commit (no-op if nothing changed)**

If everything passes cleanly, nothing to commit in this step.

If manual regressions turned up fixes, commit them with a clear message.

- [ ] **Step 4: Update the spec doc with any deviations**

If the implementation diverged from the spec in any meaningful way (e.g., cap ended up different, dedup heuristic changed), update `docs/superpowers/specs/2026-04-07-autonomous-memory-design.md` with a short "Implementation notes" section and commit separately:

```bash
git add docs/superpowers/specs/2026-04-07-autonomous-memory-design.md
git commit -m "docs: spec implementation notes for autonomous memory"
```

---

## Done

The feature is complete when:
1. `pytest chat/tests/ -v` is all green.
2. Telling the real model a durable fact triggers a visible toast.
3. That fact is recalled in a brand-new conversation without being re-told.
4. Contradictory updates ("moved to Seattle") replace rather than stack.
5. Undo on the toast removes the new entry (and restores the old one on an update).
