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

// ── Autonomous memory: save toast + undo ──

function showMemoryToast(result) {
    // result shape: { status: 'saved'|'duplicate', id, content }
    // Note: 'updated' status was removed when prefix dedup was dropped — v1
    // only has 'saved' and 'duplicate'.
    if (!result || result.status === 'duplicate') return;
    if (result.error) return;

    const toast = document.createElement('div');
    toast.className = 'memory-toast';
    toast.innerHTML = `
        <span>💾 Remembered: </span>
        <span class="memory-toast-content"></span>
        <span class="memory-toast-undo">Undo</span>
    `;
    // textContent, not innerHTML, for user content — prevents XSS if the
    // model emits HTML in the memory content.
    toast.querySelector('.memory-toast-content').textContent = `"${result.content}"`;

    const undoEl = toast.querySelector('.memory-toast-undo');
    undoEl.addEventListener('click', async () => {
        try {
            await fetch(`/api/memory/${result.id}`, { method: 'DELETE' });
            toast.querySelector('.memory-toast-content').textContent = ' Forgotten';
            undoEl.remove();
        } catch (e) {
            console.error('undo memory failed', e);
        }
    });

    document.body.appendChild(toast);
    // Next-frame trigger for the CSS transition.
    requestAnimationFrame(() => toast.classList.add('visible'));

    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 6000);
}

// Expose on window so core.js can call it without imports (the existing JS
// files are loaded as globals, not modules).
window.showMemoryToast = showMemoryToast;
