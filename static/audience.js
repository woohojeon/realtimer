/**
 * Lecture Lens - Audience JavaScript
 * Real-time subtitle display with TTS support
 */

// ========================
// Global Variables
// ========================
let socket = null;
let selectedLanguage = '';
let availableLanguages = {};
let currentSubtitle = '';
let isTTSEnabled = false;
let ttsSpeed = 1.0;
let isSpeaking = false;
let speechSynthesis = window.speechSynthesis;
let pendingTTS = null;

// TTS 언어 코드 매핑
const TTS_LANG_MAP = {
    'ko': 'ko-KR',
    'en': 'en-US',
    'ja': 'ja-JP',
    'zh': 'zh-CN',
    'es': 'es-ES',
    'fr': 'fr-FR',
    'de': 'de-DE',
    'pt': 'pt-BR',
    'ru': 'ru-RU',
    'vi': 'vi-VN'
};

// ========================
// DOM Elements
// ========================
const connectionStatus = document.getElementById('connectionStatus');
const statusDot = connectionStatus.querySelector('.status-dot');
const statusText = connectionStatus.querySelector('.status-text');
const languageSelect = document.getElementById('languageSelect');
const subtitleStatus = document.getElementById('subtitleStatus');
const subtitleText = document.getElementById('subtitleText');
const ttsToggle = document.getElementById('ttsToggle');
const ttsControls = document.getElementById('ttsControls');
const ttsSpeedInput = document.getElementById('ttsSpeed');
const speedValue = document.getElementById('speedValue');
const btnSpeak = document.getElementById('btnSpeak');
const themeToggle = document.getElementById('themeToggle');

// ========================
// Initialization
// ========================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSocket();
    initEventListeners();
    checkTTSSupport();
});

// ========================
// Theme Management
// ========================
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// ========================
// Socket Connection
// ========================
function initSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = io({
        transports: ['websocket', 'polling']
    });

    socket.on('connect', () => {
        updateConnectionStatus('connected', 'Connected');
        socket.emit('request_languages');
    });

    socket.on('disconnect', () => {
        updateConnectionStatus('disconnected', 'Disconnected');
    });

    socket.on('connect_error', () => {
        updateConnectionStatus('error', 'Connection Error');
    });

    socket.on('languages_update', handleLanguagesUpdate);
    socket.on('subtitle_update', handleSubtitleUpdate);
}

function updateConnectionStatus(status, text) {
    statusDot.className = 'status-dot';
    if (status === 'connected') {
        statusDot.classList.add('connected');
    } else if (status === 'error') {
        statusDot.classList.add('error');
    }
    statusText.textContent = text;
}

// ========================
// Language Handling
// ========================
function handleLanguagesUpdate(data) {
    availableLanguages = data.languages || {};
    updateLanguageSelect();
}

function updateLanguageSelect() {
    languageSelect.innerHTML = '';

    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Select language...';
    languageSelect.appendChild(defaultOption);

    Object.entries(availableLanguages).forEach(([code, info]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = `${info.flag || ''} ${info.name}`;
        languageSelect.appendChild(option);
    });

    // 저장된 언어 복원
    const savedLang = localStorage.getItem('selectedLanguage');
    if (savedLang && availableLanguages[savedLang]) {
        languageSelect.value = savedLang;
        selectedLanguage = savedLang;
    }
}

// ========================
// Subtitle Handling
// ========================
function handleSubtitleUpdate(data) {
    const { type, data: subtitles } = data;

    // 상태 업데이트
    if (type === 'processing') {
        subtitleStatus.textContent = 'Translating...';
        subtitleStatus.className = 'subtitle-status processing';
        subtitleText.className = 'subtitle-text processing';
        return;
    }

    if (type === 'realtime') {
        subtitleStatus.textContent = 'Real-time translation';
        subtitleStatus.className = 'subtitle-status processing';
        subtitleText.className = 'subtitle-text realtime';
    } else if (type === 'final') {
        subtitleStatus.textContent = 'Translation complete';
        subtitleStatus.className = 'subtitle-status final';
        subtitleText.className = 'subtitle-text final';
    } else {
        subtitleStatus.textContent = 'Waiting for speech...';
        subtitleStatus.className = 'subtitle-status';
        subtitleText.className = 'subtitle-text';
    }

    // 선택된 언어의 자막 표시
    if (selectedLanguage && subtitles && subtitles[selectedLanguage]) {
        const text = subtitles[selectedLanguage];
        subtitleText.textContent = text;

        // Final 번역일 때만 TTS 실행
        if (type === 'final' && text !== currentSubtitle) {
            currentSubtitle = text;
            btnSpeak.disabled = false;

            if (isTTSEnabled) {
                speakText(text);
            }
        }
    } else if (!selectedLanguage) {
        subtitleText.textContent = 'Please select a language above';
    }
}

// ========================
// TTS (Text-to-Speech)
// ========================
function checkTTSSupport() {
    if (!('speechSynthesis' in window)) {
        ttsToggle.disabled = true;
        btnSpeak.disabled = true;
        document.querySelector('.tts-label').textContent = 'TTS not supported';
    }
}

function speakText(text) {
    if (!text || !speechSynthesis) return;

    // 이전 발화 중지
    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = TTS_LANG_MAP[selectedLanguage] || 'en-US';
    utterance.rate = ttsSpeed;
    utterance.pitch = 1;

    // 해당 언어의 음성 찾기
    const voices = speechSynthesis.getVoices();
    const langVoice = voices.find(v => v.lang.startsWith(selectedLanguage) || v.lang === utterance.lang);
    if (langVoice) {
        utterance.voice = langVoice;
    }

    utterance.onstart = () => {
        isSpeaking = true;
        btnSpeak.classList.add('speaking');
        btnSpeak.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M6 6h12v12H6z"/>
            </svg>
            Stop
        `;
    };

    utterance.onend = () => {
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
        btnSpeak.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            Speak
        `;
    };

    utterance.onerror = (e) => {
        console.error('TTS Error:', e);
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
    };

    speechSynthesis.speak(utterance);
}

function stopSpeaking() {
    if (speechSynthesis) {
        speechSynthesis.cancel();
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
        btnSpeak.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            Speak
        `;
    }
}

// ========================
// Event Listeners
// ========================
function initEventListeners() {
    // Language selection
    languageSelect.addEventListener('change', (e) => {
        selectedLanguage = e.target.value;
        localStorage.setItem('selectedLanguage', selectedLanguage);

        if (selectedLanguage) {
            subtitleText.textContent = 'Waiting for translation...';
        } else {
            subtitleText.textContent = 'Please select a language above';
        }
        currentSubtitle = '';
        btnSpeak.disabled = true;
    });

    // TTS toggle
    ttsToggle.addEventListener('change', (e) => {
        isTTSEnabled = e.target.checked;
        localStorage.setItem('ttsEnabled', isTTSEnabled);
    });

    // Restore TTS setting
    const savedTTS = localStorage.getItem('ttsEnabled');
    if (savedTTS === 'true') {
        ttsToggle.checked = true;
        isTTSEnabled = true;
    }

    // TTS speed
    ttsSpeedInput.addEventListener('input', (e) => {
        ttsSpeed = parseFloat(e.target.value);
        speedValue.textContent = ttsSpeed.toFixed(1) + 'x';
        localStorage.setItem('ttsSpeed', ttsSpeed);
    });

    // Restore TTS speed
    const savedSpeed = localStorage.getItem('ttsSpeed');
    if (savedSpeed) {
        ttsSpeed = parseFloat(savedSpeed);
        ttsSpeedInput.value = ttsSpeed;
        speedValue.textContent = ttsSpeed.toFixed(1) + 'x';
    }

    // Speak button
    btnSpeak.addEventListener('click', () => {
        if (isSpeaking) {
            stopSpeaking();
        } else if (currentSubtitle) {
            speakText(currentSubtitle);
        }
    });

    // Theme toggle
    themeToggle.addEventListener('click', toggleTheme);

    // Load voices (some browsers load them async)
    if (speechSynthesis) {
        speechSynthesis.onvoiceschanged = () => {
            // Voices loaded
        };
    }
}
