/* Bonsai Chat — Settings & tools */

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

async function loadTools() {
    try {
        const resp = await fetch('/api/tools');
        const tools = await resp.json();
        const list = document.getElementById('tool-list');
        list.innerHTML = tools.map(t =>
            `<div class="tool-entry"><div class="tool-dot"></div>${t.name}</div>`
        ).join('');
    } catch (e) {}
}

/* ── Tabbed Settings ── */

function switchSettingsTab(tabName, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).style.display = 'block';
    btn.classList.add('active');

    if (tabName === 'memory') loadMemoryList();
}

async function loadMemoryList() {
    const resp = await fetch('/api/memory');
    const memories = await resp.json();
    const list = document.getElementById('memory-list');
    if (memories.length === 0) {
        list.innerHTML = '<p class="empty-state">No saved memories</p>';
        return;
    }
    list.innerHTML = memories.map(m => `
        <div class="memory-item">
            <span>${escapeHtml(m.content)}</span>
            <button onclick="deleteMemory('${m.id}')" class="memory-delete">&times;</button>
        </div>
    `).join('');
}

async function deleteMemory(id) {
    await fetch(`/api/memory/${id}`, { method: 'DELETE' });
    await loadMemoryList();
}

async function clearAllMemories() {
    if (!confirm('Delete all memories?')) return;
    await fetch('/api/memory', { method: 'DELETE' });
    await loadMemoryList();
}

/* ── Model Selector ── */

async function loadModelSelector() {
    try {
        const resp = await fetch('/api/models');
        const models = await resp.json();
        const label = document.getElementById('model-label');
        const currentModel = localStorage.getItem('bonsai-model') || models[0]?.id;

        if (models.length <= 1) {
            label.textContent = models[0]?.name || 'Bonsai 8B';
            return;
        }

        const select = document.createElement('select');
        select.id = 'model-selector';
        select.className = 'model-selector';
        for (const m of models) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            if (m.id === currentModel) opt.selected = true;
            select.appendChild(opt);
        }
        select.onchange = () => {
            localStorage.setItem('bonsai-model', select.value);
        };
        label.replaceWith(select);
    } catch (e) {}
}
