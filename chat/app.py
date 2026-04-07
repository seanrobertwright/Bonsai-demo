"""Bonsai Chat — FastAPI application."""

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi import File as FastAPIFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from chat.agent import AgentLoop
from chat.config import CHAT_PORT, DB_PATH, SANDBOX_DIR, STATIC_DIR, get_config, list_available_models, save_config_file
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
    registry = create_registry(db=db)
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


@app.get("/api/conversations/search")
async def search_conversations(q: str = ""):
    if not q.strip():
        return []
    return db.search_conversations(q)


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


@app.get("/api/models")
async def get_models():
    return list_available_models()


@app.post("/api/upload")
async def upload_file(file: UploadFile = FastAPIFile(...)):
    upload_dir = SANDBOX_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix
    file_id = str(uuid.uuid4())
    dest = upload_dir / f"{file_id}{ext}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Read text content for code/text files
    text_content = None
    text_exts = {'.txt', '.py', '.js', '.ts', '.json', '.csv', '.md', '.html', '.css'}
    if ext.lower() in text_exts:
        try:
            content = dest.read_text(encoding='utf-8')
            if len(content) > 50_000:
                content = content[:50_000] + "\n\n[File truncated to first 50KB]"
            text_content = content
        except Exception:
            pass

    return {
        "id": file_id,
        "filename": file.filename,
        "path": str(dest),
        "type": "image" if ext.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp'} else "text",
        "size": dest.stat().st_size,
        "content": text_content,
    }


@app.get("/api/conversations/{conv_id}/export")
async def export_conversation(conv_id: str, format: str = "markdown"):
    conv = db.conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not conv:
        return JSONResponse({"error": "Not found"}, status_code=404)

    messages = db.get_messages(conv_id)

    if format == "json":
        return JSONResponse({"title": conv["title"], "messages": messages})

    # Markdown format
    lines = [f"# {conv['title']}\n"]
    for m in messages:
        role = "**User:**" if m["role"] == "user" else "**Assistant:**"
        lines.append(f"{role}\n\n{m['content']}\n")
    return PlainTextResponse("\n---\n\n".join(lines), media_type="text/markdown")


@app.post("/api/conversations/{conv_id}/pin")
async def toggle_pin(conv_id: str):
    pinned = db.toggle_pin(conv_id)
    return {"pinned": pinned}


@app.get("/api/memory")
async def list_memories():
    return db.list_memories()


@app.post("/api/memory")
async def add_memory(data: dict):
    return db.add_memory(data["content"])


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    db.delete_memory(memory_id)
    return {"ok": True}


@app.delete("/api/memory")
async def delete_all_memories():
    db.delete_all_memories()
    return {"ok": True}


@app.get("/api/conversations/{conv_id}/system-prompt")
async def get_system_prompt(conv_id: str):
    return {"system_prompt": db.get_system_prompt(conv_id)}


@app.post("/api/conversations/{conv_id}/system-prompt")
async def set_system_prompt(conv_id: str, data: dict):
    db.set_system_prompt(conv_id, data.get("system_prompt", ""))
    return {"ok": True}


# ── WebSocket Chat ──


@app.websocket("/ws/chat/{conv_id}")
async def websocket_chat(ws: WebSocket, conv_id: str):
    await ws.accept()

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # Handle stop signal
            if msg.get("type") == "stop":
                if hasattr(ws, '_cancel_event'):
                    ws._cancel_event.set()
                continue

            # Handle regenerate signal
            if msg.get("type") == "regenerate":
                last_user_content = db.delete_last_assistant_message(conv_id)
                if not last_user_content:
                    continue

                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in db.get_messages(conv_id)
                    if m["role"] in ("user", "assistant")
                ]

                full_response = ""
                cancel_event = asyncio.Event()
                ws._cancel_event = cancel_event

                async def on_token_regen(token):
                    nonlocal full_response
                    full_response += token
                    await ws.send_text(json.dumps({"type": "token", "content": token}))

                async def on_tool_start_regen(name, args):
                    await ws.send_text(json.dumps({"type": "tool_start", "name": name, "arguments": args}))

                async def on_tool_end_regen(name, result):
                    await ws.send_text(json.dumps({"type": "tool_end", "name": name, "result": result}))

                result = await agent.run(history, on_token=on_token_regen, on_tool_start=on_tool_start_regen, on_tool_end=on_tool_end_regen, cancel_event=cancel_event)
                final_content = result["content"] if result else full_response
                db.add_message(conv_id, "assistant", final_content, tool_calls=result.get("tool_calls") if result else None)
                await ws.send_text(json.dumps({"type": "done"}))
                continue

            # Handle edit_resend signal
            if msg.get("type") == "edit_resend":
                new_content = msg.get("content", "")
                if not new_content.strip():
                    continue

                db.delete_messages_after_last_user(conv_id)
                db.add_message(conv_id, "user", new_content)

                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in db.get_messages(conv_id)
                    if m["role"] in ("user", "assistant")
                ]

                full_response = ""
                cancel_event = asyncio.Event()
                ws._cancel_event = cancel_event

                async def on_token_edit(token):
                    nonlocal full_response
                    full_response += token
                    await ws.send_text(json.dumps({"type": "token", "content": token}))

                async def on_tool_start_edit(name, args):
                    await ws.send_text(json.dumps({"type": "tool_start", "name": name, "arguments": args}))

                async def on_tool_end_edit(name, result):
                    await ws.send_text(json.dumps({"type": "tool_end", "name": name, "result": result}))

                result = await agent.run(history, on_token=on_token_edit, on_tool_start=on_tool_start_edit, on_tool_end=on_tool_end_edit, cancel_event=cancel_event)
                final_content = result["content"] if result else full_response
                db.add_message(conv_id, "assistant", final_content, tool_calls=result.get("tool_calls") if result else None)
                await ws.send_text(json.dumps({"type": "done"}))
                continue

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

            # Create cancellation event for this request
            cancel_event = asyncio.Event()
            ws._cancel_event = cancel_event

            # Build custom context from memories + conversation system prompt
            memories = db.list_memories()
            conv_system_prompt = db.get_system_prompt(conv_id)
            custom_context = ""
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
            if conv_system_prompt:
                custom_context += f"User instructions for this conversation:\n{conv_system_prompt}\n\n"

            result = await agent.run(
                history,
                on_token=on_token,
                on_tool_start=on_tool_start,
                on_tool_end=on_tool_end,
                cancel_event=cancel_event,
                custom_context=custom_context,
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
