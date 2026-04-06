# Bonsai Chat Implementation Plan

> **For agentic workers:** REQUIRED: Use lril-superpowers:subagent-driven-development (if subagents available) or lril-superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local agentic chat UI for Bonsai models with 6 built-in tools (web search, URL fetch, calculator, file I/O, weather, Python exec).

**Architecture:** FastAPI backend with WebSocket streaming sits between the browser and llama-server. An agent loop parses model output for tool calls (JSON first, regex fallback), executes tools, and feeds results back. Vanilla JS frontend with three-panel layout (sidebar, chat, tool panel). SQLite for conversation persistence.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, SQLite, vanilla HTML/CSS/JS, marked.js

**Spec:** `docs/superpowers/specs/2026-04-06-bonsai-chat-design.md`

---

## Chunk 1: Foundation (Config, DB, Dependencies)

### Task 1: Update pyproject.toml with new dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add chat dependencies to pyproject.toml**

Add a `chat` optional dependency group:

```toml
[project.optional-dependencies]
webui = ["open-webui"]
chat = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "websockets>=14.0",
    "beautifulsoup4>=4.13.0",
    "duckduckgo-search>=7.0.0",
    "sympy>=1.13.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `.venv/Scripts/python -m pip install -e ".[chat]"` (Windows)
Or: `uv pip install --python .venv/Scripts/python.exe -e ".[chat]"`
Expected: All packages install successfully.

- [ ] **Step 3: Verify imports work**

Run: `.venv/Scripts/python -c "import fastapi; import uvicorn; import bs4; import duckduckgo_search; import sympy; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(chat): add chat app dependencies to pyproject.toml"
```

---

### Task 2: Config module

**Files:**
- Create: `chat/config.py`

- [ ] **Step 1: Create chat/ directory**

Run: `mkdir -p chat`

- [ ] **Step 2: Write config.py**

```python
"""Bonsai Chat configuration. Reads from env vars and optional config.json."""

import json
import os
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent

# Paths
CHAT_DIR = DEMO_DIR / "chat"
DB_PATH = CHAT_DIR / "bonsai_chat.db"
CONFIG_FILE = CHAT_DIR / "config.json"
STATIC_DIR = CHAT_DIR / "static"

# Model
BONSAI_MODEL = os.environ.get("BONSAI_MODEL", "8B")
GGUF_MODEL_DIR = DEMO_DIR / "models" / "gguf" / BONSAI_MODEL

# Server ports
LLAMA_SERVER_PORT = int(os.environ.get("LLAMA_PORT", "8080"))
CHAT_PORT = int(os.environ.get("CHAT_PORT", "9090"))
LLAMA_BASE_URL = f"http://localhost:{LLAMA_SERVER_PORT}"

# Tool settings
SANDBOX_DIR = Path(os.environ.get("BONSAI_SANDBOX", Path.home() / "BonsaiFiles"))
PYTHON_EXEC_TIMEOUT = 30
MAX_TOOL_ROUNDS = 5
URL_FETCH_MAX_CHARS = 2000

# API keys (optional — free defaults used when absent)
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY", "")


def load_config_file() -> dict:
    """Load overrides from config.json if it exists."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config_file(data: dict) -> None:
    """Save settings to config.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_config() -> dict:
    """Return merged config: env vars as defaults, config.json overrides."""
    file_cfg = load_config_file()
    return {
        "llama_port": file_cfg.get("llama_port", LLAMA_SERVER_PORT),
        "chat_port": file_cfg.get("chat_port", CHAT_PORT),
        "sandbox_dir": file_cfg.get("sandbox_dir", str(SANDBOX_DIR)),
        "serpapi_key": file_cfg.get("serpapi_key", SERPAPI_KEY),
        "openweather_key": file_cfg.get("openweather_key", OPENWEATHER_KEY),
        "bonsai_model": file_cfg.get("bonsai_model", BONSAI_MODEL),
    }


def find_gguf_model() -> str | None:
    """Find the first .gguf file in the model directory."""
    model_dir = DEMO_DIR / "models" / "gguf" / get_config()["bonsai_model"]
    if model_dir.exists():
        for f in model_dir.glob("*.gguf"):
            return str(f)
    return None
```

- [ ] **Step 3: Verify config loads**

Run: `.venv/Scripts/python -c "from chat.config import get_config; print(get_config())"`
Expected: Dict with default values printed.

- [ ] **Step 4: Commit**

```bash
git add chat/config.py
git commit -m "feat(chat): add config module with env var and JSON file support"
```

---

### Task 3: SQLite database module

**Files:**
- Create: `chat/db.py`
- Create: `chat/tests/test_db.py`

- [ ] **Step 1: Create test file**

```python
# chat/tests/test_db.py
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


def test_create_conversation(db):
    conv = db.create_conversation("Test Chat")
    assert conv["id"] is not None
    assert conv["title"] == "Test Chat"


def test_list_conversations(db):
    db.create_conversation("Chat 1")
    db.create_conversation("Chat 2")
    convs = db.list_conversations()
    assert len(convs) == 2
    # Most recent first
    assert convs[0]["title"] == "Chat 2"


def test_add_and_get_messages(db):
    conv = db.create_conversation("Test")
    db.add_message(conv["id"], "user", "Hello")
    db.add_message(conv["id"], "assistant", "Hi there!", tool_calls=[{"name": "web_search", "args": {"query": "test"}}])
    msgs = db.get_messages(conv["id"])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"] == [{"name": "web_search", "args": {"query": "test"}}]


def test_delete_conversation(db):
    conv = db.create_conversation("To Delete")
    db.add_message(conv["id"], "user", "test")
    db.delete_conversation(conv["id"])
    assert db.list_conversations() == []
    assert db.get_messages(conv["id"]) == []


def test_update_title(db):
    conv = db.create_conversation("Old Title")
    db.update_title(conv["id"], "New Title")
    convs = db.list_conversations()
    assert convs[0]["title"] == "New Title"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_db.py -v`
Expected: FAIL — `chat.db` module doesn't exist yet.

- [ ] **Step 3: Write db.py**

```python
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
```

- [ ] **Step 4: Create `chat/__init__.py` and `chat/tests/__init__.py`**

Both are empty files.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_db.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add chat/__init__.py chat/db.py chat/tests/__init__.py chat/tests/test_db.py
git commit -m "feat(chat): add SQLite conversation storage with tests"
```

---

## Chunk 2: Tool System

### Task 4: Tool registry and base interface

**Files:**
- Create: `chat/tools/__init__.py`

- [ ] **Step 1: Write tool registry**

```python
"""Tool registry — discovers and manages available tools."""

from typing import Protocol


class Tool(Protocol):
    """Interface every tool must implement."""

    @property
    def definition(self) -> dict:
        """Return tool definition: {name, description, parameters (JSON Schema)}."""
        ...

    async def execute(self, params: dict) -> dict:
        """Run the tool with given params. Returns {result: str} or {error: str}."""
        ...


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition["name"]] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [t.definition for t in self._tools.values()]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())


def create_registry() -> ToolRegistry:
    """Create registry with all built-in tools."""
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
    return registry
```

- [ ] **Step 2: Commit**

```bash
git add chat/tools/__init__.py
git commit -m "feat(chat): add tool registry with Protocol interface"
```

---

### Task 5: Calculator tool

**Files:**
- Create: `chat/tools/calculator.py`
- Create: `chat/tests/test_calculator.py`

- [ ] **Step 1: Write failing test**

```python
# chat/tests/test_calculator.py
import pytest
from chat.tools.calculator import CalculatorTool


@pytest.fixture
def calc():
    return CalculatorTool()


def test_definition(calc):
    d = calc.definition
    assert d["name"] == "calculator"
    assert "parameters" in d


@pytest.mark.asyncio
async def test_basic_arithmetic(calc):
    result = await calc.execute({"expression": "2 + 3 * 4"})
    assert result["result"] == "14"


@pytest.mark.asyncio
async def test_symbolic_math(calc):
    result = await calc.execute({"expression": "sqrt(144)"})
    assert result["result"] == "12"


@pytest.mark.asyncio
async def test_invalid_expression(calc):
    result = await calc.execute({"expression": "import os"})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_calculator.py -v`
Expected: FAIL

- [ ] **Step 3: Write calculator.py**

```python
"""Calculator tool — evaluates math expressions safely using sympy."""

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)


class CalculatorTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "calculator",
            "description": "Evaluate mathematical expressions. Supports arithmetic, algebra, calculus, and unit conversions. Examples: '2+3*4', 'sqrt(144)', 'integrate(x**2, x)', 'solve(x**2 - 4, x)'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate",
                    }
                },
                "required": ["expression"],
            },
        }

    async def execute(self, params: dict) -> dict:
        expr_str = params.get("expression", "")
        if not expr_str.strip():
            return {"error": "Empty expression"}

        # Block dangerous patterns
        blocked = ["import", "exec", "eval", "open", "__", "os.", "sys.", "subprocess"]
        if any(b in expr_str.lower() for b in blocked):
            return {"error": "Expression contains blocked keywords"}

        try:
            transformations = standard_transformations + (
                implicit_multiplication_application,
                convert_xor,
            )
            parsed = parse_expr(expr_str, transformations=transformations)
            result = parsed.evalf()

            # If result is an integer float, display as int
            if result == int(result):
                return {"result": str(int(result))}
            return {"result": str(result)}
        except Exception as e:
            return {"error": f"Could not evaluate: {e}"}
```

- [ ] **Step 4: Install pytest-asyncio**

Run: `uv pip install --python .venv/Scripts/python.exe pytest pytest-asyncio`

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_calculator.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add chat/tools/calculator.py chat/tests/test_calculator.py
git commit -m "feat(chat): add calculator tool with sympy"
```

---

### Task 6: Web search tool

**Files:**
- Create: `chat/tools/web_search.py`
- Create: `chat/tests/test_web_search.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_web_search.py
import pytest
from chat.tools.web_search import WebSearchTool


@pytest.fixture
def search():
    return WebSearchTool()


def test_definition(search):
    d = search.definition
    assert d["name"] == "web_search"


@pytest.mark.asyncio
async def test_search_returns_results(search):
    """Integration test — requires internet. Skip in CI."""
    result = await search.execute({"query": "Python programming language"})
    assert "results" in result
    assert len(result["results"]) > 0
    assert "title" in result["results"][0]
    assert "url" in result["results"][0]


@pytest.mark.asyncio
async def test_empty_query(search):
    result = await search.execute({"query": ""})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_web_search.py -v`
Expected: FAIL

- [ ] **Step 3: Write web_search.py**

```python
"""Web search tool — DuckDuckGo (default) or SerpAPI."""

from chat.config import get_config


class WebSearchTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "web_search",
            "description": "Search the internet for current information. Returns top 5 results with title, snippet, and URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        }

    async def execute(self, params: dict) -> dict:
        query = params.get("query", "").strip()
        if not query:
            return {"error": "Empty search query"}

        cfg = get_config()
        if cfg.get("serpapi_key"):
            return await self._serpapi_search(query, cfg["serpapi_key"])
        return await self._ddg_search(query)

    async def _ddg_search(self, query: str) -> dict:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=5))
            results = [
                {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                for r in raw
            ]
            return {"results": results}
        except Exception as e:
            return {"error": f"Search failed: {e}"}

    async def _serpapi_search(self, query: str, api_key: str) -> dict:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={"q": query, "api_key": api_key, "num": 5},
                )
                data = resp.json()
            results = [
                {"title": r.get("title", ""), "snippet": r.get("snippet", ""), "url": r.get("link", "")}
                for r in data.get("organic_results", [])[:5]
            ]
            return {"results": results}
        except Exception as e:
            return {"error": f"SerpAPI search failed: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_web_search.py -v`
Expected: All 3 tests PASS (test_search_returns_results needs internet).

- [ ] **Step 5: Commit**

```bash
git add chat/tools/web_search.py chat/tests/test_web_search.py
git commit -m "feat(chat): add web search tool with DuckDuckGo and SerpAPI support"
```

---

### Task 7: URL fetch tool

**Files:**
- Create: `chat/tools/url_fetch.py`
- Create: `chat/tests/test_url_fetch.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_url_fetch.py
import pytest
from chat.tools.url_fetch import URLFetchTool


@pytest.fixture
def fetcher():
    return URLFetchTool()


def test_definition(fetcher):
    assert fetcher.definition["name"] == "url_fetch"


@pytest.mark.asyncio
async def test_fetch_page(fetcher):
    """Integration test — requires internet."""
    result = await fetcher.execute({"url": "https://example.com"})
    assert "text" in result
    assert "Example Domain" in result["text"]


@pytest.mark.asyncio
async def test_invalid_url(fetcher):
    result = await fetcher.execute({"url": "not-a-url"})
    assert "error" in result


@pytest.mark.asyncio
async def test_empty_url(fetcher):
    result = await fetcher.execute({"url": ""})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_url_fetch.py -v`
Expected: FAIL

- [ ] **Step 3: Write url_fetch.py**

```python
"""URL fetch tool — downloads a web page and extracts readable text."""

import httpx
from bs4 import BeautifulSoup

from chat.config import URL_FETCH_MAX_CHARS


class URLFetchTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "url_fetch",
            "description": "Fetch a web page and extract its readable text content. Useful for reading articles, documentation, or any URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    }
                },
                "required": ["url"],
            },
        }

    async def execute(self, params: dict) -> dict:
        url = params.get("url", "").strip()
        if not url:
            return {"error": "Empty URL"}
        if not url.startswith(("http://", "https://")):
            return {"error": f"Invalid URL: {url}"}

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(url, headers={"User-Agent": "BonsaiChat/1.0"})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script and style tags
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else url
            text = soup.get_text(separator="\n", strip=True)

            # Truncate
            if len(text) > URL_FETCH_MAX_CHARS:
                text = text[:URL_FETCH_MAX_CHARS] + "\n... [truncated]"

            return {"title": title, "text": text}
        except Exception as e:
            return {"error": f"Failed to fetch URL: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_url_fetch.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tools/url_fetch.py chat/tests/test_url_fetch.py
git commit -m "feat(chat): add URL fetch tool with HTML-to-text extraction"
```

---

### Task 8: File I/O tool

**Files:**
- Create: `chat/tools/file_io.py`
- Create: `chat/tests/test_file_io.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_file_io.py
import os
import tempfile
import pytest
from chat.tools.file_io import FileIOTool


@pytest.fixture
def file_tool(tmp_path):
    return FileIOTool(sandbox_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_definition(file_tool):
    assert file_tool.definition["name"] == "file_io"


@pytest.mark.asyncio
async def test_write_and_read(file_tool, tmp_path):
    result = await file_tool.execute({"action": "write", "path": "test.txt", "content": "hello world"})
    assert "written" in result.get("result", "").lower() or "success" in result.get("result", "").lower()

    result = await file_tool.execute({"action": "read", "path": "test.txt"})
    assert result["content"] == "hello world"


@pytest.mark.asyncio
async def test_list_directory(file_tool, tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = await file_tool.execute({"action": "list", "path": "."})
    assert "files" in result
    assert len(result["files"]) == 2


@pytest.mark.asyncio
async def test_path_traversal_blocked(file_tool):
    result = await file_tool.execute({"action": "read", "path": "../../etc/passwd"})
    assert "error" in result


@pytest.mark.asyncio
async def test_read_nonexistent(file_tool):
    result = await file_tool.execute({"action": "read", "path": "nope.txt"})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_file_io.py -v`
Expected: FAIL

- [ ] **Step 3: Write file_io.py**

```python
"""File I/O tool — sandboxed file read/write/list."""

from pathlib import Path

from chat.config import SANDBOX_DIR


class FileIOTool:
    def __init__(self, sandbox_dir: str | None = None):
        self._sandbox = Path(sandbox_dir) if sandbox_dir else SANDBOX_DIR
        self._sandbox.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> dict:
        return {
            "name": "file_io",
            "description": f"Read, write, or list files in the sandbox directory ({self._sandbox}). Use action 'read', 'write', or 'list'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "list"],
                        "description": "The file operation to perform",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path within the sandbox directory",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (only for 'write' action)",
                    },
                },
                "required": ["action", "path"],
            },
        }

    def _resolve_safe(self, rel_path: str) -> Path | None:
        """Resolve path within sandbox, rejecting traversal."""
        target = (self._sandbox / rel_path).resolve()
        if not str(target).startswith(str(self._sandbox.resolve())):
            return None
        return target

    async def execute(self, params: dict) -> dict:
        action = params.get("action", "")
        rel_path = params.get("path", "")

        if action == "list":
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            if not target.exists():
                return {"error": f"Directory not found: {rel_path}"}
            if not target.is_dir():
                return {"error": f"Not a directory: {rel_path}"}
            files = [
                {"name": f.name, "type": "dir" if f.is_dir() else "file", "size": f.stat().st_size if f.is_file() else 0}
                for f in sorted(target.iterdir())
            ]
            return {"files": files}

        if action == "read":
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            if not target.exists():
                return {"error": f"File not found: {rel_path}"}
            try:
                return {"content": target.read_text(encoding="utf-8")}
            except Exception as e:
                return {"error": f"Could not read file: {e}"}

        if action == "write":
            content = params.get("content", "")
            target = self._resolve_safe(rel_path)
            if target is None:
                return {"error": "Path outside sandbox"}
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return {"result": f"Written {len(content)} bytes to {rel_path}"}
            except Exception as e:
                return {"error": f"Could not write file: {e}"}

        return {"error": f"Unknown action: {action}. Use 'read', 'write', or 'list'."}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_file_io.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tools/file_io.py chat/tests/test_file_io.py
git commit -m "feat(chat): add sandboxed file I/O tool"
```

---

### Task 9: Weather tool

**Files:**
- Create: `chat/tools/weather.py`
- Create: `chat/tests/test_weather.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_weather.py
import pytest
from chat.tools.weather import WeatherTool


@pytest.fixture
def weather():
    return WeatherTool()


def test_definition(weather):
    assert weather.definition["name"] == "weather"


@pytest.mark.asyncio
async def test_get_weather(weather):
    """Integration test — requires internet."""
    result = await weather.execute({"location": "New York"})
    assert "current" in result or "error" in result
    if "current" in result:
        assert "temperature" in result["current"]


@pytest.mark.asyncio
async def test_empty_location(weather):
    result = await weather.execute({"location": ""})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_weather.py -v`
Expected: FAIL

- [ ] **Step 3: Write weather.py**

```python
"""Weather tool — Open-Meteo (default) or OpenWeatherMap."""

import httpx

from chat.config import get_config


class WeatherTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "weather",
            "description": "Get current weather and 3-day forecast for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g., 'New York', 'London, UK')",
                    }
                },
                "required": ["location"],
            },
        }

    async def execute(self, params: dict) -> dict:
        location = params.get("location", "").strip()
        if not location:
            return {"error": "Empty location"}

        cfg = get_config()
        if cfg.get("openweather_key"):
            return await self._openweather(location, cfg["openweather_key"])
        return await self._open_meteo(location)

    async def _geocode(self, location: str) -> dict | None:
        """Geocode using Open-Meteo's geocoding API."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1},
            )
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return {"lat": r["latitude"], "lon": r["longitude"], "name": r.get("name", location), "country": r.get("country", "")}

    async def _open_meteo(self, location: str) -> dict:
        try:
            geo = await self._geocode(location)
            if not geo:
                return {"error": f"Could not find location: {location}"}

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": geo["lat"],
                        "longitude": geo["lon"],
                        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                        "temperature_unit": "fahrenheit",
                        "forecast_days": 3,
                    },
                )
                data = resp.json()

            current = data.get("current", {})
            daily = data.get("daily", {})

            forecast = []
            times = daily.get("time", [])
            maxs = daily.get("temperature_2m_max", [])
            mins = daily.get("temperature_2m_min", [])
            codes = daily.get("weather_code", [])
            for i in range(len(times)):
                forecast.append({
                    "date": times[i],
                    "high": maxs[i] if i < len(maxs) else None,
                    "low": mins[i] if i < len(mins) else None,
                    "condition": self._weather_code_to_text(codes[i] if i < len(codes) else 0),
                })

            return {
                "location": f"{geo['name']}, {geo['country']}",
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "humidity": current.get("relative_humidity_2m"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "condition": self._weather_code_to_text(current.get("weather_code", 0)),
                },
                "forecast": forecast,
            }
        except Exception as e:
            return {"error": f"Weather lookup failed: {e}"}

    async def _openweather(self, location: str, api_key: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": location, "appid": api_key, "units": "imperial"},
                )
                data = resp.json()
            if data.get("cod") != 200:
                return {"error": data.get("message", "Unknown error")}
            return {
                "location": data.get("name", location),
                "current": {
                    "temperature": data["main"]["temp"],
                    "humidity": data["main"]["humidity"],
                    "wind_speed": data["wind"]["speed"],
                    "condition": data["weather"][0]["description"] if data.get("weather") else "unknown",
                },
            }
        except Exception as e:
            return {"error": f"OpenWeatherMap failed: {e}"}

    @staticmethod
    def _weather_code_to_text(code: int) -> str:
        codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        return codes.get(code, f"Code {code}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_weather.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tools/weather.py chat/tests/test_weather.py
git commit -m "feat(chat): add weather tool with Open-Meteo and OpenWeatherMap support"
```

---

### Task 10: Python exec tool

**Files:**
- Create: `chat/tools/python_exec.py`
- Create: `chat/tests/test_python_exec.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_python_exec.py
import pytest
from chat.tools.python_exec import PythonExecTool


@pytest.fixture
def pyexec(tmp_path):
    return PythonExecTool(sandbox_dir=str(tmp_path))


def test_definition(pyexec):
    assert pyexec.definition["name"] == "python_exec"


@pytest.mark.asyncio
async def test_basic_exec(pyexec):
    result = await pyexec.execute({"code": "print(2 + 2)"})
    assert result["stdout"].strip() == "4"


@pytest.mark.asyncio
async def test_error_output(pyexec):
    result = await pyexec.execute({"code": "raise ValueError('oops')"})
    assert "ValueError" in result.get("stderr", "")


@pytest.mark.asyncio
async def test_empty_code(pyexec):
    result = await pyexec.execute({"code": ""})
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_python_exec.py -v`
Expected: FAIL

- [ ] **Step 3: Write python_exec.py**

```python
"""Python execution tool — runs code in a sandboxed subprocess."""

import asyncio
import sys
from pathlib import Path

from chat.config import SANDBOX_DIR, PYTHON_EXEC_TIMEOUT


class PythonExecTool:
    def __init__(self, sandbox_dir: str | None = None):
        self._sandbox = Path(sandbox_dir) if sandbox_dir else SANDBOX_DIR
        self._sandbox.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> dict:
        return {
            "name": "python_exec",
            "description": "Execute Python code and return the output. The code runs in an isolated subprocess with a 30-second timeout. Use print() to produce output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    }
                },
                "required": ["code"],
            },
        }

    async def execute(self, params: dict) -> dict:
        code = params.get("code", "").strip()
        if not code:
            return {"error": "Empty code"}

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._sandbox),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PYTHON_EXEC_TIMEOUT
            )

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": proc.returncode,
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": f"Execution timed out after {PYTHON_EXEC_TIMEOUT} seconds"}
        except Exception as e:
            return {"error": f"Execution failed: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_python_exec.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tools/python_exec.py chat/tests/test_python_exec.py
git commit -m "feat(chat): add sandboxed Python execution tool"
```

---

## Chunk 3: Agent Loop and Tool Parser

### Task 11: Tool parser (hybrid JSON + fallback)

**Files:**
- Create: `chat/tool_parser.py`
- Create: `chat/tests/test_tool_parser.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_tool_parser.py
import pytest
from chat.tool_parser import parse_tool_calls


def test_parse_json_tool_call():
    """Model outputs clean JSON tool call."""
    text = '{"name": "web_search", "arguments": {"query": "python tutorials"}}'
    calls = parse_tool_calls(text, ["web_search", "calculator", "weather"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"
    assert calls[0]["arguments"]["query"] == "python tutorials"


def test_parse_json_in_markdown_block():
    """Model wraps tool call in ```json block."""
    text = '''Let me search for that.
```json
{"name": "web_search", "arguments": {"query": "best restaurants Portland"}}
```'''
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"


def test_parse_multiple_json_calls():
    """Model outputs multiple tool calls."""
    text = '''```json
{"name": "web_search", "arguments": {"query": "Portland activities"}}
```
```json
{"name": "weather", "arguments": {"location": "Portland, OR"}}
```'''
    calls = parse_tool_calls(text, ["web_search", "weather"])
    assert len(calls) == 2


def test_fallback_search_intent():
    """No JSON, but model expresses search intent."""
    text = "Let me search for the best restaurants in Portland for you."
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"
    assert "restaurants" in calls[0]["arguments"]["query"].lower()


def test_fallback_weather_intent():
    text = "Let me check the weather in Portland, OR."
    calls = parse_tool_calls(text, ["web_search", "weather"])
    assert len(calls) == 1
    assert calls[0]["name"] == "weather"


def test_fallback_url_intent():
    text = "Let me fetch the page at https://example.com/article for you."
    calls = parse_tool_calls(text, ["url_fetch", "web_search"])
    assert len(calls) == 1
    assert calls[0]["name"] == "url_fetch"
    assert calls[0]["arguments"]["url"] == "https://example.com/article"


def test_fallback_calculator_intent():
    text = "Let me calculate that: 15% of 250 is"
    calls = parse_tool_calls(text, ["calculator", "web_search"])
    assert len(calls) == 1
    assert calls[0]["name"] == "calculator"


def test_no_tool_call():
    """Regular response with no tool intent."""
    text = "The capital of France is Paris. It's a beautiful city."
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 0


def test_invalid_json_ignored():
    text = '{"name": "unknown_tool", "arguments": {}}'
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_tool_parser.py -v`
Expected: FAIL

- [ ] **Step 3: Write tool_parser.py**

```python
"""Hybrid tool call parser — extracts tool calls from model output.

Strategy:
1. Try to find JSON tool call objects (bare or in ```json blocks)
2. Fall back to intent/pattern matching on natural language
"""

import json
import re


def parse_tool_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Parse model output for tool calls. Returns list of {name, arguments}."""
    # Phase 1: Try JSON extraction
    calls = _extract_json_calls(text, available_tools)
    if calls:
        return calls

    # Phase 2: Fallback intent matching
    return _extract_intent_calls(text, available_tools)


def _extract_json_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Extract JSON tool call objects from text."""
    calls = []

    # Find JSON in ```json blocks
    json_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)

    # Also try to find bare JSON objects
    bare_json = re.findall(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}[^}]*\}', text)

    candidates = json_blocks + bare_json

    for candidate in candidates:
        candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "name" in parsed and parsed["name"] in available_tools:
                calls.append({
                    "name": parsed["name"],
                    "arguments": parsed.get("arguments", {}),
                })
        except json.JSONDecodeError:
            continue

    return calls


def _extract_intent_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Fall back to pattern matching for tool intent."""
    calls = []
    text_lower = text.lower()

    # Web search patterns
    if "web_search" in available_tools:
        patterns = [
            r'(?:let me |i\'ll |i will )?search(?:ing)? (?:for |the web for |the internet for )(?:"|\')?(.+?)(?:"|\')?(?:\.|$|for you)',
            r'(?:let me |i\'ll )look (?:up|into) (?:"|\')?(.+?)(?:"|\')?(?:\.|$)',
            r'search(?:ing)? for ["\'"]?(.+?)["\'"]?(?:\.|$)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                query = m.group(1).strip().rstrip(".")
                if len(query) > 3:
                    calls.append({"name": "web_search", "arguments": {"query": query}})
                    break

    # Weather patterns
    if "weather" in available_tools and not calls:
        patterns = [
            r'(?:check|get|look up) (?:the )?weather (?:in|for|at) (.+?)(?:\.|$)',
            r'weather (?:in|for|at) (.+?)(?:\.|$)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                location = m.group(1).strip().rstrip(".")
                if len(location) > 1:
                    calls.append({"name": "weather", "arguments": {"location": location}})
                    break

    # URL fetch patterns
    if "url_fetch" in available_tools and not calls:
        url_match = re.search(r'(https?://[^\s,)]+)', text)
        if url_match and any(kw in text_lower for kw in ["fetch", "read", "open", "visit", "check", "page at", "page from"]):
            calls.append({"name": "url_fetch", "arguments": {"url": url_match.group(1).rstrip(".")}})

    # Calculator patterns
    if "calculator" in available_tools and not calls:
        if any(kw in text_lower for kw in ["calculate", "compute", "evaluate", "math", "% of", "what is"]):
            # Try to extract the expression
            patterns = [
                r'(?:calculate|compute|evaluate)\s*(?:that\s*)?:?\s*(.+?)(?:\.|$)',
                r'(\d+%?\s*(?:of|times|plus|minus|divided by)\s*\d+)',
            ]
            for pattern in patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    expr = m.group(1).strip().rstrip(".")
                    if len(expr) > 1:
                        calls.append({"name": "calculator", "arguments": {"expression": expr}})
                        break

    return calls
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_tool_parser.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/tool_parser.py chat/tests/test_tool_parser.py
git commit -m "feat(chat): add hybrid tool call parser (JSON + intent fallback)"
```

---

### Task 12: Agent loop

**Files:**
- Create: `chat/agent.py`
- Create: `chat/tests/test_agent.py`

- [ ] **Step 1: Write test**

```python
# chat/tests/test_agent.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from chat.agent import AgentLoop


class FakeToolRegistry:
    def __init__(self):
        self._tools = {}

    def register_fake(self, name, result):
        tool = MagicMock()
        tool.definition = {"name": name, "description": f"Fake {name}", "parameters": {"type": "object", "properties": {}}}
        tool.execute = AsyncMock(return_value=result)
        self._tools[name] = tool

    def get(self, name):
        return self._tools.get(name)

    def list_tools(self):
        return [t.definition for t in self._tools.values()]

    def list_names(self):
        return list(self._tools.keys())


@pytest.fixture
def registry():
    reg = FakeToolRegistry()
    reg.register_fake("web_search", {"results": [{"title": "Test", "snippet": "A test result", "url": "https://example.com"}]})
    reg.register_fake("calculator", {"result": "42"})
    return reg


def test_build_system_prompt(registry):
    agent = AgentLoop(registry, llama_base_url="http://localhost:8080")
    prompt = agent._build_system_prompt()
    assert "web_search" in prompt
    assert "calculator" in prompt
    assert "JSON" in prompt


def test_format_tool_result():
    agent = AgentLoop(MagicMock(), llama_base_url="http://localhost:8080")
    result = agent._format_tool_result("web_search", {"results": [{"title": "Test"}]})
    assert "web_search" in result
    assert "Test" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest chat/tests/test_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Write agent.py**

```python
"""Agent loop — orchestrates model calls, tool parsing, and execution."""

import json
from typing import AsyncGenerator

import httpx

from chat.config import MAX_TOOL_ROUNDS, LLAMA_BASE_URL
from chat.tool_parser import parse_tool_calls
from chat.tools import ToolRegistry


class AgentLoop:
    def __init__(self, registry: ToolRegistry, llama_base_url: str | None = None):
        self.registry = registry
        self.llama_url = llama_base_url or LLAMA_BASE_URL

    def _build_system_prompt(self) -> str:
        """Build system prompt with tool definitions."""
        tools = self.registry.list_tools()
        tool_docs = []
        for t in tools:
            tool_docs.append(
                f"- **{t['name']}**: {t['description']}\n"
                f"  Parameters: {json.dumps(t['parameters'])}"
            )

        return (
            "You are Bonsai, a helpful AI assistant running locally. "
            "You have access to the following tools:\n\n"
            + "\n".join(tool_docs)
            + "\n\n"
            "To use a tool, output a JSON object with 'name' and 'arguments' fields in a ```json code block. "
            "Example:\n"
            "```json\n"
            '{"name": "web_search", "arguments": {"query": "your search query"}}\n'
            "```\n\n"
            "You can call multiple tools by outputting multiple JSON blocks. "
            "After tool results are provided, use them to give a helpful response. "
            "Only use tools when needed — if you can answer directly, do so."
        )

    def _format_tool_result(self, tool_name: str, result: dict) -> str:
        """Format a tool result for feeding back to the model."""
        return f"[Tool Result: {tool_name}]\n{json.dumps(result, indent=2)}"

    async def run(
        self,
        messages: list[dict],
        on_token: callable | None = None,
        on_tool_start: callable | None = None,
        on_tool_end: callable | None = None,
    ) -> dict:
        """Run the agent loop. Returns {content, tool_calls}.

        Callbacks:
          on_token(token: str) — called for each streamed token
          on_tool_start(name: str, args: dict) — called when tool execution starts
          on_tool_end(name: str, result: dict) — called when tool execution ends
        """
        system_prompt = self._build_system_prompt()
        all_tool_calls = []

        # Build messages with system prompt
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for round_num in range(MAX_TOOL_ROUNDS + 1):
            # Call model and collect full response
            full_response = ""
            async for token in self._stream_completion(full_messages):
                full_response += token
                if on_token and round_num == 0:
                    # Only stream first round to user (before tool calls)
                    await on_token(token)

            # Parse for tool calls
            tool_calls = parse_tool_calls(full_response, self.registry.list_names())

            if not tool_calls or round_num == MAX_TOOL_ROUNDS:
                # No tools to call (or hit max rounds) — done
                if round_num > 0 and on_token:
                    # Stream the final response after tool execution
                    for token in full_response:
                        await on_token(token)
                return {"content": full_response, "tool_calls": all_tool_calls}

            # Execute tools
            full_messages.append({"role": "assistant", "content": full_response})

            for tc in tool_calls:
                tool = self.registry.get(tc["name"])
                if not tool:
                    continue

                if on_tool_start:
                    await on_tool_start(tc["name"], tc["arguments"])

                result = await tool.execute(tc["arguments"])

                if on_tool_end:
                    await on_tool_end(tc["name"], result)

                all_tool_calls.append({"name": tc["name"], "arguments": tc["arguments"], "result": result})
                full_messages.append({
                    "role": "user",
                    "content": self._format_tool_result(tc["name"], result),
                })

            # Stop streaming first-round tokens after tool calls are found
            if round_num == 0 and on_token:
                # Clear the streamed text — we'll re-stream the final answer
                await on_token("\n\n")

    async def _stream_completion(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream tokens from llama-server's /v1/chat/completions endpoint."""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.llama_url}/v1/chat/completions",
                json={
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.5,
                    "top_p": 0.85,
                    "top_k": 20,
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest chat/tests/test_agent.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chat/agent.py chat/tests/test_agent.py
git commit -m "feat(chat): add agent loop with streaming and tool orchestration"
```

---

## Chunk 4: FastAPI App

### Task 13: FastAPI application with WebSocket and REST endpoints

**Files:**
- Create: `chat/app.py`

- [ ] **Step 1: Write app.py**

```python
"""Bonsai Chat — FastAPI application."""

import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from chat.agent import AgentLoop
from chat.config import CHAT_PORT, DB_PATH, STATIC_DIR, get_config, save_config_file
from chat.db import ChatDB
from chat.tools import create_registry

app = FastAPI(title="Bonsai Chat")

# Globals initialized on startup
db: ChatDB | None = None
agent: AgentLoop | None = None


@app.on_event("startup")
async def startup():
    global db, agent
    db = ChatDB(str(DB_PATH))
    registry = create_registry()
    agent = AgentLoop(registry)


@app.on_event("shutdown")
async def shutdown():
    if db:
        db.close()


# ── REST API ──


@app.get("/api/conversations")
async def list_conversations():
    return db.list_conversations()


@app.post("/api/conversations")
async def create_conversation():
    return db.create_conversation("New Chat")


@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    return db.get_messages(conv_id)


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    db.delete_conversation(conv_id)
    return {"ok": True}


@app.patch("/api/conversations/{conv_id}")
async def update_conversation(conv_id: str, data: dict):
    if "title" in data:
        db.update_title(conv_id, data["title"])
    return {"ok": True}


@app.get("/api/config")
async def get_configuration():
    cfg = get_config()
    # Mask API keys for display
    if cfg.get("serpapi_key"):
        cfg["serpapi_key"] = cfg["serpapi_key"][:4] + "****"
    if cfg.get("openweather_key"):
        cfg["openweather_key"] = cfg["openweather_key"][:4] + "****"
    return cfg


@app.post("/api/config")
async def save_configuration(data: dict):
    save_config_file(data)
    return {"ok": True}


@app.get("/api/tools")
async def list_tools():
    return agent.registry.list_tools()


# ── WebSocket Chat ──


@app.websocket("/ws/chat/{conv_id}")
async def websocket_chat(ws: WebSocket, conv_id: str):
    await ws.accept()

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_content = msg.get("content", "")

            if not user_content.strip():
                continue

            # Save user message
            db.add_message(conv_id, "user", user_content)

            # Auto-title on first message
            conv_messages = db.get_messages(conv_id)
            if len(conv_messages) == 1:
                title = user_content[:50] + ("..." if len(user_content) > 50 else "")
                db.update_title(conv_id, title)
                await ws.send_text(json.dumps({"type": "title_update", "title": title}))

            # Build message history for model
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in conv_messages
                if m["role"] in ("user", "assistant")
            ]

            # Run agent with streaming callbacks
            full_response = ""

            async def on_token(token: str):
                nonlocal full_response
                full_response += token
                await ws.send_text(json.dumps({"type": "token", "content": token}))

            async def on_tool_start(name: str, args: dict):
                await ws.send_text(json.dumps({"type": "tool_start", "name": name, "arguments": args}))

            async def on_tool_end(name: str, result: dict):
                await ws.send_text(json.dumps({"type": "tool_end", "name": name, "result": result}))

            result = await agent.run(
                history,
                on_token=on_token,
                on_tool_start=on_tool_start,
                on_tool_end=on_tool_end,
            )

            # If agent streamed content character-by-character in round > 0, use that
            # Otherwise use result content
            final_content = result["content"] if not full_response else full_response

            # Save assistant message
            db.add_message(
                conv_id, "assistant", final_content,
                tool_calls=result.get("tool_calls") or None,
            )

            await ws.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


# ── Static files (must be last) ──
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
```

- [ ] **Step 2: Test that app imports cleanly**

Run: `.venv/Scripts/python -c "from chat.app import app; print(app.title)"`
Expected: `Bonsai Chat`

- [ ] **Step 3: Commit**

```bash
git add chat/app.py
git commit -m "feat(chat): add FastAPI app with WebSocket chat and REST API"
```

---

## Chunk 5: Frontend

### Task 14: HTML page

**Files:**
- Create: `chat/static/index.html`

- [ ] **Step 1: Create static directory and write index.html**

Run: `mkdir -p chat/static`

Write `chat/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bonsai Chat</title>
    <link rel="stylesheet" href="/style.css">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
    <div id="app">
        <!-- Sidebar -->
        <aside id="sidebar">
            <div class="sidebar-header">
                <span class="logo">&#127793;</span>
                <span class="logo-text">Bonsai Chat</span>
            </div>
            <button id="new-chat-btn" onclick="createNewChat()">+ New Chat</button>
            <div id="conversation-list"></div>
            <div class="sidebar-footer">
                <button onclick="toggleSettings()">&#9881; Settings</button>
            </div>
        </aside>

        <!-- Main chat area -->
        <main id="chat-area">
            <!-- Welcome screen -->
            <div id="welcome" class="welcome">
                <div class="welcome-icon">&#127793;</div>
                <h1>Bonsai Chat</h1>
                <p>A local AI assistant powered by Bonsai</p>
                <div class="capabilities">
                    <div class="cap">&#127760; Web Search</div>
                    <div class="cap">&#128196; URL Fetch</div>
                    <div class="cap">&#129518; Calculator</div>
                    <div class="cap">&#128193; File Manager</div>
                    <div class="cap">&#127783;&#65039; Weather</div>
                    <div class="cap">&#128013; Python</div>
                </div>
            </div>

            <!-- Messages container -->
            <div id="messages"></div>

            <!-- Input area -->
            <div id="input-area">
                <div class="input-container">
                    <textarea id="message-input" placeholder="Message Bonsai..." rows="1"
                        onkeydown="handleKeyDown(event)"></textarea>
                    <div class="input-footer">
                        <span class="model-label" id="model-label">Bonsai 8B</span>
                        <button id="send-btn" onclick="sendMessage()">Send</button>
                    </div>
                </div>
            </div>
        </main>

        <!-- Tool panel -->
        <aside id="tool-panel">
            <div class="panel-section">
                <h3>Tools</h3>
                <div id="tool-list"></div>
            </div>
            <div class="panel-section">
                <h3>This Conversation</h3>
                <div id="tool-log">
                    <p class="empty-state">No tool usage yet</p>
                </div>
            </div>
            <div class="panel-section">
                <h3>Artifacts</h3>
                <div id="artifacts">
                    <p class="empty-state">No files yet</p>
                </div>
            </div>
        </aside>

        <!-- Settings modal -->
        <div id="settings-modal" class="modal hidden">
            <div class="modal-content">
                <h2>Settings</h2>
                <div class="setting">
                    <label>SerpAPI Key (optional)</label>
                    <input type="password" id="cfg-serpapi" placeholder="Leave blank for DuckDuckGo">
                </div>
                <div class="setting">
                    <label>OpenWeatherMap Key (optional)</label>
                    <input type="password" id="cfg-openweather" placeholder="Leave blank for Open-Meteo">
                </div>
                <div class="setting">
                    <label>Sandbox Directory</label>
                    <input type="text" id="cfg-sandbox">
                </div>
                <div class="modal-actions">
                    <button onclick="saveSettings()">Save</button>
                    <button onclick="toggleSettings()" class="secondary">Cancel</button>
                </div>
            </div>
        </div>
    </div>
    <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add chat/static/index.html
git commit -m "feat(chat): add main HTML page with three-panel layout"
```

---

### Task 15: CSS styles

**Files:**
- Create: `chat/static/style.css`

- [ ] **Step 1: Write style.css**

```css
/* Bonsai Chat — Dark theme, three-panel layout */

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #1c2128;
    --border: #30363d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #484f58;
    --accent-green: #238636;
    --accent-green-light: #3fb950;
    --accent-blue: #58a6ff;
    --accent-blue-bg: rgba(31, 111, 235, 0.13);
    --accent-orange: #f97316;
    --accent-orange-bg: rgba(249, 115, 22, 0.13);
    --radius: 8px;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    height: 100vh;
    overflow: hidden;
}

#app {
    display: flex;
    height: 100vh;
}

/* ── Sidebar ── */
#sidebar {
    width: 220px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 12px;
    flex-shrink: 0;
}

.sidebar-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    padding: 4px;
}

.logo { font-size: 22px; }
.logo-text { font-weight: 600; font-size: 15px; }

#new-chat-btn {
    background: var(--accent-green);
    color: white;
    border: none;
    border-radius: var(--radius);
    padding: 8px 12px;
    font-size: 13px;
    cursor: pointer;
    margin-bottom: 12px;
    width: 100%;
}
#new-chat-btn:hover { background: #2ea043; }

#conversation-list {
    flex: 1;
    overflow-y: auto;
}

.conv-item {
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
    color: var(--text-secondary);
    cursor: pointer;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.conv-item:hover { background: var(--bg-tertiary); }
.conv-item.active { background: var(--accent-blue-bg); color: var(--accent-blue); }

.conv-group-label {
    font-size: 10px;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 8px 10px 4px;
    letter-spacing: 0.5px;
}

.sidebar-footer {
    border-top: 1px solid var(--border);
    padding-top: 8px;
}
.sidebar-footer button {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 13px;
    cursor: pointer;
    padding: 4px;
    width: 100%;
    text-align: left;
}
.sidebar-footer button:hover { color: var(--text-primary); }

/* ── Chat Area ── */
#chat-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.welcome {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-secondary);
}
.welcome-icon { font-size: 48px; }
.welcome h1 { font-size: 24px; color: var(--text-primary); }
.welcome p { font-size: 14px; }
.capabilities {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin-top: 12px;
}
.cap {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 8px 14px;
    font-size: 13px;
}

#messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 24px;
    display: none;
}

.message {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
    max-width: 85%;
}
.message.user { margin-left: auto; flex-direction: row-reverse; }

.avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
}
.avatar.user-avatar { background: var(--border); font-size: 12px; }
.avatar.bot-avatar { background: var(--accent-green); }

.message-content {
    padding: 10px 14px;
    border-radius: var(--radius);
    font-size: 14px;
    line-height: 1.6;
}
.message.user .message-content { background: var(--bg-secondary); }
.message.assistant .message-content { background: transparent; }

.message-content pre {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    overflow-x: auto;
    margin: 8px 0;
}
.message-content code {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
}
.message-content p { margin-bottom: 8px; }
.message-content p:last-child { margin-bottom: 0; }
.message-content ul, .message-content ol { padding-left: 20px; margin-bottom: 8px; }

/* Tool call pills */
.tool-calls {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 4px 0 12px 40px;
}
.tool-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
}
.tool-pill.completed {
    background: var(--accent-blue-bg);
    border: 1px solid rgba(31, 111, 235, 0.27);
}
.tool-pill.running {
    background: var(--accent-orange-bg);
    border: 1px solid rgba(249, 115, 22, 0.27);
    animation: pulse 1.5s infinite;
}
.tool-pill .tool-status { font-size: 11px; }
.tool-pill .tool-name { color: var(--accent-blue); }
.tool-pill .tool-args { color: var(--text-muted); font-size: 11px; }
.tool-pill.running .tool-name { color: var(--accent-orange); }

.tool-detail {
    display: none;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    margin: 4px 0 8px 40px;
    font-size: 12px;
    font-family: monospace;
    white-space: pre-wrap;
    max-height: 200px;
    overflow-y: auto;
}
.tool-detail.expanded { display: block; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ── Input area ── */
#input-area {
    border-top: 1px solid var(--border);
    padding: 12px 24px;
}

.input-container {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 14px;
}

#message-input {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-size: 14px;
    font-family: inherit;
    resize: none;
    outline: none;
    max-height: 120px;
}
#message-input::placeholder { color: var(--text-muted); }

.input-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 8px;
}
.model-label { color: var(--text-muted); font-size: 12px; }

#send-btn {
    background: var(--accent-green);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 13px;
    cursor: pointer;
}
#send-btn:hover { background: #2ea043; }
#send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Tool Panel ── */
#tool-panel {
    width: 220px;
    background: var(--bg-secondary);
    border-left: 1px solid var(--border);
    padding: 12px;
    overflow-y: auto;
    flex-shrink: 0;
}

.panel-section { margin-bottom: 20px; }
.panel-section h3 {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 8px;
    letter-spacing: 0.5px;
}

.tool-entry {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 0;
    font-size: 13px;
}
.tool-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-green-light);
}

.empty-state {
    font-size: 12px;
    color: var(--text-muted);
    font-style: italic;
}

.tool-log-entry {
    font-size: 12px;
    margin-bottom: 6px;
}
.tool-log-entry .log-icon { margin-right: 4px; }
.tool-log-entry .log-detail {
    color: var(--text-muted);
    font-size: 11px;
    padding-left: 16px;
}

/* ── Settings modal ── */
.modal {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
}
.modal.hidden { display: none; }
.modal-content {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    width: 400px;
}
.modal-content h2 { margin-bottom: 16px; font-size: 18px; }

.setting {
    margin-bottom: 12px;
}
.setting label {
    display: block;
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 4px;
}
.setting input {
    width: 100%;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    color: var(--text-primary);
    font-size: 13px;
    outline: none;
}
.setting input:focus { border-color: var(--accent-blue); }

.modal-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 16px;
}
.modal-actions button {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    border: none;
}
.modal-actions button:first-child { background: var(--accent-green); color: white; }
.modal-actions button.secondary { background: var(--border); color: var(--text-primary); }
```

- [ ] **Step 2: Commit**

```bash
git add chat/static/style.css
git commit -m "feat(chat): add dark theme CSS for three-panel chat layout"
```

---

### Task 16: JavaScript application

**Files:**
- Create: `chat/static/app.js`

- [ ] **Step 1: Write app.js**

```javascript
/* Bonsai Chat — Frontend application */

let ws = null;
let currentConvId = null;
let conversations = [];

// ── Initialization ──

async function init() {
    await loadTools();
    await loadConversations();
}

// ── Conversations ──

async function loadConversations() {
    const resp = await fetch('/api/conversations');
    conversations = await resp.json();
    renderConversationList();
}

function renderConversationList() {
    const list = document.getElementById('conversation-list');
    if (conversations.length === 0) {
        list.innerHTML = '<p class="empty-state" style="padding:10px">No conversations yet</p>';
        return;
    }

    const now = new Date();
    const today = now.toDateString();
    const yesterday = new Date(now - 86400000).toDateString();

    let html = '';
    let lastGroup = '';

    for (const conv of conversations) {
        const date = new Date(conv.updated_at).toDateString();
        let group = date === today ? 'Today' : date === yesterday ? 'Yesterday' : date;
        if (group !== lastGroup) {
            html += `<div class="conv-group-label">${group}</div>`;
            lastGroup = group;
        }
        const active = conv.id === currentConvId ? ' active' : '';
        html += `<div class="conv-item${active}" onclick="openConversation('${conv.id}')" title="${conv.title}">${conv.title}</div>`;
    }
    list.innerHTML = html;
}

async function createNewChat() {
    const resp = await fetch('/api/conversations', { method: 'POST' });
    const conv = await resp.json();
    currentConvId = conv.id;
    await loadConversations();
    showChatView();
    clearMessages();
    connectWebSocket(conv.id);
}

async function openConversation(convId) {
    currentConvId = convId;
    renderConversationList();
    showChatView();

    const resp = await fetch(`/api/conversations/${convId}/messages`);
    const messages = await resp.json();
    renderMessageHistory(messages);
    connectWebSocket(convId);
}

async function deleteConversation(convId) {
    await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
    if (currentConvId === convId) {
        currentConvId = null;
        showWelcome();
    }
    await loadConversations();
}

// ── Views ──

function showChatView() {
    document.getElementById('welcome').style.display = 'none';
    document.getElementById('messages').style.display = 'block';
    document.getElementById('message-input').focus();
}

function showWelcome() {
    document.getElementById('welcome').style.display = 'flex';
    document.getElementById('messages').style.display = 'none';
}

function clearMessages() {
    document.getElementById('messages').innerHTML = '';
    document.getElementById('tool-log').innerHTML = '<p class="empty-state">No tool usage yet</p>';
    document.getElementById('artifacts').innerHTML = '<p class="empty-state">No files yet</p>';
}

// ── WebSocket ──

function connectWebSocket(convId) {
    if (ws) {
        ws.close();
    }
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws/chat/${convId}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWSMessage(data);
    };

    ws.onclose = () => {
        ws = null;
    };
}

// ── Message Handling ──

let currentAssistantEl = null;
let currentAssistantText = '';

function handleWSMessage(data) {
    switch (data.type) {
        case 'token':
            if (!currentAssistantEl) {
                currentAssistantEl = appendMessage('assistant', '');
                currentAssistantText = '';
            }
            currentAssistantText += data.content;
            const contentEl = currentAssistantEl.querySelector('.message-content');
            contentEl.innerHTML = marked.parse(currentAssistantText);
            scrollToBottom();
            break;

        case 'tool_start':
            addToolPill(data.name, data.arguments, 'running');
            addToolLog(data.name, data.arguments, 'running');
            break;

        case 'tool_end':
            updateToolPill(data.name, 'completed');
            updateToolLog(data.name, data.result);
            break;

        case 'title_update':
            loadConversations();
            break;

        case 'done':
            currentAssistantEl = null;
            currentAssistantText = '';
            document.getElementById('send-btn').disabled = false;
            document.getElementById('message-input').disabled = false;
            break;

        case 'error':
            appendSystemMessage(`Error: ${data.message}`);
            document.getElementById('send-btn').disabled = false;
            document.getElementById('message-input').disabled = false;
            break;
    }
}

function sendMessage() {
    const input = document.getElementById('message-input');
    const text = input.value.trim();
    if (!text || !ws) return;

    if (!currentConvId) {
        createNewChat().then(() => {
            sendMessageText(text);
        });
        input.value = '';
        return;
    }

    sendMessageText(text);
    input.value = '';
    input.style.height = 'auto';
}

function sendMessageText(text) {
    appendMessage('user', text);
    document.getElementById('send-btn').disabled = true;
    document.getElementById('message-input').disabled = true;
    ws.send(JSON.stringify({ content: text }));
    scrollToBottom();
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
    // Auto-resize
    const input = event.target;
    setTimeout(() => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }, 0);
}

// ── Rendering ──

function appendMessage(role, content) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatarClass = role === 'user' ? 'user-avatar' : 'bot-avatar';
    const avatarContent = role === 'user' ? 'U' : '&#127793;';

    div.innerHTML = `
        <div class="avatar ${avatarClass}">${avatarContent}</div>
        <div class="message-content">${role === 'user' ? escapeHtml(content) : marked.parse(content)}</div>
    `;

    messages.appendChild(div);
    scrollToBottom();
    return div;
}

function appendSystemMessage(text) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.style.cssText = 'text-align:center;color:var(--text-muted);font-size:13px;padding:8px;';
    div.textContent = text;
    messages.appendChild(div);
}

function renderMessageHistory(msgs) {
    clearMessages();
    for (const m of msgs) {
        if (m.role === 'user' || m.role === 'assistant') {
            appendMessage(m.role, m.content);
        }
        if (m.tool_calls) {
            for (const tc of m.tool_calls) {
                addToolPill(tc.name, tc.arguments, 'completed');
            }
        }
    }
}

// ── Tool Pills ──

let toolPillCounter = 0;

function addToolPill(name, args, status) {
    const id = `tool-pill-${toolPillCounter++}`;
    const messages = document.getElementById('messages');

    const container = document.createElement('div');
    container.className = 'tool-calls';

    const argsStr = Object.values(args || {}).join(', ');
    const statusIcon = status === 'running' ? '&#9679;' : '&#10003;';

    container.innerHTML = `
        <div class="tool-pill ${status}" id="${id}" onclick="toggleToolDetail('${id}-detail')">
            <span class="tool-status">${statusIcon}</span>
            <span class="tool-name">${name}</span>
            <span class="tool-args">${argsStr}</span>
        </div>
    `;

    const detail = document.createElement('div');
    detail.className = 'tool-detail';
    detail.id = `${id}-detail`;
    detail.textContent = `Arguments: ${JSON.stringify(args, null, 2)}`;

    messages.appendChild(container);
    messages.appendChild(detail);
    scrollToBottom();
}

function updateToolPill(name, status) {
    // Update the most recent pill matching this tool name
    const pills = document.querySelectorAll('.tool-pill.running');
    for (const pill of pills) {
        if (pill.querySelector('.tool-name')?.textContent === name) {
            pill.className = `tool-pill ${status}`;
            pill.querySelector('.tool-status').innerHTML = '&#10003;';
            break;
        }
    }
}

function toggleToolDetail(id) {
    const detail = document.getElementById(id);
    if (detail) {
        detail.classList.toggle('expanded');
    }
}

// ── Tool Log (right panel) ──

function addToolLog(name, args, status) {
    const log = document.getElementById('tool-log');
    if (log.querySelector('.empty-state')) {
        log.innerHTML = '';
    }
    const entry = document.createElement('div');
    entry.className = 'tool-log-entry';
    entry.id = `log-${name}-${toolPillCounter}`;
    const icon = status === 'running' ? '&#9679;' : '&#10003;';
    const argsStr = Object.values(args || {}).join(', ');
    entry.innerHTML = `<span class="log-icon">${icon}</span> <strong>${name}</strong><div class="log-detail">${argsStr}</div>`;
    log.appendChild(entry);
}

function updateToolLog(name, result) {
    // Find the most recent running entry for this tool
    const entries = document.querySelectorAll('.tool-log-entry');
    for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        if (entry.querySelector('strong')?.textContent === name && entry.innerHTML.includes('●')) {
            entry.querySelector('.log-icon').innerHTML = '&#10003;';
            // Add result summary
            const detail = entry.querySelector('.log-detail');
            if (result.results) {
                detail.textContent = `${result.results.length} results`;
            } else if (result.result) {
                detail.textContent = result.result;
            } else if (result.error) {
                detail.textContent = `Error: ${result.error}`;
            }
            break;
        }
    }
}

// ── Tools list ──

async function loadTools() {
    try {
        const resp = await fetch('/api/tools');
        const tools = await resp.json();
        const list = document.getElementById('tool-list');
        list.innerHTML = tools.map(t =>
            `<div class="tool-entry"><div class="tool-dot"></div>${t.name}</div>`
        ).join('');
    } catch (e) {
        // Tools endpoint might not be available yet
    }
}

// ── Settings ──

function toggleSettings() {
    document.getElementById('settings-modal').classList.toggle('hidden');
}

async function saveSettings() {
    const data = {
        serpapi_key: document.getElementById('cfg-serpapi').value,
        openweather_key: document.getElementById('cfg-openweather').value,
        sandbox_dir: document.getElementById('cfg-sandbox').value,
    };
    await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    toggleSettings();
}

// ── Helpers ──

function scrollToBottom() {
    const messages = document.getElementById('messages');
    messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Start ──
init();
```

- [ ] **Step 2: Verify the static files are complete**

Run: `ls -la chat/static/`
Expected: `index.html`, `style.css`, `app.js` all present.

- [ ] **Step 3: Commit**

```bash
git add chat/static/app.js
git commit -m "feat(chat): add frontend JavaScript with WebSocket chat and tool display"
```

---

## Chunk 6: Launch Scripts

### Task 17: PowerShell launch script (Windows)

**Files:**
- Create: `scripts/start_chat.ps1`

- [ ] **Step 1: Write start_chat.ps1**

```powershell
# Bonsai Chat — Launch script for Windows
# Usage: .\scripts\start_chat.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DemoDir = Split-Path -Parent $ScriptDir
$VenvPy = Join-Path $DemoDir ".venv\Scripts\python.exe"
$BonsaiModel = if ($env:BONSAI_MODEL) { $env:BONSAI_MODEL } else { "8B" }
$LlamaPort = if ($env:LLAMA_PORT) { $env:LLAMA_PORT } else { "8080" }
$ChatPort = if ($env:CHAT_PORT) { $env:CHAT_PORT } else { "9090" }

Write-Host ""
Write-Host "========================================="
Write-Host "   Bonsai Chat"
Write-Host "   Model: $BonsaiModel"
Write-Host "========================================="
Write-Host ""

# ── Check venv exists ──
if (-not (Test-Path $VenvPy)) {
    Write-Host "[ERR] Python venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# ── Install chat dependencies if needed ──
$HasFastAPI = & $VenvPy -c "import fastapi" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Installing chat dependencies ..." -ForegroundColor Cyan
    & (Join-Path $DemoDir ".venv\Scripts\pip.exe") install -e ".[chat]" --quiet
    Write-Host "[OK] Dependencies installed." -ForegroundColor Green
}

# ── Check if llama-server is already running ──
$LlamaRunning = $false
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) { $LlamaRunning = $true }
} catch {}

if ($LlamaRunning) {
    Write-Host "[OK] llama-server already running on port $LlamaPort" -ForegroundColor Green
} else {
    # Find model file
    $ModelDir = Join-Path $DemoDir "models\gguf\$BonsaiModel"
    $ModelFile = Get-ChildItem -Path $ModelDir -Filter "*.gguf" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ModelFile) {
        Write-Host "[ERR] No .gguf model found in $ModelDir. Run .\setup.ps1 first." -ForegroundColor Red
        exit 1
    }

    # Find llama-server binary
    $LlamaServer = Join-Path $DemoDir "bin\cuda\llama-server.exe"
    if (-not (Test-Path $LlamaServer)) {
        Write-Host "[ERR] llama-server.exe not found. Run .\setup.ps1 first." -ForegroundColor Red
        exit 1
    }

    Write-Host "==> Starting llama-server (port $LlamaPort) ..." -ForegroundColor Cyan
    $LlamaProc = Start-Process -FilePath $LlamaServer -ArgumentList @(
        "-m", $ModelFile.FullName,
        "--host", "127.0.0.1",
        "--port", $LlamaPort,
        "-ngl", "99",
        "-c", "0",
        "--temp", "0.5",
        "--top-p", "0.85",
        "--top-k", "20",
        "--min-p", "0",
        "--reasoning-budget", "0",
        "--reasoning-format", "none",
        "--chat-template-kwargs", '{"enable_thinking": false}'
    ) -PassThru -WindowStyle Minimized

    # Wait for server to be ready
    Write-Host "    Waiting for llama-server to be ready ..." -ForegroundColor Cyan
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }
    if (-not $ready) {
        Write-Host "[ERR] llama-server failed to start within 60 seconds." -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] llama-server ready." -ForegroundColor Green
}

# ── Start Bonsai Chat ──
Write-Host "==> Starting Bonsai Chat (port $ChatPort) ..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Open http://localhost:$ChatPort in your browser to chat." -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

$env:LLAMA_PORT = $LlamaPort
$env:CHAT_PORT = $ChatPort
$env:BONSAI_MODEL = $BonsaiModel

& $VenvPy -m uvicorn chat.app:app --host 127.0.0.1 --port $ChatPort
```

- [ ] **Step 2: Commit**

```bash
git add scripts/start_chat.ps1
git commit -m "feat(chat): add Windows PowerShell launch script"
```

---

### Task 18: Bash launch script (Mac/Linux)

**Files:**
- Create: `scripts/start_chat.sh`

- [ ] **Step 1: Write start_chat.sh**

```bash
#!/bin/sh
# Bonsai Chat — Launch script
# Usage: ./scripts/start_chat.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/common.sh"
assert_valid_model
DEMO_DIR="$(resolve_demo_dir)"
cd "$DEMO_DIR"
assert_gguf_downloaded

LLAMA_PORT="${LLAMA_PORT:-8080}"
CHAT_PORT="${CHAT_PORT:-9090}"

echo ""
echo "========================================="
echo "   Bonsai Chat"
echo "   Model: $BONSAI_MODEL"
echo "========================================="
echo ""

# ── Check venv ──
ensure_venv "$DEMO_DIR"

# ── Install chat deps if needed ──
if ! python -c "import fastapi" 2>/dev/null; then
    step "Installing chat dependencies ..."
    pip install -e ".[chat]" --quiet
    info "Dependencies installed."
fi

# ── Check llama-server ──
if curl -s --max-time 2 "http://localhost:$LLAMA_PORT/health" >/dev/null 2>&1; then
    info "llama-server already running on port $LLAMA_PORT"
else
    # Find model
    MODEL=""
    for _m in $GGUF_MODEL_DIR/*.gguf; do
        [ -f "$_m" ] && MODEL="$DEMO_DIR/$_m" && break
    done

    # Find binary
    BIN=""
    for _d in bin/mac bin/cuda; do
        [ -f "$DEMO_DIR/$_d/llama-server" ] && BIN="$DEMO_DIR/$_d/llama-server" && break
    done
    if [ -z "$BIN" ]; then
        err "llama-server not found. Run ./setup.sh first."
        exit 1
    fi

    BIN_DIR="$(cd "$(dirname "$BIN")" && pwd)"
    export LD_LIBRARY_PATH="$BIN_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

    step "Starting llama-server (port $LLAMA_PORT) ..."
    "$BIN" -m "$MODEL" --host 127.0.0.1 --port "$LLAMA_PORT" -ngl 99 -c "$CTX_SIZE_DEFAULT" \
        --temp 0.5 --top-p 0.85 --top-k 20 --min-p 0 \
        --reasoning-budget 0 --reasoning-format none \
        --chat-template-kwargs '{"enable_thinking": false}' &
    LLAMA_PID=$!

    step "Waiting for llama-server to be ready ..."
    for _i in $(seq 1 60); do
        if curl -s --max-time 2 "http://localhost:$LLAMA_PORT/health" >/dev/null 2>&1; then
            info "llama-server ready."
            break
        fi
        sleep 1
    done

    trap "kill $LLAMA_PID 2>/dev/null" EXIT
fi

# ── Start Bonsai Chat ──
step "Starting Bonsai Chat (port $CHAT_PORT) ..."
echo ""
echo "  Open http://localhost:$CHAT_PORT in your browser to chat."
echo "  Press Ctrl+C to stop."
echo ""

export LLAMA_PORT CHAT_PORT BONSAI_MODEL
exec python -m uvicorn chat.app:app --host 127.0.0.1 --port "$CHAT_PORT"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/start_chat.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/start_chat.sh
git commit -m "feat(chat): add bash launch script for Mac/Linux"
```

---

## Chunk 7: Integration and Polish

### Task 19: Add .gitignore entries and update README

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: Add chat artifacts to .gitignore**

Append these lines to `.gitignore`:

```
# Bonsai Chat
chat/bonsai_chat.db
chat/config.json
.superpowers/
```

- [ ] **Step 2: Add Bonsai Chat section to README.md**

Add after the "Open WebUI (Optional)" section:

```markdown
## Bonsai Chat (Agentic Assistant)

A local ChatGPT-like assistant with built-in tools: web search, URL fetch, calculator, file manager, weather, and Python execution.

### Windows (PowerShell)

```powershell
.\scripts\start_chat.ps1
# Opens http://localhost:9090
```

### macOS / Linux

```bash
./scripts/start_chat.sh
# Opens http://localhost:9090
```

The script auto-starts llama-server if it's not already running. No API keys needed — free providers (DuckDuckGo, Open-Meteo) work out of the box. Optionally configure SerpAPI or OpenWeatherMap keys in Settings.
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore README.md
git commit -m "docs: add Bonsai Chat section to README and update .gitignore"
```

---

### Task 20: End-to-end smoke test

- [ ] **Step 1: Start the chat app**

Run: `.\scripts\start_chat.ps1` (in a separate terminal)

- [ ] **Step 2: Verify health endpoints**

Run: `curl http://localhost:9090/api/tools`
Expected: JSON array of 6 tool definitions.

Run: `curl http://localhost:9090/api/conversations`
Expected: Empty JSON array `[]`.

- [ ] **Step 3: Test conversation creation**

Run: `curl -X POST http://localhost:9090/api/conversations`
Expected: JSON with `id`, `title` fields.

- [ ] **Step 4: Open browser and test**

Open `http://localhost:9090` in a browser. Verify:
- Three-panel layout renders
- New Chat button works
- Can send a message and get streaming response
- Tool panel shows 6 tools with green dots

- [ ] **Step 5: Test a tool call**

Send: "What's the weather in New York?"
Expected: Weather tool pill appears (orange → green), assistant responds with weather data.

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat(chat): complete Bonsai Chat v1 — agentic local AI assistant"
```
