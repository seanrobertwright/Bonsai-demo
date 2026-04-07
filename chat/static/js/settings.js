/* Bonsai Chat — Settings & tools */

function toggleSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.toggle('hidden');
    if (!modal.classList.contains('hidden')) {
        loadSettingsIntoForm().catch((e) => console.error('loadSettingsIntoForm', e));
    }
}

async function loadSettingsIntoForm() {
    const resp = await fetch('/api/config');
    if (!resp.ok) return;
    const cfg = await resp.json();
    const serp = document.getElementById('cfg-serpapi');
    const owm = document.getElementById('cfg-openweather');
    const sandbox = document.getElementById('cfg-sandbox');
    const temp = document.getElementById('cfg-temperature');
    const topP = document.getElementById('cfg-top-p');
    const topK = document.getElementById('cfg-top-k');
    if (serp) serp.value = cfg.serpapi_key ?? '';
    if (owm) owm.value = cfg.openweather_key ?? '';
    if (sandbox) sandbox.value = cfg.sandbox_dir ?? '';
    if (temp) temp.value = cfg.temperature != null ? String(cfg.temperature) : '0.5';
    if (topP) topP.value = cfg.top_p != null ? String(cfg.top_p) : '0.85';
    if (topK) topK.value = cfg.top_k != null ? String(cfg.top_k) : '20';
}

async function saveSettings() {
    const parseFloatOr = (raw, fallback) => {
        if (raw === '' || raw == null) return fallback;
        const n = Number.parseFloat(String(raw));
        return Number.isFinite(n) ? n : fallback;
    };
    const parseIntOr = (raw, fallback) => {
        if (raw === '' || raw == null) return fallback;
        const n = Number.parseInt(String(raw), 10);
        return Number.isFinite(n) ? n : fallback;
    };
    const tempRaw = document.getElementById('cfg-temperature').value;
    const topPRaw = document.getElementById('cfg-top-p').value;
    const topKRaw = document.getElementById('cfg-top-k').value;
    const data = {
        serpapi_key: document.getElementById('cfg-serpapi').value,
        openweather_key: document.getElementById('cfg-openweather').value,
        sandbox_dir: document.getElementById('cfg-sandbox').value,
        temperature: parseFloatOr(tempRaw, 0.5),
        top_p: parseFloatOr(topPRaw, 0.85),
        top_k: parseIntOr(topKRaw, 20),
    };
    const resp = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!resp.ok) {
        window.alert('Failed to save settings.');
        return;
    }
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

/** Fetches GET /api/memory (full list, newest first per server) and fills the right tool panel list. */
async function loadSidebarMemories() {
    const el = document.getElementById('tool-panel-memory-list');
    if (!el) return;
    const esc =
        typeof escapeHtml === 'function'
            ? escapeHtml
            : (t) => {
                  const d = document.createElement('div');
                  d.textContent = t;
                  return d.innerHTML;
              };
    try {
        const resp = await fetch('/api/memory');
        if (!resp.ok) return;
        const memories = await resp.json();
        if (memories.length === 0) {
            el.innerHTML =
                '<li class="memory-datalist-empty" role="presentation">No memories yet</li>';
            return;
        }
        el.innerHTML = memories
            .map(
                (m) => `
            <li class="memory-datalist-item" role="listitem">
                <span class="memory-datalist-text">${esc(m.content)}</span>
                <button type="button" title="Remove" aria-label="Remove memory" onclick="deleteMemory('${m.id}')">&times;</button>
            </li>
        `
            )
            .join('');
    } catch (e) {}
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
    await loadSidebarMemories();
}

async function clearAllMemories() {
    if (!confirm('Delete all memories?')) return;
    await fetch('/api/memory', { method: 'DELETE' });
    await loadMemoryList();
    await loadSidebarMemories();
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
