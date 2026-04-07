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

/* ── Conversation Search ── */

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
