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
