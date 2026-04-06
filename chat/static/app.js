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
    const entries = document.querySelectorAll('.tool-log-entry');
    for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        if (entry.querySelector('strong')?.textContent === name && entry.innerHTML.includes('\u25CF')) {
            entry.querySelector('.log-icon').innerHTML = '&#10003;';
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
