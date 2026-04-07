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
    if (typeof loadSidebarMemories === 'function') await loadSidebarMemories();
}

// ── Autonomous memory: save toast + undo ──

function dismissMemoryToast(toast, ms) {
    const delay = ms != null ? ms : 5000;
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, delay);
}

/** Simple banner (no undo) — duplicate, error, or short notices */
function showMemoryBanner(message, opts) {
    const toast = document.createElement('div');
    toast.className = 'memory-toast';
    toast.setAttribute('role', 'status');
    toast.innerHTML = `<span class="memory-toast-content"></span>`;
    toast.querySelector('.memory-toast-content').textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('visible'));
    dismissMemoryToast(toast, opts && opts.durationMs);
}

function showMemoryToast(result) {
    // Keep sidebar in sync whenever the remember tool returns (saved, duplicate, or error).
    if (typeof loadSidebarMemories === 'function') {
        void loadSidebarMemories();
    }

    if (!result || typeof result !== 'object') {
        return;
    }
    if (result.error) {
        showMemoryBanner('Memory: ' + String(result.error), { durationMs: 6000 });
        return;
    }
    if (result.status === 'duplicate') {
        showMemoryBanner('Already saved — that fact is already in your memories.', {
            durationMs: 4000,
        });
        return;
    }

    const toast = document.createElement('div');
    toast.className = 'memory-toast';
    toast.setAttribute('role', 'status');
    toast.innerHTML = `
        <span>Remembered: </span>
        <span class="memory-toast-content"></span>
        <span class="memory-toast-undo">Undo</span>
    `;
    const content = result.content != null ? String(result.content) : '';
    toast.querySelector('.memory-toast-content').textContent = content ? `"${content}"` : 'Saved.';

    const undoEl = toast.querySelector('.memory-toast-undo');
    const memoryId = result.id;
    undoEl.addEventListener('click', async () => {
        if (!memoryId) return;
        try {
            await fetch(`/api/memory/${memoryId}`, { method: 'DELETE' });
            toast.querySelector('.memory-toast-content').textContent = 'Removed.';
            undoEl.remove();
            if (typeof loadSidebarMemories === 'function') await loadSidebarMemories();
        } catch (e) {
            console.error('undo memory failed', e);
        }
    });

    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('visible'));
    dismissMemoryToast(toast, 6000);
}

// Expose on window so core.js can call it without imports (the existing JS
// files are loaded as globals, not modules).
window.showMemoryToast = showMemoryToast;
