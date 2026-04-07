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

## Bonsai Chat — Custom Web UI with Tools

Bonsai Chat is a local, agentic chat assistant with a custom three-panel web UI and 6 built-in tools. It provides a ChatGPT-like experience powered entirely by the Bonsai model running on your machine — no cloud APIs required for core functionality.

### Features

- **Three-panel UI** — conversation sidebar, chat area with markdown rendering, and a live tool status panel
- **6 built-in tools** the model can call autonomously:

  | Tool | Description | Provider |
  |------|-------------|----------|
  | **Web Search** | Search the internet for current information | DuckDuckGo (free) or SerpAPI |
  | **URL Fetch** | Read and summarize any web page | Built-in (httpx + BeautifulSoup) |
  | **Calculator** | Arithmetic, algebra, calculus, unit conversions | Built-in (sympy) |
  | **File Manager** | Read, write, and list files in a sandboxed directory | Built-in (~/BonsaiFiles/) |
  | **Weather** | Current conditions and 3-day forecast | Open-Meteo (free) or OpenWeatherMap |
  | **Python Exec** | Run Python code snippets with captured output | Built-in (subprocess, 30s timeout) |

- **Hybrid tool-calling** — tries structured JSON parsing first, falls back to intent detection from natural language (handles cases where the 8B model produces imperfect JSON)
- **Streaming responses** — tokens stream to the browser in real-time via WebSocket
- **Conversation persistence** — SQLite-backed chat history with auto-generated titles
- **Transparent tool use** — tool calls appear as clickable pills showing what was called and the results
- **Dark theme** — GitHub-inspired dark UI
- **No API keys needed** — works out of the box with free providers; optionally upgrade via Settings

### Architecture

```
Browser (vanilla JS) ←→ FastAPI (WebSocket + REST) ←→ llama-server (GGUF)
                              ↓
                        Agent Loop (tool parsing, execution, multi-round)
                              ↓
                        Tools (web search, URL fetch, calculator, files, weather, Python)
```

The FastAPI backend sits between the browser and llama-server. An agent loop intercepts model output, detects tool calls, executes them, feeds results back to the model, and streams the final answer — up to 5 tool rounds per message.

### Installation

Bonsai Chat is included in the demo. After running the standard setup (`setup.sh` or `setup.ps1`), install the chat dependencies:

```bash
# macOS / Linux
source .venv/bin/activate
pip install -e ".[chat]"

# Windows (PowerShell)
.\.venv\Scripts\pip.exe install -e ".[chat]"
```

> **Note:** The launch scripts below auto-install these dependencies if they're missing, so you can skip this step and just run the launch script directly.

### Running

#### Windows (PowerShell)

```powershell
.\scripts\start_chat.ps1
```

#### macOS / Linux

```bash
./scripts/start_chat.sh
```

Then open **http://localhost:9090** in your browser.

The launch script handles everything:
1. Checks for (and installs) chat dependencies if missing
2. Starts llama-server in the background if not already running
3. Starts the Bonsai Chat web app on port 9090

Press **Ctrl+C** to stop the chat server. The llama-server continues running in the background for reuse.

### Configuration

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BONSAI_MODEL` | `8B` | Model size to use (8B, 4B, or 1.7B) |
| `CHAT_PORT` | `9090` | Port for the chat web UI |
| `LLAMA_PORT` | `8080` | Port for llama-server |
| `BONSAI_CTX` | `8192` | Context size (token limit). Use `0` for auto-fit (slower startup) |
| `BONSAI_SANDBOX` | `~/BonsaiFiles/` | Sandbox directory for file I/O tool |

#### Optional API Keys

All tools work out of the box with free providers. For higher-quality results, configure premium providers via the Settings page in the UI, or set environment variables:

| Variable | Provider | Replaces |
|----------|----------|----------|
| `SERPAPI_KEY` | [SerpAPI](https://serpapi.com/) (web search) | DuckDuckGo |
| `OPENWEATHER_KEY` | [OpenWeatherMap](https://openweathermap.org/api) | Open-Meteo |

### File Structure

```
chat/
├── app.py                 # FastAPI entry point (REST + WebSocket)
├── agent.py               # Agent loop (model → parse tools → execute → respond)
├── tool_parser.py         # Hybrid JSON/fallback tool call parser
├── config.py              # Configuration (env vars + config.json)
├── db.py                  # SQLite conversation storage
├── tools/
│   ├── __init__.py        # Tool registry and interface
│   ├── web_search.py      # DuckDuckGo / SerpAPI
│   ├── url_fetch.py       # HTTP fetch + HTML-to-text
│   ├── calculator.py      # sympy-based math
│   ├── file_io.py         # Sandboxed file operations
│   ├── weather.py         # Open-Meteo / OpenWeatherMap
│   └── python_exec.py     # Sandboxed Python execution
├── static/
│   ├── index.html         # Main page
│   ├── style.css          # Dark theme styles
│   └── app.js             # Chat UI (WebSocket, tool pills, markdown)
└── tests/                 # Unit tests (36 tests)
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
├── chat/                           # Bonsai Chat — agentic web UI
│   ├── app.py                      # FastAPI app (REST + WebSocket)
│   ├── agent.py                    # Agent loop
│   ├── tool_parser.py              # Hybrid tool call parser
│   ├── config.py                   # Configuration
│   ├── db.py                       # SQLite storage
│   ├── tools/                      # 6 built-in tools
│   ├── static/                     # Frontend (HTML/CSS/JS)
│   └── tests/                      # Unit tests
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
