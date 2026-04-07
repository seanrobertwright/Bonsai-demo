/* Bonsai Chat — Voice input via Web Speech API */

let recognition = null;
let isListening = false;

function initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        const micBtn = document.getElementById('mic-btn');
        if (micBtn) micBtn.style.display = 'none';
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
        const input = document.getElementById('message-input');
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        input.value = input.dataset.preVoice + transcript;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    };

    recognition.onend = () => {
        if (isListening) {
            stopListening();
        }
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopListening();
    };
}

function toggleVoice() {
    if (isListening) {
        stopListening();
    } else {
        startListening();
    }
}

function startListening() {
    if (!recognition) return;
    const input = document.getElementById('message-input');
    input.dataset.preVoice = input.value;
    isListening = true;
    const btn = document.getElementById('mic-btn');
    btn.classList.add('listening');
    recognition.start();
}

function stopListening() {
    if (!recognition) return;
    isListening = false;
    const btn = document.getElementById('mic-btn');
    btn.classList.remove('listening');
    recognition.stop();
}

initVoice();
