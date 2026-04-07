# Bonsai Chat Feature Expansion — Implementation Plan

> **For agentic workers:** REQUIRED: Use lril-superpowers:subagent-driven-development (if subagents available) or lril-superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ChatGPT/Claude.ai-level features to Bonsai Chat — response controls, keyboard shortcuts, conversation management, file uploads, token stats, LaTeX, memory, model switching, voice input, and settings redesign.

**Architecture:** Incremental enhancement of existing vanilla JS frontend. Split monolithic `app.js` into focused JS modules under `chat/static/js/`. Backend additions to existing `app.py`, `db.py`, `agent.py`. No framework, no bundler.

**Tech Stack:** Python/FastAPI, vanilla JS, SQLite, marked.js, highlight.js, KaTeX, Web Speech API

**Spec:** `docs/superpowers/specs/2026-04-06-bonsai-chat-features-design.md`

---

## Chunk 1: Foundation — JS Module Split & Response Controls

This chunk restructures the frontend into modules and adds the highest-impact UX features: stop generation, regenerate response, edit & resend messages, and copy response.

### Task 1: Split app.js into JS modules

**Files:**
- Create: `chat/static/js/core.js`
- Create: `chat/static/js/messages.js`
- Create: `chat/static/js/conversations.js`
- Create: `chat/static/js/controls.js`
- Create: `chat/static/js/settings.js`
- Modify: `chat/static/index.html`
- Delete contents of: `chat/static/app.js` (keep as empty file or remove)

This is a pure refactor — no new features. Extract existing code into modules.

- [ ] **Step 1: Create `core.js` — shared state, WebSocket, init**

Extract from `app.js`: the global variables (`ws`, `currentConvId`, `conversations`, `currentAssistantEl`, `currentAssistantText`), `init()`, `connectWebSocket()`, `handleWSMessage()`, `sendMessage()`, `sendMessageText()`, `handleKeyDown()`, `scrollToBottom()`, `escapeHtml()`, and the `window.onerror` handler.

```javascript
/* Bonsai Chat — Core: shared state, WebSocket, init */

let ws = null;
let currentConvId = null;
let conversations = [];
let currentAssistantEl = null;
let currentAssistantText = '';

async function init() {
    await loadTools();
    await loadConversations();
}

function connectWebSocket(convId) {
    return new Promise((resolve) => {
        if (ws) ws.close();
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws/chat/${convId}`);
        ws.onopen = () => resolve();
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleWSMessage(data);
        };
        ws.onclose = () => { ws = null; };
    });
}

function handleWSMessage(data) {
    switch (data.type) {
        case 'token':
            if (!currentAssistantEl) {
                currentAssistantEl = appendMessage('assistant', '');
                currentAssistantText = '';
            }
            currentAssistantText += data.content;
            const contentEl = currentAssistantEl.querySelector('.message-content');
            contentEl.innerHTML = marked.parse(preprocessMarkdown(currentAssistantText));
            enhanceCodeBlocks(contentEl);
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
            if (currentAssistantEl && currentAssistantText) {
                const finalEl = currentAssistantEl.querySelector('.message-content');
                finalEl.innerHTML = marked.parse(preprocessMarkdown(currentAssistantText));
                enhanceCodeBlocks(finalEl);
            }
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

async function sendMessage() {
    const input = document.getElementById('message-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';
    try {
        if (!currentConvId || !ws || ws.readyState !== WebSocket.OPEN) {
            await createNewChat();
        }
        sendMessageText(text);
    } catch (e) {
        console.error('sendMessage error:', e);
        appendSystemMessage('Failed to send message: ' + e.message);
    }
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
    const input = event.target;
    setTimeout(() => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }, 0);
}

function scrollToBottom() {
    const messages = document.getElementById('messages');
    messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

window.onerror = function(msg, url, line) {
    console.error(`JS Error: ${msg} at ${url}:${line}`);
};

init().catch(e => console.error('init error:', e));
```

- [ ] **Step 2: Create `messages.js` — rendering, markdown, code blocks**

Extract from `app.js`: `preprocessMarkdown()`, `enhanceCodeBlocks()`, `appendMessage()`, `appendSystemMessage()`, `renderMessageHistory()`, and all tool pill functions (`addToolPill`, `updateToolPill`, `toggleToolDetail`, `addToolLog`, `updateToolLog`, `toolPillCounter`).

```javascript
/* Bonsai Chat — Messages: rendering, markdown, code blocks, tool pills */

let toolPillCounter = 0;

function preprocessMarkdown(text) {
    const trimmed = text.trim();
    if (!trimmed.includes('"name"')) return text;

    if (trimmed.startsWith('{')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && parsed.name && parsed.arguments) {
                if (parsed.name === 'python_exec' && parsed.arguments.code) {
                    return '```python\n' + parsed.arguments.code + '\n```';
                }
                return '```json\n' + JSON.stringify(parsed, null, 2) + '\n```';
            }
        } catch (e) {}
    }

    const codeMatch = trimmed.match(/"code"\s*:\s*"((?:[^"\\]|\\.)*)"/s);
    if (codeMatch && trimmed.includes('"python_exec"')) {
        const code = codeMatch[1]
            .replace(/\\n/g, '\n')
            .replace(/\\t/g, '\t')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\');
        return '```python\n' + code + '\n```';
    }

    if (trimmed.startsWith('{') && trimmed.includes('"arguments"')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed) return '```json\n' + JSON.stringify(parsed, null, 2) + '\n```';
        } catch (e) {}
    }

    return text;
}

function enhanceCodeBlocks(container) {
    const codeBlocks = container.querySelectorAll('pre code');
    for (const codeEl of codeBlocks) {
        const pre = codeEl.parentElement;
        if (pre.classList.contains('enhanced')) continue;
        pre.classList.add('enhanced');
        try { hljs.highlightElement(codeEl); } catch (e) {}

        const lines = codeEl.textContent.split('\n');
        if (lines.length > 1) {
            const lineNums = document.createElement('span');
            lineNums.className = 'line-numbers';
            lineNums.setAttribute('aria-hidden', 'true');
            lineNums.innerHTML = lines.map((_, i) => `<span>${i + 1}</span>`).join('\n');
            pre.insertBefore(lineNums, codeEl);
            pre.classList.add('has-line-numbers');
        }

        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        btn.onclick = () => {
            navigator.clipboard.writeText(codeEl.textContent).then(() => {
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
                setTimeout(() => {
                    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                }, 2000);
            });
        };
        pre.appendChild(btn);
    }
}

function appendMessage(role, content) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatarClass = role === 'user' ? 'user-avatar' : 'bot-avatar';
    const avatarContent = role === 'user' ? 'U' : '&#127793;';
    div.innerHTML = `
        <div class="avatar ${avatarClass}">${avatarContent}</div>
        <div class="message-content">${role === 'user' ? escapeHtml(content) : marked.parse(preprocessMarkdown(content))}</div>
    `;
    if (role === 'assistant') enhanceCodeBlocks(div);
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
    if (detail) detail.classList.toggle('expanded');
}

function addToolLog(name, args, status) {
    const log = document.getElementById('tool-log');
    if (log.querySelector('.empty-state')) log.innerHTML = '';
    const entry = document.createElement('div');
    entry.className = 'tool-log-entry';
    entry.id = `log-${name}-${toolPillCounter}`;
    const icon = status === 'running' ? '&#9679;' : '&#10003;';
    const argsStr = Object.values(args || {}).join(', ');
    entry.innerHTML = `<span class="log-icon">${icon}</span> <strong>${name}</strong><div class="log-detail">${argsStr}</div>`;
    log.appendChild(entry);
}

function updateToolLog(name, result) {
    const entries = document.querySelectorAll('.tool-log-entry');
    for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        if (entry.querySelector('strong')?.textContent === name && entry.innerHTML.includes('\u25CF')) {
            entry.querySelector('.log-icon').innerHTML = '&#10003;';
            const detail = entry.querySelector('.log-detail');
            if (result.results) detail.textContent = `${result.results.length} results`;
            else if (result.result) detail.textContent = result.result;
            else if (result.error) detail.textContent = `Error: ${result.error}`;
            break;
        }
    }
}
```

- [ ] **Step 3: Create `conversations.js` — sidebar, views, clear**

Extract from `app.js`: `loadConversations()`, `renderConversationList()`, `createNewChat()`, `openConversation()`, `deleteConversation()`, `showChatView()`, `showWelcome()`, `clearMessages()`.

```javascript
/* Bonsai Chat — Conversations: sidebar, navigation, views */

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
    await connectWebSocket(conv.id);
}

async function openConversation(convId) {
    currentConvId = convId;
    renderConversationList();
    showChatView();
    const resp = await fetch(`/api/conversations/${convId}/messages`);
    const messages = await resp.json();
    renderMessageHistory(messages);
    await connectWebSocket(convId);
}

async function deleteConversation(convId) {
    await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
    if (currentConvId === convId) {
        currentConvId = null;
        showWelcome();
    }
    await loadConversations();
}

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
```

- [ ] **Step 4: Create `settings.js` — settings modal, tools list**

Extract from `app.js`: `toggleSettings()`, `saveSettings()`, `loadTools()`.

```javascript
/* Bonsai Chat — Settings & tools */

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

async function loadTools() {
    try {
        const resp = await fetch('/api/tools');
        const tools = await resp.json();
        const list = document.getElementById('tool-list');
        list.innerHTML = tools.map(t =>
            `<div class="tool-entry"><div class="tool-dot"></div>${t.name}</div>`
        ).join('');
    } catch (e) {}
}
```

- [ ] **Step 5: Create empty `controls.js` placeholder**

```javascript
/* Bonsai Chat — Response controls: stop, regenerate, edit, copy */
// Implemented in Task 2
```

- [ ] **Step 6: Update `index.html` to load modules**

Replace the single `<script src="/app.js?v=5">` with ordered module script tags. Order matters — `messages.js` and `conversations.js` depend on functions in `core.js`, and `core.js` depends on functions in `messages.js` and `conversations.js` (circular). Since these are all globals, load order is: messages, conversations, settings, controls, then core (which calls `init()`).

```html
    <script src="/js/messages.js?v=6"></script>
    <script src="/js/conversations.js?v=6"></script>
    <script src="/js/settings.js?v=6"></script>
    <script src="/js/controls.js?v=6"></script>
    <script src="/js/core.js?v=6"></script>
```

- [ ] **Step 7: Verify the refactored app works**

Open `localhost:9090` in browser. Verify:
- New chat works
- Messages send and stream
- Tool pills display
- Code blocks render with syntax highlighting
- Conversation list loads
- Settings modal opens/saves

- [ ] **Step 8: Commit**

```bash
git add chat/static/js/ chat/static/index.html
git rm chat/static/app.js  # or keep as empty
git commit -m "refactor(chat): split app.js into focused JS modules"
```

---

### Task 2: Stop Generation Button

**Files:**
- Modify: `chat/static/js/core.js` — handle stop in `handleWSMessage`, transform send button
- Modify: `chat/static/js/controls.js` — `stopGeneration()` function
- Modify: `chat/app.py` — handle `{type: "stop"}` WebSocket message
- Modify: `chat/agent.py` — accept cancellation signal
- Modify: `chat/static/style.css` — stop button styles

- [ ] **Step 1: Add stop button styles to `style.css`**

```css
/* Stop button (replaces Send during streaming) */
#send-btn.stop-btn {
    background: #da3633;
    padding: 5px 10px;
}
#send-btn.stop-btn:hover {
    background: #f85149;
}
```

- [ ] **Step 2: Add `stopGeneration()` to `controls.js`**

```javascript
function stopGeneration() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }));
    }
    // Restore send button immediately
    const btn = document.getElementById('send-btn');
    btn.textContent = 'Send';
    btn.classList.remove('stop-btn');
    btn.onclick = sendMessage;
    btn.disabled = false;
    document.getElementById('message-input').disabled = false;
}
```

- [ ] **Step 3: Update `core.js` — transform Send to Stop during streaming**

In `sendMessageText()`, after disabling the button, transform it:

```javascript
function sendMessageText(text) {
    appendMessage('user', text);
    const btn = document.getElementById('send-btn');
    btn.disabled = false;  // Keep enabled as Stop
    btn.textContent = 'Stop';
    btn.classList.add('stop-btn');
    btn.onclick = stopGeneration;
    document.getElementById('message-input').disabled = true;
    ws.send(JSON.stringify({ content: text }));
    scrollToBottom();
}
```

In the `done` case of `handleWSMessage()`, restore the Send button:

```javascript
case 'done':
    // ... existing final render pass ...
    const doneBtn = document.getElementById('send-btn');
    doneBtn.textContent = 'Send';
    doneBtn.classList.remove('stop-btn');
    doneBtn.onclick = sendMessage;
    doneBtn.disabled = false;
    document.getElementById('message-input').disabled = false;
    break;
```

- [ ] **Step 4: Backend — handle stop in `app.py` WebSocket handler**

Add a cancellation event that the agent loop can check. Modify the WebSocket handler in `app.py`:

```python
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

            user_content = msg.get("content", "")
            if not user_content.strip():
                continue

            # Create cancellation event for this request
            cancel_event = asyncio.Event()
            ws._cancel_event = cancel_event

            # ... rest of existing handler, pass cancel_event to agent.run() ...

            result = await agent.run(
                history,
                on_token=on_token,
                on_tool_start=on_tool_start,
                on_tool_end=on_tool_end,
                cancel_event=cancel_event,
            )

            # ... rest unchanged ...
```

- [ ] **Step 5: Backend — add cancellation to `agent.py`**

Add `cancel_event` parameter to `run()` and check it during streaming:

```python
async def run(self, messages, on_token=None, on_tool_start=None, on_tool_end=None, cancel_event=None):
    # ... existing setup ...
    for round_num in range(MAX_TOOL_ROUNDS + 1):
        full_response = ""
        async for token in self._stream_completion(full_messages):
            if cancel_event and cancel_event.is_set():
                break
            full_response += token

        if cancel_event and cancel_event.is_set():
            # Stream what we have so far
            if on_token and full_response:
                display_text = self._strip_tool_json(full_response)
                for char in display_text:
                    await on_token(char)
            return {"content": full_response, "tool_calls": all_tool_calls}

        # ... rest of existing loop ...
```

- [ ] **Step 6: Verify stop generation works**

Send a message, click Stop mid-stream. Verify:
- Streaming stops
- Partial response is preserved
- Send button restores
- Can send new messages after stopping

- [ ] **Step 7: Commit**

```bash
git add chat/static/js/controls.js chat/static/js/core.js chat/static/style.css chat/app.py chat/agent.py
git commit -m "feat(chat): add stop generation button"
```

---

### Task 3: Regenerate Response

**Files:**
- Modify: `chat/static/js/messages.js` — add regenerate button to assistant messages
- Modify: `chat/static/js/controls.js` — `regenerateResponse()` function
- Modify: `chat/db.py` — `delete_last_assistant_message()` method
- Modify: `chat/app.py` — handle regenerate WebSocket message
- Modify: `chat/static/style.css` — regenerate button styles

- [ ] **Step 1: Add regenerate button styles**

```css
/* Response action buttons */
.message-actions {
    display: flex;
    gap: 4px;
    margin-top: 4px;
    margin-left: 40px;
    opacity: 0;
    transition: opacity 0.15s;
}
.message:hover .message-actions,
.message-actions:focus-within {
    opacity: 1;
}
.message-action-btn {
    background: none;
    border: 1px solid transparent;
    color: var(--text-muted);
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
}
.message-action-btn:hover {
    color: var(--text-secondary);
    border-color: var(--border);
    background: var(--bg-tertiary);
}
```

- [ ] **Step 2: Add regenerate button rendering in `messages.js`**

Modify `appendMessage()` to add action buttons for assistant messages. After the message div is created, append an actions row:

```javascript
function appendMessage(role, content) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatarClass = role === 'user' ? 'user-avatar' : 'bot-avatar';
    const avatarContent = role === 'user' ? 'U' : '&#127793;';

    div.innerHTML = `
        <div class="avatar ${avatarClass}">${avatarContent}</div>
        <div class="message-content">${role === 'user' ? escapeHtml(content) : marked.parse(preprocessMarkdown(content))}</div>
    `;

    if (role === 'assistant') {
        enhanceCodeBlocks(div);
    }

    messages.appendChild(div);

    // Add action buttons for assistant messages (only for completed messages with content)
    if (role === 'assistant' && content) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        actions.innerHTML = `
            <button class="message-action-btn" onclick="copyResponse(this)" title="Copy">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy
            </button>
            <button class="message-action-btn" onclick="regenerateResponse()" title="Regenerate">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                Regenerate
            </button>
        `;
        messages.appendChild(actions);
    }

    scrollToBottom();
    return div;
}
```

- [ ] **Step 3: Add `regenerateResponse()` and `copyResponse()` to `controls.js`**

```javascript
async function regenerateResponse() {
    if (!currentConvId || !ws || ws.readyState !== WebSocket.OPEN) return;

    // Remove the last assistant message and its action buttons from DOM
    const messages = document.getElementById('messages');
    const allMessages = messages.querySelectorAll('.message.assistant');
    const lastAssistant = allMessages[allMessages.length - 1];
    if (lastAssistant) {
        // Remove action buttons that follow it
        const nextEl = lastAssistant.nextElementSibling;
        if (nextEl && nextEl.classList.contains('message-actions')) {
            nextEl.remove();
        }
        lastAssistant.remove();
    }

    // Tell backend to regenerate
    ws.send(JSON.stringify({ type: 'regenerate' }));

    // Set up UI for streaming
    const btn = document.getElementById('send-btn');
    btn.textContent = 'Stop';
    btn.classList.add('stop-btn');
    btn.onclick = stopGeneration;
    btn.disabled = false;
    document.getElementById('message-input').disabled = true;
}

function copyResponse(btn) {
    const messageEl = btn.closest('.message-actions').previousElementSibling;
    const content = messageEl?.querySelector('.message-content');
    if (content) {
        navigator.clipboard.writeText(content.textContent).then(() => {
            const label = btn.querySelector('svg').nextSibling;
            if (label) label.textContent = ' Copied!';
            setTimeout(() => { if (label) label.textContent = '\n                Copy'; }, 2000);
        });
    }
}
```

- [ ] **Step 4: Backend — add `delete_last_assistant_message()` to `db.py`**

```python
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
```

- [ ] **Step 5: Backend — handle regenerate in `app.py`**

In the WebSocket handler, add a case for the regenerate message type:

```python
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

                async def on_token(token):
                    nonlocal full_response
                    full_response += token
                    await ws.send_text(json.dumps({"type": "token", "content": token}))

                # ... same on_tool_start, on_tool_end as existing ...
                result = await agent.run(history, on_token=on_token, on_tool_start=on_tool_start, on_tool_end=on_tool_end, cancel_event=cancel_event)
                final_content = result["content"] if result else full_response
                db.add_message(conv_id, "assistant", final_content, tool_calls=result.get("tool_calls") if result else None)
                await ws.send_text(json.dumps({"type": "done"}))
                continue
```

- [ ] **Step 6: Verify regenerate works**

Send a message, wait for response, click Regenerate. Verify:
- Old response is removed from UI
- New response streams in
- New response is saved to DB
- Can regenerate multiple times

- [ ] **Step 7: Commit**

```bash
git add chat/static/js/messages.js chat/static/js/controls.js chat/static/style.css chat/db.py chat/app.py
git commit -m "feat(chat): add regenerate response and copy buttons"
```

---

### Task 4: Edit & Resend User Messages

**Files:**
- Modify: `chat/static/js/messages.js` — add edit button to user messages
- Modify: `chat/static/js/controls.js` — `editMessage()`, `saveAndResend()` functions
- Modify: `chat/db.py` — `delete_messages_after()` method
- Modify: `chat/app.py` — handle edit-resend WebSocket message
- Modify: `chat/static/style.css` — edit UI styles

- [ ] **Step 1: Add edit UI styles**

```css
/* User message edit */
.message.user .edit-btn {
    position: absolute;
    top: 8px;
    left: -28px;
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s;
    padding: 2px;
}
.message.user:hover .edit-btn {
    opacity: 1;
}
.message.user .edit-btn:hover {
    color: var(--text-secondary);
}
.message.user .message-content {
    position: relative;
}
.edit-textarea {
    width: 100%;
    background: var(--bg-primary);
    border: 1px solid var(--accent-blue);
    border-radius: 6px;
    padding: 8px 10px;
    color: var(--text-primary);
    font-size: 14px;
    font-family: inherit;
    resize: none;
    outline: none;
    min-height: 60px;
}
.edit-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
    margin-top: 6px;
}
.edit-actions button {
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    border: none;
}
.edit-actions .save-resend {
    background: var(--accent-green);
    color: white;
}
.edit-actions .cancel-edit {
    background: var(--border);
    color: var(--text-primary);
}
```

- [ ] **Step 2: Add edit button to user messages in `messages.js`**

Modify `appendMessage()` — for user messages, add an edit pencil icon. Store the message ID on the element via a `data-msg-index` attribute (the index in the messages list):

```javascript
    if (role === 'user') {
        const contentWrapper = div.querySelector('.message-content');
        contentWrapper.style.position = 'relative';
        const editBtn = document.createElement('button');
        editBtn.className = 'edit-btn';
        editBtn.title = 'Edit message';
        editBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
        editBtn.onclick = () => editMessage(div, content);
        contentWrapper.appendChild(editBtn);
    }
```

- [ ] **Step 3: Add `editMessage()` and `saveAndResend()` to `controls.js`**

```javascript
function editMessage(messageEl, originalText) {
    const contentEl = messageEl.querySelector('.message-content');
    contentEl.innerHTML = `
        <textarea class="edit-textarea">${escapeHtml(originalText)}</textarea>
        <div class="edit-actions">
            <button class="cancel-edit" onclick="cancelEdit(this, '${escapeHtml(originalText).replace(/'/g, "\\'")}')">Cancel</button>
            <button class="save-resend" onclick="saveAndResend(this)">Save & Resend</button>
        </div>
    `;
    const textarea = contentEl.querySelector('.edit-textarea');
    textarea.focus();
    textarea.style.height = textarea.scrollHeight + 'px';
}

function cancelEdit(btn, originalText) {
    const messageEl = btn.closest('.message');
    const contentEl = messageEl.querySelector('.message-content');
    contentEl.innerHTML = escapeHtml(originalText);
    // Re-add the edit button
    contentEl.style.position = 'relative';
    const editBtn = document.createElement('button');
    editBtn.className = 'edit-btn';
    editBtn.title = 'Edit message';
    editBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
    editBtn.onclick = () => editMessage(messageEl, originalText);
    contentEl.appendChild(editBtn);
}

async function saveAndResend(btn) {
    const messageEl = btn.closest('.message');
    const textarea = messageEl.querySelector('.edit-textarea');
    const newText = textarea.value.trim();
    if (!newText) return;

    // Remove all messages after (and including) this one from the DOM
    const messagesContainer = document.getElementById('messages');
    let el = messageEl;
    while (el) {
        const next = el.nextElementSibling;
        el.remove();
        el = next;
    }

    // Send edit-resend to backend
    ws.send(JSON.stringify({ type: 'edit_resend', content: newText }));

    // Show the edited message and set up streaming UI
    appendMessage('user', newText);
    const sendBtn = document.getElementById('send-btn');
    sendBtn.textContent = 'Stop';
    sendBtn.classList.add('stop-btn');
    sendBtn.onclick = stopGeneration;
    sendBtn.disabled = false;
    document.getElementById('message-input').disabled = true;
}
```

- [ ] **Step 4: Backend — add `delete_messages_after_last_user()` to `db.py`**

```python
def delete_messages_after_last_user(self, conversation_id: str) -> None:
    """Delete the last user message and all messages after it."""
    # Find the last user message
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
```

- [ ] **Step 5: Backend — handle edit_resend in `app.py`**

In the WebSocket handler, add a case for `edit_resend`:

```python
            if msg.get("type") == "edit_resend":
                new_content = msg.get("content", "")
                if not new_content.strip():
                    continue

                # Delete the last user message and everything after
                db.delete_messages_after_last_user(conv_id)

                # Add the edited message
                db.add_message(conv_id, "user", new_content)

                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in db.get_messages(conv_id)
                    if m["role"] in ("user", "assistant")
                ]

                full_response = ""
                cancel_event = asyncio.Event()
                ws._cancel_event = cancel_event

                async def on_token(token):
                    nonlocal full_response
                    full_response += token
                    await ws.send_text(json.dumps({"type": "token", "content": token}))

                async def on_tool_start(name, args):
                    await ws.send_text(json.dumps({"type": "tool_start", "name": name, "arguments": args}))

                async def on_tool_end(name, result):
                    await ws.send_text(json.dumps({"type": "tool_end", "name": name, "result": result}))

                result = await agent.run(history, on_token=on_token, on_tool_start=on_tool_start, on_tool_end=on_tool_end, cancel_event=cancel_event)
                final_content = result["content"] if result else full_response
                db.add_message(conv_id, "assistant", final_content, tool_calls=result.get("tool_calls") if result else None)
                await ws.send_text(json.dumps({"type": "done"}))
                continue
```

- [ ] **Step 6: Verify edit & resend works**

Send multiple messages. Edit an earlier user message, change text, click "Save & Resend". Verify:
- All messages after the edited one are removed
- New message appears with edited text
- Fresh response streams in
- Cancel button restores original message

- [ ] **Step 7: Commit**

```bash
git add chat/static/js/messages.js chat/static/js/controls.js chat/static/style.css chat/db.py chat/app.py
git commit -m "feat(chat): add edit and resend for user messages"
```

---

## Chunk 2: Keyboard Shortcuts, UI Polish & Token Stats

### Task 5: Keyboard Shortcuts

**Files:**
- Create: `chat/static/js/shortcuts.js`
- Modify: `chat/static/index.html` — add script tag
- Modify: `chat/static/style.css` — shortcuts help overlay

- [ ] **Step 1: Create `shortcuts.js`**

```javascript
/* Bonsai Chat — Keyboard shortcuts */

function initShortcuts() {
    document.addEventListener('keydown', handleShortcut);
}

function handleShortcut(e) {
    // Don't fire when typing in inputs (except Escape)
    const tag = document.activeElement?.tagName;
    const isTyping = tag === 'INPUT' || tag === 'TEXTAREA';

    // Escape — always works
    if (e.key === 'Escape') {
        e.preventDefault();
        closeAllOverlays();
        return;
    }

    if (isTyping) return;

    const mod = e.ctrlKey || e.metaKey;

    // Ctrl/Cmd+K — search conversations
    if (mod && e.key === 'k') {
        e.preventDefault();
        toggleSearchOverlay();
        return;
    }

    // Ctrl/Cmd+N — new chat
    if (mod && e.key === 'n') {
        e.preventDefault();
        createNewChat();
        return;
    }

    // Ctrl/Cmd+Shift+Backspace — delete current conversation
    if (mod && e.shiftKey && e.key === 'Backspace') {
        e.preventDefault();
        if (currentConvId && confirm('Delete this conversation?')) {
            deleteConversation(currentConvId);
        }
        return;
    }

    // ? or Ctrl+/ — show shortcuts help
    if (e.key === '?' || (mod && e.key === '/')) {
        e.preventDefault();
        toggleShortcutsHelp();
        return;
    }
}

// Up arrow in empty input — edit last message
// (handled separately since it fires inside textarea)
function handleInputKeyDown(event) {
    if (event.key === 'ArrowUp' && event.target.value === '') {
        event.preventDefault();
        const userMessages = document.querySelectorAll('.message.user');
        const lastUser = userMessages[userMessages.length - 1];
        if (lastUser) {
            const content = lastUser.querySelector('.message-content').textContent;
            editMessage(lastUser, content);
        }
        return;
    }
    handleKeyDown(event);
}

function closeAllOverlays() {
    // Close search
    const search = document.getElementById('search-overlay');
    if (search && !search.classList.contains('hidden')) {
        search.classList.add('hidden');
        return;
    }
    // Close shortcuts help
    const help = document.getElementById('shortcuts-help');
    if (help && !help.classList.contains('hidden')) {
        help.classList.add('hidden');
        return;
    }
    // Close settings
    const settings = document.getElementById('settings-modal');
    if (settings && !settings.classList.contains('hidden')) {
        settings.classList.add('hidden');
        return;
    }
}

function toggleShortcutsHelp() {
    document.getElementById('shortcuts-help').classList.toggle('hidden');
}

// Placeholder — search implemented in Task 7
function toggleSearchOverlay() {
    const overlay = document.getElementById('search-overlay');
    if (overlay) {
        overlay.classList.toggle('hidden');
        if (!overlay.classList.contains('hidden')) {
            overlay.querySelector('input')?.focus();
        }
    }
}

// Init on load
initShortcuts();
```

- [ ] **Step 2: Add shortcuts help overlay and search overlay HTML to `index.html`**

Add before the closing `</div>` of `#app`:

```html
        <!-- Search overlay -->
        <div id="search-overlay" class="overlay hidden">
            <div class="overlay-content search-content">
                <input type="text" id="search-input" placeholder="Search conversations..." oninput="handleSearch(this.value)">
                <div id="search-results"></div>
            </div>
        </div>

        <!-- Shortcuts help -->
        <div id="shortcuts-help" class="modal hidden">
            <div class="modal-content" style="width:340px">
                <h2>Keyboard Shortcuts</h2>
                <div class="shortcut-list">
                    <div class="shortcut-row"><kbd>Ctrl+K</kbd><span>Search conversations</span></div>
                    <div class="shortcut-row"><kbd>Ctrl+N</kbd><span>New chat</span></div>
                    <div class="shortcut-row"><kbd>Ctrl+Shift+&larr;</kbd><span>Delete conversation</span></div>
                    <div class="shortcut-row"><kbd>Escape</kbd><span>Close overlay</span></div>
                    <div class="shortcut-row"><kbd>&uarr;</kbd><span>Edit last message</span></div>
                    <div class="shortcut-row"><kbd>?</kbd><span>Show this help</span></div>
                </div>
                <div class="modal-actions"><button onclick="toggleShortcutsHelp()" class="secondary">Close</button></div>
            </div>
        </div>
```

Update textarea `onkeydown` to use `handleInputKeyDown`:

```html
<textarea id="message-input" placeholder="Message Bonsai..." rows="1"
    onkeydown="handleInputKeyDown(event)"></textarea>
```

- [ ] **Step 3: Add styles for overlays, shortcuts help**

```css
/* ── Overlays ── */
.overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 100;
    display: flex;
    justify-content: center;
    padding-top: 80px;
}
.overlay.hidden { display: none; }
.overlay-content {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    width: 500px;
    max-height: 400px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    animation: slideDown 0.15s ease-out;
}
@keyframes slideDown {
    from { transform: translateY(-10px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
}
.search-content input {
    width: 100%;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--border);
    padding: 14px 16px;
    color: var(--text-primary);
    font-size: 15px;
    outline: none;
}
#search-results {
    overflow-y: auto;
    flex: 1;
}
.search-result {
    padding: 10px 16px;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
}
.search-result:hover { background: var(--bg-tertiary); }
.search-result .search-title { font-size: 13px; font-weight: 600; }
.search-result .search-snippet { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.search-result mark { background: var(--accent-blue-bg); color: var(--accent-blue); }

/* Shortcuts help */
.shortcut-list { margin-bottom: 12px; }
.shortcut-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    font-size: 13px;
}
.shortcut-row kbd {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-family: monospace;
}
```

- [ ] **Step 4: Add `shortcuts.js` script tag to `index.html`**

```html
    <script src="/js/shortcuts.js?v=6"></script>
```

Place before `core.js` in the script load order.

- [ ] **Step 5: Verify shortcuts work**

Test: Ctrl+N creates new chat, Ctrl+K opens search (empty for now), Escape closes overlays, ? shows help, Up arrow in empty input edits last message.

- [ ] **Step 6: Commit**

```bash
git add chat/static/js/shortcuts.js chat/static/index.html chat/static/style.css
git commit -m "feat(chat): add keyboard shortcuts and help overlay"
```

---

### Task 6: UI Polish & Animations

**Files:**
- Modify: `chat/static/style.css` — animations, transitions, skeleton loading

- [ ] **Step 1: Add message animations**

```css
/* ── Animations ── */
.message {
    animation: fadeIn 0.15s ease-out;
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Modal animations */
.modal:not(.hidden) .modal-content {
    animation: modalIn 0.15s ease-out;
}
@keyframes modalIn {
    from { opacity: 0; transform: scale(0.95); }
    to { opacity: 1; transform: scale(1); }
}

/* Skeleton loading (shown before first token) */
.skeleton {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
    max-width: 60%;
}
.skeleton-lines {
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
}
.skeleton-line {
    height: 14px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    animation: shimmer 1.5s infinite;
}
.skeleton-line:nth-child(1) { width: 80%; }
.skeleton-line:nth-child(2) { width: 60%; }
.skeleton-line:nth-child(3) { width: 70%; }
@keyframes shimmer {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.8; }
}

/* Tool pill transitions */
.tool-detail {
    transition: max-height 0.2s ease-out, padding 0.2s ease-out;
}

/* Sidebar items */
.conv-item {
    transition: background 0.1s, color 0.1s;
}
```

- [ ] **Step 2: Add skeleton loading to message streaming**

In `core.js`, when a new assistant message starts (in the `token` case), show a skeleton first then replace it on the first token. Modify the `token` handler:

```javascript
        case 'token':
            if (!currentAssistantEl) {
                // Show skeleton first
                currentAssistantEl = createSkeleton();
                currentAssistantText = '';
            }
            // Replace skeleton with real content on first token
            if (currentAssistantEl.classList.contains('skeleton')) {
                const realMsg = appendMessage('assistant', '');
                currentAssistantEl.remove();
                currentAssistantEl = realMsg;
            }
            currentAssistantText += data.content;
            const contentEl = currentAssistantEl.querySelector('.message-content');
            contentEl.innerHTML = marked.parse(preprocessMarkdown(currentAssistantText));
            enhanceCodeBlocks(contentEl);
            scrollToBottom();
            break;
```

Add `createSkeleton()` to `messages.js`:

```javascript
function createSkeleton() {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'skeleton';
    div.innerHTML = `
        <div class="avatar bot-avatar">&#127793;</div>
        <div class="skeleton-lines">
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
        </div>
    `;
    messages.appendChild(div);
    scrollToBottom();
    return div;
}
```

- [ ] **Step 3: Use smooth scroll**

In `core.js`, update `scrollToBottom()`:

```javascript
function scrollToBottom() {
    const messages = document.getElementById('messages');
    const lastChild = messages.lastElementChild;
    if (lastChild) {
        lastChild.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
}
```

- [ ] **Step 4: Verify animations**

Open app, send message. Verify: skeleton appears briefly, message fades in, modals animate, scroll is smooth.

- [ ] **Step 5: Commit**

```bash
git add chat/static/style.css chat/static/js/core.js chat/static/js/messages.js
git commit -m "feat(chat): add UI animations, skeleton loading, smooth scroll"
```

---

### Task 7: Conversation Search

**Files:**
- Modify: `chat/static/js/conversations.js` — search handler
- Modify: `chat/db.py` — `search_conversations()` method
- Modify: `chat/app.py` — search endpoint

- [ ] **Step 1: Add `search_conversations()` to `db.py`**

```python
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
```

- [ ] **Step 2: Add search endpoint to `app.py`**

```python
@app.get("/api/conversations/search")
async def search_conversations(q: str = ""):
    if not q.strip():
        return []
    return db.search_conversations(q)
```

Note: this endpoint must be defined BEFORE the `/{conv_id}` routes to avoid path conflicts.

- [ ] **Step 3: Add `handleSearch()` to `conversations.js`**

```javascript
let searchDebounce = null;

async function handleSearch(query) {
    clearTimeout(searchDebounce);
    if (!query.trim()) {
        document.getElementById('search-results').innerHTML = '<p class="empty-state" style="padding:16px">Type to search...</p>';
        return;
    }
    searchDebounce = setTimeout(async () => {
        const resp = await fetch(`/api/conversations/search?q=${encodeURIComponent(query)}`);
        const results = await resp.json();
        const container = document.getElementById('search-results');
        if (results.length === 0) {
            container.innerHTML = '<p class="empty-state" style="padding:16px">No results found</p>';
            return;
        }
        container.innerHTML = results.map(r => {
            const highlighted = r.snippet.replace(
                new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
                '<mark>$1</mark>'
            );
            return `<div class="search-result" onclick="openConversation('${r.id}'); closeAllOverlays();">
                <div class="search-title">${escapeHtml(r.title)}</div>
                <div class="search-snippet">${highlighted}</div>
            </div>`;
        }).join('');
    }, 200);
}
```

- [ ] **Step 4: Verify search works**

Press Ctrl+K, type a query. Verify: results show matching conversations with highlighted snippets. Click a result opens that conversation. Escape closes.

- [ ] **Step 5: Commit**

```bash
git add chat/static/js/conversations.js chat/db.py chat/app.py
git commit -m "feat(chat): add conversation search (Ctrl+K)"
```

---

### Task 8: Token & Performance Stats

**Files:**
- Create: `chat/static/js/stats.js`
- Modify: `chat/static/js/core.js` — track token timing
- Modify: `chat/static/index.html` — add script tag
- Modify: `chat/static/style.css` — stats display

- [ ] **Step 1: Create `stats.js`**

```javascript
/* Bonsai Chat — Token & performance stats */

let streamStartTime = 0;
let tokenCount = 0;

function resetStreamStats() {
    streamStartTime = 0;
    tokenCount = 0;
}

function trackToken() {
    if (tokenCount === 0) {
        streamStartTime = performance.now();
    }
    tokenCount++;
}

function getStreamStats() {
    if (tokenCount === 0) return null;
    const elapsed = (performance.now() - streamStartTime) / 1000;
    const tokPerSec = elapsed > 0 ? (tokenCount / elapsed).toFixed(1) : '0';
    return {
        tokens: tokenCount,
        elapsed: elapsed.toFixed(1),
        tokPerSec: tokPerSec,
    };
}

function renderStats(messageEl) {
    const stats = getStreamStats();
    if (!stats || !messageEl) return;

    const statsEl = document.createElement('div');
    statsEl.className = 'message-stats';
    statsEl.textContent = `${stats.tokens} tokens \u00b7 ${stats.tokPerSec} tok/s \u00b7 ${stats.elapsed}s`;

    // Insert after the message
    messageEl.parentElement.insertBefore(statsEl, messageEl.nextSibling);
}
```

- [ ] **Step 2: Wire stats tracking into `core.js`**

In the `token` case of `handleWSMessage()`, call `trackToken()`:

```javascript
        case 'token':
            trackToken();  // <-- add this line
            // ... rest of existing token handling ...
```

In the `done` case, render stats and reset:

```javascript
        case 'done':
            // ... existing final render pass ...
            if (currentAssistantEl) {
                renderStats(currentAssistantEl);
            }
            resetStreamStats();
            // ... rest of existing done handling ...
```

Also call `resetStreamStats()` in `sendMessageText()` before sending.

- [ ] **Step 3: Add stats styles**

```css
.message-stats {
    font-size: 11px;
    color: var(--text-muted);
    margin: 2px 0 12px 40px;
}
```

- [ ] **Step 4: Add script tag to `index.html`**

```html
    <script src="/js/stats.js?v=6"></script>
```

Place before `core.js`.

- [ ] **Step 5: Verify stats display**

Send a message, wait for response to complete. Verify: stats line appears below the response (e.g., "127 tokens · 18.3 tok/s · 6.9s").

- [ ] **Step 6: Commit**

```bash
git add chat/static/js/stats.js chat/static/js/core.js chat/static/index.html chat/static/style.css
git commit -m "feat(chat): add token count and performance stats"
```

---

## Chunk 3: File Uploads, LaTeX, Conversation Export

### Task 9: File Uploads

**Files:**
- Create: `chat/static/js/uploads.js`
- Modify: `chat/static/index.html` — attach button, drop zone, script tag
- Modify: `chat/static/style.css` — upload UI styles
- Modify: `chat/app.py` — upload endpoint
- Modify: `chat/db.py` — attachments column migration

- [ ] **Step 1: Add attachments column to DB**

In `db.py`, update `_init_tables()` to add the column if missing:

```python
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
        # Add attachments column if missing
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        self.conn.commit()
```

- [ ] **Step 2: Add upload endpoint to `app.py`**

```python
from fastapi import UploadFile, File as FastAPIFile
import shutil

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
```

Add required imports at top of `app.py`:

```python
import uuid
from chat.config import SANDBOX_DIR
```

- [ ] **Step 3: Create `uploads.js`**

```javascript
/* Bonsai Chat — File uploads: drag-drop, attach button */

let pendingAttachments = [];

function initUploads() {
    const chatArea = document.getElementById('chat-area');

    // Drag-drop zone
    chatArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        chatArea.classList.add('drag-over');
    });
    chatArea.addEventListener('dragleave', () => {
        chatArea.classList.remove('drag-over');
    });
    chatArea.addEventListener('drop', async (e) => {
        e.preventDefault();
        chatArea.classList.remove('drag-over');
        for (const file of e.dataTransfer.files) {
            await uploadFile(file);
        }
    });
}

async function triggerFileAttach() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.py,.js,.ts,.json,.csv,.md,.html,.css,.png,.jpg,.jpeg,.gif,.webp';
    input.multiple = true;
    input.onchange = async () => {
        for (const file of input.files) {
            await uploadFile(file);
        }
    };
    input.click();
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/upload', { method: 'POST', body: formData });
        const result = await resp.json();
        pendingAttachments.push(result);
        renderAttachmentPreview();
    } catch (e) {
        console.error('Upload failed:', e);
    }
}

function renderAttachmentPreview() {
    let preview = document.getElementById('attachment-preview');
    if (!preview) {
        preview = document.createElement('div');
        preview.id = 'attachment-preview';
        const inputContainer = document.querySelector('.input-container');
        inputContainer.insertBefore(preview, inputContainer.firstChild);
    }

    preview.innerHTML = pendingAttachments.map((att, i) => {
        if (att.type === 'image') {
            return `<div class="attachment-chip">
                <img src="/api/upload/${att.id}${att.filename.substring(att.filename.lastIndexOf('.'))}" alt="${att.filename}" class="attachment-thumb">
                <span>${att.filename}</span>
                <button onclick="removeAttachment(${i})">&times;</button>
            </div>`;
        }
        return `<div class="attachment-chip">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>${att.filename}</span>
            <button onclick="removeAttachment(${i})">&times;</button>
        </div>`;
    }).join('');
}

function removeAttachment(index) {
    pendingAttachments.splice(index, 1);
    renderAttachmentPreview();
}

function getAttachmentContext() {
    // Build text to prepend to user message with file contents
    if (pendingAttachments.length === 0) return '';
    let context = '';
    for (const att of pendingAttachments) {
        if (att.type === 'text' && att.content) {
            const ext = att.filename.split('.').pop();
            context += `\u{1F4CE} ${att.filename}\n\`\`\`${ext}\n${att.content}\n\`\`\`\n\n`;
        } else if (att.type === 'image') {
            context += `\u{1F4CE} ${att.filename} (image attached \u2014 model cannot analyze images with current model)\n\n`;
        }
    }
    return context;
}

function clearAttachments() {
    pendingAttachments = [];
    const preview = document.getElementById('attachment-preview');
    if (preview) preview.innerHTML = '';
}

initUploads();
```

- [ ] **Step 4: Update `core.js` `sendMessageText()` to include attachments**

```javascript
function sendMessageText(text) {
    const attachmentContext = getAttachmentContext();
    const fullContent = attachmentContext ? attachmentContext + text : text;

    appendMessage('user', text);  // Show user's text only in UI
    // ... rest of existing function, but send fullContent to WS:
    ws.send(JSON.stringify({ content: fullContent }));
    clearAttachments();
    // ...
}
```

- [ ] **Step 5: Add attach button to `index.html`**

In the input-container, before the textarea:

```html
<div class="input-row">
    <button class="attach-btn" onclick="triggerFileAttach()" title="Attach file">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
    </button>
    <textarea id="message-input" placeholder="Message Bonsai..." rows="1"
        onkeydown="handleInputKeyDown(event)"></textarea>
</div>
```

- [ ] **Step 6: Add upload styles**

```css
/* File uploads */
.input-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
}
.input-row textarea { flex: 1; }
.attach-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    margin-top: 2px;
    flex-shrink: 0;
}
.attach-btn:hover { color: var(--text-secondary); }

#attachment-preview {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
}
.attachment-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}
.attachment-chip button {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 14px;
}
.attachment-chip button:hover { color: var(--text-primary); }
.attachment-thumb {
    width: 24px;
    height: 24px;
    border-radius: 3px;
    object-fit: cover;
}

/* Drag-drop zone */
#chat-area.drag-over::after {
    content: 'Drop file here';
    position: absolute;
    inset: 0;
    background: rgba(88, 166, 255, 0.08);
    border: 2px dashed var(--accent-blue);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: var(--accent-blue);
    z-index: 50;
    border-radius: 8px;
    margin: 8px;
}
#chat-area { position: relative; }
```

- [ ] **Step 7: Add script tag and verify**

Add `<script src="/js/uploads.js?v=6"></script>` to `index.html`. Verify: attach button works, drag-drop works, file chips appear, text file contents are sent with message.

- [ ] **Step 8: Commit**

```bash
git add chat/static/js/uploads.js chat/static/index.html chat/static/style.css chat/app.py chat/db.py
git commit -m "feat(chat): add file upload with drag-drop and attach button"
```

---

### Task 10: LaTeX Math Rendering

**Files:**
- Modify: `chat/static/index.html` — add KaTeX CDN
- Modify: `chat/static/js/messages.js` — LaTeX preprocessing
- Modify: `chat/static/style.css` — KaTeX overrides

- [ ] **Step 1: Add KaTeX CDN to `index.html`**

In `<head>`, after highlight.js:

```html
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css">
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"></script>
    <script>
        if (typeof katex === 'undefined') {
            window.katex = { renderToString: function(tex) { return '<code>' + tex + '</code>'; } };
        }
    </script>
```

- [ ] **Step 2: Add LaTeX rendering to `messages.js`**

Add a `renderLatex()` function called after `marked.parse()` but before DOM insertion. Process both block `$$...$$` and inline `$...$`:

```javascript
function renderLatex(html) {
    // Block math: $$...$$
    html = html.replace(/\$\$([\s\S]+?)\$\$/g, (match, tex) => {
        try {
            return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
        } catch (e) {
            return `<code class="latex-error" title="LaTeX parse error">${escapeHtml(tex)}</code>`;
        }
    });

    // Inline math: $...$ (no space after opening, no space before closing — avoids currency)
    html = html.replace(/\$(\S(?:[^$]*?\S)?)\$/g, (match, tex) => {
        // Skip if inside a code block
        if (match.includes('<code>') || match.includes('</code>')) return match;
        try {
            return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false });
        } catch (e) {
            return `<code class="latex-error" title="LaTeX parse error">${escapeHtml(tex)}</code>`;
        }
    });

    return html;
}
```

Update all places where `marked.parse()` is called to also call `renderLatex()`:

In `appendMessage()`:
```javascript
marked.parse(preprocessMarkdown(content))
// becomes:
renderLatex(marked.parse(preprocessMarkdown(content)))
```

Same in `handleWSMessage()` token and done cases in `core.js`.

- [ ] **Step 3: Add LaTeX error styles**

```css
/* LaTeX */
.latex-error {
    color: var(--accent-orange);
    background: var(--accent-orange-bg);
    padding: 2px 6px;
    border-radius: 3px;
}
.katex-display {
    margin: 12px 0;
    overflow-x: auto;
}
```

- [ ] **Step 4: Verify LaTeX rendering**

Send a message with `$E = mc^2$` and `$$\int_0^1 x^2 dx = \frac{1}{3}$$`. Verify: inline and block math render properly. Malformed LaTeX shows as orange code.

- [ ] **Step 5: Commit**

```bash
git add chat/static/index.html chat/static/js/messages.js chat/static/js/core.js chat/static/style.css
git commit -m "feat(chat): add LaTeX math rendering with KaTeX"
```

---

### Task 11: Conversation Export & Sidebar Menu

**Files:**
- Modify: `chat/static/js/conversations.js` — three-dot menu, export, inline rename, pin
- Modify: `chat/app.py` — export endpoint
- Modify: `chat/db.py` — pinned column, update title
- Modify: `chat/static/style.css` — menu styles

- [ ] **Step 1: Add pinned column to DB**

In `db.py` `_init_tables()`, add migration:

```python
        try:
            self.conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
```

Add methods:

```python
def toggle_pin(self, conversation_id: str) -> bool:
    row = self.conn.execute("SELECT pinned FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    new_val = 0 if row and row["pinned"] else 1
    self.conn.execute("UPDATE conversations SET pinned = ? WHERE id = ?", (new_val, conversation_id))
    self.conn.commit()
    return bool(new_val)
```

Update `list_conversations()` to sort pinned first:

```python
def list_conversations(self) -> list[dict]:
    rows = self.conn.execute(
        "SELECT * FROM conversations ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Add export endpoint to `app.py`**

```python
from fastapi.responses import PlainTextResponse, JSONResponse

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
```

Add pin toggle endpoint:

```python
@app.post("/api/conversations/{conv_id}/pin")
async def toggle_pin(conv_id: str):
    pinned = db.toggle_pin(conv_id)
    return {"pinned": pinned}
```

- [ ] **Step 3: Update `renderConversationList()` in `conversations.js`**

Add three-dot menu, pin indicator, inline rename, and pinned group:

```javascript
function renderConversationList() {
    const list = document.getElementById('conversation-list');
    if (conversations.length === 0) {
        list.innerHTML = '<p class="empty-state" style="padding:10px">No conversations yet</p>';
        return;
    }

    const now = new Date();
    const today = now.toDateString();
    const yesterday = new Date(now - 86400000).toDateString();

    // Separate pinned and unpinned
    const pinned = conversations.filter(c => c.pinned);
    const unpinned = conversations.filter(c => !c.pinned);

    let html = '';

    if (pinned.length > 0) {
        html += '<div class="conv-group-label">Pinned</div>';
        for (const conv of pinned) {
            html += renderConvItem(conv);
        }
    }

    let lastGroup = '';
    for (const conv of unpinned) {
        const date = new Date(conv.updated_at).toDateString();
        let group = date === today ? 'Today' : date === yesterday ? 'Yesterday' : date;
        if (group !== lastGroup) {
            html += `<div class="conv-group-label">${group}</div>`;
            lastGroup = group;
        }
        html += renderConvItem(conv);
    }
    list.innerHTML = html;
}

function renderConvItem(conv) {
    const active = conv.id === currentConvId ? ' active' : '';
    const pinIcon = conv.pinned ? '<span class="pin-icon" title="Pinned">&#128204;</span>' : '';
    return `<div class="conv-item${active}" onclick="openConversation('${conv.id}')" title="${conv.title}" ondblclick="startInlineRename('${conv.id}', this)">
        ${pinIcon}<span class="conv-title">${conv.title}</span>
        <button class="conv-menu-btn" onclick="event.stopPropagation(); toggleConvMenu('${conv.id}', this)">&#8942;</button>
    </div>`;
}

function toggleConvMenu(convId, btn) {
    // Close any existing menu
    document.querySelectorAll('.conv-menu').forEach(m => m.remove());

    const menu = document.createElement('div');
    menu.className = 'conv-menu';
    menu.innerHTML = `
        <button onclick="pinConversation('${convId}')">&#128204; Pin/Unpin</button>
        <button onclick="exportConversation('${convId}', 'markdown')">&#128196; Export Markdown</button>
        <button onclick="exportConversation('${convId}', 'json')">&#128196; Export JSON</button>
        <button onclick="startInlineRename('${convId}')">&#9998; Rename</button>
        <button onclick="deleteConversation('${convId}')" style="color:#f85149">&#128465; Delete</button>
    `;
    btn.parentElement.appendChild(menu);

    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function closeMenu() {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        }, { once: true });
    }, 0);
}

async function pinConversation(convId) {
    await fetch(`/api/conversations/${convId}/pin`, { method: 'POST' });
    await loadConversations();
}

async function exportConversation(convId, format) {
    const resp = await fetch(`/api/conversations/${convId}/export?format=${format}`);
    const blob = await resp.blob();
    const ext = format === 'json' ? '.json' : '.md';
    const conv = conversations.find(c => c.id === convId);
    const filename = (conv?.title || 'conversation') + ext;

    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
}

function startInlineRename(convId, el) {
    const item = el || document.querySelector(`.conv-item[onclick*="${convId}"]`);
    if (!item) return;
    const titleSpan = item.querySelector('.conv-title');
    const currentTitle = titleSpan.textContent;

    const input = document.createElement('input');
    input.className = 'inline-rename-input';
    input.value = currentTitle;
    input.onclick = (e) => e.stopPropagation();
    input.onkeydown = async (e) => {
        if (e.key === 'Enter') {
            await fetch(`/api/conversations/${convId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: input.value }),
            });
            await loadConversations();
        } else if (e.key === 'Escape') {
            await loadConversations();
        }
    };
    input.onblur = () => loadConversations();

    titleSpan.replaceWith(input);
    input.focus();
    input.select();
}
```

- [ ] **Step 4: Add conversation menu styles**

```css
/* Conversation item menu */
.conv-item {
    display: flex;
    align-items: center;
    position: relative;
}
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.pin-icon { font-size: 10px; margin-right: 4px; flex-shrink: 0; }
.conv-menu-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0 2px;
    font-size: 14px;
    opacity: 0;
    flex-shrink: 0;
}
.conv-item:hover .conv-menu-btn { opacity: 1; }
.conv-menu {
    position: absolute;
    right: 0;
    top: 100%;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px;
    z-index: 50;
    min-width: 160px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.conv-menu button {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    color: var(--text-secondary);
    padding: 6px 10px;
    font-size: 12px;
    cursor: pointer;
    border-radius: 4px;
}
.conv-menu button:hover { background: var(--bg-secondary); color: var(--text-primary); }
.inline-rename-input {
    background: var(--bg-primary);
    border: 1px solid var(--accent-blue);
    border-radius: 4px;
    padding: 4px 8px;
    color: var(--text-primary);
    font-size: 13px;
    width: 100%;
    outline: none;
}
```

- [ ] **Step 5: Verify export, pin, rename**

Right-click three-dot menu on a conversation. Verify: pin/unpin works and moves to top, export downloads a file, rename edits inline, delete still works.

- [ ] **Step 6: Commit**

```bash
git add chat/static/js/conversations.js chat/static/style.css chat/db.py chat/app.py
git commit -m "feat(chat): add conversation export, pin, rename, and context menu"
```

---

## Chunk 4: Memory, Model Switching, Voice Input, Settings

### Task 12: Memory & Custom Instructions

**Files:**
- Create: `chat/static/js/memory.js`
- Modify: `chat/db.py` — memories table, system_prompt column
- Modify: `chat/app.py` — memory endpoints, system prompt in agent
- Modify: `chat/agent.py` — accept custom system prompt prefix
- Modify: `chat/static/index.html` — memory UI, brain icon, script tag
- Modify: `chat/static/style.css` — memory modal styles

- [ ] **Step 1: Add memories table and system_prompt column to DB**

In `db.py` `_init_tables()`:

```python
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        try:
            self.conn.execute("ALTER TABLE conversations ADD COLUMN system_prompt TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
```

Add memory CRUD methods:

```python
def add_memory(self, content: str) -> dict:
    mid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    self.conn.execute("INSERT INTO memories (id, content, created_at) VALUES (?, ?, ?)", (mid, content, now))
    # Auto-prune to 20
    self.conn.execute("""
        DELETE FROM memories WHERE id NOT IN (
            SELECT id FROM memories ORDER BY created_at DESC LIMIT 20
        )
    """)
    self.conn.commit()
    return {"id": mid, "content": content, "created_at": now}

def list_memories(self) -> list[dict]:
    rows = self.conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()
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
```

- [ ] **Step 2: Add memory endpoints to `app.py`**

```python
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
```

- [ ] **Step 3: Update `agent.py` to accept custom context**

Add `custom_context` parameter to `run()`:

```python
async def run(self, messages, on_token=None, on_tool_start=None, on_tool_end=None, cancel_event=None, custom_context=""):
    system_prompt = self._build_system_prompt()
    if custom_context:
        system_prompt = custom_context + "\n\n" + system_prompt
    # ... rest unchanged ...
```

- [ ] **Step 4: Update `app.py` WebSocket handler to pass memory + system prompt**

In the WebSocket handler, before calling `agent.run()`, build the custom context:

```python
            # Build custom context from memories + conversation system prompt
            memories = db.list_memories()
            conv_system_prompt = db.get_system_prompt(conv_id)
            custom_context = ""
            if memories:
                custom_context += "Things you know about the user:\n"
                custom_context += "\n".join(f"- {m['content']}" for m in memories)
                custom_context += "\n\n"
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
```

- [ ] **Step 5: Create `memory.js`**

```javascript
/* Bonsai Chat — Memory: custom instructions, cross-conversation memory */

function toggleSystemPrompt() {
    document.getElementById('system-prompt-modal').classList.toggle('hidden');
    if (!document.getElementById('system-prompt-modal').classList.contains('hidden')) {
        loadSystemPrompt();
    }
}

async function loadSystemPrompt() {
    if (!currentConvId) return;
    const resp = await fetch(`/api/conversations/${currentConvId}/system-prompt`);
    const data = await resp.json();
    document.getElementById('system-prompt-input').value = data.system_prompt || '';
}

async function saveSystemPrompt() {
    if (!currentConvId) return;
    const prompt = document.getElementById('system-prompt-input').value;
    await fetch(`/api/conversations/${currentConvId}/system-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_prompt: prompt }),
    });
    toggleSystemPrompt();
}

async function saveMemory(prefill) {
    const content = prompt('What should I remember?', prefill || '');
    if (!content) return;
    await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
    });
}
```

- [ ] **Step 6: Add memory UI to `index.html`**

Add brain icon button in the input footer:

```html
<span class="input-actions">
    <button class="icon-btn" onclick="toggleSystemPrompt()" title="System prompt">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a9 9 0 0 0-9 9c0 3.6 2.4 6.6 5.5 7.7.3.1.5-.1.5-.4v-1.5c-2.2.5-2.7-1-2.7-1-.4-.9-.9-1.1-.9-1.1-.7-.5.1-.5.1-.5.8.1 1.2.8 1.2.8.7 1.2 1.9.9 2.3.7.1-.5.3-.9.5-1.1-1.8-.2-3.7-.9-3.7-4 0-.9.3-1.6.8-2.2-.1-.2-.4-1 .1-2.1 0 0 .7-.2 2.2.8.6-.2 1.3-.3 2-.3s1.4.1 2 .3c1.5-1 2.2-.8 2.2-.8.4 1.1.2 1.9.1 2.1.5.6.8 1.3.8 2.2 0 3.1-1.9 3.8-3.7 4 .3.3.6.8.6 1.6v2.4c0 .3.2.5.5.4A9 9 0 0 0 12 2z"/></svg>
    </button>
</span>
```

Add system prompt modal:

```html
<div id="system-prompt-modal" class="modal hidden">
    <div class="modal-content">
        <h2>System Prompt</h2>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Custom instructions for this conversation</p>
        <textarea id="system-prompt-input" rows="6" style="width:100%;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;padding:10px;color:var(--text-primary);font-size:13px;resize:vertical;outline:none" placeholder="e.g., Always respond in Python code..."></textarea>
        <div class="modal-actions">
            <button onclick="saveSystemPrompt()">Save</button>
            <button onclick="toggleSystemPrompt()" class="secondary">Cancel</button>
        </div>
    </div>
</div>
```

Add "Save to Memory" button to assistant message actions in `messages.js`:

```html
<button class="message-action-btn" onclick="saveMemory(this.closest('.message-actions').previousElementSibling.querySelector('.message-content').textContent.substring(0, 100))" title="Save to Memory">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
    Remember
</button>
```

- [ ] **Step 7: Add script tag and verify**

Add `<script src="/js/memory.js?v=6"></script>` to `index.html`. Verify: brain icon opens system prompt modal, save works, "Remember" button on assistant messages saves memory, memories affect future responses.

- [ ] **Step 8: Commit**

```bash
git add chat/static/js/memory.js chat/static/index.html chat/static/style.css chat/db.py chat/app.py chat/agent.py
git commit -m "feat(chat): add memory system and per-conversation system prompts"
```

---

### Task 13: Model Switching

**Files:**
- Modify: `chat/static/js/settings.js` — model selector dropdown
- Modify: `chat/app.py` — models endpoint
- Modify: `chat/config.py` — models directory scanning
- Modify: `chat/static/index.html` — model selector in input footer
- Modify: `chat/static/style.css` — dropdown styles

- [ ] **Step 1: Add model scanning to `config.py`**

```python
MODELS_DIR = Path(os.environ.get("BONSAI_MODELS_DIR", DEMO_DIR / "models" / "gguf"))

def list_available_models() -> list[dict]:
    """Scan models directory for available .gguf models."""
    models = []
    if MODELS_DIR.exists():
        for model_dir in sorted(MODELS_DIR.iterdir()):
            if model_dir.is_dir():
                gguf_files = list(model_dir.glob("*.gguf"))
                if gguf_files:
                    models.append({
                        "id": model_dir.name,
                        "name": f"Bonsai {model_dir.name}",
                        "path": str(gguf_files[0]),
                    })
    if not models:
        models.append({"id": BONSAI_MODEL, "name": f"Bonsai {BONSAI_MODEL}", "path": ""})
    return models
```

- [ ] **Step 2: Add models endpoint to `app.py`**

```python
from chat.config import list_available_models

@app.get("/api/models")
async def get_models():
    return list_available_models()
```

- [ ] **Step 3: Update model selector in `settings.js`**

```javascript
async function loadModelSelector() {
    try {
        const resp = await fetch('/api/models');
        const models = await resp.json();
        const label = document.getElementById('model-label');
        const currentModel = localStorage.getItem('bonsai-model') || models[0]?.id;

        if (models.length <= 1) {
            label.textContent = models[0]?.name || 'Bonsai 8B';
            return;
        }

        // Replace label with dropdown
        const select = document.createElement('select');
        select.id = 'model-selector';
        select.className = 'model-selector';
        for (const m of models) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            if (m.id === currentModel) opt.selected = true;
            select.appendChild(opt);
        }
        select.onchange = () => {
            localStorage.setItem('bonsai-model', select.value);
        };
        label.replaceWith(select);
    } catch (e) {}
}
```

Call `loadModelSelector()` from `init()` in `core.js`.

- [ ] **Step 4: Add model selector styles**

```css
.model-selector {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-muted);
    font-size: 12px;
    padding: 2px 6px;
    outline: none;
    cursor: pointer;
}
.model-selector:hover { border-color: var(--text-muted); }
```

- [ ] **Step 5: Verify model selector**

Open app. If multiple model dirs exist under `models/gguf/`, a dropdown appears. Selection persists across page reloads via localStorage.

- [ ] **Step 6: Commit**

```bash
git add chat/static/js/settings.js chat/static/style.css chat/config.py chat/app.py chat/static/js/core.js
git commit -m "feat(chat): add model switching dropdown"
```

---

### Task 14: Voice Input

**Files:**
- Create: `chat/static/js/voice.js`
- Modify: `chat/static/index.html` — mic button, script tag
- Modify: `chat/static/style.css` — mic button styles

- [ ] **Step 1: Create `voice.js`**

```javascript
/* Bonsai Chat — Voice input via Web Speech API */

let recognition = null;
let isListening = false;

function initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        // Browser doesn't support — hide mic button
        const micBtn = document.getElementById('mic-btn');
        if (micBtn) micBtn.style.display = 'none';
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
        const input = document.getElementById('message-input');
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        // Replace from the point where we started listening
        input.value = input.dataset.preVoice + transcript;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    };

    recognition.onend = () => {
        if (isListening) {
            // Stopped unexpectedly — update UI
            stopListening();
        }
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopListening();
    };
}

function toggleVoice() {
    if (isListening) {
        stopListening();
    } else {
        startListening();
    }
}

function startListening() {
    if (!recognition) return;
    const input = document.getElementById('message-input');
    input.dataset.preVoice = input.value;  // Preserve existing text
    isListening = true;
    const btn = document.getElementById('mic-btn');
    btn.classList.add('listening');
    recognition.start();
}

function stopListening() {
    if (!recognition) return;
    isListening = false;
    const btn = document.getElementById('mic-btn');
    btn.classList.remove('listening');
    recognition.stop();
}

initVoice();
```

- [ ] **Step 2: Add mic button to `index.html`**

In the input footer, between the model label and send button, add:

```html
<div class="input-actions-right">
    <button id="mic-btn" class="icon-btn" onclick="toggleVoice()" title="Voice input">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
    </button>
    <button id="send-btn" onclick="sendMessage()">Send</button>
</div>
```

- [ ] **Step 3: Add mic button styles**

```css
.icon-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
}
.icon-btn:hover { color: var(--text-secondary); }

#mic-btn.listening {
    color: #da3633;
    animation: pulse 1.5s infinite;
}
.input-actions-right {
    display: flex;
    align-items: center;
    gap: 6px;
}
```

- [ ] **Step 4: Add script tag**

```html
    <script src="/js/voice.js?v=6"></script>
```

- [ ] **Step 5: Verify voice input**

Click mic button (in Chrome/Edge). Speak. Verify: text appears in textarea, mic button turns red while listening, click again to stop. In Firefox/Safari: mic button is hidden.

- [ ] **Step 6: Commit**

```bash
git add chat/static/js/voice.js chat/static/index.html chat/static/style.css
git commit -m "feat(chat): add voice input via Web Speech API"
```

---

### Task 15: Settings Redesign — Tabbed Modal

**Files:**
- Modify: `chat/static/js/settings.js` — tabbed settings with memory tab
- Modify: `chat/static/index.html` — updated settings modal HTML
- Modify: `chat/static/style.css` — tab styles

- [ ] **Step 1: Update settings modal HTML in `index.html`**

Replace the existing settings modal:

```html
<div id="settings-modal" class="modal hidden">
    <div class="modal-content" style="width:480px">
        <h2>Settings</h2>
        <div class="settings-tabs">
            <button class="tab-btn active" onclick="switchSettingsTab('general', this)">General</button>
            <button class="tab-btn" onclick="switchSettingsTab('memory', this)">Memory</button>
            <button class="tab-btn" onclick="switchSettingsTab('shortcuts', this)">Shortcuts</button>
        </div>

        <div id="tab-general" class="tab-content">
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
        </div>

        <div id="tab-memory" class="tab-content" style="display:none">
            <div id="memory-list"></div>
            <button class="secondary" style="margin-top:8px;font-size:12px" onclick="clearAllMemories()">Clear All Memories</button>
        </div>

        <div id="tab-shortcuts" class="tab-content" style="display:none">
            <div class="shortcut-list">
                <div class="shortcut-row"><kbd>Ctrl+K</kbd><span>Search conversations</span></div>
                <div class="shortcut-row"><kbd>Ctrl+N</kbd><span>New chat</span></div>
                <div class="shortcut-row"><kbd>Ctrl+Shift+Bksp</kbd><span>Delete conversation</span></div>
                <div class="shortcut-row"><kbd>Escape</kbd><span>Close overlay</span></div>
                <div class="shortcut-row"><kbd>&uarr;</kbd><span>Edit last message (empty input)</span></div>
                <div class="shortcut-row"><kbd>?</kbd><span>Shortcuts help</span></div>
            </div>
        </div>

        <div class="modal-actions">
            <button onclick="saveSettings()">Save</button>
            <button onclick="toggleSettings()" class="secondary">Close</button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Add tab switching and memory list to `settings.js`**

```javascript
function switchSettingsTab(tabName, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).style.display = 'block';
    btn.classList.add('active');

    if (tabName === 'memory') loadMemoryList();
}

async function loadMemoryList() {
    const resp = await fetch('/api/memory');
    const memories = await resp.json();
    const list = document.getElementById('memory-list');
    if (memories.length === 0) {
        list.innerHTML = '<p class="empty-state">No saved memories</p>';
        return;
    }
    list.innerHTML = memories.map(m => `
        <div class="memory-item">
            <span>${escapeHtml(m.content)}</span>
            <button onclick="deleteMemory('${m.id}')" class="memory-delete">&times;</button>
        </div>
    `).join('');
}

async function deleteMemory(id) {
    await fetch(`/api/memory/${id}`, { method: 'DELETE' });
    await loadMemoryList();
}

async function clearAllMemories() {
    if (!confirm('Delete all memories?')) return;
    await fetch('/api/memory', { method: 'DELETE' });
    await loadMemoryList();
}
```

- [ ] **Step 3: Add tab styles**

```css
/* Settings tabs */
.settings-tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
}
.tab-btn {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
    padding: 8px 16px;
    font-size: 13px;
    cursor: pointer;
}
.tab-btn:hover { color: var(--text-secondary); }
.tab-btn.active { color: var(--accent-blue); border-bottom-color: var(--accent-blue); }

/* Memory items */
.memory-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}
.memory-delete {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 16px;
    padding: 0 4px;
}
.memory-delete:hover { color: #f85149; }
```

- [ ] **Step 4: Verify tabbed settings**

Open settings. Verify: three tabs work, General shows API key fields, Memory shows list with delete, Shortcuts shows reference list.

- [ ] **Step 5: Commit**

```bash
git add chat/static/js/settings.js chat/static/index.html chat/static/style.css
git commit -m "feat(chat): redesign settings with tabs — general, memory, shortcuts"
```

---

## Final Verification

- [ ] **Full integration test:** Open the app, create a new chat, send messages, test every feature: stop, regenerate, edit, search (Ctrl+K), shortcuts (?), export, pin, system prompt, memory, file upload, voice input, model selector, token stats, LaTeX. Verify all work together without conflicts.

- [ ] **Final commit with cache-bust version bump**

```bash
# Update all ?v= version numbers in index.html to v=7
git add -A
git commit -m "feat(chat): complete feature expansion — ChatGPT/Claude.ai parity"
```
