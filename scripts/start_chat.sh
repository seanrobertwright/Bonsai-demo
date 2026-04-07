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
