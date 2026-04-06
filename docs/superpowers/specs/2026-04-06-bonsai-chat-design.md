# Bonsai Chat — Design Spec

## Overview

Bonsai Chat is a local, agentic chat UI for Bonsai language models. It provides a ChatGPT-like experience with 6 built-in tools, powered by the Bonsai GGUF model via llama-server. Single-user, no accounts, runs entirely on the user's machine.

**Principles:**
- One command to launch (`start_chat.ps1` / `start_chat.sh`)
- Works out of the box with no API keys (free providers as defaults)
- Tool use is transparent — users see what tools are called and their results
- Hybrid tool-calling: structured JSON first, regex/intent fallback
- Max 5 tool rounds per message to prevent loops

## Architecture

```
Browser (Vanilla JS)
    │
    ├── Chat Panel — messages, streaming, markdown
    ├── Tool Panel — active tools, artifacts, status
    └── Conversation Sidebar — history, new chat, search
    │
    ▼ WebSocket (streaming) + REST
    │
FastAPI Backend (Python)
    │
    ├── Chat Router — WS endpoint, message handling
    ├── Agent Loop — tool decision, fallback parsing, execution
    ├── Conversation Store — SQLite
    ├── Tool Registry — pluggable tool definitions
    ├── Structured Call Parser — JSON → fallback → regex
    └── Result Formatter — tool output → model context
    │
    ▼ OpenAI-compatible API        ▼ HTTP / subprocess
    │                               │
llama-server (Bonsai GGUF)     Tools (6 built-in)
```

## File Structure

```
Bonsai-demo/
├── chat/
│   ├── app.py                 # FastAPI entry point
│   ├── agent.py               # Agent loop
│   ├── tool_parser.py         # Hybrid JSON/fallback parser
│   ├── tools/
│   │   ├── __init__.py        # Tool registry
│   │   ├── web_search.py      # DuckDuckGo (default) / SerpAPI
│   │   ├── url_fetch.py       # Fetch + summarize web pages
│   │   ├── calculator.py      # Math via sympy
│   │   ├── file_io.py         # Sandboxed file read/write
│   │   ├── weather.py         # Open-Meteo (default) / OpenWeatherMap
│   │   └── python_exec.py     # Sandboxed Python execution
│   ├── db.py                  # SQLite conversation storage
│   ├── static/
│   │   ├── index.html         # Main page
│   │   ├── style.css          # Styles
│   │   └── app.js             # Chat UI, WebSocket, tool panel
│   └── config.py              # Settings (API keys, ports, model path)
├── scripts/
│   ├── start_chat.sh          # Launch script (Mac/Linux)
│   └── start_chat.ps1         # Launch script (Windows)
└── pyproject.toml             # Updated with new deps
```

## Agent Loop

For each user message:

1. **User sends message** via WebSocket
2. **Build prompt** — conversation history + system prompt with tool definitions (JSON schemas)
3. **Call llama-server** — stream from `/v1/chat/completions`, forward tokens to browser
4. **Parse for tool calls** (hybrid approach):
   - First pass: check for valid JSON tool call blocks (OpenAI function-calling format)
   - Second pass: scan for intent patterns if no valid JSON found:
     - "let me search for X" / "searching for X" → `web_search(query=X)`
     - "let me calculate" / math expressions → `calculator(expr=...)`
     - URLs mentioned → `url_fetch(url=...)`
     - "let me check the weather in X" → `weather(location=X)`
   - Validate extracted params before execution
5. **Execute tools** — run in parallel where possible, send "tool executing..." status via WebSocket
6. **Feed results back** — append tool results to conversation, call llama-server again
7. **Repeat** up to 5 rounds; force final response after limit
8. **Save** full exchange to SQLite

### Streaming Behavior

During initial model response, tokens stream live. When a tool call is detected, streaming pauses, a "running tool..." indicator appears, then the final response streams after tool execution.

## Tools

Each tool implements a standard interface:
- `definition: dict` — name, description, parameters as JSON schema
- `async execute(params: dict) -> dict` — runs the tool, returns results

### Web Search
- Default: `duckduckgo-search` Python library (no API key)
- Optional: set `SERPAPI_KEY` env var for SerpAPI
- Returns top 5 results: title, snippet, URL

### URL Fetch
- Uses `httpx` to GET page, `beautifulsoup4` to strip HTML to text
- Truncates to ~2000 chars for model context
- Returns extracted text + page title

### Calculator
- `ast.literal_eval` for simple arithmetic
- `sympy` for symbolic math, equations, unit conversions
- No arbitrary code execution

### File I/O
- Read/write within configurable sandbox directory (default: `~/BonsaiFiles/`)
- List directory contents, read files, write new files
- Refuses paths outside sandbox

### Weather
- Default: Open-Meteo API (free, no key)
- Optional: set `OPENWEATHER_KEY` for OpenWeatherMap
- Geocodes location string, returns current conditions + 3-day forecast

### Python Exec
- Runs code in subprocess with 30s timeout
- Captures stdout/stderr
- No network access, no file writes outside sandbox
- Returns output + any generated files

## Frontend

Three-panel layout (vanilla HTML/CSS/JS):

### Conversation Sidebar (left)
- Conversation list grouped by date (Today, Yesterday, etc.)
- New Chat button
- Settings link at bottom
- Active conversation highlighted

### Chat Area (center)
- User messages with avatar
- Assistant messages with Bonsai avatar, rendered as markdown (via marked.js)
- Tool call pills between user/assistant messages:
  - Green check + tool name + params = completed
  - Orange pulse + tool name + "running..." = in progress
  - Clickable to expand full input/output
- Input bar at bottom: text area, attach button, model indicator, send button

### Tool Panel (right)
- All 6 tools listed with green status indicators
- Per-conversation tool usage log (searches made, calculations run, etc.)
- Artifacts section for generated files

### Settings Page
- API keys: SerpAPI, OpenWeatherMap
- Model path override
- Sandbox directory path
- Context size setting
- Stored in local JSON config file

## Data Storage

SQLite database (`chat/bonsai_chat.db`):

- `conversations` table: id, title (auto-generated from first message), created_at, updated_at
- `messages` table: id, conversation_id, role (user/assistant/tool), content, tool_calls (JSON), created_at

No user accounts. Single-user local app.

## Dependencies (added to pyproject.toml)

```
fastapi
uvicorn[standard]
websockets
beautifulsoup4
duckduckgo-search
sympy
```

`httpx` is already present in the project.

## Launch Scripts

### `scripts/start_chat.ps1` (Windows)
1. Check if llama-server is already running on port 8080; if not, start it in background
2. Find the GGUF model file (respects `BONSAI_MODEL` env var)
3. Start FastAPI app via uvicorn on port 9090
4. Print URL and open browser

### `scripts/start_chat.sh` (Mac/Linux)
Same logic, bash version.

### Integration with setup
- New dependencies added to `pyproject.toml` (installed during `setup.sh` / `setup.ps1`)
- No additional setup step needed — `start_chat` handles everything

## API Keys (Optional)

All tools work out of the box with free providers. Power users can upgrade by setting env vars or using the settings page:

| Env Var | Provider | Default |
|---------|----------|---------|
| `SERPAPI_KEY` | SerpAPI (web search) | DuckDuckGo |
| `OPENWEATHER_KEY` | OpenWeatherMap | Open-Meteo |
