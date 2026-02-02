# -*- coding: utf-8 -*-
"""
QR 기반 청중용 실시간 번역 TTS 웹 서버
ngrok 자동 터널링 지원
"""
import socket
import threading
import qrcode
import io
import base64
import os
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

# ngrok 지원
try:
    from pyngrok import ngrok, conf
    NGROK_SUPPORT = True
except ImportError:
    NGROK_SUPPORT = False
    print("[INFO] pyngrok not installed. Public URL disabled.")

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
        self.public_url = None  # ngrok URL
        self.server_url = None  # 실제 사용할 URL
        self.qr_code_base64 = None
        self.ngrok_tunnel = None
        self.use_ngrok = False

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

    def start(self, use_ngrok=True):
        """서버 시작

        Args:
            use_ngrok: True면 ngrok 터널 생성 (외부 접속 가능)
        """
        if self.is_running:
            return

        self.use_ngrok = use_ngrok

        # 로컬 URL 설정
        local_ip = get_local_ip()
        self.local_url = f"http://{local_ip}:{self.port}"

        # Flask 서버 시작
        def run_server():
            socketio.run(app, host='0.0.0.0', port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.is_running = True
        print(f"[WebServer] Local server started at {self.local_url}")

        # ngrok 터널 시작
        if use_ngrok and NGROK_SUPPORT:
            self._start_ngrok()

        # 사용할 URL 결정 (ngrok 우선)
        if self.public_url:
            self.server_url = self.public_url
        else:
            self.server_url = self.local_url

        # QR 코드 생성
        self.qr_code_base64 = generate_qr_code(self.server_url)
        print(f"[WebServer] QR URL: {self.server_url}")

    def _start_ngrok(self):
        """ngrok 터널 시작"""
        try:
            # 기존 터널 정리
            try:
                tunnels = ngrok.get_tunnels()
                for tunnel in tunnels:
                    ngrok.disconnect(tunnel.public_url)
            except:
                pass

            # ngrok authtoken 설정 (환경변수에서)
            auth_token = os.getenv("NGROK_AUTH_TOKEN")
            if auth_token:
                ngrok.set_auth_token(auth_token)
                print("[ngrok] Auth token configured")

            # 터널 생성
            self.ngrok_tunnel = ngrok.connect(self.port, "http")
            self.public_url = self.ngrok_tunnel.public_url

            # HTTPS로 변환 (ngrok은 기본적으로 https 제공)
            if self.public_url.startswith("http://"):
                self.public_url = self.public_url.replace("http://", "https://")

            print(f"[ngrok] Public URL: {self.public_url}")

        except Exception as e:
            print(f"[ngrok] Failed to start tunnel: {e}")
            print("[ngrok] Falling back to local URL")
            self.public_url = None

    def stop(self):
        """서버 중지"""
        if self.ngrok_tunnel:
            try:
                ngrok.disconnect(self.ngrok_tunnel.public_url)
                print("[ngrok] Tunnel disconnected")
            except:
                pass
        self.is_running = False
        print("[WebServer] Stopped")

    def get_qr_code(self):
        """QR 코드 이미지 (Base64) 반환"""
        return self.qr_code_base64

    def get_url(self):
        """서버 URL 반환 (ngrok URL 우선)"""
        return self.server_url

    def get_local_url(self):
        """로컬 URL 반환"""
        return self.local_url

    def get_public_url(self):
        """공개 URL (ngrok) 반환"""
        return self.public_url

    def get_client_count(self):
        """연결된 클라이언트 수 반환"""
        return connected_clients

    def is_public(self):
        """외부 접속 가능 여부"""
        return self.public_url is not None

    def refresh_qr(self, use_public=True):
        """QR 코드 새로고침

        Args:
            use_public: True면 ngrok URL, False면 로컬 URL 사용
        """
        if use_public and self.public_url:
            self.server_url = self.public_url
        else:
            self.server_url = self.local_url

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
