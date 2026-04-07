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
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
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
    if (pendingAttachments.length === 0) return '';
    let context = '';
    for (const att of pendingAttachments) {
        if (att.type === 'text' && att.content) {
            const ext = att.filename.split('.').pop();
            context += `\u{1F4CE} ${att.filename}\n\`\`\`${ext}\n${att.content}\n\`\`\`\n\n`;
        } else if (att.type === 'image') {
            context += `\u{1F4CE} ${att.filename} (image attached)\n\n`;
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
