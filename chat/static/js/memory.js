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
