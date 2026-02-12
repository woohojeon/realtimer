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

# ngrok 지원
try:
    from pyngrok import ngrok as pyngrok, conf as pyngrok_conf
    NGROK_AVAILABLE = True
    # .env에서 auth token 설정
    ngrok_token = os.environ.get('NGROK_AUTH_TOKEN', '')
    if ngrok_token:
        pyngrok_conf.get_default().auth_token = ngrok_token
        print("[WebServer] ngrok auth token loaded.")
    else:
        print("[WebServer] NGROK_AUTH_TOKEN not found in .env")
        NGROK_AVAILABLE = False
except ImportError:
    NGROK_AVAILABLE = False
    print("[WebServer] pyngrok not installed. External access disabled.")

# Flask 앱 설정
app = Flask(__name__)
app.config['SECRET_KEY'] = 'lecture-lens-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

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
        self.ngrok_tunnel = None

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
        """서버 시작 (ngrok 터널로 외부 접속 지원)"""
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

        # ngrok 터널 시작 (별도 스레드에서 실행하여 메인 기능에 영향 없도록)
        if NGROK_AVAILABLE:
            def start_ngrok_tunnel():
                import time
                print("[WebServer] Waiting for server ready...")
                time.sleep(2)
                try:
                    print("[WebServer] Starting ngrok tunnel...")
                    # PyInstaller frozen 환경에서 subprocess 문제 회피
                    if IS_FROZEN:
                        import os
                        os.environ['PYTHONIOENCODING'] = 'utf-8'
                    self.ngrok_tunnel = pyngrok.connect(self.port, "http")
                    self.public_url = self.ngrok_tunnel.public_url
                    self.server_url = self.public_url
                    self.qr_code_base64 = generate_qr_code(self.server_url)
                    print(f"[WebServer] ngrok tunnel: {self.public_url}")
                except Exception as e:
                    import traceback
                    print(f"[WebServer] ngrok failed, using local URL: {e}")
                    traceback.print_exc()
                    self.public_url = None
                    # ngrok 실패해도 local URL로 계속 동작
                    print(f"[WebServer] Continuing with local URL: {self.local_url}")

            # 별도 스레드에서 ngrok 시작 (메인 기능 블로킹 방지)
            ngrok_thread = threading.Thread(target=start_ngrok_tunnel, daemon=True)
            ngrok_thread.start()

        # QR 코드 생성
        self.qr_code_base64 = generate_qr_code(self.server_url)
        print(f"[WebServer] QR URL: {self.server_url}")

    def stop(self):
        """서버 중지"""
        if self.ngrok_tunnel and NGROK_AVAILABLE:
            try:
                pyngrok.disconnect(self.ngrok_tunnel.public_url)
            except Exception:
                pass
            self.ngrok_tunnel = None
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
