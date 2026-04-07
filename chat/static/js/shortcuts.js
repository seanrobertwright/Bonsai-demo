/* Bonsai Chat — Keyboard shortcuts */

function initShortcuts() {
    document.addEventListener('keydown', handleShortcut);
}

function handleShortcut(e) {
    // Don't fire when typing in inputs (except Escape)
    const tag = document.activeElement?.tagName;
    const isTyping = tag === 'INPUT' || tag === 'TEXTAREA';

    // Escape — always works
    if (e.key === 'Escape') {
        e.preventDefault();
        closeAllOverlays();
        return;
    }

    if (isTyping) return;

    const mod = e.ctrlKey || e.metaKey;

    // Ctrl/Cmd+K — search conversations
    if (mod && e.key === 'k') {
        e.preventDefault();
        toggleSearchOverlay();
        return;
    }

    // Ctrl/Cmd+N — new chat
    if (mod && e.key === 'n') {
        e.preventDefault();
        createNewChat();
        return;
    }

    // Ctrl/Cmd+Shift+Backspace — delete current conversation
    if (mod && e.shiftKey && e.key === 'Backspace') {
        e.preventDefault();
        if (currentConvId && confirm('Delete this conversation?')) {
            deleteConversation(currentConvId);
        }
        return;
    }

    // ? or Ctrl+/ — show shortcuts help
    if (e.key === '?' || (mod && e.key === '/')) {
        e.preventDefault();
        toggleShortcutsHelp();
        return;
    }
}

// Up arrow in empty input — edit last message
function handleInputKeyDown(event) {
    if (event.key === 'ArrowUp' && event.target.value === '') {
        event.preventDefault();
        const userMessages = document.querySelectorAll('.message.user');
        const lastUser = userMessages[userMessages.length - 1];
        if (lastUser) {
            const content = lastUser.querySelector('.message-content').textContent;
            editMessage(lastUser, content);
        }
        return;
    }
    handleKeyDown(event);
}

function closeAllOverlays() {
    // Close search
    const search = document.getElementById('search-overlay');
    if (search && !search.classList.contains('hidden')) {
        search.classList.add('hidden');
        return;
    }
    // Close shortcuts help
    const help = document.getElementById('shortcuts-help');
    if (help && !help.classList.contains('hidden')) {
        help.classList.add('hidden');
        return;
    }
    // Close settings
    const settings = document.getElementById('settings-modal');
    if (settings && !settings.classList.contains('hidden')) {
        settings.classList.add('hidden');
        return;
    }
}

function toggleShortcutsHelp() {
    document.getElementById('shortcuts-help').classList.toggle('hidden');
}

// Placeholder — search implemented in conversations.js
function toggleSearchOverlay() {
    const overlay = document.getElementById('search-overlay');
    if (overlay) {
        overlay.classList.toggle('hidden');
        if (!overlay.classList.contains('hidden')) {
            overlay.querySelector('input')?.focus();
        }
    }
}

// Init on load
initShortcuts();
