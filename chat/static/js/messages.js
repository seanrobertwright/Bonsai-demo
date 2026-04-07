/* Bonsai Chat — Messages: rendering, markdown, code blocks, tool pills */

let toolPillCounter = 0;

function preprocessMarkdown(text) {
    const trimmed = text.trim();
    if (!trimmed.includes('"name"')) return text;

    if (trimmed.startsWith('{')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && parsed.name && parsed.arguments) {
                if (parsed.name === 'python_exec' && parsed.arguments.code) {
                    return '```python\n' + parsed.arguments.code + '\n```';
                }
                return '```json\n' + JSON.stringify(parsed, null, 2) + '\n```';
            }
        } catch (e) {}
    }

    const codeMatch = trimmed.match(/"code"\s*:\s*"((?:[^"\\]|\\.)*)"/s);
    if (codeMatch && trimmed.includes('"python_exec"')) {
        const code = codeMatch[1]
            .replace(/\\n/g, '\n')
            .replace(/\\t/g, '\t')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\');
        return '```python\n' + code + '\n```';
    }

    if (trimmed.startsWith('{') && trimmed.includes('"arguments"')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed) return '```json\n' + JSON.stringify(parsed, null, 2) + '\n```';
        } catch (e) {}
    }

    return text;
}

function renderLatex(html) {
    // Block math: $$...$$
    html = html.replace(/\$\$([\s\S]+?)\$\$/g, (match, tex) => {
        try {
            return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
        } catch (e) {
            return `<code class="latex-error" title="LaTeX parse error">${escapeHtml(tex)}</code>`;
        }
    });

    // Inline math: $...$ (no space after opening, no space before closing)
    html = html.replace(/\$(\S(?:[^$]*?\S)?)\$/g, (match, tex) => {
        if (match.includes('<code>') || match.includes('</code>')) return match;
        try {
            return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false });
        } catch (e) {
            return `<code class="latex-error" title="LaTeX parse error">${escapeHtml(tex)}</code>`;
        }
    });

    return html;
}

/** Toggle full-width code layout for assistant rows that contain fenced code blocks. */
function syncAssistantCodeLayout(messageEl) {
    if (!messageEl || !messageEl.classList.contains('assistant')) return;
    const hasPre = messageEl.querySelector('.message-content pre');
    messageEl.classList.toggle('has-code', !!hasPre);
}

function enhanceCodeBlocks(container) {
    const codeBlocks = container.querySelectorAll('pre code');
    for (const codeEl of codeBlocks) {
        const pre = codeEl.parentElement;
        if (pre.classList.contains('enhanced')) continue;
        pre.classList.add('enhanced');
        try { hljs.highlightElement(codeEl); } catch (e) {}

        const lines = codeEl.textContent.split('\n');
        if (lines.length > 1) {
            const lineNums = document.createElement('span');
            lineNums.className = 'line-numbers';
            lineNums.setAttribute('aria-hidden', 'true');
            lineNums.innerHTML = lines.map((_, i) => `<span>${i + 1}</span>`).join('\n');
            pre.insertBefore(lineNums, codeEl);
            pre.classList.add('has-line-numbers');
        }

        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        btn.onclick = () => {
            navigator.clipboard.writeText(codeEl.textContent).then(() => {
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
                setTimeout(() => {
                    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                }, 2000);
            });
        };
        pre.appendChild(btn);
    }
}

function appendMessage(role, content) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatarClass = role === 'user' ? 'user-avatar' : 'bot-avatar';
    const avatarContent = role === 'user' ? 'U' : '&#127793;';

    div.innerHTML = `
        <div class="avatar ${avatarClass}">${avatarContent}</div>
        <div class="message-content">${role === 'user' ? escapeHtml(content) : renderLatex(marked.parse(preprocessMarkdown(content)))}</div>
    `;

    if (role === 'assistant') {
        enhanceCodeBlocks(div);
        syncAssistantCodeLayout(div);
    }

    // Add edit button for user messages
    if (role === 'user') {
        const contentWrapper = div.querySelector('.message-content');
        contentWrapper.style.position = 'relative';
        const editBtn = document.createElement('button');
        editBtn.className = 'edit-btn';
        editBtn.title = 'Edit message';
        editBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
        editBtn.onclick = () => editMessage(div, content);
        contentWrapper.appendChild(editBtn);
    }

    messages.appendChild(div);

    // Add action buttons for assistant messages (only for completed messages with content)
    if (role === 'assistant' && content) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        actions.innerHTML = `
            <button class="message-action-btn" onclick="copyResponse(this)" title="Copy">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy
            </button>
            <button class="message-action-btn" onclick="regenerateResponse()" title="Regenerate">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                Regenerate
            </button>
            <button class="message-action-btn" onclick="saveMemory(this.closest('.message-actions').previousElementSibling.querySelector('.message-content').textContent.substring(0, 100))" title="Save to Memory">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                Remember
            </button>
        `;
        messages.appendChild(actions);
    }

    scrollToBottom();
    return div;
}

function createSkeleton() {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'skeleton';
    div.innerHTML = `
        <div class="avatar bot-avatar">&#127793;</div>
        <div class="skeleton-lines">
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>
        </div>
    `;
    messages.appendChild(div);
    scrollToBottom();
    return div;
}

function appendSystemMessage(text) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.style.cssText = 'text-align:center;color:var(--text-muted);font-size:13px;padding:8px;';
    div.textContent = text;
    messages.appendChild(div);
}

function renderMessageHistory(msgs) {
    clearMessages();
    for (const m of msgs) {
        if (m.role === 'user' || m.role === 'assistant') {
            appendMessage(m.role, m.content);
        }
        if (m.tool_calls) {
            for (const tc of m.tool_calls) {
                addToolPill(tc.name, tc.arguments, 'completed');
            }
        }
    }
}

function addToolPill(name, args, status) {
    const id = `tool-pill-${toolPillCounter++}`;
    const messages = document.getElementById('messages');
    const container = document.createElement('div');
    container.className = 'tool-calls';
    const argsStr = Object.values(args || {}).join(', ');
    const statusIcon = status === 'running' ? '&#9679;' : '&#10003;';
    container.innerHTML = `
        <div class="tool-pill ${status}" id="${id}" onclick="toggleToolDetail('${id}-detail')">
            <span class="tool-status">${statusIcon}</span>
            <span class="tool-name">${name}</span>
            <span class="tool-args">${argsStr}</span>
        </div>
    `;
    const detail = document.createElement('div');
    detail.className = 'tool-detail';
    detail.id = `${id}-detail`;
    detail.textContent = `Arguments: ${JSON.stringify(args, null, 2)}`;
    messages.appendChild(container);
    messages.appendChild(detail);
    scrollToBottom();
}

function updateToolPill(name, status) {
    const pills = document.querySelectorAll('.tool-pill.running');
    for (const pill of pills) {
        if (pill.querySelector('.tool-name')?.textContent === name) {
            pill.className = `tool-pill ${status}`;
            pill.querySelector('.tool-status').innerHTML = '&#10003;';
            break;
        }
    }
}

function toggleToolDetail(id) {
    const detail = document.getElementById(id);
    if (detail) detail.classList.toggle('expanded');
}

function addToolLog(name, args, status) {
    const log = document.getElementById('tool-log');
    if (log.querySelector('.empty-state')) log.innerHTML = '';
    const entry = document.createElement('div');
    entry.className = 'tool-log-entry';
    entry.id = `log-${name}-${toolPillCounter}`;
    const icon = status === 'running' ? '&#9679;' : '&#10003;';
    const argsStr = Object.values(args || {}).join(', ');
    entry.innerHTML = `<span class="log-icon">${icon}</span> <strong>${name}</strong><div class="log-detail">${argsStr}</div>`;
    log.appendChild(entry);
}

function updateToolLog(name, result) {
    const entries = document.querySelectorAll('.tool-log-entry');
    for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        if (entry.querySelector('strong')?.textContent === name && entry.innerHTML.includes('\u25CF')) {
            entry.querySelector('.log-icon').innerHTML = '&#10003;';
            const detail = entry.querySelector('.log-detail');
            if (result.results) detail.textContent = `${result.results.length} results`;
            else if (result.result) detail.textContent = result.result;
            else if (result.error) detail.textContent = `Error: ${result.error}`;
            break;
        }
    }
}
