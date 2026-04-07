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
