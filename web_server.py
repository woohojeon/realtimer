# -*- coding: utf-8 -*-
"""
QR 기반 청중용 실시간 번역 TTS 웹 서버
같은 Wi-Fi 또는 외부 네트워크에서 ngrok 터널로 접속
"""
import socket
import threading
import qrcode
import io
import base64
import os
import azure.cognitiveservices.speech as speechsdk
from xml.sax.saxutils import escape as xml_escape
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

# PyInstaller frozen exe 감지
import sys
import subprocess

IS_FROZEN = getattr(sys, 'frozen', False)

# .env 로드 (exe 빌드 시 _internal 폴더 기준)
from dotenv import load_dotenv
if getattr(sys, 'frozen', False):
    _base_dir = sys._MEIPASS
else:
    _base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_base_dir, '.env'))

import re

# cloudflared 지원 확인
CLOUDFLARED_AVAILABLE = False
try:
    _cf_check = subprocess.run(['cloudflared', '--version'], capture_output=True, text=True, timeout=5)
    if _cf_check.returncode == 0:
        CLOUDFLARED_AVAILABLE = True
        print(f"[WebServer] cloudflared found: {_cf_check.stdout.strip()}")
except (FileNotFoundError, subprocess.TimeoutExpired):
    print("[WebServer] cloudflared not installed. External access disabled.")

# Flask 앱 설정
app = Flask(__name__)
app.config['SECRET_KEY'] = 'lecture-lens-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Azure Neural TTS 음성 매핑 (voice_name, xml:lang locale)
NEURAL_VOICES = {
    'ko': ('ko-KR-SunHiNeural', 'ko-KR'),
    'en': ('en-US-JennyNeural', 'en-US'),
    'ja': ('ja-JP-NanamiNeural', 'ja-JP'),
    'zh': ('zh-CN-XiaoxiaoNeural', 'zh-CN'),
    'es': ('es-ES-ElviraNeural', 'es-ES'),
    'fr': ('fr-FR-DeniseNeural', 'fr-FR'),
    'de': ('de-DE-KatjaNeural', 'de-DE'),
    'pt': ('pt-BR-FranciscaNeural', 'pt-BR'),
    'ru': ('ru-RU-SvetlanaNeural', 'ru-RU'),
    'vi': ('vi-VN-HoaiMyNeural', 'vi-VN'),
}

# 전역 상태
connected_clients = 0
available_languages = {}
current_subtitles = {}
source_language_info = {}


def get_local_ip():
    """로컬 네트워크 IP 주소 가져오기"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def generate_qr_code(url):
    """QR 코드 생성 (Base64 이미지 반환)"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # 이미지를 Base64로 변환
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return f"data:image/png;base64,{img_base64}"


class WebServer:
    """청중용 웹 서버 클래스"""

    def __init__(self, port=5000):
        self.port = port
        self.server_thread = None
        self.is_running = False
        self.local_url = None
        self.public_url = None
        self.server_url = None
        self.qr_code_base64 = None
        self._cf_process = None  # cloudflared 프로세스

    def set_languages(self, languages_dict, source_lang, target_langs):
        """사용 가능한 언어 설정"""
        global available_languages, source_language_info
        available_languages = {
            code: languages_dict[code]
            for code in target_langs
            if code in languages_dict
        }
        source_language_info = languages_dict.get(source_lang, {})

    def broadcast_subtitle(self, msg_type, data):
        """모든 클라이언트에게 자막 브로드캐스트"""
        global current_subtitles

        if msg_type in ("realtime", "final"):
            current_subtitles = data if isinstance(data, dict) else {}
            socketio.emit('subtitle_update', {
                'type': msg_type,
                'data': data,
                'source_lang': source_language_info
            })
        elif msg_type == "recognized":
            socketio.emit('subtitle_update', {
                'type': 'processing',
                'data': {},
                'source_lang': source_language_info
            })

    def start(self):
        """서버 시작 (cloudflared 터널로 외부 접속 지원)"""
        if self.is_running:
            return

        # 로컬 URL 설정
        local_ip = get_local_ip()
        self.local_url = f"http://{local_ip}:{self.port}"
        self.server_url = self.local_url

        # Flask 서버 시작
        def run_server():
            socketio.run(app, host='0.0.0.0', port=self.port, debug=False,
                         use_reloader=False, allow_unsafe_werkzeug=True)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.is_running = True
        print(f"[WebServer] Local server started at {self.local_url}")

        # cloudflared 터널 시작 (별도 스레드, 완료 시 이벤트 통지)
        self._tunnel_ready = threading.Event()
        if CLOUDFLARED_AVAILABLE:
            def start_cloudflared_tunnel():
                import time
                print("[WebServer] Waiting for server ready...")
                time.sleep(2)
                try:
                    print("[WebServer] Starting cloudflared tunnel...")
                    self._cf_process = subprocess.Popen(
                        ['cloudflared', 'tunnel', '--url', f'http://localhost:{self.port}'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    # cloudflared 출력에서 public URL 파싱
                    for line in self._cf_process.stdout:
                        match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                        if match:
                            self.public_url = match.group(0)
                            self.server_url = self.public_url
                            print(f"[WebServer] cloudflared tunnel: {self.public_url}")
                            break
                    if not self.public_url:
                        print("[WebServer] cloudflared: URL not found, using local URL")
                except Exception as e:
                    print(f"[WebServer] cloudflared failed, using local URL: {e}")
                    self.public_url = None
                finally:
                    self._tunnel_ready.set()

            threading.Thread(target=start_cloudflared_tunnel, daemon=True).start()
        else:
            self._tunnel_ready.set()

        # 터널 완료 대기 후 QR 생성 (별도 스레드 — UI 블로킹 방지)
        def wait_and_generate_qr():
            self._tunnel_ready.wait(timeout=20)
            self.qr_code_base64 = generate_qr_code(self.server_url)
            print(f"[WebServer] QR URL: {self.server_url}")

        threading.Thread(target=wait_and_generate_qr, daemon=True).start()

    def stop(self):
        """서버 중지"""
        if self._cf_process:
            try:
                self._cf_process.terminate()
                self._cf_process.wait(timeout=5)
            except Exception:
                pass
            self._cf_process = None
        self.is_running = False
        print("[WebServer] Stopped")

    def get_qr_code(self):
        """QR 코드 이미지 (Base64) 반환"""
        return self.qr_code_base64

    def get_url(self):
        """서버 URL 반환"""
        return self.server_url

    def get_local_url(self):
        """로컬 URL 반환"""
        return self.local_url

    def get_public_url(self):
        """공개 URL 반환"""
        return self.public_url

    def get_client_count(self):
        """연결된 클라이언트 수 반환"""
        return connected_clients

    def is_public(self):
        """외부 접속 가능 여부"""
        return self.public_url is not None

    def refresh_qr(self, use_public=True):
        """QR 코드 새로고침"""
        self.qr_code_base64 = generate_qr_code(self.server_url)
        return self.server_url


# 웹 서버 싱글톤 인스턴스
web_server = WebServer()


# ========================
# Flask Routes
# ========================
@app.route('/')
def index():
    """청중용 메인 페이지"""
    return render_template('audience.html')


@app.route('/api/languages')
def get_languages():
    """사용 가능한 언어 목록 반환"""
    return jsonify({
        'languages': available_languages,
        'source': source_language_info
    })


@app.route('/api/current')
def get_current():
    """현재 자막 상태 반환"""
    return jsonify({
        'subtitles': current_subtitles,
        'source': source_language_info
    })


# ========================
# SocketIO Events
# ========================
@socketio.on('connect')
def handle_connect():
    """클라이언트 연결"""
    global connected_clients
    connected_clients += 1
    print(f"[WebServer] Client connected. Total: {connected_clients}")
    # 현재 자막 전송
    emit('subtitle_update', {
        'type': 'current',
        'data': current_subtitles,
        'source_lang': source_language_info
    })


@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제"""
    global connected_clients
    connected_clients = max(0, connected_clients - 1)
    print(f"[WebServer] Client disconnected. Total: {connected_clients}")


@socketio.on('request_languages')
def handle_request_languages():
    """언어 목록 요청"""
    emit('languages_update', {
        'languages': available_languages,
        'source': source_language_info
    })


@socketio.on('request_tts')
def handle_request_tts(data):
    """Azure Neural TTS 음성 합성 요청"""
    text = data.get('text', '')
    lang = data.get('lang', 'en')
    speed = data.get('speed', 1.0)
    print(f"[TTS] Request received: lang={lang}, speed={speed}, text='{text[:50]}'")

    if not text:
        emit('tts_error', {'error': 'No text provided'})
        return

    try:
        speech_key = os.environ.get('SPEECH_KEY', '')
        speech_region = os.environ.get('SPEECH_REGION', 'eastus')
        if not speech_key:
            print("[TTS] ERROR: SPEECH_KEY not set")
            emit('tts_error', {'error': 'Azure Speech key not configured'})
            return

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )

        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        voice_name, voice_locale = NEURAL_VOICES.get(lang, ('en-US-JennyNeural', 'en-US'))
        rate_percent = int((speed - 1.0) * 100)
        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

        safe_text = xml_escape(text)
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{voice_locale}">
  <voice name="{voice_name}">
    <prosody rate="{rate_str}">{safe_text}</prosody>
  </voice>
</speak>"""

        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_b64 = base64.b64encode(result.audio_data).decode('utf-8')
            print(f"[TTS] Success: {len(result.audio_data)} bytes → sending to client")
            emit('tts_audio', {'audio': audio_b64, 'format': 'mp3'})
        else:
            cancellation = result.cancellation_details
            print(f"[TTS] Synthesis failed: {cancellation.reason} - {cancellation.error_details}")
            emit('tts_error', {'error': 'Synthesis failed'})
    except Exception as e:
        print(f"[TTS] Error: {e}")
        emit('tts_error', {'error': str(e)})
