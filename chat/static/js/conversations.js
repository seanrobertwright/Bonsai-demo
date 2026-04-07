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
