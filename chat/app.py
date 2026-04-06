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

            # Use result content
            final_content = result["content"] if result else full_response

            # Save assistant message
            db.add_message(
                conv_id, "assistant", final_content,
                tool_calls=result.get("tool_calls") if result else None,
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
