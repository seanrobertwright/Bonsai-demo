/* Bonsai Chat — Conversations: sidebar, navigation, views */

function convEscapeHtml(text) {
    if (typeof escapeHtml === 'function') {
        return escapeHtml(String(text));
    }
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function convEscapeAttr(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

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
            html += `<div class="conv-group-label">${convEscapeHtml(group)}</div>`;
            lastGroup = group;
        }
        html += renderConvItem(conv);
    }
    list.innerHTML = html;
}

function renderConvItem(conv) {
    const active = conv.id === currentConvId ? ' active' : '';
    const pinIcon = conv.pinned ? '<span class="pin-icon" title="Pinned">&#128204;</span>' : '';
    const safeTitle = convEscapeHtml(conv.title);
    const safeAttr = convEscapeAttr(conv.title);
    return `<div class="conv-item${active}" data-conv-id="${conv.id}" onclick="openConversation('${conv.id}')" title="${safeAttr} — Double-click to rename" role="button" tabindex="0" onkeydown="handleConvItemKeydown(event, '${conv.id}')" ondblclick="startInlineRename('${conv.id}', this)">
        ${pinIcon}<span class="conv-title">${safeTitle}</span>
        <button type="button" class="conv-menu-btn" aria-label="Conversation actions" onclick="event.stopPropagation(); toggleConvMenu('${conv.id}', this)">&#8942;</button>
    </div>`;
}

function handleConvItemKeydown(event, convId) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openConversation(convId);
    }
}

let _convMenuCleanup = null;
let _convMenuEsc = null;

function removeFloatingConvMenu() {
    document.querySelectorAll('.conv-menu').forEach(m => m.remove());
    if (_convMenuCleanup) {
        window.removeEventListener('scroll', _convMenuCleanup, true);
        window.removeEventListener('resize', _convMenuCleanup);
        _convMenuCleanup = null;
    }
    if (_convMenuEsc) {
        document.removeEventListener('keydown', _convMenuEsc);
        _convMenuEsc = null;
    }
}

function toggleConvMenu(convId, btn) {
    removeFloatingConvMenu();

    const menu = document.createElement('div');
    menu.className = 'conv-menu conv-menu-fixed';
    menu.innerHTML = `
        <button type="button" onclick="removeFloatingConvMenu(); void pinConversation('${convId}')">&#128204; Pin/Unpin</button>
        <button type="button" onclick="removeFloatingConvMenu(); void exportConversation('${convId}', 'markdown')">&#128196; Export Markdown</button>
        <button type="button" onclick="removeFloatingConvMenu(); void exportConversation('${convId}', 'json')">&#128196; Export JSON</button>
        <button type="button" onclick="removeFloatingConvMenu(); startInlineRename('${convId}')">&#9998; Rename</button>
        <button type="button" onclick="removeFloatingConvMenu(); void confirmDeleteConversation('${convId}')" style="color:#f85149">&#128465; Delete</button>
    `;
    document.body.appendChild(menu);

    const place = () => {
        const r = btn.getBoundingClientRect();
        const h = menu.offsetHeight;
        let top = r.bottom + 4;
        if (top + h > window.innerHeight - 8 && r.top > h + 8) {
            top = Math.max(8, r.top - h - 4);
        } else if (top + h > window.innerHeight - 8) {
            top = Math.max(8, window.innerHeight - h - 8);
        }
        menu.style.top = `${top}px`;
        menu.style.right = `${window.innerWidth - r.right}px`;
        menu.style.left = 'auto';
    };
    place();
    requestAnimationFrame(place);

    _convMenuCleanup = () => removeFloatingConvMenu();
    window.addEventListener('scroll', _convMenuCleanup, true);
    window.addEventListener('resize', _convMenuCleanup);
    _convMenuEsc = (e) => {
        if (e.key === 'Escape') removeFloatingConvMenu();
    };
    document.addEventListener('keydown', _convMenuEsc);

    setTimeout(() => {
        document.addEventListener('click', function closeIfOutside(e) {
            if (!menu.isConnected) return;
            if (menu.contains(e.target)) return;
            removeFloatingConvMenu();
        }, { once: true, capture: true });
    }, 0);
}

async function confirmDeleteConversation(convId) {
    if (!confirm('Delete this conversation?')) return;
    await deleteConversation(convId);
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

async function commitConversationRename(convId, rawTitle) {
    const resp = await fetch(`/api/conversations/${convId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: rawTitle }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        window.alert(data.error || 'Could not rename conversation.');
        return false;
    }
    return true;
}

function startInlineRename(convId, el) {
    const item = el || document.querySelector(`.conv-item[data-conv-id="${convId}"]`);
    if (!item) return;
    const titleSpan = item.querySelector('.conv-title');
    const currentTitle = titleSpan.textContent;

    const input = document.createElement('input');
    input.className = 'inline-rename-input';
    input.value = currentTitle;
    input.onclick = (e) => e.stopPropagation();

    let finished = false;

    const finish = async () => {
        if (finished) return;
        finished = true;
        await commitConversationRename(convId, input.value);
        await loadConversations();
    };

    input.onkeydown = async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            await finish();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            finished = true;
            await loadConversations();
        }
    };
    input.onblur = () => {
        setTimeout(async () => {
            if (finished) return;
            await finish();
        }, 0);
    };

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
    const resp = await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        window.alert(data.error || 'Could not delete conversation.');
        return;
    }
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
                <div class="search-title">${convEscapeHtml(r.title)}</div>
                <div class="search-snippet">${highlighted}</div>
            </div>`;
        }).join('');
    }, 200);
}
