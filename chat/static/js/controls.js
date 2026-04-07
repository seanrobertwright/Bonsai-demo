/* Bonsai Chat — Response controls: stop, regenerate, edit, copy */

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
            const origHTML = btn.innerHTML;
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
            setTimeout(() => { btn.innerHTML = origHTML; }, 2000);
        });
    }
}

function editMessage(messageEl, originalText) {
    const contentEl = messageEl.querySelector('.message-content');
    const escaped = escapeHtml(originalText);
    contentEl.innerHTML = `
        <textarea class="edit-textarea">${escaped}</textarea>
        <div class="edit-actions">
            <button class="cancel-edit" onclick="cancelEdit(this, '${escaped.replace(/'/g, "\\'")}')">Cancel</button>
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
