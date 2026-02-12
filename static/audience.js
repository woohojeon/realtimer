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
let subtitleFontSize = 1.35; // rem

const FONT_SIZE_MIN = 0.8;
const FONT_SIZE_MAX = 3.0;
const FONT_SIZE_STEP = 0.2;

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

// 문장 종결 패턴 (다국어)
const SENTENCE_END_RE = /(?<=[.!?。！？])\s*/;

// ========================
// DOM Elements
// ========================
const connectionStatus = document.getElementById('connectionStatus');
const statusDot = connectionStatus.querySelector('.status-dot');
const languageSelect = document.getElementById('languageSelect');
const subtitleHistory = document.getElementById('subtitleHistory');
const subtitleRealtime = document.getElementById('subtitleRealtime');
const ttsToggle = document.getElementById('ttsToggle');
const ttsSpeedInput = document.getElementById('ttsSpeed');
const speedValue = document.getElementById('speedValue');
const btnSpeak = document.getElementById('btnSpeak');
const themeToggle = document.getElementById('themeToggle');
const fontIncrease = document.getElementById('fontIncrease');
const fontDecrease = document.getElementById('fontDecrease');

// ========================
// Initialization
// ========================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initFontSize();
    initSocket();
    initEventListeners();
    checkTTSSupport();
});

// ========================
// Theme Management
// ========================
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// ========================
// Font Size Management
// ========================
function initFontSize() {
    const saved = localStorage.getItem('subtitleFontSize');
    if (saved) {
        subtitleFontSize = parseFloat(saved);
    }
    applyFontSize();
}

function applyFontSize() {
    document.documentElement.style.setProperty('--subtitle-size', subtitleFontSize + 'rem');
}

function changeFontSize(delta) {
    subtitleFontSize = Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, subtitleFontSize + delta));
    applyFontSize();
    localStorage.setItem('subtitleFontSize', subtitleFontSize);
}

// ========================
// Socket Connection
// ========================
function initSocket() {
    socket = io({
        transports: ['polling', 'websocket'],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000
    });

    socket.on('connect', () => {
        updateConnectionStatus('connected');
        socket.emit('request_languages');
    });

    socket.on('disconnect', () => {
        updateConnectionStatus('disconnected');
    });

    socket.on('connect_error', () => {
        updateConnectionStatus('error');
    });

    socket.on('languages_update', handleLanguagesUpdate);
    socket.on('subtitle_update', handleSubtitleUpdate);
}

function updateConnectionStatus(status) {
    statusDot.className = 'status-dot';
    if (status === 'connected') {
        statusDot.classList.add('connected');
    } else if (status === 'error') {
        statusDot.classList.add('error');
    }
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

    if (type === 'processing') {
        setRealtimeText('...');
        return;
    }

    // 선택된 언어의 자막 표시
    if (selectedLanguage && subtitles && subtitles[selectedLanguage]) {
        const text = subtitles[selectedLanguage];

        if (type === 'realtime') {
            setRealtimeText(text);
        } else if (type === 'final' && text !== currentSubtitle) {
            currentSubtitle = text;
            resetRealtimeText();

            // 문장 단위로 분리하여 각각 entry로 추가
            const sentences = splitSentences(text);
            sentences.forEach(sentence => {
                const entry = document.createElement('div');
                entry.className = 'subtitle-entry';
                entry.textContent = sentence;
                subtitleHistory.appendChild(entry);
            });

            // 자동 스크롤
            subtitleHistory.scrollTop = subtitleHistory.scrollHeight;

            btnSpeak.disabled = false;
            if (isTTSEnabled) {
                speakText(text);
            }
        }
    } else if (!selectedLanguage) {
        if (subtitleHistory.children.length === 0) {
            subtitleRealtime.textContent = 'Please select a language above';
        }
    }
}

/**
 * 문장 종결 부호(. ! ? 。 ！ ？) 기준으로 텍스트를 분리
 */
function splitSentences(text) {
    const parts = text.split(SENTENCE_END_RE).filter(s => s.trim().length > 0);
    if (parts.length === 0) return [text];
    return parts;
}

// ========================
// Realtime text auto-shrink
// ========================
/**
 * 실시간 텍스트를 고정 영역 안에 맞추어 폰트 축소
 */
function setRealtimeText(text) {
    // 기본 크기로 복원 후 텍스트 세팅
    subtitleRealtime.style.fontSize = '';
    subtitleRealtime.textContent = text;

    // 넘치면 폰트를 줄여서 맞추기
    let size = parseFloat(getComputedStyle(subtitleRealtime).fontSize);
    const minSize = 10; // px 최소값
    while (subtitleRealtime.scrollHeight > subtitleRealtime.clientHeight && size > minSize) {
        size -= 1;
        subtitleRealtime.style.fontSize = size + 'px';
    }
}

function resetRealtimeText() {
    subtitleRealtime.style.fontSize = '';
    subtitleRealtime.textContent = '';
}

// ========================
// TTS (Text-to-Speech)
// ========================
function checkTTSSupport() {
    if (!('speechSynthesis' in window)) {
        ttsToggle.disabled = true;
        btnSpeak.disabled = true;
        document.querySelector('.tts-label').textContent = 'N/A';
    }
}

function speakText(text) {
    if (!text || !speechSynthesis) return;

    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = TTS_LANG_MAP[selectedLanguage] || 'en-US';
    utterance.rate = ttsSpeed;
    utterance.pitch = 1;

    const voices = speechSynthesis.getVoices();
    const langVoice = voices.find(v => v.lang.startsWith(selectedLanguage) || v.lang === utterance.lang);
    if (langVoice) {
        utterance.voice = langVoice;
    }

    utterance.onstart = () => {
        isSpeaking = true;
        btnSpeak.classList.add('speaking');
    };

    utterance.onend = () => {
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
    };

    utterance.onerror = () => {
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

        subtitleHistory.innerHTML = '';
        subtitleRealtime.textContent = selectedLanguage
            ? 'Waiting for translation...'
            : 'Please select a language above';
        currentSubtitle = '';
        btnSpeak.disabled = true;
    });

    // TTS toggle - 매 세션마다 꺼진 상태로 시작, 사용자가 직접 켜야 함
    ttsToggle.checked = false;
    isTTSEnabled = false;
    ttsToggle.addEventListener('change', (e) => {
        isTTSEnabled = e.target.checked;
    });

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

    // Font size controls
    fontIncrease.addEventListener('click', () => changeFontSize(FONT_SIZE_STEP));
    fontDecrease.addEventListener('click', () => changeFontSize(-FONT_SIZE_STEP));

    // Load voices
    if (speechSynthesis) {
        speechSynthesis.onvoiceschanged = () => {};
    }
}
