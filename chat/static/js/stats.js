/* Bonsai Chat — Token & performance stats */

let streamStartTime = 0;
let tokenCount = 0;

function resetStreamStats() {
    streamStartTime = 0;
    tokenCount = 0;
}

function trackToken() {
    if (tokenCount === 0) {
        streamStartTime = performance.now();
    }
    tokenCount++;
}

function getStreamStats() {
    if (tokenCount === 0) return null;
    const elapsed = (performance.now() - streamStartTime) / 1000;
    const tokPerSec = elapsed > 0 ? (tokenCount / elapsed).toFixed(1) : '0';
    return {
        tokens: tokenCount,
        elapsed: elapsed.toFixed(1),
        tokPerSec: tokPerSec,
    };
}

function renderStats(messageEl) {
    const stats = getStreamStats();
    if (!stats || !messageEl) return;

    const statsEl = document.createElement('div');
    statsEl.className = 'message-stats';
    statsEl.textContent = `${stats.tokens} tokens \u00b7 ${stats.tokPerSec} tok/s \u00b7 ${stats.elapsed}s`;

    // Insert after the message
    messageEl.parentElement.insertBefore(statsEl, messageEl.nextSibling);
}
