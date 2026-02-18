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
let ttsAudioEl = null;  // 재사용 <audio> 엘리먼트
let ttsQueue = [];       // TTS 오디오 재생 큐
let subtitleFontSize = 1.35; // rem

const FONT_SIZE_MIN = 0.8;
const FONT_SIZE_MAX = 3.0;
const FONT_SIZE_STEP = 0.2;

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

    // Azure Neural TTS 응답
    socket.on('tts_audio', handleTTSAudio);
    socket.on('tts_error', (data) => {
        console.warn('[TTS] Server error:', data.error);
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
    });
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
// TTS (Azure Neural TTS via server)
// ========================

// 무음 MP3 (극소 크기) — <audio> 엘리먼트를 사용자 제스처로 활성화하기 위한 용도
const SILENT_MP3 = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYYoRwMHAAAAAAD/+1DEAAAHAAGf9AAAIgAANIAAAAS7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//tQxBcAAADSAAAAAAAAANIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

/**
 * <audio> 엘리먼트를 생성하고 무음 재생으로 활성화 (사용자 제스처 내에서 호출해야 함)
 */
function warmUpAudioElement() {
    if (ttsAudioEl) return;
    ttsAudioEl = new Audio();
    ttsAudioEl.src = SILENT_MP3;
    ttsAudioEl.play().then(() => {
        console.log('[TTS] Audio element warmed up');
    }).catch(e => {
        console.warn('[TTS] Audio warm-up failed:', e);
    });
}

function checkTTSSupport() {
    // 서버 TTS이므로 항상 활성화
}

function speakText(text) {
    if (!text || !socket) return;

    console.log('[TTS] Requesting:', selectedLanguage, text.substring(0, 50));
    socket.emit('request_tts', {
        text: text,
        lang: selectedLanguage || 'en',
        speed: ttsSpeed
    });
}

function handleTTSAudio(data) {
    console.log('[TTS] Audio received:', data.audio ? data.audio.length + ' chars' : 'empty');

    try {
        const byteChars = atob(data.audio);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) {
            byteArray[i] = byteChars.charCodeAt(i);
        }
        const blob = new Blob([byteArray], { type: 'audio/mp3' });
        const url = URL.createObjectURL(blob);

        // 큐에 추가하고, 현재 재생 중이 아니면 재생 시작
        ttsQueue.push(url);
        if (!isSpeaking) {
            playNextInQueue();
        }
    } catch (e) {
        console.warn('[TTS] handleTTSAudio error:', e);
    }
}

function playNextInQueue() {
    if (ttsQueue.length === 0) {
        isSpeaking = false;
        btnSpeak.classList.remove('speaking');
        return;
    }

    if (!ttsAudioEl) {
        ttsAudioEl = new Audio();
    }

    const url = ttsQueue.shift();

    // 기존 blob URL 정리
    if (ttsAudioEl._blobUrl) {
        URL.revokeObjectURL(ttsAudioEl._blobUrl);
    }
    ttsAudioEl._blobUrl = url;

    ttsAudioEl.onplay = () => {
        isSpeaking = true;
        btnSpeak.classList.add('speaking');
    };
    ttsAudioEl.onended = () => {
        // 다음 큐 재생
        playNextInQueue();
    };
    ttsAudioEl.onerror = (e) => {
        console.warn('[TTS] Playback error:', e);
        playNextInQueue();
    };

    ttsAudioEl.src = url;
    ttsAudioEl.play().then(() => {
        console.log('[TTS] Playing, queue:', ttsQueue.length, 'remaining');
    }).catch(e => {
        console.warn('[TTS] Play failed:', e);
        playNextInQueue();
    });
}

function stopSpeaking() {
    // 큐 비우고 현재 재생 중지
    ttsQueue.forEach(url => URL.revokeObjectURL(url));
    ttsQueue = [];
    if (ttsAudioEl) {
        ttsAudioEl.pause();
        ttsAudioEl.currentTime = 0;
    }
    isSpeaking = false;
    btnSpeak.classList.remove('speaking');
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
        // 토글 ON 시 사용자 제스처로 <audio> 활성화 (모바일 autoplay 우회)
        if (isTTSEnabled) {
            warmUpAudioElement();
        }
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
        warmUpAudioElement();
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

}
