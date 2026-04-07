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
            trackToken();
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
            if (currentAssistantEl) {
                renderStats(currentAssistantEl);
            }
            resetStreamStats();
            currentAssistantEl = null;
            currentAssistantText = '';
            const doneBtn = document.getElementById('send-btn');
            doneBtn.textContent = 'Send';
            doneBtn.classList.remove('stop-btn');
            doneBtn.onclick = sendMessage;
            doneBtn.disabled = false;
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
    resetStreamStats();
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
    const lastChild = messages.lastElementChild;
    if (lastChild) {
        lastChild.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
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
