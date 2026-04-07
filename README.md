# Bonsai Demo

<p align="center">
  <img src="./assets/bonsai-logo.svg" width="280" alt="Bonsai">
</p>

<p align="center">
  <a href="https://prismml.com"><b>Website</b></a> &nbsp;|&nbsp;
  <a href="https://huggingface.co/collections/prism-ml/bonsai"><b>HuggingFace Collection</b></a> &nbsp;|&nbsp;
  <a href="1-bit-bonsai-8b-whitepaper.pdf"><b>Whitepaper</b></a> &nbsp;|&nbsp;
  <a href="https://github.com/PrismML-Eng/Bonsai-demo"><b>GitHub</b></a> &nbsp;|&nbsp;
  <a href="https://discord.gg/prismml"><b>Discord</b></a>
</p>

Using this demo you can run Bonsai language models locally on Mac (Metal), Linux/Windows (CUDA).

- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** (GGUF) — C/C++, runs on Mac (Metal), Linux/Windows (CUDA), and CPU.
- **[MLX](https://github.com/ml-explore/mlx)** (MLX format) — Python, optimized for Apple Silicon.

The required inference kernels are not yet available in upstream llama.cpp or MLX. Pre-built binaries and source code come from our forks:
- **llama.cpp:** [PrismML-Eng/llama.cpp](https://github.com/PrismML-Eng/llama.cpp) — [pre-built binaries](https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b8196-f5dda72)
- **MLX:** [PrismML-Eng/mlx](https://github.com/PrismML-Eng/mlx) (branch `prism`)

## Models

Three model sizes are available: **8B**, **4B**, and **1.7B**, each in two formats:

<p align="center">
  <img src="./assets/frontier.svg" width="700" alt="Bonsai accuracy vs model size frontier">
</p>

| Model               | Format | HuggingFace Repo                                                                          |
|---------------------|--------|-------------------------------------------------------------------------------------------|
| Bonsai-8B           | GGUF   | [prism-ml/Bonsai-8B-gguf](https://huggingface.co/prism-ml/Bonsai-8B-gguf)               |
| Bonsai-8B           | MLX    | [prism-ml/Bonsai-8B-mlx-1bit](https://huggingface.co/prism-ml/Bonsai-8B-mlx-1bit)       |
| Bonsai-4B           | GGUF   | [prism-ml/Bonsai-4B-gguf](https://huggingface.co/prism-ml/Bonsai-4B-gguf)               |
| Bonsai-4B           | MLX    | [prism-ml/Bonsai-4B-mlx-1bit](https://huggingface.co/prism-ml/Bonsai-4B-mlx-1bit)       |
| Bonsai-1.7B         | GGUF   | [prism-ml/Bonsai-1.7B-gguf](https://huggingface.co/prism-ml/Bonsai-1.7B-gguf)           |
| Bonsai-1.7B         | MLX    | [prism-ml/Bonsai-1.7B-mlx-1bit](https://huggingface.co/prism-ml/Bonsai-1.7B-mlx-1bit)   |

Set `BONSAI_MODEL` to choose which size to download and run (default: `8B`).

---

## Quick Start

### macOS / Linux

```bash
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo

# (Optional) Choose a model size: 8B (default), 4B, or 1.7B
export BONSAI_MODEL=8B

# One command does everything: installs deps, downloads models + binaries
./setup.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo

# (Optional) Choose a model size: 8B (default), 4B, or 1.7B
$env:BONSAI_MODEL = "8B"

# Run setup
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

### Switching models

You can download a different size and switch between them instantly — no full re-setup needed:

```bash
BONSAI_MODEL=4B ./scripts/download_models.sh
BONSAI_MODEL=4B ./scripts/run_llama.sh -p "Who are you? Introduce yourself in haiku"
```
---

## What `setup.sh` Does

The setup script handles everything for you, even on a fresh machine:

1. **Checks/installs system deps** — Xcode CLT on macOS, build-essential on Linux
2. **Installs [uv](https://docs.astral.sh/uv/)** — fast Python package manager (user-local, not global)
3. **Creates a Python venv** and runs `uv sync` — installs cmake, ninja, huggingface-cli from `pyproject.toml`
4. **Downloads models** from HuggingFace (needs `PRISM_HF_TOKEN` while repos are private)
5. **Downloads pre-built binaries** from [GitHub Release](https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b8196-f5dda72) (or builds from source if you prefer)
6. **Builds MLX from source** (macOS only) — clones our fork, then `uv sync --extra mlx` for the full ML stack

Re-running `setup.sh` is safe — it skips already-completed steps.

---

## Running the Model

All run scripts respect `BONSAI_MODEL` (default `8B`). Set it to run a different size:

### llama.cpp (Mac / Linux — auto-detects platform)

```bash
./scripts/run_llama.sh -p "What is the capital of France?"

# Run a different model size
BONSAI_MODEL=4B ./scripts/run_llama.sh -p "Who are you? Introduce yourself in haiku"
```

### MLX — Mac (Apple Silicon)

```bash
source .venv/bin/activate
./scripts/run_mlx.sh -p "What is the capital of France?"
```

### Chat Server

Start llama-server with its built-in chat UI:

```bash
./scripts/start_llama_server.sh    # http://localhost:8080

# Serve a different model size
BONSAI_MODEL=4B ./scripts/start_llama_server.sh
```

### Context Size

The 8B model supports up to 65,536 tokens.

By default the scripts pass `-c 0`, which lets llama.cpp's `--fit` automatically size the KV cache to your available memory (no pre-allocation waste). If your build doesn't support `-c 0`, the scripts fall back to a safe value based on system RAM:

*Estimates for Bonsai-8B (weights + KV cache + activations):*

| Context Size        | Est. Memory Usage |
|---------------------|-------------------|
| 8,192 tokens        | ~2.5 GB           |
| 32,768 tokens       | ~5.9 GB           |
| 65,536 tokens       | ~10.5 GB          |

Override with: `./scripts/run_llama.sh -c 8192 -p "Your prompt"`

---

## Open WebUI (Optional)

[Open WebUI](https://github.com/open-webui/open-webui) provides a ChatGPT-like browser interface.
It auto-starts the backend servers if they're not already running. Ctrl+C stops everything.

```bash
# Install (heavy — separate from base deps)
source .venv/bin/activate
uv pip install open-webui

# One command — starts backends + opens http://localhost:9090
./scripts/start_openwebui.sh
```

---

## Bonsai Chat — Full-Featured Local Web UI

Bonsai Chat is a local, agentic chat assistant with ChatGPT/Claude.ai-level features running **entirely on your machine** — no cloud APIs required. Custom FastAPI + vanilla JS frontend with 6 built-in tools, conversation persistence, memory, voice input, file uploads, LaTeX rendering, and more.

<p align="center">
  <em>Dark three-panel UI • Streaming responses • Tool pills • Markdown + syntax highlighting + LaTeX</em>
</p>

### At a Glance

| Category | Features |
|---|---|
| **Response controls** | Stop generation, Regenerate, Edit & Resend, Copy response |
| **Conversation management** | SQLite history, search (Ctrl+K), pin, rename, export (Markdown/JSON), context menu |
| **Rich content** | Markdown, syntax highlighting, line numbers, copy-code button, LaTeX (KaTeX), file uploads (drag-drop) |
| **Intelligence** | 6 built-in tools, cross-conversation memory, per-conversation system prompts, model switching |
| **Input** | Voice input (Web Speech API), keyboard shortcuts, multi-line textarea, attachments |
| **Polish** | Skeleton loading, fade-in animations, token/speed stats, tabbed settings |

### The 6 Built-in Tools

| Tool | Description | Provider |
|------|-------------|----------|
| **Web Search** | Search the internet for current information | DuckDuckGo (free) or SerpAPI |
| **URL Fetch** | Read and summarize any web page | Built-in (httpx + BeautifulSoup) |
| **Calculator** | Arithmetic, algebra, calculus, unit conversions | Built-in (sympy) |
| **File Manager** | Read, write, and list files in a sandboxed directory | Built-in (~/BonsaiFiles/) |
| **Weather** | Current conditions and 3-day forecast | Open-Meteo (free) or OpenWeatherMap |
| **Python Exec** | Run Python code snippets with captured output | Built-in (subprocess, 30s timeout) |

The agent loop intercepts model output, detects tool calls (hybrid JSON + intent parsing), executes them, feeds results back to the model, and streams the final answer — up to 5 tool rounds per message.

### Architecture

```
Browser (vanilla JS modules) ←──WebSocket/REST──→ FastAPI app.py
                                                       │
                                                       ├─→ Agent Loop (agent.py)
                                                       │       ├─ parse tool calls
                                                       │       ├─ execute tools
                                                       │       └─ stream response
                                                       │
                                                       ├─→ SQLite (db.py)
                                                       │       ├─ conversations
                                                       │       ├─ messages
                                                       │       └─ memories
                                                       │
                                                       └─→ llama-server :8080
                                                               └─ Bonsai GGUF model
```

---

## Zero-to-Hero Setup Walkthrough

This walks you through everything from a fresh clone to a fully working Bonsai Chat instance with all features enabled.

### Prerequisites

- **OS:** macOS (Apple Silicon), Linux, or Windows 10/11
- **Disk:** ~10 GB free (model + binaries + deps)
- **RAM:** 8 GB minimum for 1.7B, 16 GB recommended for 8B
- **GPU (optional):** CUDA 12.4+ on Linux/Windows, Metal on macOS (auto-detected)
- **A browser:** Chrome or Edge recommended (for voice input). Firefox/Safari work but voice button is hidden.

### Step 1 — Clone & Run the Base Setup

This downloads the Bonsai model weights and the llama.cpp binaries. If you already ran this, skip ahead to Step 2.

**macOS / Linux:**
```bash
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo

# Optional: choose a smaller model if you have limited RAM
export BONSAI_MODEL=8B   # or 4B, 1.7B

./setup.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/PrismML-Eng/Bonsai-demo.git
cd Bonsai-demo

$env:BONSAI_MODEL = "8B"   # or 4B, 1.7B

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

When this finishes you'll have:
- `models/gguf/<SIZE>/*.gguf` — the Bonsai model weights
- `bin/<platform>/` — the llama-server binary
- `.venv/` — Python environment with base deps

### Step 2 — Launch Bonsai Chat

The launch script installs chat dependencies if missing, boots `llama-server` if it's not already running, and starts the chat web app on port 9090.

**macOS / Linux:**
```bash
./scripts/start_chat.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\start_chat.ps1
```

You should see output like:
```
[1/3] Checking chat dependencies...          OK
[2/3] Starting llama-server on :8080...      OK
[3/3] Starting Bonsai Chat on :9090...       OK

  →  Open http://localhost:9090 in your browser
```

### Step 3 — Open the UI

Navigate to **http://localhost:9090**. You'll land on the welcome screen with six capability pills. Click **+ New Chat** (or press `Ctrl+N`) and say hi.

The first message auto-titles the conversation using the first 50 characters.

### Step 4 — Try a Tool Call

Ask the model to use a tool, e.g.:

```
What's the weather in Tokyo?
```

You'll see:
1. A **skeleton placeholder** while the model thinks
2. A **running tool pill** (orange pulse) showing `weather → Tokyo`
3. The pill turns blue/completed after execution
4. The model's natural-language answer streams in
5. A **stats footer** shows `<tokens> · <tok/s> · <elapsed>s`

Click the pill to expand the raw arguments. The right-hand **Tools** panel also logs every tool execution.

### Step 5 — Explore the Controls

While the model is streaming, the **Send** button turns red and becomes **Stop**. Hit it to cancel — the partial response is preserved.

Hover over any assistant message to reveal the action row:

| Button | What it does |
|---|---|
| **Copy** | Copy the full response text to clipboard |
| **Regenerate** | Delete the last response and get a fresh one |
| **Remember** | Save the first 100 chars as a cross-conversation memory |

Hover over any **user** message to reveal a pencil icon on the left. Click it to edit inline — **Save & Resend** replaces the message and all subsequent ones with a fresh response. **Cancel** restores the original.

Or just press `↑` in an empty input box to instantly edit your last message.

### Step 6 — Attach a File

Two ways to attach:

1. **Drag-and-drop** any file onto the chat area — a blue dashed overlay appears
2. Click the **paperclip icon** next to the input box

Supported formats:
- **Text/code:** `.txt`, `.py`, `.js`, `.ts`, `.json`, `.csv`, `.md`, `.html`, `.css` (content is embedded in the message, capped at 50 KB)
- **Images:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` (attached but not analyzed — the current model is text-only)

Files appear as chips above the input. Click `×` to remove before sending.

### Step 7 — Use the Memory System

Bonsai Chat has two types of persistent context:

**Cross-conversation memories** — facts the model should know about you across every chat. Two ways to add:
- Click **Remember** under any assistant response to save a key fact
- Open **Settings → Memory** tab and manage the full list

Memories are auto-pruned to the 20 most recent and injected into the system prompt of every conversation.

**Per-conversation system prompts** — scoped instructions for one specific chat. Click the **brain icon** in the input footer → enter instructions → Save. Example:

```
Always respond in JSON with keys "summary" and "action_items".
```

### Step 8 — Search, Pin, Export

- `Ctrl+K` opens the **search overlay**. Type to full-text search all conversations (title + message content). Click a result to jump there.
- Hover over any conversation in the sidebar and click the `⋮` button for the context menu:
  - **Pin/Unpin** — pinned conversations float to the top of the sidebar under a "Pinned" label
  - **Export Markdown** — downloads a readable `.md` file
  - **Export JSON** — downloads structured JSON (title + messages)
  - **Rename** — inline editable title
  - **Delete** — removes the conversation
- Double-click a conversation title to rename it directly.

### Step 9 — Keyboard Shortcuts

Press `?` to see the full list. The essentials:

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Search conversations |
| `Ctrl+N` | New chat |
| `Ctrl+Shift+⌫` | Delete current conversation |
| `↑` (empty input) | Edit last message |
| `Enter` | Send message |
| `Shift+Enter` | Newline in input |
| `Escape` | Close any open overlay/modal |
| `?` | Show shortcut help |

On macOS, `Cmd` works in place of `Ctrl`.

### Step 10 — Voice Input (Chrome/Edge)

Click the microphone icon in the input footer. It turns red and pulses while listening. Speak — the transcript fills the textarea in real-time. Click again to stop.

Firefox and Safari don't ship the Web Speech API, so the mic button is hidden automatically there.

### Step 11 — LaTeX Math

Inline math uses `$...$`, block math uses `$$...$$`. Ask:

```
Write the quadratic formula in LaTeX and prove it.
```

The `$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$` expressions render via KaTeX. Malformed LaTeX is shown as an orange code block instead of crashing the page.

### Step 12 — Settings Deep Dive

Click **⚙ Settings** in the sidebar footer. The modal has three tabs:

**General**
- **SerpAPI Key** (optional) — upgrade web search from DuckDuckGo to SerpAPI
- **OpenWeatherMap Key** (optional) — upgrade weather from Open-Meteo to OWM
- **Sandbox Directory** — where the File Manager tool can read/write (default `~/BonsaiFiles/`)

**Memory** — browse, delete individual memories, or clear all

**Shortcuts** — reference card of all keyboard shortcuts

### Step 13 — (Optional) Switch Models

If you've downloaded multiple model sizes, a dropdown appears next to the brain icon in the input footer. Selection persists in `localStorage`.

To download additional sizes:
```bash
BONSAI_MODEL=4B ./scripts/download_models.sh
BONSAI_MODEL=1.7B ./scripts/download_models.sh
```

Note: model switching in the UI selects which model you *prefer*, but the active `llama-server` process always serves whatever size it was started with. To actually serve a different size, stop and restart:
```bash
BONSAI_MODEL=4B ./scripts/start_chat.sh
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BONSAI_MODEL` | `8B` | Model size to use (8B, 4B, or 1.7B) |
| `BONSAI_MODELS_DIR` | `models/gguf/` | Where to scan for available models (for the UI dropdown) |
| `CHAT_PORT` | `9090` | Port for the chat web UI |
| `LLAMA_PORT` | `8080` | Port for llama-server |
| `BONSAI_CTX` | `8192` | Context size (token limit). Use `0` for auto-fit |
| `BONSAI_SANDBOX` | `~/BonsaiFiles/` | Sandbox directory for File Manager + uploads |
| `SERPAPI_KEY` | *(unset)* | Optional — use SerpAPI instead of DuckDuckGo |
| `OPENWEATHER_KEY` | *(unset)* | Optional — use OpenWeatherMap instead of Open-Meteo |

### Files & Paths

| Path | What it is |
|---|---|
| `chat/bonsai_chat.db` | SQLite database (conversations, messages, memories) |
| `chat/config.json` | Settings saved via the Settings UI |
| `~/BonsaiFiles/` | Sandbox for File Manager tool |
| `~/BonsaiFiles/uploads/` | Where attached files are stored |

All of these are `.gitignore`d by default.

### Database Reset

To wipe all conversations and memories and start fresh:
```bash
rm chat/bonsai_chat.db
```
The next launch will recreate an empty DB with the latest schema.

---

## Troubleshooting

**"Connection refused" or the page loads but chat doesn't stream**
→ llama-server isn't running or crashed. Check `llama-server.log`. Restart with `./scripts/start_chat.sh`.

**Port 9090 or 8080 already in use**
→ Either stop the conflicting process, or override the port:
```bash
CHAT_PORT=9091 LLAMA_PORT=8081 ./scripts/start_chat.sh
```

**Tool calls fail silently / model returns raw JSON**
→ The hybrid parser handles most cases, but some malformed outputs fall through. Check the browser devtools console for errors and `llama-server.log` for model output.

**Voice button is missing in Firefox/Safari**
→ Expected. The Web Speech API only ships in Chromium-based browsers. Use Chrome or Edge.

**Styles look wrong after updating**
→ Hard-refresh the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`) to bypass the cache. All asset URLs include a `?v=` cache-buster that increments with releases.

**Model switching dropdown doesn't appear**
→ You only have one model size downloaded. Download additional sizes with `BONSAI_MODEL=4B ./scripts/download_models.sh`.

**`pytest` fails**
→ Ensure chat deps are installed: `pip install -e ".[chat]"`. Run from the repo root: `python -m pytest chat/ -q` (36 tests should pass).

---

## File Structure

```
chat/
├── app.py                 # FastAPI entry point (REST + WebSocket + endpoints)
├── agent.py               # Agent loop (model → parse tools → execute → respond)
├── tool_parser.py         # Hybrid JSON/intent tool call parser
├── config.py              # Config (env vars + config.json + model scan)
├── db.py                  # SQLite: conversations, messages, memories, pin, system prompt
├── tools/
│   ├── __init__.py        # Tool registry and interface
│   ├── web_search.py      # DuckDuckGo / SerpAPI
│   ├── url_fetch.py       # HTTP fetch + HTML-to-text
│   ├── calculator.py      # sympy-based math
│   ├── file_io.py         # Sandboxed file operations
│   ├── weather.py         # Open-Meteo / OpenWeatherMap
│   └── python_exec.py     # Sandboxed Python execution
├── static/
│   ├── index.html         # Main page (modals, overlays, input area)
│   ├── style.css          # Dark theme, animations, all component styles
│   └── js/                # Modular vanilla JS (no build step)
│       ├── core.js        # WebSocket, state, init
│       ├── messages.js    # Rendering, markdown, LaTeX, code blocks, tool pills
│       ├── conversations.js  # Sidebar, search, pin, rename, export
│       ├── controls.js    # Stop, regenerate, copy, edit & resend
│       ├── settings.js    # Tabbed settings, memory list, model selector
│       ├── memory.js      # System prompt, save-to-memory
│       ├── uploads.js     # File upload, drag-drop, attachment chips
│       ├── voice.js       # Web Speech API voice input
│       ├── shortcuts.js   # Keyboard shortcut handler
│       └── stats.js       # Token count / speed tracking
└── tests/                 # 36 unit tests (db, tools, agent, parser)
```

---

## Building from Source

If you prefer to build llama.cpp from source instead of using pre-built binaries:

### Mac

```bash
./scripts/build_mac.sh
```

Clones [PrismML-Eng/llama.cpp](https://github.com/PrismML-Eng/llama.cpp), builds with Metal, outputs to `bin/mac/`.

### Linux (CUDA)

```bash
./scripts/build_cuda_linux.sh
```

Auto-detects CUDA version. Pass `--cuda-path /usr/local/cuda-12.8` to use a specific toolkit.

### Windows (CUDA)

```powershell
.\scripts\build_cuda_windows.ps1
```

Auto-detects CUDA toolkit. Pass `-CudaPath "C:\path\to\cuda"` to use a specific version.
Requires Visual Studio Build Tools (or full Visual Studio) and CUDA toolkit.

---

## llama.cpp Pre-built Binary Downloads

All binaries are available from the [GitHub Release](https://github.com/PrismML-Eng/llama.cpp/releases/tag/prism-b8196-f5dda72):

| Platform                |
|-------------------------|
| macOS Apple Silicon     |
| Linux x64 (CUDA 12.4)  |
| Linux x64 (CUDA 12.8)  |
| Linux x64 (CUDA 13.1)  |
| Windows x64 (CUDA 12.4) |
| Windows x64 (CUDA 13.1) |

---

## Folder Structure

After setup, the directory looks like this:

```
Bonsai-demo/
├── README.md
├── setup.sh                        # macOS/Linux setup
├── setup.ps1                       # Windows setup
├── pyproject.toml                  # Python dependencies
├── scripts/
│   ├── common.sh                   # Shared helpers + BONSAI_MODEL
│   ├── download_models.sh          # HuggingFace download
│   ├── download_binaries.sh        # GitHub release download
│   ├── run_llama.sh                # llama.cpp (auto-detects Mac/Linux)
│   ├── run_mlx.sh                  # MLX inference
│   ├── mlx_generate.py             # MLX Python script
│   ├── start_llama_server.sh       # llama.cpp server (port 8080)
│   ├── start_mlx_server.sh         # MLX server (port 8081)
│   ├── start_openwebui.sh          # Open WebUI + auto-starts backends
│   ├── start_chat.sh               # Bonsai Chat (Mac/Linux)
│   ├── start_chat.ps1              # Bonsai Chat (Windows)
│   ├── build_mac.sh                # Build llama.cpp for Mac
│   ├── build_cuda_linux.sh         # Build llama.cpp for Linux CUDA
│   └── build_cuda_windows.ps1      # Build llama.cpp for Windows CUDA
├── chat/                           # Bonsai Chat — full-featured web UI
│   ├── app.py                      # FastAPI app (REST + WebSocket)
│   ├── agent.py                    # Agent loop (tool parsing, cancel, custom context)
│   ├── tool_parser.py              # Hybrid tool call parser
│   ├── config.py                   # Configuration + model scanning
│   ├── db.py                       # SQLite storage (convs, msgs, memories)
│   ├── tools/                      # 6 built-in tools
│   ├── static/
│   │   ├── index.html              # Main page
│   │   ├── style.css               # Dark theme
│   │   └── js/                     # 10 vanilla JS modules (no bundler)
│   └── tests/                      # 36 unit tests
├── models/                         # ← downloaded by setup
│   ├── gguf/
│   │   ├── 8B/                     # GGUF 8B model
│   │   ├── 4B/                     # GGUF 4B model
│   │   └── 1.7B/                   # GGUF 1.7B model
│   ├── Bonsai-8B-mlx/             # MLX 8B model (macOS)
│   ├── Bonsai-4B-mlx/             # MLX 4B model (macOS)
│   └── Bonsai-1.7B-mlx/           # MLX 1.7B model (macOS)
├── bin/                            # ← downloaded or built by setup
│   ├── mac/                        # macOS binaries
│   └── cuda/                       # CUDA binaries
├── mlx/                            # ← cloned by setup (macOS)
└── .venv/                          # ← created by setup
```

Items marked with ← are created at setup time and excluded from git.
