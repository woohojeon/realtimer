# -*- coding: utf-8 -*-
import azure.cognitiveservices.speech as speechsdk
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import threading
import queue
from openai import OpenAI
import anthropic
from collections import deque
import os
import json
from dotenv import load_dotenv
import sys
import time
import ctypes

# 웹 서버 (청중용 QR TTS)
try:
    from web_server import web_server
    WEB_SERVER_SUPPORT = True
except Exception as e:
    WEB_SERVER_SUPPORT = False

# ========================
# Windows 둥근 모서리 및 리사이즈 헬퍼
# ========================
def apply_rounded_corners(window, radius=10):
    """Windows에서 창에 둥근 모서리 적용"""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        # Windows 11 스타일 둥근 모서리
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), ctypes.sizeof(ctypes.c_int)
        )
    except:
        # Windows 10 이하: SetWindowRgn 사용
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            width = window.winfo_width()
            height = window.winfo_height()
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except:
            pass


class ResizableWindow:
    """창 가장자리 리사이즈 기능을 추가하는 믹스인 클래스"""
    EDGE_SIZE = 6  # 가장자리 감지 영역 크기

    def setup_resizable(self, min_width=400, min_height=300):
        """리사이즈 기능 설정"""
        self.min_width = min_width
        self.min_height = min_height
        self.resize_edge = None
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_w = 0
        self.resize_start_h = 0
        self.resize_start_pos_x = 0
        self.resize_start_pos_y = 0

        # 마우스 이동 및 클릭 이벤트 바인딩
        self.root.bind("<Motion>", self._on_mouse_move)
        self.root.bind("<Button-1>", self._on_mouse_down)
        self.root.bind("<B1-Motion>", self._on_mouse_drag)
        self.root.bind("<ButtonRelease-1>", self._on_mouse_up)

    def _get_edge(self, x, y):
        """마우스 위치에 따른 가장자리 방향 반환"""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        edge = ""

        if y < self.EDGE_SIZE:
            edge += "n"
        elif y > h - self.EDGE_SIZE:
            edge += "s"

        if x < self.EDGE_SIZE:
            edge += "w"
        elif x > w - self.EDGE_SIZE:
            edge += "e"

        return edge if edge else None

    def _get_cursor(self, edge):
        """가장자리에 따른 커서 반환"""
        cursors = {
            "n": "top_side",
            "s": "bottom_side",
            "e": "right_side",
            "w": "left_side",
            "ne": "top_right_corner",
            "nw": "top_left_corner",
            "se": "bottom_right_corner",
            "sw": "bottom_left_corner",
        }
        return cursors.get(edge, "")

    def _is_root_alive(self):
        """root 윈도우가 아직 유효한지 확인"""
        try:
            return self.root.winfo_exists()
        except:
            return False

    def _on_mouse_move(self, event):
        """마우스 이동 시 커서 변경"""
        if not self._is_root_alive():
            return
        if hasattr(self, '_is_dragging') and self._is_dragging:
            return

        edge = self._get_edge(event.x, event.y)
        if edge:
            cursor = self._get_cursor(edge)
            self.root.config(cursor=cursor)
        else:
            self.root.config(cursor="")

    def _on_mouse_down(self, event):
        """마우스 클릭 시 리사이즈 시작"""
        if not self._is_root_alive():
            return
        edge = self._get_edge(event.x, event.y)
        if edge:
            self.resize_edge = edge
            self.resize_start_x = event.x_root
            self.resize_start_y = event.y_root
            self.resize_start_w = self.root.winfo_width()
            self.resize_start_h = self.root.winfo_height()
            self.resize_start_pos_x = self.root.winfo_x()
            self.resize_start_pos_y = self.root.winfo_y()
            self._is_dragging = True

    def _on_mouse_drag(self, event):
        """마우스 드래그 시 리사이즈"""
        if not self._is_root_alive():
            return
        if not self.resize_edge:
            return

        dx = event.x_root - self.resize_start_x
        dy = event.y_root - self.resize_start_y

        new_x = self.resize_start_pos_x
        new_y = self.resize_start_pos_y
        new_w = self.resize_start_w
        new_h = self.resize_start_h

        # 방향에 따른 크기/위치 계산
        if "e" in self.resize_edge:
            new_w = max(self.min_width, self.resize_start_w + dx)
        if "w" in self.resize_edge:
            new_w = max(self.min_width, self.resize_start_w - dx)
            if new_w > self.min_width:
                new_x = self.resize_start_pos_x + dx
        if "s" in self.resize_edge:
            new_h = max(self.min_height, self.resize_start_h + dy)
        if "n" in self.resize_edge:
            new_h = max(self.min_height, self.resize_start_h - dy)
            if new_h > self.min_height:
                new_y = self.resize_start_pos_y + dy

        self.root.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")

        # 자막 창의 경우 wraplength 업데이트
        if hasattr(self, 'subtitle_label'):
            try:
                self.subtitle_label.config(wraplength=new_w - 60)
            except:
                pass

    def _on_mouse_up(self, event):
        """마우스 버튼 해제 시 리사이즈 종료"""
        if not self._is_root_alive():
            return
        self.resize_edge = None
        self._is_dragging = False

        # 둥근 모서리 다시 적용 (Windows 10)
        self.root.after(10, lambda: apply_rounded_corners(self.root))

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    try:
        import PyPDF2
        PDF_SUPPORT = True
    except ImportError:
        PDF_SUPPORT = False

# 드래그 앤 드롭 지원
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False

# ========================
# 1. API 설정 (환경 변수에서 자동 로드)
# ========================
if getattr(sys, 'frozen', False):
    _base_dir = sys._MEIPASS
else:
    _base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_base_dir, '.env'))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

# API 키 검증
if not OPENAI_API_KEY or not SPEECH_KEY or not SPEECH_REGION:
    sys.exit(1)

# ========================
# 2. 글로벌 변수
# ========================
subtitle_queue = queue.Queue()
is_listening = False
client = OpenAI(api_key=OPENAI_API_KEY)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
history = deque(maxlen=5)
last_realtime_translation = ''
terminology_list = []  # 전문용어 리스트 (영어)

# 모델 호환성 자동 감지
_model_lower = OPENAI_MODEL.lower()
_is_reasoning_model = _model_lower.startswith(('o1', 'o3', 'o4', 'gpt-5'))
_no_temperature = _is_reasoning_model

def _llm_call(messages, temperature=0.0, max_tokens_val=500):
    """OpenAI API 호출 래퍼 (모델 비호환 파라미터 자동 감지/제거)"""
    global _no_temperature

    def _build_kwargs():
        kwargs = {"model": OPENAI_MODEL, "messages": messages}
        if not _no_temperature:
            kwargs["temperature"] = temperature
        kwargs["max_completion_tokens"] = max_tokens_val
        return kwargs

    last_error = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(**_build_kwargs())
        except Exception as e:
            last_error = e
            err = str(e)
            changed = False
            if 'temperature' in err and 'unsupported' in err.lower():
                _no_temperature = True
                changed = True
            if not changed:
                raise
    raise last_error

# 다국어 설정
LANGUAGES = {
    'ko': {'name': '한국어', 'code': 'ko-KR', 'flag': '🇰🇷'},
    'en': {'name': 'English', 'code': 'en-US', 'flag': '🇺🇸'},
    'ja': {'name': '日本語', 'code': 'ja-JP', 'flag': '🇯🇵'},
    'zh': {'name': '中文', 'code': 'zh-CN', 'flag': '🇨🇳'},
    'es': {'name': 'Español', 'code': 'es-ES', 'flag': '🇪🇸'},
    'fr': {'name': 'Français', 'code': 'fr-FR', 'flag': '🇫🇷'},
    'de': {'name': 'Deutsch', 'code': 'de-DE', 'flag': '🇩🇪'},
    'pt': {'name': 'Português', 'code': 'pt-BR', 'flag': '🇧🇷'},
    'ru': {'name': 'Русский', 'code': 'ru-RU', 'flag': '🇷🇺'},
    'vi': {'name': 'Tiếng Việt', 'code': 'vi-VN', 'flag': '🇻🇳'},
}
source_language = 'ko'  # 소스 언어
target_languages = ['en']  # 타겟 언어 리스트 (여러 개 선택 가능)
selected_mic_id = None  # 선택된 마이크 장치 ID (None=시스템 기본)

# sounddevice 지원
try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False


def get_microphone_list():
    """시스템 마이크/입력 장치 목록 반환 [{'name': ..., 'id': index or None}, ...]"""
    devices = [{'name': 'System Default', 'id': None}]
    if not SD_AVAILABLE:
        return devices
    try:
        # Windows MME (hostapi 0) 입력 장치만 필터
        all_devs = sd.query_devices()
        for i, d in enumerate(all_devs):
            if d['max_input_channels'] > 0 and d['hostapi'] == 0:
                devices.append({'name': d['name'], 'id': i})
    except Exception as e:
        pass
    return devices

# ========================
# 색상 테마
# ========================
COLORS_LIGHT = {
    'bg_main': '#F7F8FC',
    'bg_white': '#FFFFFF',
    'bg_card': '#FFFFFF',
    'bg_btn': '#FEFEFE',  # 버튼용 (bg_card와 거의 동일, 투명 처리 안됨)
    'bg_input': '#F0F1F5',
    'primary': '#7C5CFC',
    'primary_hover': '#6B4FE0',
    'secondary': '#5B8DEF',
    'accent_mint': '#4ECDC4',
    'accent_coral': '#FF6B6B',
    'text_primary': '#2D3748',
    'text_secondary': '#718096',
    'text_dim': '#A0AEC0',
    'border': '#E2E8F0',
    'danger': '#FC5C65',
    'success': '#26DE81',
}

COLORS_DARK = {
    'bg_main': '#1a1a2e',
    'bg_white': '#16213e',
    'bg_card': '#1f2940',
    'bg_btn': '#1f2941',  # 버튼용 (bg_card와 거의 동일, 투명 처리 안됨)
    'bg_input': '#2a3a5a',
    'primary': '#7C5CFC',
    'primary_hover': '#9B7DFF',
    'secondary': '#5B8DEF',
    'accent_mint': '#4ECDC4',
    'accent_coral': '#FF6B6B',
    'text_primary': '#E8E8E8',
    'text_secondary': '#A0AEC0',
    'text_dim': '#6B7280',
    'border': '#3a4a6a',
    'danger': '#FC5C65',
    'success': '#26DE81',
}

# 현재 테마 (기본: 라이트)
is_dark_mode = True
COLORS = COLORS_LIGHT.copy()

def set_theme(dark_mode):
    """테마 변경"""
    global COLORS, is_dark_mode
    is_dark_mode = dark_mode
    if dark_mode:
        COLORS = COLORS_DARK.copy()
    else:
        COLORS = COLORS_LIGHT.copy()

# ========================
# 단어장 저장/불러오기
# ========================
GLOSSARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glossary.json')

def load_glossary():
    """저장된 단어장 불러오기"""
    try:
        if os.path.exists(GLOSSARY_FILE):
            with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception as e:
        pass
    return []

def save_glossary(terms):
    """단어장 파일로 저장"""
    try:
        with open(GLOSSARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass

# ========================
# 3. PDF 전문용어 추출
# ========================
def extract_text_from_pdf(filepath):
    """PDF에서 텍스트 추출"""
    text = ""
    try:
        if 'pdfplumber' in sys.modules:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        elif 'PyPDF2' in sys.modules:
            import PyPDF2
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
    except Exception as e:
        pass
    return text


def extract_terminology_with_gpt(text):
    """GPT로 전문용어 추출"""
    try:

        prompt = f"""다음 텍스트에서 전문용어(영어)를 추출하세요.
의학, 수의학, 과학 분야의 전문 용어만 추출하세요.
한 줄에 하나씩, 영어 용어만 출력하세요. 설명 없이 용어만.
최대 30개까지만 추출하세요.

텍스트:
{text[:4000]}"""

        resp = _llm_call([{"role": "user", "content": prompt}], temperature=0.0, max_tokens_val=500)

        result = resp.choices[0].message.content.strip()

        # 코드 블록 마커 제거
        result = result.replace('```', '')

        terms = []
        for line in result.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 불릿 포인트 제거 (-, *, •, 숫자. 등)
            if line.startswith(('-', '*', '•')):
                line = line[1:].strip()
            elif len(line) > 2 and line[0].isdigit() and line[1] in '.):':
                line = line[2:].strip()
            elif len(line) > 3 and line[:2].isdigit() and line[2] in '.):':
                line = line[3:].strip()

            if len(line) > 1:
                terms.append(line)

        # 중복 제거 및 정리
        terms = list(dict.fromkeys(terms))
        return terms
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


class TermSelectionModal:
    """전문용어 선택 모달 (현대적 디자인)"""
    def __init__(self, parent, terms):
        self.result = []
        self.terms = terms
        self.check_items = []  # (term, var, checkbox_frame, icon_label)

        self.modal = tk.Toplevel(parent)
        self.modal.overrideredirect(True)  # 기본 타이틀바 제거
        self.modal.configure(bg=COLORS['bg_main'])
        self.modal.transient(parent)

        # 창 크기 및 위치 (화면 중앙)
        width, height = 480, 580
        screen_w = self.modal.winfo_screenwidth()
        screen_h = self.modal.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.modal.geometry(f"{width}x{height}+{x}+{y}")

        # 드래그 변수
        self.drag_x = 0
        self.drag_y = 0

        # 모달 표시 후 포커스
        self.modal.deiconify()
        self.modal.lift()
        self.modal.focus_force()
        self.modal.grab_set()

        self.setup_ui()

        # 둥근 모서리 적용
        self.modal.update_idletasks()
        apply_rounded_corners(self.modal)

    def setup_ui(self):
        # 커스텀 타이틀바
        titlebar = tk.Frame(self.modal, bg=COLORS['bg_white'], height=45)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        # 타이틀바 드래그
        titlebar.bind("<Button-1>", self.start_drag)
        titlebar.bind("<B1-Motion>", self.on_drag)

        # 타이틀 텍스트
        title_label = tk.Label(
            titlebar,
            text="Select Terms",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_white']
        )
        title_label.pack(side="left", padx=20)
        title_label.bind("<Button-1>", self.start_drag)
        title_label.bind("<B1-Motion>", self.on_drag)

        # 닫기 버튼
        close_btn = tk.Label(
            titlebar,
            text="✕",
            font=("Segoe UI", 11),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_white'],
            cursor="hand2",
            padx=15
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.cancel())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLORS['danger']))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLORS['text_dim']))

        # 컨테이너
        container = tk.Frame(self.modal, bg=COLORS['bg_main'])
        container.pack(fill="both", expand=True, padx=25, pady=20)

        # 헤더
        header_frame = tk.Frame(container, bg=COLORS['bg_main'])
        header_frame.pack(fill="x", pady=(0, 5))

        tk.Label(
            header_frame,
            text=f"Found {len(self.terms)} terms",
            font=("Segoe UI", 16, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_main']
        ).pack(side="left")

        # 선택 카운트
        self.count_label = tk.Label(
            header_frame,
            text="0 selected",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_main']
        )
        self.count_label.pack(side="right")

        tk.Label(
            container,
            text="Select terms to add to your terminology list",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_main']
        ).pack(anchor="w", pady=(0, 15))

        # 모두 선택 토글 (현대적 스타일)
        select_all_frame = tk.Frame(container, bg=COLORS['bg_main'])
        select_all_frame.pack(fill="x", pady=(0, 12))

        self.select_all_var = tk.BooleanVar(value=False)
        self.select_all_btn = tk.Frame(select_all_frame, bg=COLORS['bg_input'], cursor="hand2")
        self.select_all_btn.pack(side="left")

        self.select_all_icon = tk.Label(
            self.select_all_btn,
            text="○",
            font=("Segoe UI", 12),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_input'],
            padx=10,
            pady=6
        )
        self.select_all_icon.pack(side="left")

        self.select_all_text = tk.Label(
            self.select_all_btn,
            text="Select All",
            font=("Segoe UI", 10),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_input'],
            padx=10,
            pady=6
        )
        self.select_all_text.pack(side="left")

        # 클릭 이벤트
        for widget in [self.select_all_btn, self.select_all_icon, self.select_all_text]:
            widget.bind("<Button-1>", lambda e: self.toggle_all())
            widget.bind("<Enter>", lambda e: self._hover_select_all(True))
            widget.bind("<Leave>", lambda e: self._hover_select_all(False))

        # 카드 영역
        card = tk.Frame(container, bg=COLORS['bg_card'])
        card.pack(fill="both", expand=True)

        # 스크롤 가능한 체크박스 목록
        canvas_frame = tk.Frame(card, bg=COLORS['bg_card'])
        canvas_frame.pack(fill="both", expand=True, padx=15, pady=15)

        self.canvas = tk.Canvas(canvas_frame, bg=COLORS['bg_card'], highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.checkbox_frame = tk.Frame(self.canvas, bg=COLORS['bg_card'])

        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        canvas_window = self.canvas.create_window((0, 0), window=self.checkbox_frame, anchor="nw")
        self.checkbox_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(canvas_window, width=e.width))

        # 마우스 휠 스크롤 바인딩
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.checkbox_frame.bind("<MouseWheel>", self._on_mousewheel)

        # 체크박스 생성 (현대적 스타일)
        for term in self.terms:
            var = tk.BooleanVar(value=False)
            item_frame = tk.Frame(self.checkbox_frame, bg=COLORS['bg_card'], cursor="hand2")
            item_frame.pack(fill="x", pady=2)

            # 체크 아이콘
            icon_label = tk.Label(
                item_frame,
                text="○",
                font=("Segoe UI", 11),
                fg=COLORS['text_dim'],
                bg=COLORS['bg_card'],
                padx=8,
                pady=8
            )
            icon_label.pack(side="left")

            # 용어 텍스트
            text_label = tk.Label(
                item_frame,
                text=term,
                font=("Segoe UI", 10),
                fg=COLORS['text_primary'],
                bg=COLORS['bg_card'],
                anchor="w",
                pady=8
            )
            text_label.pack(side="left", fill="x", expand=True)

            # 클릭 이벤트 바인딩
            def make_toggle(v, f, i):
                return lambda e: self._toggle_item(v, f, i)

            def make_hover(f, i, entering):
                return lambda e: self._hover_item(f, i, entering)

            for widget in [item_frame, icon_label, text_label]:
                widget.bind("<Button-1>", make_toggle(var, item_frame, icon_label))
                widget.bind("<Enter>", make_hover(item_frame, icon_label, True))
                widget.bind("<Leave>", make_hover(item_frame, icon_label, False))
                widget.bind("<MouseWheel>", self._on_mousewheel)

            self.check_items.append((term, var, item_frame, icon_label))

        # 버튼 프레임
        btn_frame = tk.Frame(container, bg=COLORS['bg_main'])
        btn_frame.pack(fill="x", pady=(15, 0))

        # 취소 버튼
        cancel_btn = tk.Label(
            btn_frame,
            text="Cancel",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_main'],
            cursor="hand2",
            padx=20,
            pady=10
        )
        cancel_btn.pack(side="right", padx=(10, 0))
        cancel_btn.bind("<Button-1>", lambda e: self.cancel())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(fg=COLORS['danger']))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(fg=COLORS['text_secondary']))

        # 확인 버튼
        confirm_btn = tk.Label(
            btn_frame,
            text="Add Selected",
            font=("Segoe UI", 10, "bold"),
            fg=COLORS['bg_white'],
            bg=COLORS['primary'],
            cursor="hand2",
            padx=20,
            pady=10
        )
        confirm_btn.pack(side="right")
        confirm_btn.bind("<Button-1>", lambda e: self.confirm())
        confirm_btn.bind("<Enter>", lambda e: confirm_btn.config(bg=COLORS['primary_hover']))
        confirm_btn.bind("<Leave>", lambda e: confirm_btn.config(bg=COLORS['primary']))

    def start_drag(self, event):
        """드래그 시작"""
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        """드래그 이동"""
        x = self.modal.winfo_x() + event.x - self.drag_x
        y = self.modal.winfo_y() + event.y - self.drag_y
        self.modal.geometry(f"+{x}+{y}")

    def _hover_select_all(self, entering):
        """Select All 호버 효과"""
        if entering:
            self.select_all_btn.config(bg=COLORS['border'])
            self.select_all_icon.config(bg=COLORS['border'])
            self.select_all_text.config(bg=COLORS['border'])
        else:
            self.select_all_btn.config(bg=COLORS['bg_input'])
            self.select_all_icon.config(bg=COLORS['bg_input'])
            self.select_all_text.config(bg=COLORS['bg_input'])

    def _toggle_item(self, var, frame, icon):
        """체크박스 토글"""
        new_state = not var.get()
        var.set(new_state)
        if new_state:
            icon.config(text="●", fg=COLORS['primary'])
            frame.config(bg=COLORS['bg_input'])
            for child in frame.winfo_children():
                child.config(bg=COLORS['bg_input'])
        else:
            icon.config(text="○", fg=COLORS['text_dim'])
            frame.config(bg=COLORS['bg_card'])
            for child in frame.winfo_children():
                child.config(bg=COLORS['bg_card'])
        self._update_count()

    def _hover_item(self, frame, icon, entering):
        """아이템 호버 효과"""
        var = None
        for term, v, f, i in self.check_items:
            if f == frame:
                var = v
                break
        if var and not var.get():
            if entering:
                frame.config(bg=COLORS['bg_input'])
                for child in frame.winfo_children():
                    child.config(bg=COLORS['bg_input'])
            else:
                frame.config(bg=COLORS['bg_card'])
                for child in frame.winfo_children():
                    child.config(bg=COLORS['bg_card'])

    def _update_count(self):
        """선택 개수 업데이트"""
        count = sum(1 for _, var, _, _ in self.check_items if var.get())
        self.count_label.config(text=f"{count} selected")

        # Select All 상태 업데이트
        all_selected = count == len(self.check_items)
        self.select_all_var.set(all_selected)
        if all_selected:
            self.select_all_icon.config(text="●", fg=COLORS['primary'])
        else:
            self.select_all_icon.config(text="○", fg=COLORS['text_dim'])

    def _on_mousewheel(self, event):
        """마우스 휠 스크롤"""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def toggle_all(self):
        """모두 선택/해제"""
        new_state = not self.select_all_var.get()
        self.select_all_var.set(new_state)

        for term, var, frame, icon in self.check_items:
            var.set(new_state)
            if new_state:
                icon.config(text="●", fg=COLORS['primary'])
                frame.config(bg=COLORS['bg_input'])
                for child in frame.winfo_children():
                    child.config(bg=COLORS['bg_input'])
            else:
                icon.config(text="○", fg=COLORS['text_dim'])
                frame.config(bg=COLORS['bg_card'])
                for child in frame.winfo_children():
                    child.config(bg=COLORS['bg_card'])

        # Select All 아이콘 업데이트
        if new_state:
            self.select_all_icon.config(text="●", fg=COLORS['primary'])
        else:
            self.select_all_icon.config(text="○", fg=COLORS['text_dim'])

        self._update_count()

    def confirm(self):
        """선택 확인"""
        self.result = [term for term, var, _, _ in self.check_items if var.get()]
        self.modal.destroy()

    def cancel(self):
        """취소"""
        self.result = []
        self.modal.destroy()

    def show(self):
        """모달 표시 및 결과 반환"""
        self.modal.wait_window()
        return self.result


# ========================
# 4. 설정 화면 (사이버펑크 스타일)
# ========================
class SettingsWindow(ResizableWindow):
    def __init__(self):
        # 드래그 앤 드롭 지원 시 TkinterDnD 사용
        if DND_SUPPORT:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        self.root.overrideredirect(True)  # 기본 타이틀바 제거
        self.root.configure(bg=COLORS['bg_main'])

        # 창 크기 및 위치
        window_width = 600
        window_height = 730  # 커스텀 타이틀바 높이 추가
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - window_width) // 2
        y = (screen_h - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(True, True)
        self.root.minsize(500, 630)

        # 단어집 데이터
        self.glossary_entries = []
        self.pdf_path = None

        # 결과 저장
        self.result = None

        # PDF 처리 결과 (스레드 통신용)
        self.pending_terms = None
        self.pending_filepath = None
        self.pending_pdf_item = None
        self.pdf_thread = None
        self.pdf_list = []  # 추가된 PDF 목록 [(filepath, frame, label), ...]
        self._pdf_batch_threads = []  # 배치 처리 중인 스레드 목록
        self._pdf_batch_terms = []    # 배치 처리에서 수집된 전체 용어
        self._pdf_batch_items = []    # 배치 처리 pdf_item 목록

        # 드래그 변수
        self.drag_x = 0
        self.drag_y = 0

        self.setup_ui()

        # 가장자리 리사이즈 기능 설정
        self.setup_resizable(min_width=50, min_height=50)

        # 둥근 모서리 적용
        self.root.update_idletasks()
        apply_rounded_corners(self.root)

        # 창을 맨 앞으로 가져오기
        self.root.after(100, self._bring_to_front)

    def _bring_to_front(self):
        """프로그램 실행 시 창을 맨 앞으로"""
        self.root.lift()
        self.root.focus_force()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except:
            pass

    def setup_ui(self):
        # 커스텀 타이틀바
        titlebar = tk.Frame(self.root, bg=COLORS['bg_white'], height=50)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        # 타이틀바 드래그
        titlebar.bind("<Button-1>", self.start_drag)
        titlebar.bind("<B1-Motion>", self.on_drag)

        # 로고 + 타이틀 컨테이너
        title_container = tk.Frame(titlebar, bg=COLORS['bg_white'])
        title_container.pack(side="left", padx=15)
        title_container.bind("<Button-1>", self.start_drag)
        title_container.bind("<B1-Motion>", self.on_drag)

        # 타이틀 텍스트
        title_label = tk.Label(
            title_container,
            text="Lecture Lens",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_white']
        )
        title_label.pack(side="left")
        title_label.bind("<Button-1>", self.start_drag)
        title_label.bind("<B1-Motion>", self.on_drag)

        # 버튼 컨테이너
        btn_container = tk.Frame(titlebar, bg=COLORS['bg_white'])
        btn_container.pack(side="right", padx=10)

        # 최소화 버튼
        minimize_btn = tk.Label(
            btn_container,
            text="─",
            font=("Segoe UI", 10),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_white'],
            cursor="hand2",
            padx=8
        )
        minimize_btn.pack(side="left", padx=2)
        minimize_btn.bind("<Button-1>", lambda e: self._minimize_window())
        minimize_btn.bind("<Enter>", lambda e: minimize_btn.config(fg=COLORS['primary']))
        minimize_btn.bind("<Leave>", lambda e: minimize_btn.config(fg=COLORS['text_dim']))

        # 닫기 버튼
        close_btn = tk.Label(
            btn_container,
            text="✕",
            font=("Segoe UI", 11),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_white'],
            cursor="hand2",
            padx=8
        )
        close_btn.pack(side="left", padx=2)
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLORS['danger']))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLORS['text_dim']))

        # 메인 컨테이너
        container = tk.Frame(self.root, bg=COLORS['bg_main'])
        container.pack(fill="both", expand=True, padx=30, pady=25)

        # 제목
        tk.Label(
            container,
            text="Hi!",
            font=("Segoe UI", 28, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_main']
        ).pack(anchor="w", pady=(0, 5))

        tk.Label(
            container,
            text="Configure your translation settings",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_main']
        ).pack(anchor="w", pady=(0, 20))

        # 언어 설정 섹션
        lang_section = tk.Frame(container, bg=COLORS['bg_main'])
        lang_section.pack(fill="x", pady=(0, 20))

        # 첫 번째 줄: 소스 언어 + 다크모드
        first_row = tk.Frame(lang_section, bg=COLORS['bg_main'])
        first_row.pack(fill="x", pady=(0, 10))

        # 소스 언어 드롭다운
        self.source_lang_var = tk.StringVar(value=source_language)
        source_info = LANGUAGES.get(source_language, {})

        self.source_dropdown_frame = tk.Frame(first_row, bg=COLORS['bg_input'], cursor="hand2")
        self.source_dropdown_frame.pack(side="left")

        self.source_dropdown_text = tk.Label(
            self.source_dropdown_frame,
            text=f"{source_info.get('flag', '')}  {source_info.get('name', '')}",
            font=("Segoe UI", 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_primary'],
            anchor="w",
            padx=15,
            pady=8
        )
        self.source_dropdown_text.pack(side="left")

        self.source_dropdown_arrow = tk.Label(
            self.source_dropdown_frame,
            text="▼",
            font=("Segoe UI", 8),
            bg=COLORS['bg_input'],
            fg=COLORS['text_dim'],
            padx=10
        )
        self.source_dropdown_arrow.pack(side="left")

        for w in [self.source_dropdown_frame, self.source_dropdown_text, self.source_dropdown_arrow]:
            w.bind("<Button-1>", lambda e: self.show_source_dropdown())
            w.bind("<Enter>", lambda e: self._hover_dropdown(self.source_dropdown_frame, self.source_dropdown_text, self.source_dropdown_arrow, True))
            w.bind("<Leave>", lambda e: self._hover_dropdown(self.source_dropdown_frame, self.source_dropdown_text, self.source_dropdown_arrow, False))

        # 화살표 라벨
        tk.Label(
            first_row,
            text="→",
            font=("Segoe UI", 12),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_main'],
            padx=10
        ).pack(side="left")

        # 타겟 언어 드롭다운
        self.target_langs = set(target_languages)

        self.target_dropdown_frame = tk.Frame(first_row, bg=COLORS['bg_input'], cursor="hand2")
        self.target_dropdown_frame.pack(side="left")

        self.target_dropdown_text = tk.Label(
            self.target_dropdown_frame,
            text=self._get_target_display_text(),
            font=("Segoe UI", 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_primary'],
            anchor="w",
            padx=15,
            pady=8
        )
        self.target_dropdown_text.pack(side="left")

        self.target_dropdown_arrow = tk.Label(
            self.target_dropdown_frame,
            text="▼",
            font=("Segoe UI", 8),
            bg=COLORS['bg_input'],
            fg=COLORS['text_dim'],
            padx=10
        )
        self.target_dropdown_arrow.pack(side="left")

        for w in [self.target_dropdown_frame, self.target_dropdown_text, self.target_dropdown_arrow]:
            w.bind("<Button-1>", lambda e: self.show_target_dropdown())
            w.bind("<Enter>", lambda e: self._hover_dropdown(self.target_dropdown_frame, self.target_dropdown_text, self.target_dropdown_arrow, True))
            w.bind("<Leave>", lambda e: self._hover_dropdown(self.target_dropdown_frame, self.target_dropdown_text, self.target_dropdown_arrow, False))

        # 다크모드 토글 (오른쪽)
        self.dark_mode_var = tk.BooleanVar(value=is_dark_mode)
        self.btn_dark_mode = tk.Label(
            first_row,
            text="White" if is_dark_mode else "Dark",
            font=("Segoe UI", 10),
            bg=COLORS['bg_input'] if not is_dark_mode else COLORS['primary'],
            fg=COLORS['text_secondary'] if not is_dark_mode else COLORS['bg_white'],
            cursor="hand2",
            padx=15,
            pady=8
        )
        self.btn_dark_mode.pack(side="right")
        self.btn_dark_mode.bind("<Button-1>", lambda e: self.toggle_dark_mode())

        # 두 번째 줄: 마이크 선택
        mic_row = tk.Frame(lang_section, bg=COLORS['bg_main'])
        mic_row.pack(fill="x", pady=(0, 10))

        self.mic_list = get_microphone_list()

        # 현재 선택된 마이크 이름
        current_mic_name = 'System Default'
        for m in self.mic_list:
            if m['id'] == selected_mic_id:
                current_mic_name = m['name']
                break

        # 마이크 드롭다운 (소스 언어 드롭다운과 동일한 스타일)
        self.mic_dropdown_frame = tk.Frame(mic_row, bg=COLORS['bg_input'], cursor="hand2")
        self.mic_dropdown_frame.pack(side="left", fill="x", expand=True)

        self.mic_dropdown_icon = tk.Label(
            self.mic_dropdown_frame,
            text="🎤",
            font=("Segoe UI", 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_dim'],
            padx=(10)
        )
        self.mic_dropdown_icon.pack(side="left")

        self.mic_dropdown_text = tk.Label(
            self.mic_dropdown_frame,
            text=current_mic_name,
            font=("Segoe UI", 10),
            bg=COLORS['bg_input'],
            fg=COLORS['text_primary'],
            anchor="w",
            padx=5,
            pady=8
        )
        self.mic_dropdown_text.pack(side="left", fill="x", expand=True)

        self.mic_dropdown_arrow = tk.Label(
            self.mic_dropdown_frame,
            text="▼",
            font=("Segoe UI", 8),
            bg=COLORS['bg_input'],
            fg=COLORS['text_dim'],
            padx=10
        )
        self.mic_dropdown_arrow.pack(side="left")

        def _mic_hover(entering):
            bg = COLORS['border'] if entering else COLORS['bg_input']
            self.mic_dropdown_frame.config(bg=bg)
            self.mic_dropdown_icon.config(bg=bg)
            self.mic_dropdown_text.config(bg=bg)
            self.mic_dropdown_arrow.config(bg=bg)

        for w in [self.mic_dropdown_frame, self.mic_dropdown_icon, self.mic_dropdown_text, self.mic_dropdown_arrow]:
            w.bind("<Button-1>", lambda e: self.show_mic_dropdown())
            w.bind("<Enter>", lambda e: _mic_hover(True))
            w.bind("<Leave>", lambda e: _mic_hover(False))

        # 새로고침 버튼
        self.mic_refresh_btn = tk.Label(
            mic_row,
            text="↻",
            font=("Segoe UI", 12),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_main'],
            cursor="hand2",
            padx=8
        )
        self.mic_refresh_btn.pack(side="left")
        self.mic_refresh_btn.bind("<Button-1>", lambda e: self._refresh_mic_list())
        self.mic_refresh_btn.bind("<Enter>", lambda e: self.mic_refresh_btn.config(fg=COLORS['primary']))
        self.mic_refresh_btn.bind("<Leave>", lambda e: self.mic_refresh_btn.config(fg=COLORS['text_dim']))

        # 드롭다운 팝업 참조
        self.dropdown_popup = None

        # PDF 카드
        pdf_card = tk.Frame(container, bg=COLORS['bg_card'])
        pdf_card.pack(fill="x", pady=(0, 15))

        # PDF 카드 내부 패딩
        pdf_inner_container = tk.Frame(pdf_card, bg=COLORS['bg_card'])
        pdf_inner_container.pack(fill="x", padx=20, pady=15)

        tk.Label(
            pdf_inner_container,
            text="PDF Extract",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_card']
        ).pack(anchor="w")

        tk.Label(
            pdf_inner_container,
            text="Extract terminology from PDF files",
            font=("Segoe UI", 9),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_card']
        ).pack(anchor="w", pady=(2, 10))

        # 드롭 존 프레임
        self.pdf_drop_frame = tk.Frame(
            pdf_inner_container,
            bg=COLORS['bg_input'],
            cursor="hand2"
        )
        self.pdf_drop_frame.pack(fill="x", pady=(0, 5))

        pdf_inner = tk.Frame(self.pdf_drop_frame, bg=COLORS['bg_input'])
        pdf_inner.pack(fill="x", padx=15, pady=15)

        self.pdf_label = tk.Label(
            pdf_inner,
            text="+ Drop PDF or click to select",
            font=("Segoe UI", 10),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_input']
        )
        self.pdf_label.pack(fill="x")

        # 클릭으로 파일 선택
        self.pdf_drop_frame.bind("<Button-1>", lambda e: self.select_pdf())
        pdf_inner.bind("<Button-1>", lambda e: self.select_pdf())
        self.pdf_label.bind("<Button-1>", lambda e: self.select_pdf())

        # 드래그 앤 드롭 바인딩
        if DND_SUPPORT:
            self.pdf_drop_frame.drop_target_register(DND_FILES)
            self.pdf_drop_frame.dnd_bind('<<Drop>>', self.on_pdf_drop)
            self.pdf_drop_frame.dnd_bind('<<DragEnter>>', self.on_drag_enter)
            self.pdf_drop_frame.dnd_bind('<<DragLeave>>', self.on_drag_leave)

        # 추가된 PDF 목록 프레임
        self.pdf_list_frame = tk.Frame(pdf_inner_container, bg=COLORS['bg_card'])
        self.pdf_list_frame.pack(fill="x")

        # 단어집 카드
        glossary_card = tk.Frame(container, bg=COLORS['bg_card'])
        glossary_card.pack(fill="both", expand=True, pady=(0, 15))

        glossary_inner = tk.Frame(glossary_card, bg=COLORS['bg_card'])
        glossary_inner.pack(fill="both", expand=True, padx=20, pady=15)

        glossary_header = tk.Frame(glossary_inner, bg=COLORS['bg_card'])
        glossary_header.pack(fill="x")

        tk.Label(
            glossary_header,
            text="Terminology",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_card']
        ).pack(side="left")

        # 추가 버튼
        add_btn = tk.Label(
            glossary_header,
            text="+ Add",
            font=("Segoe UI", 9),
            fg=COLORS['primary'],
            bg=COLORS['bg_card'],
            cursor="hand2"
        )
        add_btn.pack(side="right")
        add_btn.bind("<Button-1>", lambda e: self.add_glossary_row())
        add_btn.bind("<Enter>", lambda e: add_btn.config(fg=COLORS['primary_hover']))
        add_btn.bind("<Leave>", lambda e: add_btn.config(fg=COLORS['primary']))

        # 스크롤 영역
        self.glossary_canvas = tk.Canvas(glossary_inner, bg=COLORS['bg_card'], highlightthickness=0, height=120)
        self.glossary_scrollbar = tk.Scrollbar(glossary_inner, orient="vertical", command=self.glossary_canvas.yview)
        self.glossary_frame = tk.Frame(self.glossary_canvas, bg=COLORS['bg_card'])

        self.glossary_canvas.configure(yscrollcommand=self.glossary_scrollbar.set)
        self.glossary_scrollbar.pack(side="right", fill="y", pady=(10, 0))
        self.glossary_canvas.pack(side="left", fill="both", expand=True, pady=(10, 0))

        self.canvas_window = self.glossary_canvas.create_window((0, 0), window=self.glossary_frame, anchor="nw")
        self.glossary_frame.bind("<Configure>", lambda e: self.glossary_canvas.configure(scrollregion=self.glossary_canvas.bbox("all")))
        self.glossary_canvas.bind("<Configure>", lambda e: self.glossary_canvas.itemconfig(self.canvas_window, width=e.width))

        # 마우스 휠 스크롤
        self.glossary_canvas.bind("<MouseWheel>", self._on_glossary_scroll)
        self.glossary_frame.bind("<MouseWheel>", self._on_glossary_scroll)

        # 저장된 단어장 불러오기
        saved_terms = load_glossary()
        for term in saved_terms:
            self.add_glossary_row_with_text(term)

        # 시작 버튼
        start_btn = tk.Label(
            container,
            text="Start Translation",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['bg_white'],
            bg=COLORS['primary'],
            cursor="hand2",
            pady=14
        )
        start_btn.pack(fill="x")
        start_btn.bind("<Button-1>", lambda e: self.start_overlay())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg=COLORS['primary_hover']))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg=COLORS['primary']))

        # ESC로 닫기
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _minimize_window(self):
        """overrideredirect 창 최소화 (Windows 우회)"""
        self.root.overrideredirect(False)
        self.root.iconify()
        def _on_restore(event):
            if self.root.state() == 'normal':
                self.root.overrideredirect(True)
                self.root.unbind("<Map>")
        self.root.bind("<Map>", _on_restore)

    def start_drag(self, event):
        """드래그 시작"""
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        """드래그 이동"""
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def create_section_header(self, parent, text):
        """섹션 헤더 생성"""
        header_frame = tk.Frame(parent, bg=COLORS['bg_main'])
        header_frame.pack(fill="x", pady=(0, 5))

        tk.Label(
            header_frame,
            text=text,
            font=("Segoe UI", 9, "bold"),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_main']
        ).pack(side="left")

    def btn_hover(self, btn, entering):
        """버튼 호버 효과"""
        if entering:
            btn.config(bg=COLORS['primary_hover'])
        else:
            btn.config(bg=COLORS['primary'])

    def _on_glossary_scroll(self, event):
        """Terminology database 마우스 휠 스크롤"""
        self.glossary_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_pdf_drop(self, event):
        """PDF 파일 드롭 처리 (여러 파일 → 배치 처리 후 한번에 모달)"""
        data = event.data

        # 여러 파일 파싱 (공백으로 구분, 중괄호로 감싸진 경로 처리)
        filepaths = []
        if '{' in data:
            # 중괄호로 감싸진 경로들 추출
            import re
            matches = re.findall(r'\{([^}]+)\}', data)
            filepaths.extend(matches)
            # 중괄호 없는 경로도 추출
            remaining = re.sub(r'\{[^}]+\}', '', data).strip()
            if remaining:
                filepaths.extend(remaining.split())
        else:
            filepaths = data.split()

        # PDF 파일만 필터링
        pdf_files = [fp.strip() for fp in filepaths if fp.strip() and fp.strip().lower().endswith('.pdf')]

        if not pdf_files:
            self.pdf_label.config(text="PDF files only", fg=COLORS['danger'])
            return

        # 배치 처리: 모든 PDF 스레드 시작 후 전부 완료되면 모달 1회 표시
        self._pdf_batch_threads = []
        self._pdf_batch_terms = []
        self._pdf_batch_items = []
        for filepath in pdf_files:
            self._process_pdf_file(filepath)

    def on_drag_enter(self, event):
        """드래그 진입 시 하이라이트"""
        self.pdf_drop_frame.config(bg=COLORS['border'])
        self.pdf_label.config(bg=COLORS['border'], fg=COLORS['primary'])

    def on_drag_leave(self, event):
        """드래그 이탈 시 원래대로"""
        self.pdf_drop_frame.config(bg=COLORS['bg_input'])
        self.pdf_label.config(bg=COLORS['bg_input'], fg=COLORS['text_dim'])

    def select_pdf(self):
        """PDF 파일 선택 다이얼로그"""
        if not PDF_SUPPORT:
            self.pdf_label.config(text="PDF library not found", fg=COLORS['danger'])
            return

        filepath = filedialog.askopenfilename(
            title="PDF 파일 선택",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filepath:
            self._pdf_batch_threads = []
            self._pdf_batch_terms = []
            self._pdf_batch_items = []
            self._process_pdf_file(filepath)

    def _process_pdf_file(self, filepath):
        """PDF 파일 처리 시작 (배치 처리 지원)"""
        self.pdf_path = filepath
        filename = os.path.basename(filepath)

        # PDF 항목 UI 생성
        pdf_item = self._create_pdf_item(filepath, filename)

        self.pdf_drop_frame.config(highlightbackground=COLORS['text_dim'], highlightthickness=1)
        self.root.update()

        # 배치 목록에 추가
        self._pdf_batch_items.append(pdf_item)
        t = threading.Thread(target=self.process_pdf, args=(filepath, pdf_item), daemon=True)
        t.start()
        self._pdf_batch_threads.append(t)

        # 첫 번째 PDF일 때만 배치 폴링 시작
        if len(self._pdf_batch_threads) == 1:
            self.root.after(200, self._poll_pdf_batch)

    def _create_pdf_item(self, filepath, filename):
        """PDF 목록 항목 생성"""
        display_name = filename if len(filename) <= 35 else filename[:32] + "..."

        item_frame = tk.Frame(self.pdf_list_frame, bg=COLORS['bg_input'])
        item_frame.pack(fill="x", pady=4)

        # 파일명 라벨
        name_label = tk.Label(
            item_frame,
            text=display_name,
            font=("Segoe UI", 10),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_input'],
            anchor="w",
            padx=12,
            pady=10
        )
        name_label.pack(side="left")

        # 상태 라벨 (진행률)
        status_label = tk.Label(
            item_frame,
            text="0%",
            font=("Segoe UI", 9),
            fg=COLORS['secondary'],
            bg=COLORS['bg_input'],
            anchor="e",
            padx=8,
            pady=10
        )
        status_label.pack(side="left", fill="x", expand=True)

        # 삭제 버튼
        del_btn = tk.Label(
            item_frame,
            text="✕",
            font=("Segoe UI", 10),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_input'],
            cursor="hand2",
            padx=12
        )
        del_btn.pack(side="right")
        del_btn.bind("<Button-1>", lambda e, f=item_frame: self._remove_pdf_item(f))
        del_btn.bind("<Enter>", lambda e: del_btn.config(fg=COLORS['danger']))
        del_btn.bind("<Leave>", lambda e: del_btn.config(fg=COLORS['text_dim']))

        self.pdf_list.append((filepath, item_frame, status_label))
        return (item_frame, status_label, display_name)

    def _remove_pdf_item(self, item_frame):
        """PDF 항목 삭제"""
        for i, (fp, frame, label) in enumerate(self.pdf_list):
            if frame == item_frame:
                frame.destroy()
                self.pdf_list.pop(i)
                break

    def process_pdf(self, filepath, pdf_item):
        """PDF 처리 및 전문용어 추출"""
        item_frame, status_label, display_name = pdf_item

        try:
            filename = os.path.basename(filepath)

            # 로딩 애니메이션 시작
            self._loading_active = True
            def _animate_loading(dots=[0]):
                if not self._loading_active:
                    return
                dots[0] = (dots[0] % 3) + 1
                self.root.after(0, lambda: status_label.config(
                    text="Loading" + "." * dots[0],
                    fg=COLORS['secondary']
                ))
                self.root.after(500, _animate_loading)
            self.root.after(0, _animate_loading)

            # PDF 텍스트 추출
            text = extract_text_from_pdf(filepath)

            if not text.strip():
                self._loading_active = False
                self.root.after(0, lambda: status_label.config(text="Failed", fg=COLORS['danger']))
                return

            # GPT 분석
            terms = extract_terminology_with_gpt(text)
            self._loading_active = False

            if not terms:
                self.root.after(0, lambda: status_label.config(text="No terms", fg=COLORS['danger']))
                return

            count = len(terms)
            self.root.after(0, lambda c=count: status_label.config(text=f"{c} terms", fg=COLORS['success']))

            # 배치 리스트에 누적 (중복 제거)
            for term in terms:
                if term not in self._pdf_batch_terms:
                    self._pdf_batch_terms.append(term)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: status_label.config(text="Error", fg=COLORS['danger']))

    def _poll_pdf_batch(self):
        """배치 PDF 처리 스레드 전체 완료 확인"""
        if any(t.is_alive() for t in self._pdf_batch_threads):
            # 아직 처리 중 - 계속 폴링
            self.root.after(200, self._poll_pdf_batch)
        else:
            # 모든 PDF 처리 완료 - 합쳐진 용어로 모달 1회 표시
            if self._pdf_batch_terms:
                terms = list(self._pdf_batch_terms)
                items = list(self._pdf_batch_items)
                self._pdf_batch_terms.clear()
                self._pdf_batch_threads.clear()
                self._pdf_batch_items.clear()
                self.show_term_modal(terms, None, items)
            else:
                self._pdf_batch_threads.clear()
                self._pdf_batch_items.clear()

    def show_term_modal(self, terms, filepath, pdf_item=None):
        """전문용어 선택 모달 표시 (배치: pdf_item이 리스트일 수 있음)"""

        try:
            modal = TermSelectionModal(self.root, terms)
            selected = modal.show()

            # 용어 추가
            if selected:
                for term in selected:
                    self.add_glossary_row_with_text(term)

            # 상태 라벨: 취소 시만 업데이트 (각 PDF는 이미 개별 추출 수 표시중)
            if not selected:
                items = pdf_item if isinstance(pdf_item, list) else [pdf_item] if pdf_item else []
                for item in items:
                    if item:
                        item_frame, status_label, _ = item
                        status_label.config(text="Cancelled", fg=COLORS['text_dim'])
        except Exception as e:
            import traceback
            traceback.print_exc()

    def add_glossary_row_with_text(self, text):
        """텍스트가 채워진 단어집 행 추가 (태그 스타일)"""
        # 빈 텍스트는 추가하지 않음
        if not text or not text.strip():
            return

        text = text.strip()

        # 태그 스타일 프레임
        tag_frame = tk.Frame(self.glossary_frame, bg=COLORS['bg_card'])
        tag_frame.pack(anchor="w", pady=2, padx=2)

        # 태그 컨테이너 (둥근 느낌을 위한 패딩)
        tag_container = tk.Frame(tag_frame, bg=COLORS['primary'], cursor="hand2")
        tag_container.pack(side="left")

        # 용어 텍스트
        term_label = tk.Label(
            tag_container,
            text=text,
            font=("Segoe UI", 9),
            fg="#FFFFFF",
            bg=COLORS['primary'],
            padx=12,
            pady=6
        )
        term_label.pack(side="left")

        # 삭제 버튼 (태그 내부)
        del_btn = tk.Label(
            tag_container,
            text="×",
            font=("Segoe UI", 10),
            fg="#FFFFFF",
            bg=COLORS['primary'],
            cursor="hand2",
            padx=6,
            pady=6
        )
        del_btn.pack(side="left")

        # 호버 효과
        def on_enter(e):
            tag_container.config(bg=COLORS['primary_hover'])
            term_label.config(bg=COLORS['primary_hover'])
            del_btn.config(bg=COLORS['primary_hover'])

        def on_leave(e):
            tag_container.config(bg=COLORS['primary'])
            term_label.config(bg=COLORS['primary'])
            del_btn.config(bg=COLORS['primary'])

        for widget in [tag_container, term_label, del_btn]:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<MouseWheel>", self._on_glossary_scroll)

        del_btn.bind("<Button-1>", lambda e: self.remove_glossary_tag(tag_frame, text))

        # 저장 (text와 frame)
        self.glossary_entries.append((text, tag_frame))
        self.glossary_canvas.update_idletasks()
        self.glossary_canvas.configure(scrollregion=self.glossary_canvas.bbox("all"))

        # 파일에 저장
        save_glossary([t for t, _ in self.glossary_entries])

    def show_mic_dropdown(self):
        """마이크 선택 드롭다운 표시"""
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            self.dropdown_popup.destroy()
            self.dropdown_popup = None
            return

        self.dropdown_popup = tk.Toplevel(self.root)
        self.dropdown_popup.overrideredirect(True)
        self.dropdown_popup.configure(bg=COLORS['border'])
        self.dropdown_popup.attributes("-topmost", True)

        x = self.mic_dropdown_frame.winfo_rootx()
        y = self.mic_dropdown_frame.winfo_rooty() + self.mic_dropdown_frame.winfo_height() + 3
        width = max(300, self.mic_dropdown_frame.winfo_width())

        inner = tk.Frame(self.dropdown_popup, bg=COLORS['bg_card'])
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        canvas = tk.Canvas(inner, bg=COLORS['bg_card'], highlightthickness=0, width=width - 2)
        scroll_frame = tk.Frame(canvas, bg=COLORS['bg_card'])
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=width - 2)

        for mic in self.mic_list:
            is_selected = mic['id'] == selected_mic_id
            item = tk.Frame(scroll_frame, bg=COLORS['bg_card'], cursor="hand2")
            item.pack(fill="x")

            check = tk.Label(
                item,
                text="✓" if is_selected else "",
                font=("Segoe UI", 10, "bold"),
                fg=COLORS['primary'],
                bg=COLORS['bg_card'],
                width=3,
                pady=8
            )
            check.pack(side="left")

            label = tk.Label(
                item,
                text=mic['name'],
                font=("Segoe UI", 10),
                fg=COLORS['text_primary'] if not is_selected else COLORS['primary'],
                bg=COLORS['bg_card'],
                anchor="w",
                pady=8
            )
            label.pack(side="left", fill="x", expand=True)

            mic_id = mic['id']
            mic_name = mic['name']
            for w in [item, check, label]:
                w.bind("<Button-1>", lambda e, mid=mic_id, mn=mic_name: self._select_mic(mid, mn))
                w.bind("<Enter>", lambda e, it=item: it.config(bg=COLORS['bg_input']) or [
                    c.config(bg=COLORS['bg_input']) for c in it.winfo_children()])
                w.bind("<Leave>", lambda e, it=item: it.config(bg=COLORS['bg_card']) or [
                    c.config(bg=COLORS['bg_card']) for c in it.winfo_children()])

        scroll_frame.update_idletasks()
        total_h = min(scroll_frame.winfo_reqheight() + 2, 300)
        canvas.configure(height=total_h)
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.dropdown_popup.geometry(f"{width}x{total_h + 2}+{x}+{y}")
        self.dropdown_popup.bind("<FocusOut>", lambda e: self._close_dropdown_delayed())
        self.dropdown_popup.focus_set()

    def _select_mic(self, mic_id, mic_name):
        """마이크 선택"""
        global selected_mic_id
        selected_mic_id = mic_id
        self.mic_dropdown_text.config(text=mic_name)
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            self.dropdown_popup.destroy()
            self.dropdown_popup = None

    def _refresh_mic_list(self):
        """마이크 목록 새로고침 (sounddevice 캐시 강제 갱신)"""
        global selected_mic_id
        if SD_AVAILABLE:
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        self.mic_list = get_microphone_list()
        # 현재 선택이 여전히 유효한지 확인
        found = False
        for m in self.mic_list:
            if m['id'] == selected_mic_id:
                found = True
                break
        if not found:
            selected_mic_id = None
            self.mic_dropdown_text.config(text='System Default')

    def toggle_dark_mode(self):
        """다크모드 토글"""
        global is_dark_mode
        is_dark_mode = not is_dark_mode
        set_theme(is_dark_mode)
        self.dark_mode_var.set(is_dark_mode)
        self.apply_theme()

    def apply_theme(self):
        """전체 UI에 테마 적용"""
        # 루트 윈도우
        self.root.configure(bg=COLORS['bg_main'])

        # 모든 위젯 업데이트 (재귀적으로)
        self._apply_theme_to_widget(self.root)

        # 다크모드 버튼 상태 업데이트
        if is_dark_mode:
            self.btn_dark_mode.config(text="White", bg=COLORS['primary'], fg=COLORS['bg_white'])
        else:
            self.btn_dark_mode.config(text="Dark", bg=COLORS['bg_input'], fg=COLORS['text_secondary'])

    def _apply_theme_to_widget(self, widget):
        """위젯에 테마 적용 (재귀)"""
        widget_class = widget.winfo_class()

        try:
            # 배경색 결정
            if hasattr(widget, 'cget'):
                current_bg = widget.cget('bg')

                # 색상 매핑
                color_map = {
                    COLORS_LIGHT['bg_main']: COLORS['bg_main'],
                    COLORS_DARK['bg_main']: COLORS['bg_main'],
                    COLORS_LIGHT['bg_white']: COLORS['bg_white'],
                    COLORS_DARK['bg_white']: COLORS['bg_white'],
                    COLORS_LIGHT['bg_card']: COLORS['bg_card'],
                    COLORS_DARK['bg_card']: COLORS['bg_card'],
                    COLORS_LIGHT['bg_input']: COLORS['bg_input'],
                    COLORS_DARK['bg_input']: COLORS['bg_input'],
                    '#F7F8FC': COLORS['bg_main'],
                    '#1a1a2e': COLORS['bg_main'],
                    '#FFFFFF': COLORS['bg_card'],
                    '#1f2940': COLORS['bg_card'],
                    '#F0F1F5': COLORS['bg_input'],
                    '#2a3a5a': COLORS['bg_input'],
                }

                if current_bg in color_map:
                    widget.configure(bg=color_map[current_bg])

                # 텍스트 색상 업데이트
                if widget_class in ('Label', 'Entry'):
                    try:
                        current_fg = widget.cget('fg')
                        fg_map = {
                            COLORS_LIGHT['text_primary']: COLORS['text_primary'],
                            COLORS_DARK['text_primary']: COLORS['text_primary'],
                            COLORS_LIGHT['text_secondary']: COLORS['text_secondary'],
                            COLORS_DARK['text_secondary']: COLORS['text_secondary'],
                            COLORS_LIGHT['text_dim']: COLORS['text_dim'],
                            COLORS_DARK['text_dim']: COLORS['text_dim'],
                            '#2D3748': COLORS['text_primary'],
                            '#E8E8E8': COLORS['text_primary'],
                            '#718096': COLORS['text_secondary'],
                            '#A0AEC0': COLORS['text_secondary'],
                        }
                        if current_fg in fg_map:
                            widget.configure(fg=fg_map[current_fg])
                    except:
                        pass
        except:
            pass

        # 자식 위젯에 재귀 적용
        for child in widget.winfo_children():
            self._apply_theme_to_widget(child)

    def _hover_dropdown(self, frame, text, arrow, entering):
        """드롭다운 호버 효과"""
        bg = COLORS['border'] if entering else COLORS['bg_input']
        frame.config(bg=bg)
        text.config(bg=bg)
        arrow.config(bg=bg)

    def _get_target_display_text(self):
        """타겟 언어 표시 텍스트 생성"""
        if not self.target_langs:
            return "Select languages"
        names = [f"{LANGUAGES[lc]['flag']}  {LANGUAGES[lc]['name']}" for lc in list(self.target_langs)[:2] if lc in LANGUAGES]
        if len(self.target_langs) > 2:
            return ", ".join(names) + f" +{len(self.target_langs)-2}"
        return ", ".join(names)

    def show_source_dropdown(self):
        """소스 언어 드롭다운 표시"""
        # 이미 열려있으면 닫기
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            self.dropdown_popup.destroy()
            self.dropdown_popup = None
            return

        self._create_dropdown(
            self.source_dropdown_frame,
            single_select=True,
            selected=set([self.source_lang_var.get()]),
            callback=self._select_source_language
        )

    def show_target_dropdown(self):
        """타겟 언어 드롭다운 표시"""
        # 이미 열려있으면 닫기
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            self.dropdown_popup.destroy()
            self.dropdown_popup = None
            return

        self._create_dropdown(
            self.target_dropdown_frame,
            single_select=False,
            selected=self.target_langs,
            callback=self._toggle_target_lang,
            excluded=set([self.source_lang_var.get()])
        )

    def _create_dropdown(self, anchor, single_select, selected, callback, excluded=None):
        """현대적인 드롭다운 생성"""
        self.dropdown_popup = tk.Toplevel(self.root)
        self.dropdown_popup.overrideredirect(True)
        self.dropdown_popup.configure(bg=COLORS['border'])
        self.dropdown_popup.attributes("-topmost", True)

        # 위치 계산
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 3
        width = max(250, anchor.winfo_width())

        # 내부 컨테이너 (테두리 효과)
        inner = tk.Frame(self.dropdown_popup, bg=COLORS['bg_card'])
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # 스크롤 영역
        canvas = tk.Canvas(inner, bg=COLORS['bg_card'], highlightthickness=0, width=width-2)
        scroll_frame = tk.Frame(canvas, bg=COLORS['bg_card'])

        canvas.pack(side="left", fill="both", expand=True)
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=width-2)

        # 언어 항목 생성
        excluded = excluded or set()
        self._dropdown_checks = {}

        for lang_code, lang_info in LANGUAGES.items():
            is_excluded = lang_code in excluded
            is_selected = lang_code in selected

            item = tk.Frame(scroll_frame, bg=COLORS['bg_card'], cursor="hand2" if not is_excluded else "")
            item.pack(fill="x")

            # 체크박스 영역
            check = tk.Label(
                item,
                text="✓" if is_selected else "",
                font=("Segoe UI", 10, "bold"),
                fg=COLORS['primary'],
                bg=COLORS['bg_card'],
                width=3,
                pady=10
            )
            check.pack(side="left")

            # 언어 텍스트
            text = tk.Label(
                item,
                text=f"{lang_info['flag']}  {lang_info['name']}",
                font=("Segoe UI", 10),
                fg=COLORS['text_dim'] if is_excluded else COLORS['text_primary'],
                bg=COLORS['bg_card'],
                anchor="w",
                pady=10
            )
            text.pack(side="left", fill="x", expand=True, padx=(0, 15))

            self._dropdown_checks[lang_code] = check

            if not is_excluded:
                # 클릭 핸들러
                def make_handler(lc):
                    def handler(e):
                        callback(lc, single_select)
                    return handler

                for w in [item, check, text]:
                    w.bind("<Button-1>", make_handler(lang_code))

                # 호버 효과
                def make_hover(f, c, t, enter):
                    def hover(e):
                        bg = COLORS['bg_input'] if enter else COLORS['bg_card']
                        f.config(bg=bg)
                        c.config(bg=bg)
                        t.config(bg=bg)
                    return hover

                for w in [item, check, text]:
                    w.bind("<Enter>", make_hover(item, check, text, True))
                    w.bind("<Leave>", make_hover(item, check, text, False))

        # 스크롤 설정
        scroll_frame.update_idletasks()
        content_height = scroll_frame.winfo_reqheight()
        display_height = min(300, content_height)
        canvas.config(height=display_height)

        if content_height > display_height:
            scrollbar = tk.Scrollbar(inner, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # 마우스 휠
        def on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", on_wheel)
        scroll_frame.bind("<MouseWheel>", on_wheel)
        for child in scroll_frame.winfo_children():
            child.bind("<MouseWheel>", on_wheel)
            for c in child.winfo_children():
                c.bind("<MouseWheel>", on_wheel)

        # 위치 설정
        self.dropdown_popup.geometry(f"{width}x{display_height + 2}+{x}+{y}")

        # 외부 클릭 시 닫기
        self.dropdown_popup.bind("<FocusOut>", lambda e: self._close_dropdown_delayed())
        self.root.bind("<Button-1>", self._on_root_click, add="+")

        # 둥근 모서리
        self.dropdown_popup.update_idletasks()
        apply_rounded_corners(self.dropdown_popup)

    def _close_dropdown_delayed(self):
        """지연 후 드롭다운 닫기"""
        self.root.after(100, self._try_close_dropdown)

    def _try_close_dropdown(self):
        """드롭다운 닫기 시도"""
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            try:
                # 마우스가 팝업 위에 있는지 확인
                mx = self.root.winfo_pointerx()
                my = self.root.winfo_pointery()
                px = self.dropdown_popup.winfo_rootx()
                py = self.dropdown_popup.winfo_rooty()
                pw = self.dropdown_popup.winfo_width()
                ph = self.dropdown_popup.winfo_height()
                if not (px <= mx <= px + pw and py <= my <= py + ph):
                    self.dropdown_popup.destroy()
                    self.dropdown_popup = None
            except:
                pass

    def _on_root_click(self, event):
        """루트 클릭 시 드롭다운 닫기"""
        if self.dropdown_popup and self.dropdown_popup.winfo_exists():
            # 드롭다운 버튼 클릭인지 확인
            widget = event.widget
            if widget in [self.source_dropdown_frame, self.source_dropdown_text, self.source_dropdown_arrow,
                          self.target_dropdown_frame, self.target_dropdown_text, self.target_dropdown_arrow]:
                return
            # 팝업 내부 클릭인지 확인
            try:
                mx = event.x_root
                my = event.y_root
                px = self.dropdown_popup.winfo_rootx()
                py = self.dropdown_popup.winfo_rooty()
                pw = self.dropdown_popup.winfo_width()
                ph = self.dropdown_popup.winfo_height()
                if not (px <= mx <= px + pw and py <= my <= py + ph):
                    self.dropdown_popup.destroy()
                    self.dropdown_popup = None
            except:
                pass

    def _select_source_language(self, lang_code, single_select):
        """소스 언어 선택"""
        global source_language
        source_language = lang_code
        self.source_lang_var.set(lang_code)

        # UI 업데이트
        lang_info = LANGUAGES.get(lang_code, {})
        self.source_dropdown_text.config(text=f"{lang_info.get('flag', '')}  {lang_info.get('name', '')}")

        # 소스 언어를 타겟에서 제거
        if lang_code in self.target_langs:
            self.target_langs.discard(lang_code)
            self.target_dropdown_text.config(text=self._get_target_display_text())

        # 드롭다운 닫기
        if self.dropdown_popup:
            self.dropdown_popup.destroy()
            self.dropdown_popup = None

    def _toggle_target_lang(self, lang_code, single_select):
        """타겟 언어 토글"""
        if lang_code == self.source_lang_var.get():
            return

        if lang_code in self.target_langs:
            if len(self.target_langs) > 1:
                self.target_langs.discard(lang_code)
                if lang_code in self._dropdown_checks:
                    self._dropdown_checks[lang_code].config(text="")
        else:
            self.target_langs.add(lang_code)
            if lang_code in self._dropdown_checks:
                self._dropdown_checks[lang_code].config(text="✓")

        # UI 업데이트
        self.target_dropdown_text.config(text=self._get_target_display_text())

    def add_glossary_row(self):
        """단어집 입력 필드 추가 (현대적 스타일)"""
        # 이미 입력 필드가 있으면 추가하지 않음
        if hasattr(self, '_input_frame') and self._input_frame.winfo_exists():
            self._input_entry.focus_set()
            return

        self._input_frame = tk.Frame(self.glossary_frame, bg=COLORS['bg_card'])
        self._input_frame.pack(fill="x", pady=4, padx=2)

        # 입력 컨테이너
        input_container = tk.Frame(self._input_frame, bg=COLORS['bg_card'])
        input_container.pack(fill="x")

        # 입력 필드
        self._input_entry = tk.Entry(
            input_container,
            font=("Segoe UI", 10),
            bg=COLORS['bg_card'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['primary'],
            relief="flat",
            highlightthickness=0
        )
        self._input_entry.pack(side="left", fill="x", expand=True, ipady=6)

        # 밑줄 (포커스 표시)
        self._input_underline = tk.Frame(self._input_frame, bg=COLORS['primary'], height=2)
        self._input_underline.pack(fill="x", padx=(0, 15))

        # 이벤트 바인딩
        self._input_entry.bind("<Return>", self._on_input_submit)
        self._input_entry.bind("<Escape>", self._on_input_cancel)
        self._input_entry.bind("<FocusOut>", self._on_input_blur)
        self._input_entry.bind("<MouseWheel>", self._on_glossary_scroll)

        self.glossary_canvas.update_idletasks()
        self.glossary_canvas.configure(scrollregion=self.glossary_canvas.bbox("all"))

        # 포커스
        self._input_entry.focus_set()

    def _on_input_submit(self, event):
        """입력 완료"""
        text = self._input_entry.get().strip()
        if text:
            # 입력 필드 제거
            self._input_frame.destroy()
            # 태그로 추가
            self.add_glossary_row_with_text(text)
            # 새 입력 필드 추가
            self.add_glossary_row()

    def _on_input_cancel(self, event):
        """입력 취소"""
        self._input_frame.destroy()

    def _on_input_blur(self, event):
        """포커스 잃음"""
        # 약간의 지연 후 처리 (다른 위젯 클릭 시)
        self.root.after(100, self._check_input_blur)

    def _check_input_blur(self):
        """입력 필드 상태 확인"""
        if not hasattr(self, '_input_frame') or not self._input_frame.winfo_exists():
            return
        try:
            text = self._input_entry.get().strip()
            if text:
                self._input_frame.destroy()
                self.add_glossary_row_with_text(text)
            elif not self._input_entry.focus_get():
                self._input_frame.destroy()
        except:
            pass

    def remove_glossary_tag(self, tag_frame, text):
        """태그 제거"""
        for i, (term, frame) in enumerate(self.glossary_entries):
            if frame == tag_frame:
                frame.destroy()
                self.glossary_entries.pop(i)
                break
        self.glossary_canvas.update_idletasks()
        self.glossary_canvas.configure(scrollregion=self.glossary_canvas.bbox("all"))

        # 파일에 저장
        save_glossary([t for t, _ in self.glossary_entries])

    def start_overlay(self):
        """설정 저장 후 오버레이 시작"""
        global source_language, target_languages, terminology_list

        source_language = self.source_lang_var.get()
        target_languages = list(self.target_langs)

        # 전문용어 수집 (태그에서 텍스트 직접 가져오기)
        terminology_list = []
        for term, _ in self.glossary_entries:
            if isinstance(term, str) and term.strip():
                terminology_list.append(term.strip())

        self.result = {
            'source_lang': source_language,
            'target_langs': target_languages,
            'terminology': terminology_list,
            'pdf_path': self.pdf_path,
            'dark_mode': is_dark_mode
        }

        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result


# ========================
# 5. 오버레이 자막 시스템 (사이버펑크 스타일)
# ========================
class SubtitleOverlay(ResizableWindow):
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Subtitle Overlay")
        self.go_back = False
        self.sd_stream = None
        self.push_stream = None
        self.speech_recognizer = None

        # 조기 확정 (Early Confirm) 상태
        self._early_confirmed_word_count = 0  # 이번 발화에서 조기 확정된 단어 수
        self._early_confirm_lock = threading.Lock()
        self._early_confirm_in_progress = False  # 중복 API 호출 방지
        self._last_realtime_source = ""       # 실시간 번역 중복 방지
        self._realtime_in_progress = False    # 실시간 번역 진행 중 플래그

        # 창 설정
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 1.0)

        # 배경 투명도
        self.bg_opacity = 1.0

        # 화면 오른쪽, 작업표시줄 제외 전체 높이, 좁게 배치
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        # 작업표시줄 높이 계산 (실제 작업 영역과의 차이)
        try:
            work_h = self.root.winfo_vrootheight()
            taskbar_h = screen_h - work_h if work_h < screen_h else 48
        except:
            taskbar_h = 48
        self.overlay_width = screen_w // 4
        self.overlay_height = screen_h - taskbar_h
        x_pos = screen_w - self.overlay_width
        y_pos = 0

        self.root.geometry(f"{self.overlay_width}x{self.overlay_height}+{x_pos}+{y_pos}")
        self.root.configure(bg=COLORS['bg_card'])

        # 배경 투명도 전용 윈도우 (전체 창 뒤에 위치)
        self._bg_window = tk.Toplevel(self.root)
        self._bg_window.overrideredirect(True)
        self._bg_window.attributes("-topmost", True)
        self._bg_window.attributes("-alpha", self.bg_opacity)
        self._bg_window.configure(bg=COLORS['bg_card'])
        self._bg_window.geometry(f"{self.overlay_width}x{self.overlay_height}+{x_pos}+{y_pos}")
        self._bg_window.lower(self.root)
        # 메인 창의 bg_card 색상을 투명 처리 → 글씨만 남음
        self.root.attributes("-transparentcolor", COLORS['bg_card'])

        # 메인 프레임
        main_frame = tk.Frame(self.root, bg=COLORS['bg_card'])
        main_frame.pack(fill="both", expand=True)

        # 컨트롤 바
        control_frame = tk.Frame(main_frame, bg=COLORS['bg_card'])
        control_frame.pack(fill="x", side="top")

        # 상태 표시 (소스 언어 표시)
        source_info = LANGUAGES.get(source_language, {})
        self.status_label = tk.Label(
            control_frame,
            text=f"{source_info.get('flag', '')} Listening",
            font=("Segoe UI", 9),
            fg=COLORS['success'],
            bg=COLORS['bg_card']
        )
        self.status_label.pack(side="left", padx=15, pady=8)

        # 오른쪽 버튼들
        btn_container = tk.Frame(control_frame, bg=COLORS['bg_btn'])
        btn_container.pack(side="right", padx=10, pady=4)

        # 자막 위치 토글 버튼 (3/4 배치)
        self.spacer_btn = tk.Label(
            btn_container, text="▲", font=("Segoe UI", 10),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=10, pady=8
        )
        self.spacer_btn.pack(side="left", padx=1)
        self.spacer_btn.bind("<Button-1>", lambda e: self._toggle_spacer())
        self.spacer_btn.bind("<Enter>", lambda e: self.spacer_btn.config(fg=COLORS['primary']))
        self.spacer_btn.bind("<Leave>", lambda e: self.spacer_btn.config(
            fg=COLORS['primary'] if self._spacer_visible else COLORS['text_dim']
        ))

        # 폰트 크기 조절
        self.subtitle_font_size = 14

        font_down_btn = tk.Label(
            btn_container, text="A-", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        font_down_btn.pack(side="left", padx=1)
        font_down_btn.bind("<Button-1>", lambda e: self._change_font_size(-2))
        font_down_btn.bind("<Enter>", lambda e: font_down_btn.config(fg=COLORS['primary']))
        font_down_btn.bind("<Leave>", lambda e: font_down_btn.config(fg=COLORS['text_dim']))

        self.font_size_label = tk.Label(
            btn_container, text="14", font=("Segoe UI", 8),
            fg=COLORS['text_secondary'], bg=COLORS['bg_btn'], padx=2, pady=8
        )
        self.font_size_label.pack(side="left")

        font_up_btn = tk.Label(
            btn_container, text="A+", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        font_up_btn.pack(side="left", padx=1)
        font_up_btn.bind("<Button-1>", lambda e: self._change_font_size(2))
        font_up_btn.bind("<Enter>", lambda e: font_up_btn.config(fg=COLORS['primary']))
        font_up_btn.bind("<Leave>", lambda e: font_up_btn.config(fg=COLORS['text_dim']))

        # 다크모드 토글 버튼
        self.dark_btn = tk.Label(
            btn_container, text="Dark" if not is_dark_mode else "White", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=10, pady=8
        )
        self.dark_btn.pack(side="left", padx=1)
        self.dark_btn.bind("<Button-1>", lambda e: self.toggle_dark_mode())
        self.dark_btn.bind("<Enter>", lambda e: self.dark_btn.config(fg=COLORS['primary']))
        self.dark_btn.bind("<Leave>", lambda e: self.dark_btn.config(fg=COLORS['text_dim']))

        # 번역 일시정지/재개 버튼
        self.pause_btn = tk.Label(
            btn_container, text="Pause", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=10, pady=8
        )
        self.pause_btn.pack(side="left", padx=1)
        self.pause_btn.bind("<Button-1>", lambda e: self.toggle_pause())
        self.pause_btn.bind("<Enter>", lambda e: self.pause_btn.config(fg=COLORS['primary']))
        self.pause_btn.bind("<Leave>", lambda e: self.pause_btn.config(fg=COLORS['text_dim']))

        # 최소화 버튼 (고정 크기 프레임, Label이 전체 채움)
        minimize_frame = tk.Frame(btn_container, width=32, height=32, bg=COLORS['bg_btn'])
        minimize_frame.pack(side="left", padx=1)
        minimize_frame.pack_propagate(False)
        self.minimize_btn = tk.Label(
            minimize_frame, text="─", font=("Segoe UI", 12),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2"
        )
        self.minimize_btn.pack(fill="both", expand=True)
        self.minimize_btn.bind("<Button-1>", lambda e: self._minimize_window())
        self.minimize_btn.bind("<Enter>", lambda e: self.minimize_btn.config(fg=COLORS['primary']))
        self.minimize_btn.bind("<Leave>", lambda e: self.minimize_btn.config(fg=COLORS['text_dim']))

        # 종료 버튼 (고정 크기 프레임, Label이 전체 채움)
        close_frame = tk.Frame(btn_container, width=32, height=32, bg=COLORS['bg_btn'])
        close_frame.pack(side="left", padx=1)
        close_frame.pack_propagate(False)
        self.close_btn = tk.Label(
            close_frame, text="✕", font=("Segoe UI", 12),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2"
        )
        self.close_btn.pack(fill="both", expand=True)
        self.close_btn.bind("<Button-1>", lambda e: self.quit_app())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg=COLORS['danger']))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg=COLORS['text_dim']))

        # 전체 기록 저장 (다운로드용)
        self.full_history = []  # [(source_text, {lang: translation, ...}), ...]

        # 자막 컨테이너 (여러 언어 표시)
        subtitle_container = tk.Frame(main_frame, bg=COLORS['bg_card'])
        subtitle_container.pack(expand=True, fill="both", padx=20, pady=(0, 46))

        # 하단 여백 (토글용, 초기 숨김)
        self._bottom_spacer = tk.Frame(main_frame, bg=COLORS['bg_card'])
        self._spacer_visible = False

        # 각 타겟 언어별 확정 자막 영역 생성
        self.subtitle_texts = {}    # lang_code -> Text widget (확정 자막 누적용)
        self.realtime_texts = {}    # lang_code -> Text widget (실시간 자막, 별도 창)
        self.subtitle_labels = {}   # lang_code -> Label (호환성 래퍼)
        self._realtime_tags = {}    # lang_code -> 실시간 번역 태그 추적

        for lang_code in target_languages:
            lang_info = LANGUAGES.get(lang_code, {'name': lang_code, 'flag': ''})

            row_frame = tk.Frame(subtitle_container, bg=COLORS['bg_card'])
            row_frame.pack(fill="both", expand=True, pady=2)

            # 확정 자막 Text 위젯 (스크롤 가능)
            subtitle_text = tk.Text(
                row_frame,
                font=("Segoe UI", 14),
                fg=COLORS['text_primary'],
                bg=COLORS['bg_card'],
                wrap="word",
                borderwidth=0,
                highlightthickness=0,
                state="disabled",
                cursor="arrow",
                height=3,
                takefocus=False
            )
            subtitle_text.pack(fill="both", expand=True)
            subtitle_text.tag_configure("final", foreground=COLORS['text_primary'])

            self.subtitle_texts[lang_code] = subtitle_text
            self._realtime_tags[lang_code] = False

        # 호환성 래퍼: subtitle_labels를 유지하되 내부적으로 Text 위젯 사용
        class _TextLabelAdapter:
            """기존 label.config(text=..., fg=...) 호출을 Text 위젯으로 변환"""
            def __init__(self, text_widget, overlay):
                self._text = text_widget
                self._overlay = overlay
            def config(self, text=None, fg=None, **kwargs):
                # 외부에서 호출되지 않도록 — check_queue에서 직접 처리
                pass

        for lang_code in target_languages:
            self.subtitle_labels[lang_code] = _TextLabelAdapter(
                self.subtitle_texts[lang_code], self
            )

        # 단일 언어 호환용
        if target_languages:
            self.subtitle_label = self.subtitle_labels[target_languages[0]]
        else:
            self.subtitle_label = tk.Label(main_frame, text="No target language", bg=COLORS['bg_card'])
            self.subtitle_label.pack()

        # 음성 인식 설정
        self.speech_recognizer = None
        self.setup_recognition()
        self.check_queue()

        # ESC 키로 종료
        self.root.bind("<Escape>", lambda e: self.quit_app())

        # 비버튼 영역 클릭 시 focus 방지
        def _prevent_focus(event):
            widget = event.widget
            # cursor="hand2" 인 위젯(버튼)만 focus 허용
            try:
                if str(widget.cget("cursor")) == "hand2":
                    return
            except:
                pass
            self.root.focus_set()
        self.root.bind_all("<Button-1>", _prevent_focus, add="+")

        # 드래그 (컨트롤바에서)
        control_frame.bind("<Button-1>", self.start_drag)
        control_frame.bind("<B1-Motion>", self.on_drag)
        self.status_label.bind("<Button-1>", self.start_drag)
        self.status_label.bind("<B1-Motion>", self.on_drag)

        # 자동 시작
        if self.speech_recognizer:
            self.root.after(500, self.start_listening)

        # 가장자리 리사이즈 기능 설정
        self.setup_resizable(min_width=50, min_height=50)

        # 배경 투명도 버튼 (우측 하단)
        opacity_frame = tk.Frame(main_frame, bg=COLORS['bg_btn'])
        opacity_frame.place(relx=1.0, rely=1.0, anchor="se", x=-8, y=-2)

        opacity_down_btn = tk.Label(
            opacity_frame, text="BG-", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        opacity_down_btn.pack(side="left", padx=1)
        opacity_down_btn.bind("<Button-1>", lambda e: self._change_opacity(-0.1))
        opacity_down_btn.bind("<Enter>", lambda e: opacity_down_btn.config(fg=COLORS['primary']))
        opacity_down_btn.bind("<Leave>", lambda e: opacity_down_btn.config(fg=COLORS['text_dim']))

        self._opacity_label = tk.Label(
            opacity_frame, text="100%", font=("Segoe UI", 8),
            fg=COLORS['text_secondary'], bg=COLORS['bg_btn'], padx=2, pady=8
        )
        self._opacity_label.pack(side="left")

        opacity_up_btn = tk.Label(
            opacity_frame, text="BG+", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        opacity_up_btn.pack(side="left", padx=1)
        opacity_up_btn.bind("<Button-1>", lambda e: self._change_opacity(0.1))
        opacity_up_btn.bind("<Enter>", lambda e: opacity_up_btn.config(fg=COLORS['primary']))
        opacity_up_btn.bind("<Leave>", lambda e: opacity_up_btn.config(fg=COLORS['text_dim']))

        # 구분선
        sep_label = tk.Label(opacity_frame, text="|", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], padx=4, pady=8)
        sep_label.pack(side="left")

        # QR 코드 버튼 (웹 서버 지원 시)
        if WEB_SERVER_SUPPORT:
            self.qr_btn = tk.Label(
                opacity_frame, text="QR", font=("Segoe UI", 9),
                fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
            )
            self.qr_btn.pack(side="left", padx=1)
            self.qr_btn.bind("<Button-1>", lambda e: self.show_qr_popup())
            self.qr_btn.bind("<Enter>", lambda e: self.qr_btn.config(fg=COLORS['primary']))
            self.qr_btn.bind("<Leave>", lambda e: self.qr_btn.config(fg=COLORS['text_dim']))

            self.client_count_label = tk.Label(
                opacity_frame, text="0", font=("Segoe UI", 8),
                fg=COLORS['text_dim'], bg=COLORS['bg_btn'], padx=2, pady=8
            )
            self.client_count_label.pack(side="left")

        # Settings 바로가기 버튼
        self.go_settings_btn = tk.Label(
            opacity_frame, text="Settings", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        self.go_settings_btn.pack(side="left", padx=1)
        self.go_settings_btn.bind("<Button-1>", lambda e: self._go_settings_direct())
        self.go_settings_btn.bind("<Enter>", lambda e: self.go_settings_btn.config(fg=COLORS['primary']))
        self.go_settings_btn.bind("<Leave>", lambda e: self.go_settings_btn.config(fg=COLORS['text_dim']))

        # Save .txt 버튼
        self.settings_btn = tk.Label(
            opacity_frame, text="Save .txt", font=("Segoe UI", 9),
            fg=COLORS['text_dim'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        self.settings_btn.pack(side="left", padx=1)
        self.settings_btn.bind("<Button-1>", lambda e: self.back_to_settings())
        self.settings_btn.bind("<Enter>", lambda e: self.settings_btn.config(fg=COLORS['primary']))
        self.settings_btn.bind("<Leave>", lambda e: self.settings_btn.config(fg=COLORS['text_dim']))

        # 실시간 창 보이기/숨기기 토글 버튼
        self._rt_pin_btn = tk.Label(
            opacity_frame, text="RT", font=("Segoe UI", 9),
            fg=COLORS['success'], bg=COLORS['bg_btn'], cursor="hand2", padx=8, pady=8
        )
        self._rt_pin_btn.pack(side="left", padx=1)
        self._rt_pin_btn.bind("<Button-1>", lambda e: self._toggle_rt_pin())
        self._rt_pin_btn.bind("<Enter>", lambda e: self._rt_pin_btn.config(
            fg=COLORS['primary'] if not self._rt_visible else COLORS['success']
        ))
        self._rt_pin_btn.bind("<Leave>", lambda e: self._rt_pin_btn.config(
            fg=COLORS['success'] if self._rt_visible else COLORS['text_dim']
        ))

        # ── 실시간 자막 별도 창 (확정 자막 아래에 배치) ──
        # 전체 높이의 20%를 실시간 창에 할당
        total_h = self.overlay_height
        rt_height = int(total_h * 0.2)
        # 메인 창(확정)은 나머지 80%
        self.overlay_height = total_h - rt_height - 4
        self.root.geometry(f"{self.overlay_width}x{self.overlay_height}+{x_pos}+{y_pos}")
        self._bg_window.geometry(f"{self.overlay_width}x{self.overlay_height}+{x_pos}+{y_pos}")
        rt_x = x_pos
        rt_y = y_pos + self.overlay_height + 4  # 메인 창 바로 아래

        self._rt_window = tk.Toplevel(self.root)
        self._rt_window.overrideredirect(True)
        self._rt_window.attributes("-topmost", True)
        self._rt_window.attributes("-alpha", 1.0)
        self._rt_window.geometry(f"{self.overlay_width}x{rt_height}+{rt_x}+{rt_y}")
        self._rt_window.configure(bg=COLORS['bg_card'])
        self._rt_window.attributes("-transparentcolor", COLORS['bg_card'])

        self._rt_bg_window = tk.Toplevel(self.root)
        self._rt_bg_window.overrideredirect(True)
        self._rt_bg_window.attributes("-topmost", True)
        self._rt_bg_window.attributes("-alpha", self.bg_opacity)
        self._rt_bg_window.geometry(f"{self.overlay_width}x{rt_height}+{rt_x}+{rt_y}")
        self._rt_bg_window.configure(bg=COLORS['bg_card'])
        self._rt_bg_window.lower(self._rt_window)

        rt_frame = tk.Frame(self._rt_window, bg=COLORS['bg_card'])
        rt_frame.pack(fill="both", expand=True, padx=20, pady=4)

        for lang_code in target_languages:
            rt_row = tk.Frame(rt_frame, bg=COLORS['bg_card'])
            rt_row.pack(fill="both", expand=True, pady=1)

            realtime_text = tk.Text(
                rt_row,
                font=("Segoe UI", 14),
                fg=COLORS['text_secondary'],
                bg=COLORS['bg_card'],
                wrap="word",
                borderwidth=0,
                highlightthickness=0,
                state="disabled",
                cursor="arrow",
                height=3,
                takefocus=False
            )
            realtime_text.pack(fill="both", expand=True)
            realtime_text.tag_configure("realtime", foreground=COLORS['text_secondary'])
            realtime_text.tag_configure("dim", foreground=COLORS['text_dim'])

            self.realtime_texts[lang_code] = realtime_text

        # 실시간 창 표시 (항상 보임)
        self._rt_visible = True
        self._show_rt_waiting()

        # 실시간 창 위치 동기화 + 드래그/리사이즈
        self._rt_window.bind("<Configure>", self._sync_rt_bg_window)
        self._rt_drag_x = 0
        self._rt_drag_y = 0
        self._rt_resize_edge = None
        self._rt_resize_data = {}
        self._rt_bg_window.bind("<Button-1>", self._rt_bg_mouse_down)
        self._rt_bg_window.bind("<B1-Motion>", self._rt_bg_mouse_drag)
        self._rt_bg_window.bind("<ButtonRelease-1>", self._rt_bg_mouse_up)
        self._rt_bg_window.bind("<Motion>", self._rt_bg_mouse_move)

        # 배경 윈도우 위치 동기화
        self.root.bind("<Configure>", self._sync_bg_window)

        # bg_window 드래그/리사이즈 (투명 영역 클릭 시 bg_window가 받음)
        self._bg_drag_x = 0
        self._bg_drag_y = 0
        self._bg_resize_edge = None
        self._bg_resize_data = {}
        self._bg_window.bind("<Button-1>", self._bg_mouse_down)
        self._bg_window.bind("<B1-Motion>", self._bg_mouse_drag)
        self._bg_window.bind("<ButtonRelease-1>", self._bg_mouse_up)
        self._bg_window.bind("<Motion>", self._bg_mouse_move)

        # 둥근 모서리 적용
        self.root.update_idletasks()
        apply_rounded_corners(self.root)

        # 웹 서버 시작 (청중용 QR TTS)
        if WEB_SERVER_SUPPORT:
            self.start_web_server()
            # 접속자 수 업데이트 타이머
            self.root.after(2000, self.update_client_count)

    def start_web_server(self):
        """청중용 웹 서버 시작"""
        try:
            web_server.set_languages(LANGUAGES, source_language, target_languages)
            web_server.start()
        except Exception as e:
            pass

    def update_client_count(self):
        """접속자 수 업데이트"""
        if WEB_SERVER_SUPPORT and hasattr(self, 'client_count_label'):
            count = web_server.get_client_count()
            self.client_count_label.config(text=str(count))
            if count > 0:
                self.client_count_label.config(fg=COLORS['success'])
            else:
                self.client_count_label.config(fg=COLORS['text_dim'])
        self.root.after(2000, self.update_client_count)

    def show_qr_popup(self):
        """QR 코드 팝업 표시"""
        if not WEB_SERVER_SUPPORT:
            return

        qr_window = tk.Toplevel(self.root)
        qr_window.title("QR Code - Audience Access")
        qr_window.geometry("420x580")
        qr_window.configure(bg=COLORS['bg_card'])
        qr_window.attributes("-topmost", True)

        # 상태 변수
        is_public = [web_server.is_public()]  # 리스트로 감싸서 클로저에서 수정 가능하게

        # 제목
        title_label = tk.Label(
            qr_window,
            text="Scan to Join",
            font=("Segoe UI", 18, "bold"),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_card']
        )
        title_label.pack(pady=(20, 5))

        # 모드 표시 (Public/Local)
        mode_label = tk.Label(
            qr_window,
            text="Public (ngrok)" if is_public[0] else "Local Network",
            font=("Segoe UI", 10, "bold"),
            fg=COLORS['success'] if is_public[0] else COLORS['secondary'],
            bg=COLORS['bg_card']
        )
        mode_label.pack(pady=(0, 10))

        # 설명
        desc_label = tk.Label(
            qr_window,
            text="Audience can scan this QR code\nto receive real-time translated subtitles with TTS",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_card'],
            justify="center"
        )
        desc_label.pack(pady=(0, 15))

        # QR 코드 프레임
        qr_frame = tk.Frame(qr_window, bg=COLORS['bg_card'])
        qr_frame.pack(pady=5)

        # QR 코드 이미지 레이블 (나중에 업데이트용)
        qr_label = tk.Label(qr_frame, bg=COLORS['bg_card'])
        qr_label.pack()

        # URL 표시
        url_label = tk.Label(
            qr_window,
            text=web_server.get_url() or "Loading...",
            font=("Segoe UI", 11),
            fg=COLORS['primary'],
            bg=COLORS['bg_card'],
            cursor="hand2",
            wraplength=380
        )
        url_label.pack(pady=10)

        # QR 원본 이미지 캐시
        qr_pil_image = [None]  # 클로저용 리스트

        def update_qr_display(qr_size=220):
            """QR 코드와 URL 업데이트"""
            qr_base64 = web_server.get_qr_code()
            url = web_server.get_url()

            if qr_base64:
                import base64
                from io import BytesIO
                try:
                    from PIL import Image, ImageTk
                    if qr_pil_image[0] is None:
                        img_data = base64.b64decode(qr_base64.split(',')[1])
                        qr_pil_image[0] = Image.open(BytesIO(img_data))
                    img = qr_pil_image[0].resize((qr_size, qr_size), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    qr_label.config(image=photo)
                    qr_label.image = photo
                except ImportError:
                    qr_label.config(text="[QR Code]\n(Install Pillow)", font=("Segoe UI", 12))

            url_label.config(text=url)

            # 모드 표시 업데이트
            if is_public[0]:
                mode_label.config(text="Public (ngrok)", fg=COLORS['success'])
            else:
                mode_label.config(text="Local Network", fg=COLORS['secondary'])

        def on_qr_window_resize(event):
            """창 리사이즈 시 QR 이미지 크기 조정"""
            if event.widget != qr_window:
                return
            w = event.width
            h = event.height
            # 창 너비/높이 중 작은 쪽 기준, 여백 제외
            qr_size = min(w, h) - 160
            qr_size = max(100, min(qr_size, 600))
            update_qr_display(qr_size)

        qr_window.bind("<Configure>", on_qr_window_resize)

        # 초기 QR 표시
        update_qr_display()

        # 버튼 프레임
        btn_frame = tk.Frame(qr_window, bg=COLORS['bg_card'])
        btn_frame.pack(pady=10)

        # URL 복사 버튼
        def copy_url():
            url = web_server.get_url()
            qr_window.clipboard_clear()
            qr_window.clipboard_append(url)
            copy_btn.config(text="Copied!")
            qr_window.after(1500, lambda: copy_btn.config(text="Copy URL"))

        copy_btn = tk.Button(
            btn_frame,
            text="Copy URL",
            font=("Segoe UI", 10),
            fg="white",
            bg=COLORS['primary'],
            activebackground=COLORS['primary_hover'],
            activeforeground="white",
            relief="flat",
            padx=15,
            pady=6,
            cursor="hand2",
            command=copy_url
        )
        copy_btn.pack(side="left", padx=5)

        # URL 정보 프레임
        info_frame = tk.Frame(qr_window, bg=COLORS['bg_card'])
        info_frame.pack(pady=10, fill="x", padx=20)

        # Public URL 표시 (있을 경우)
        public_url = web_server.get_public_url()
        local_url = web_server.get_local_url()

        if public_url:
            tk.Label(
                info_frame,
                text=f"Public: {public_url}",
                font=("Segoe UI", 8),
                fg=COLORS['success'],
                bg=COLORS['bg_card'],
                wraplength=360,
                justify="left"
            ).pack(anchor="w")

        tk.Label(
            info_frame,
            text=f"Local: {local_url}",
            font=("Segoe UI", 8),
            fg=COLORS['text_dim'],
            bg=COLORS['bg_card']
        ).pack(anchor="w")

        # 접속자 수
        client_frame = tk.Frame(qr_window, bg=COLORS['bg_card'])
        client_frame.pack(pady=15)

        client_icon = tk.Label(
            client_frame,
            text="Connected:",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_card']
        )
        client_icon.pack(side="left", padx=5)

        client_count = tk.Label(
            client_frame,
            text=str(web_server.get_client_count()),
            font=("Segoe UI", 14, "bold"),
            fg=COLORS['success'],
            bg=COLORS['bg_card']
        )
        client_count.pack(side="left")

        # 접속자 수 업데이트
        def update_popup_count():
            if qr_window.winfo_exists():
                client_count.config(text=str(web_server.get_client_count()))
                qr_window.after(1000, update_popup_count)

        update_popup_count()

    def start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def _stop_mic_stream(self):
        """sounddevice 마이크 스트림 정리"""
        if hasattr(self, 'sd_stream') and self.sd_stream is not None:
            try:
                self.sd_stream.stop()
                self.sd_stream.close()
            except Exception:
                pass
            self.sd_stream = None
        if hasattr(self, 'push_stream') and self.push_stream is not None:
            try:
                self.push_stream.close()
            except Exception:
                pass
            self.push_stream = None

    def setup_recognition(self):
        """음성 인식 설정"""
        try:
            # 기존 마이크 스트림 정리
            self._stop_mic_stream()

            speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)

            # 소스 언어 설정
            lang_info = LANGUAGES.get(source_language, {})
            speech_config.speech_recognition_language = lang_info.get('code', 'ko-KR')

            # 마이크 선택
            audio_config = None
            mic_id = selected_mic_id  # 로컬 복사 (스레드 안전)
            if mic_id is not None and SD_AVAILABLE:
                try:
                    # 선택된 마이크로 PushAudioInputStream 생성
                    audio_format = speechsdk.audio.AudioStreamFormat(
                        samples_per_second=16000, bits_per_sample=16, channels=1
                    )
                    self.push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
                    audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)

                    push_ref = self.push_stream

                    def audio_callback(indata, frames, time_info, status):
                        if push_ref:
                            push_ref.write(indata.tobytes())

                    self.sd_stream = sd.InputStream(
                        device=mic_id,
                        samplerate=16000, channels=1, dtype='int16',
                        blocksize=3200,
                        callback=audio_callback
                    )
                    self.sd_stream.start()

                    mic_name = "?"
                    for m in get_microphone_list():
                        if m['id'] == mic_id:
                            mic_name = m['name']
                            break
                except Exception as mic_err:
                    self._stop_mic_stream()
                    audio_config = None
            else:
                self.push_stream = None
                self.sd_stream = None

            self.speech_recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )

            # 단어장 용어를 PhraseList에 등록 (STT 인식률 향상)
            if terminology_list:
                phrase_list = speechsdk.PhraseListGrammar.from_recognizer(self.speech_recognizer)
                for term in terminology_list:
                    phrase_list.addPhrase(term)

            self.speech_recognizer.recognized.connect(self.on_recognized)
            self.speech_recognizer.recognizing.connect(self.on_recognizing)
            self.speech_recognizer.canceled.connect(self.on_canceled)
            self.speech_recognizer.session_stopped.connect(self.on_session_stopped)
        except Exception as e:
            for lang_code, tw in self.subtitle_texts.items():
                tw.config(state="normal")
                tw.delete("1.0", "end")
                tw.insert("end", f"ERROR: {str(e)[:50]}")
                tw.config(state="disabled", fg=COLORS['danger'])

    def _get_remaining_text(self, full_text):
        """조기 확정된 단어 수만큼 앞에서 잘라내고 잔여 텍스트 반환"""
        with self._early_confirm_lock:
            skip_words = self._early_confirmed_word_count
        if skip_words <= 0:
            return full_text
        words = full_text.split()
        if skip_words >= len(words):
            return ""
        remaining = ' '.join(words[skip_words:])
        return remaining

    def on_recognizing(self, evt):
        """실시간 인식 중"""
        if evt.result.text and is_listening:
            text = evt.result.text
            if len(text.strip()) <= 3:
                return

            # 조기 확정된 단어 수만큼 앞에서 잘라냄
            remaining = self._get_remaining_text(text)
            if not remaining:
                return

            # 중복 제거: 이전과 동일한 잔여 텍스트면 스킵
            if remaining == self._last_realtime_source:
                return
            self._last_realtime_source = remaining

            with self._early_confirm_lock:
                skip = self._early_confirmed_word_count
            print(f"[EarlyConfirm] on_recognizing: full={len(text)}자({len(text.split())}w), skip={skip}w, remaining={len(remaining)}자 | '{remaining[:60]}'")

            # 잔여 텍스트 50자 초과 + 조기 확정 진행 중이 아닐 때 → 조기 확정 시도
            if len(remaining) > 50 and not self._early_confirm_in_progress:
                print(f"[EarlyConfirm] 50자 초과 → early_confirm 시작: '{remaining[:80]}'")
                threading.Thread(
                    target=self.early_confirm, args=(remaining,), daemon=True
                ).start()

            # 잔여 텍스트로 실시간 번역 (이전 번역 진행 중이면 스킵)
            if len(remaining.strip()) > 3 and not self._realtime_in_progress:
                self._realtime_in_progress = True
                threading.Thread(
                    target=self._realtime_translate_wrapper, args=(remaining,), daemon=True
                ).start()

    def on_recognized(self, evt):
        """인식 완료"""
        if evt.result.text and is_listening:
            text = evt.result.text

            # 조기 확정된 부분 제거 → 잔여분만 최종 번역
            # 조기 확정된 단어 수만큼 앞에서 잘라냄
            remaining = self._get_remaining_text(text)

            # 상태 초기화 (다음 발화를 위해)
            with self._early_confirm_lock:
                skip = self._early_confirmed_word_count
                self._early_confirmed_word_count = 0
                self._early_confirm_in_progress = False
            self._last_realtime_source = ""
            self._realtime_in_progress = False

            total_words = len(text.split())
            print(f"[EarlyConfirm] on_recognized: total={total_words}w, skip={skip}w, remaining='{remaining[:60]}' ({len(remaining)}자)")

            if remaining:
                subtitle_queue.put(("recognized", remaining))
            else:
                print(f"[EarlyConfirm] on_recognized: 전부 조기확정됨, 스킵")

    def early_confirm(self, source_text):
        """50자 초과 시 LLM에게 확정 가능한 단어 수를 물어봄 → 원본에서 잘라서 확정"""
        self._early_confirm_in_progress = True
        words = source_text.split()
        total_words = len(words)
        print(f"[EarlyConfirm] === API 호출 시작 === {total_words}w, '{source_text[:100]}'")
        try:
            # 단어에 번호를 매겨서 LLM에게 보여줌 → 숫자만 반환받음 (환각 방지)
            numbered = ' '.join([f"[{i+1}]{w}" for i, w in enumerate(words)])
            if source_language == 'ko':
                boundary_hint = "- Count only up to a natural sentence boundary (period, question mark, or sentence-ending grammar like 다/요/니다/습니다/겁니다/입니다)"
            else:
                boundary_hint = ("- Count only up to a natural sentence boundary (period, question mark, exclamation mark, "
                                 "or a clause boundary before conjunctions like 'and', 'but', 'so', 'because', 'however', "
                                 "or after a complete subordinate clause with comma)")

            prompt = f"""You are a speech recognition assistant. The following text is being spoken in real-time (not yet complete).
Each word is numbered like [1]word [2]word ...

Text: {numbered}

How many words from the beginning form complete sentence(s) or clause(s) that are unlikely to change?
{boundary_hint}
- If no clear boundary exists, answer 0
- Answer with ONLY a single integer (e.g. 0, 5, 12)"""

            if claude_client:
                resp = claude_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=10,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = resp.content[0].text.strip()
            else:
                resp = _llm_call(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens_val=10
                )
                result = resp.choices[0].message.content.strip()
            print(f"[EarlyConfirm] API 응답: '{result}' ({'Claude' if claude_client else 'OpenAI'})")

            # 숫자 파싱
            import re
            match = re.search(r'\d+', result)
            if not match:
                print(f"[EarlyConfirm] 숫자 파싱 실패, 스킵")
                return

            confirm_count = int(match.group())
            print(f"[EarlyConfirm] 확정 단어 수: {confirm_count}/{total_words}")

            if confirm_count <= 0 or confirm_count >= total_words:
                print(f"[EarlyConfirm] 확정 없음 (0이거나 전체)")
                return

            # 확정 텍스트가 너무 짧으면 스킵 (단어 단편 번역 방지)
            confirmed_text = ' '.join(words[:confirm_count])
            if len(confirmed_text) < 10:
                print(f"[EarlyConfirm] 확정 텍스트 너무 짧음 ({len(confirmed_text)}자), 스킵")
                return
            pending_text = ' '.join(words[confirm_count:])

            with self._early_confirm_lock:
                self._early_confirmed_word_count += confirm_count
                total_skip = self._early_confirmed_word_count
            print(f"[EarlyConfirm] 확정! skip={total_skip}w | confirmed='{confirmed_text[:60]}' | pending='{pending_text[:60]}'")

            # 확정 부분 → 최종 번역 → 확정 윈도우로
            self.translate_final(confirmed_text)

            # 잔여 부분 → 실시간 윈도우에 표시
            if pending_text:
                self.realtime_translate(pending_text)

        except Exception as e:
            print(f"[EarlyConfirm] API 오류: {e}")
        finally:
            self._early_confirm_in_progress = False
            print(f"[EarlyConfirm] === 처리 완료 ===")

    def on_canceled(self, evt):
        """음성 인식 취소/타임아웃 시 자동 재연결"""
        reason = evt.cancellation_details.reason
        if is_listening:
            self._reconnect_recognition()

    def on_session_stopped(self, evt):
        """세션 중지 시 자동 재연결"""
        if is_listening:
            self._reconnect_recognition()

    def _reconnect_recognition(self):
        """음성 인식 재연결"""
        def do_reconnect():
            try:
                if self.speech_recognizer:
                    try:
                        self.speech_recognizer.stop_continuous_recognition_async()
                    except:
                        pass
                self.setup_recognition()
                if self.speech_recognizer and is_listening:
                    self.speech_recognizer.start_continuous_recognition_async()
                    source_info = LANGUAGES.get(source_language, {})
                    self.status_label.config(
                        text=f"{source_info.get('flag', '')} Listening",
                        fg=COLORS['success']
                    )
            except Exception as e:
                # 3초 후 재시도
                self.root.after(3000, do_reconnect)

        # UI 스레드에서 실행 (약간의 딜레이)
        self.root.after(1000, do_reconnect)

    def _realtime_translate_wrapper(self, source_text):
        """실시간 번역 래퍼 (진행 중 플래그 관리)"""
        try:
            self.realtime_translate(source_text)
        finally:
            self._realtime_in_progress = False

    def realtime_translate(self, source_text):
        """실시간 번역 (여러 언어 동시)"""
        try:
            term_hint = ""
            if terminology_list:
                term_hint = f"\nTerminology to use: {', '.join(terminology_list)}\n"

            # 타겟 언어 목록
            target_lang_names = [LANGUAGES[lc]['name'] for lc in target_languages if lc in LANGUAGES]

            ko_hint = "\n- For Korean (ko): MUST use formal polite style (합쇼체/존댓말, ending in ~습니다/~입니다/~됩니다)" if 'ko' in target_languages else ""

            prompt = f"""You are a professional simultaneous interpreter. Translate the following text in a professional tone to these languages: {', '.join(target_lang_names)}.
{term_hint}{ko_hint}
Format: Output each translation on a new line with language code prefix like:
{chr(10).join([f'{lc}: [translation]' for lc in target_languages])}

Text: {source_text}"""

            resp = _llm_call([{"role": "user", "content": prompt}], temperature=0.0, max_tokens_val=200)
            result = resp.choices[0].message.content.strip()

            # 결과 파싱
            translations = {}
            for line in result.split('\n'):
                line = line.strip()
                if ':' in line:
                    parts = line.split(':', 1)
                    lang_code = parts[0].strip().lower()
                    translation = parts[1].strip()
                    translations[lang_code] = translation

            subtitle_queue.put(("realtime", translations))
        except Exception as e:
            pass

    def translate_final(self, source_text):
        """최종 번역 (여러 언어 동시)"""
        try:
            context = ""
            if history:
                recent = list(history)[-2:]
                context = "Context: " + " | ".join([str(t) for _, t in recent]) + "\n"

            term_hint = ""
            if terminology_list:
                term_hint = f"\nTerminology to use accurately: {', '.join(terminology_list)}\n"

            # 타겟 언어 목록
            target_lang_names = [LANGUAGES[lc]['name'] for lc in target_languages if lc in LANGUAGES]

            ko_hint = "\n- For Korean (ko): MUST use formal polite style (합쇼체/존댓말, ending in ~습니다/~입니다/~됩니다)" if 'ko' in target_languages else ""

            prompt = f"""You are a professional simultaneous interpreter. Translate the following text naturally and in a professional tone to these languages: {', '.join(target_lang_names)}.
{term_hint}{context}{ko_hint}
Format: Output each translation on a new line with language code prefix like:
{chr(10).join([f'{lc}: [translation]' for lc in target_languages])}

Text: {source_text}"""

            resp = _llm_call([{"role": "user", "content": prompt}], temperature=0.0, max_tokens_val=300)
            result = resp.choices[0].message.content.strip()

            # 결과 파싱
            translations = {}
            for line in result.split('\n'):
                line = line.strip()
                if ':' in line:
                    parts = line.split(':', 1)
                    lang_code = parts[0].strip().lower()
                    translation = parts[1].strip()
                    translations[lang_code] = translation

            history.append((source_text, translations))
            self.full_history.append((source_text, translations))
            subtitle_queue.put(("final", translations))
        except Exception as e:
            pass

    def toggle_pause(self):
        """번역 일시정지/재개 토글"""
        if is_listening:
            self.stop_listening()
            self.pause_btn.config(text="Resume", fg=COLORS['text_dim'])
        else:
            self.start_listening()
            self.pause_btn.config(text="Pause", fg=COLORS['text_dim'])

    def start_listening(self):
        """음성 인식 시작"""
        global is_listening
        if not is_listening and self.speech_recognizer:
            is_listening = True
            self.speech_recognizer.start_continuous_recognition_async()
            source_info = LANGUAGES.get(source_language, {})
            self.status_label.config(text=f"{source_info.get('flag', '')} Listening", fg=COLORS['success'])

    def stop_listening(self):
        """음성 인식 중지"""
        global is_listening
        if is_listening and self.speech_recognizer:
            is_listening = False
            self.speech_recognizer.stop_continuous_recognition_async()
            self._stop_mic_stream()
            self.status_label.config(text="Stopped", fg=COLORS['text_dim'])

    def toggle_dark_mode(self):
        """다크모드 토글"""
        global is_dark_mode
        is_dark_mode = not is_dark_mode
        set_theme(is_dark_mode)
        self.apply_theme()

    def apply_theme(self):
        """오버레이에 테마 적용"""
        # 투명 컬러를 새 테마의 bg_card로 갱신
        self.root.attributes("-transparentcolor", COLORS['bg_card'])

        # 루트 윈도우
        self.root.configure(bg=COLORS['bg_card'])

        # 배경 윈도우 테마 업데이트
        try:
            if self._bg_window.winfo_exists():
                self._bg_window.configure(bg=COLORS['bg_card'])
        except:
            pass

        # 실시간 창 테마 업데이트
        try:
            if hasattr(self, '_rt_window') and self._rt_window.winfo_exists():
                self._rt_window.configure(bg=COLORS['bg_card'])
                self._rt_window.attributes("-transparentcolor", COLORS['bg_card'])
                self._apply_theme_to_widget(self._rt_window)
            if hasattr(self, '_rt_bg_window') and self._rt_bg_window.winfo_exists():
                self._rt_bg_window.configure(bg=COLORS['bg_card'])
        except:
            pass

        # 모든 위젯 업데이트
        self._apply_theme_to_widget(self.root)

        # 다크모드 버튼 텍스트 업데이트
        self.dark_btn.config(text="White" if is_dark_mode else "Dark")

        # 모든 자막 Text 위젯 테마 업데이트
        for lang_code, tw in self.subtitle_texts.items():
            tw.config(bg=COLORS['bg_card'], fg=COLORS['text_primary'])
            tw.tag_configure("final", foreground=COLORS['text_primary'])
        for lang_code, rtw in self.realtime_texts.items():
            rtw.config(bg=COLORS['bg_card'], fg=COLORS['text_secondary'])
            rtw.tag_configure("realtime", foreground=COLORS['text_secondary'])
            rtw.tag_configure("dim", foreground=COLORS['text_dim'])

    def _apply_theme_to_widget(self, widget):
        """위젯에 테마 적용 (재귀)"""
        try:
            if hasattr(widget, 'cget'):
                current_bg = widget.cget('bg')

                color_map = {
                    COLORS_LIGHT['bg_card']: COLORS['bg_card'],
                    COLORS_DARK['bg_card']: COLORS['bg_card'],
                    COLORS_LIGHT['bg_btn']: COLORS['bg_btn'],
                    COLORS_DARK['bg_btn']: COLORS['bg_btn'],
                    '#FFFFFF': COLORS['bg_card'],
                    '#1f2940': COLORS['bg_card'],
                    '#FEFEFE': COLORS['bg_btn'],
                    '#1f2941': COLORS['bg_btn'],
                }

                if current_bg in color_map:
                    widget.configure(bg=color_map[current_bg])

                # 텍스트 색상
                widget_class = widget.winfo_class()
                if widget_class == 'Label':
                    try:
                        current_fg = widget.cget('fg')
                        fg_map = {
                            COLORS_LIGHT['text_primary']: COLORS['text_primary'],
                            COLORS_DARK['text_primary']: COLORS['text_primary'],
                            COLORS_LIGHT['text_dim']: COLORS['text_dim'],
                            COLORS_DARK['text_dim']: COLORS['text_dim'],
                            '#2D3748': COLORS['text_primary'],
                            '#E8E8E8': COLORS['text_primary'],
                            '#A0AEC0': COLORS['text_dim'],
                            '#6B7280': COLORS['text_dim'],
                        }
                        if current_fg in fg_map:
                            widget.configure(fg=fg_map[current_fg])
                    except:
                        pass
        except:
            pass

        for child in widget.winfo_children():
            self._apply_theme_to_widget(child)

    def _toggle_spacer(self):
        """자막 하단 여백 토글 (화면 1/4 여백 → 자막 3/4 영역)"""
        if self._spacer_visible:
            self._bottom_spacer.pack_forget()
            self._spacer_visible = False
            self.spacer_btn.config(fg=COLORS['text_dim'])
        else:
            h = self.root.winfo_height() // 4
            self._bottom_spacer.config(height=h)
            self._bottom_spacer.pack(fill="x")
            self._bottom_spacer.pack_propagate(False)
            self._spacer_visible = True
            self.spacer_btn.config(fg=COLORS['primary'])

    def _minimize_window(self):
        """overrideredirect 창 최소화 (Windows 우회)"""
        # bg_window, 실시간 창도 숨기기
        try:
            if self._bg_window.winfo_exists():
                self._bg_window.withdraw()
        except:
            pass
        try:
            if hasattr(self, '_rt_window') and self._rt_window.winfo_exists():
                self._rt_window.withdraw()
            if hasattr(self, '_rt_bg_window') and self._rt_bg_window.winfo_exists():
                self._rt_bg_window.withdraw()
        except:
            pass
        self.root.overrideredirect(False)
        self.root.iconify()
        def _on_restore(event):
            if self.root.state() == 'normal':
                self.root.overrideredirect(True)
                self.root.attributes("-topmost", True)
                # bg_window 복원
                try:
                    if self._bg_window.winfo_exists():
                        self._bg_window.deiconify()
                        self._sync_bg_window()
                except:
                    pass
                # 실시간 창 복원 (내용 있을 때만)
                if hasattr(self, '_rt_visible') and self._rt_visible:
                    try:
                        self._rt_window.deiconify()
                        self._rt_bg_window.deiconify()
                        self._sync_rt_bg_window()
                    except:
                        pass
                self.root.unbind("<Map>")
        self.root.bind("<Map>", _on_restore)

    def _go_settings_direct(self):
        """저장 없이 바로 설정 화면으로 돌아가기"""
        global is_listening
        is_listening = False
        if self.speech_recognizer:
            try:
                self.speech_recognizer.stop_continuous_recognition_async()
            except:
                pass
        try:
            if self._bg_window.winfo_exists():
                self._bg_window.destroy()
        except:
            pass
        try:
            if hasattr(self, '_rt_window') and self._rt_window.winfo_exists():
                self._rt_window.destroy()
            if hasattr(self, '_rt_bg_window') and self._rt_bg_window.winfo_exists():
                self._rt_bg_window.destroy()
        except:
            pass
        self.go_back = True
        self.root.quit()
        self.root.destroy()

    def back_to_settings(self):
        """다운로드 모달 표시 (음성인식은 계속 유지)"""
        self._show_download_modal()

    def _back_translate_korean(self, english_texts, source_texts):
        """영어 번역문들을 한국어로 역번역 (LLM 경유로 정확도 향상)"""
        try:
            combined = "\n".join([f"{i+1}. {t}" for i, t in enumerate(english_texts)])
            prompt = f"""You are a professional English-to-Korean translator.
Translate each numbered English sentence below into natural, professional-toned Korean.
MUST use formal polite style (합쇼체/존댓말, ending in ~습니다/~입니다/~됩니다).
Keep the numbering. Output ONLY the Korean translations, one per line.

{combined}"""

            resp = _llm_call([{"role": "user", "content": prompt}], temperature=0.0, max_tokens_val=2000)
            result = resp.choices[0].message.content.strip()

            # 번호별로 파싱
            ko_texts = []
            for line in result.split('\n'):
                line = line.strip()
                if not line:
                    continue
                # "1. 번역문" 형태에서 번호 제거
                import re
                m = re.match(r'^\d+[\.\)]\s*', line)
                if m:
                    ko_texts.append(line[m.end():].strip())
                else:
                    ko_texts.append(line)

            # 개수가 맞지 않으면 원본(STT) 사용
            if len(ko_texts) != len(english_texts):
                return source_texts
            return ko_texts
        except Exception as e:
            return source_texts

    def _build_full_transcript(self):
        """전체 기록을 텍스트로 변환 (한국어는 영어→한국어 역번역으로 정확도 향상)"""
        # 영어 번역문 & 원문 수집
        en_texts = []
        source_texts = []
        for source, translations in self.full_history:
            source_texts.append(source)
            en_text = translations.get('en', '')
            if not en_text:
                for lc in target_languages:
                    if lc in translations and translations[lc]:
                        en_text = translations[lc]
                        break
            en_texts.append(en_text if en_text else source)

        # 영어→한국어 역번역 (배치)
        ko_texts = self._back_translate_korean(en_texts, source_texts)

        lines = []
        lines.append("=" * 50)
        lines.append("  Lecture Lens - Full Transcript")
        lines.append("=" * 50)
        lines.append("")
        for i, (source, translations) in enumerate(self.full_history):
            ko = ko_texts[i] if i < len(ko_texts) else source
            lines.append(f"[{i+1}] (한국어) {ko}")
            for lang_code in target_languages:
                lang_name = LANGUAGES.get(lang_code, {}).get('name', lang_code)
                trans = translations.get(lang_code, '')
                if trans:
                    lines.append(f"    ({lang_name}) {trans}")
            lines.append("")
        lines.append(f"Total: {len(self.full_history)} segments")
        return "\n".join(lines)

    def _generate_summary(self):
        """GPT로 요약본 생성"""
        try:
            # 원문 + 번역문 합치기
            all_source = []
            all_translations = {lc: [] for lc in target_languages}
            for source, translations in self.full_history:
                all_source.append(source)
                for lc in target_languages:
                    if lc in translations:
                        all_translations[lc].append(translations[lc])

            source_text = " ".join(all_source)
            trans_texts = {}
            for lc in target_languages:
                trans_texts[lc] = " ".join(all_translations[lc])

            # 요약 요청
            lang_names = [LANGUAGES[lc]['name'] for lc in target_languages if lc in LANGUAGES]
            prompt = f"""Summarize the following lecture/presentation content concisely.
Provide a summary in the original language ({LANGUAGES.get(source_language, {}).get('name', source_language)}) and also in: {', '.join(lang_names)}.

Format:
[{LANGUAGES.get(source_language, {}).get('name', source_language)} Summary]
(summary here)

"""
            for lc in target_languages:
                lang_name = LANGUAGES.get(lc, {}).get('name', lc)
                prompt += f"[{lang_name} Summary]\n(summary here)\n\n"

            prompt += f"""Original text:
{source_text[:3000]}"""

            resp = _llm_call([{"role": "user", "content": prompt}], temperature=0.3, max_tokens_val=800)
            summary = resp.choices[0].message.content.strip()

            lines = []
            lines.append("=" * 50)
            lines.append("  Lecture Lens - Summary")
            lines.append("=" * 50)
            lines.append("")
            lines.append(summary)
            lines.append("")
            lines.append(f"(Based on {len(self.full_history)} segments)")
            return "\n".join(lines)
        except Exception as e:
            return f"Summary generation failed: {e}"

    def _download_txt(self, content, default_name):
        """텍스트를 .txt 파일로 저장"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            initialfile=default_name,
            title="Save As"
        )
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False

    def _show_download_modal(self):
        """다운로드 모달 표시"""
        self.modal = tk.Toplevel(self.root)
        self.modal.overrideredirect(True)
        self.modal.configure(bg=COLORS['bg_main'])
        self.modal.transient(self.root)
        self.modal.attributes("-topmost", True)

        width, height = 420, 340
        screen_w = self.modal.winfo_screenwidth()
        screen_h = self.modal.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.modal.geometry(f"{width}x{height}+{x}+{y}")

        # 맨 앞으로 가져오기
        self.modal.lift()
        self.modal.focus_force()

        # 드래그 변수
        self._modal_drag_x = 0
        self._modal_drag_y = 0

        # 타이틀바
        titlebar = tk.Frame(self.modal, bg=COLORS['bg_white'], height=45)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        def modal_start_drag(event):
            self._modal_drag_x = event.x
            self._modal_drag_y = event.y

        def modal_on_drag(event):
            dx = event.x - self._modal_drag_x
            dy = event.y - self._modal_drag_y
            nx = self.modal.winfo_x() + dx
            ny = self.modal.winfo_y() + dy
            self.modal.geometry(f"+{nx}+{ny}")

        titlebar.bind("<Button-1>", modal_start_drag)
        titlebar.bind("<B1-Motion>", modal_on_drag)

        title_label = tk.Label(
            titlebar, text="Session Ended",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS['text_primary'], bg=COLORS['bg_white']
        )
        title_label.pack(side="left", padx=20)
        title_label.bind("<Button-1>", modal_start_drag)
        title_label.bind("<B1-Motion>", modal_on_drag)

        # 컨테이너
        container = tk.Frame(self.modal, bg=COLORS['bg_main'])
        container.pack(fill="both", expand=True, padx=30, pady=20)

        # 안내 메시지
        tk.Label(
            container,
            text=f"{len(self.full_history)} segments recorded",
            font=("Segoe UI", 14, "bold"),
            fg=COLORS['text_primary'], bg=COLORS['bg_main']
        ).pack(anchor="w", pady=(0, 5))

        tk.Label(
            container,
            text="Download your session transcript before leaving.",
            font=("Segoe UI", 10),
            fg=COLORS['text_secondary'], bg=COLORS['bg_main']
        ).pack(anchor="w", pady=(0, 20))

        # 전문 다운로드 버튼
        transcript_btn = tk.Frame(container, bg=COLORS['primary'], cursor="hand2")
        transcript_btn.pack(fill="x", pady=(0, 10), ipady=12)

        transcript_label = tk.Label(
            transcript_btn,
            text="Download Full Transcript (.txt)",
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF", bg=COLORS['primary']
        )
        transcript_label.pack()

        self._transcript_generating = False

        def on_download_transcript(e=None):
            if self._transcript_generating:
                return
            self._transcript_generating = True
            transcript_label.config(text="Generating transcript...")

            def generate():
                content = self._build_full_transcript()
                self.modal.after(0, lambda: _transcript_done(content))

            def _transcript_done(content):
                self._transcript_generating = False
                transcript_label.config(text="Download Full Transcript (.txt)")
                self._download_txt(content, "transcript.txt")

            threading.Thread(target=generate, daemon=True).start()

        for w in [transcript_btn, transcript_label]:
            w.bind("<Button-1>", on_download_transcript)
            w.bind("<Enter>", lambda e: transcript_btn.config(bg=COLORS['primary_hover']) or transcript_label.config(bg=COLORS['primary_hover']))
            w.bind("<Leave>", lambda e: transcript_btn.config(bg=COLORS['primary']) or transcript_label.config(bg=COLORS['primary']))

        # 요약본 다운로드 버튼
        summary_btn = tk.Frame(container, bg=COLORS['secondary'], cursor="hand2")
        summary_btn.pack(fill="x", pady=(0, 10), ipady=12)

        summary_label = tk.Label(
            summary_btn,
            text="Download Summary (.txt)",
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF", bg=COLORS['secondary']
        )
        summary_label.pack()

        self._summary_generating = False

        def on_download_summary(e=None):
            if self._summary_generating:
                return
            self._summary_generating = True
            summary_label.config(text="Generating summary...")

            def generate():
                content = self._generate_summary()
                self.modal.after(0, lambda: _summary_done(content))

            def _summary_done(content):
                self._summary_generating = False
                summary_label.config(text="Download Summary (.txt)")
                self._download_txt(content, "summary.txt")

            threading.Thread(target=generate, daemon=True).start()

        for w in [summary_btn, summary_label]:
            w.bind("<Button-1>", on_download_summary)
            w.bind("<Enter>", lambda e: summary_btn.config(bg=COLORS['primary']) or summary_label.config(bg=COLORS['primary']))
            w.bind("<Leave>", lambda e: summary_btn.config(bg=COLORS['secondary']) or summary_label.config(bg=COLORS['secondary']))

        # 하단 버튼 프레임
        bottom_frame = tk.Frame(container, bg=COLORS['bg_main'])
        bottom_frame.pack(fill="x", pady=(15, 0))

        # 닫기 버튼 (모달만 닫고 자막 계속)
        close_btn = tk.Label(
            bottom_frame,
            text="Close",
            font=("Segoe UI", 10),
            fg=COLORS['text_dim'], bg=COLORS['bg_main'],
            cursor="hand2"
        )
        close_btn.pack(side="left")

        def on_close(e=None):
            self.full_history.clear()
            self.modal.destroy()

        close_btn.bind("<Button-1>", on_close)
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=COLORS['text_secondary']))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLORS['text_dim']))

        # Settings로 이동 (세션 종료)
        settings_btn = tk.Label(
            bottom_frame,
            text="Go to Settings",
            font=("Segoe UI", 10),
            fg=COLORS['text_dim'], bg=COLORS['bg_main'],
            cursor="hand2"
        )
        settings_btn.pack(side="right")

        def on_go_settings(e=None):
            global is_listening
            is_listening = False
            if self.speech_recognizer:
                try:
                    self.speech_recognizer.stop_continuous_recognition_async()
                except:
                    pass
            self.modal.destroy()
            self.go_back = True
            self.root.quit()
            self.root.destroy()

        settings_btn.bind("<Button-1>", on_go_settings)
        settings_btn.bind("<Enter>", lambda e: settings_btn.config(fg=COLORS['text_secondary']))
        settings_btn.bind("<Leave>", lambda e: settings_btn.config(fg=COLORS['text_dim']))

        self.modal.grab_set()
        self.modal.focus_force()

        # 둥근 모서리
        self.modal.update_idletasks()
        apply_rounded_corners(self.modal)

    def quit_app(self):
        """앱 종료"""
        global is_listening
        is_listening = False
        if self.speech_recognizer:
            try:
                self.speech_recognizer.stop_continuous_recognition_async()
            except:
                pass
        try:
            if self._bg_window.winfo_exists():
                self._bg_window.destroy()
        except:
            pass
        try:
            if hasattr(self, '_rt_window') and self._rt_window.winfo_exists():
                self._rt_window.destroy()
            if hasattr(self, '_rt_bg_window') and self._rt_bg_window.winfo_exists():
                self._rt_bg_window.destroy()
        except:
            pass
        self.go_back = False
        self.root.quit()
        self.root.destroy()

    def _sync_bg_window(self, event=None):
        """배경 윈도우를 메인 윈도우와 동기화"""
        try:
            if not self._bg_window.winfo_exists():
                return
            geo = self.root.geometry()
            self._bg_window.geometry(geo)
            self._bg_window.lower(self.root)
        except:
            pass

    def _sync_rt_bg_window(self, event=None):
        """실시간 배경 윈도우를 실시간 윈도우와 동기화"""
        try:
            if not self._rt_bg_window.winfo_exists():
                return
            geo = self._rt_window.geometry()
            self._rt_bg_window.geometry(geo)
            self._rt_bg_window.lower(self._rt_window)
        except:
            pass

    # ── 실시간 창 드래그/리사이즈 핸들러 ──

    def _rt_bg_get_edge(self, x, y):
        """실시간 bg_window 가장자리 판별"""
        w = self._rt_bg_window.winfo_width()
        h = self._rt_bg_window.winfo_height()
        edge = ""
        if y < 6: edge += "n"
        elif y > h - 6: edge += "s"
        if x < 6: edge += "w"
        elif x > w - 6: edge += "e"
        return edge if edge else None

    def _rt_bg_mouse_move(self, event):
        """실시간 bg_window 마우스 이동 - 커서 변경"""
        edge = self._rt_bg_get_edge(event.x, event.y)
        cursor_map = {
            "n": "top_side", "s": "bottom_side", "e": "right_side", "w": "left_side",
            "ne": "top_right_corner", "nw": "top_left_corner",
            "se": "bottom_right_corner", "sw": "bottom_left_corner",
        }
        self._rt_bg_window.config(cursor=cursor_map.get(edge, ""))

    def _rt_bg_mouse_down(self, event):
        """실시간 bg_window 클릭 - 드래그 또는 리사이즈 시작"""
        self._rt_bg_window.lower(self._rt_window)
        edge = self._rt_bg_get_edge(event.x, event.y)
        if edge:
            self._rt_resize_edge = edge
            self._rt_resize_data = {
                'x': event.x_root, 'y': event.y_root,
                'w': self._rt_window.winfo_width(), 'h': self._rt_window.winfo_height(),
                'px': self._rt_window.winfo_x(), 'py': self._rt_window.winfo_y()
            }
        else:
            self._rt_resize_edge = None
            self._rt_drag_x = event.x
            self._rt_drag_y = event.y

    def _rt_bg_mouse_drag(self, event):
        """실시간 bg_window 드래그 - 이동 또는 리사이즈"""
        if self._rt_resize_edge:
            d = self._rt_resize_data
            dx = event.x_root - d['x']
            dy = event.y_root - d['y']
            new_x, new_y, new_w, new_h = d['px'], d['py'], d['w'], d['h']
            edge = self._rt_resize_edge
            if "e" in edge: new_w = max(50, d['w'] + dx)
            if "w" in edge:
                new_w = max(50, d['w'] - dx)
                if new_w > 50: new_x = d['px'] + dx
            if "s" in edge: new_h = max(50, d['h'] + dy)
            if "n" in edge:
                new_h = max(50, d['h'] - dy)
                if new_h > 50: new_y = d['py'] + dy
            geo = f"{new_w}x{new_h}+{new_x}+{new_y}"
            self._rt_window.geometry(geo)
            self._rt_bg_window.geometry(geo)
        else:
            x = self._rt_bg_window.winfo_x() + event.x - self._rt_drag_x
            y = self._rt_bg_window.winfo_y() + event.y - self._rt_drag_y
            self._rt_window.geometry(f"+{x}+{y}")
            self._rt_bg_window.geometry(f"+{x}+{y}")

    def _rt_bg_mouse_up(self, event):
        """실시간 bg_window 마우스 해제"""
        self._rt_bg_window.lower(self._rt_window)
        self._rt_resize_edge = None

    def _bg_mouse_move(self, event):
        """bg_window 마우스 이동 - 커서 변경"""
        edge = self._bg_get_edge(event.x, event.y)
        cursor_map = {
            "n": "top_side", "s": "bottom_side", "e": "right_side", "w": "left_side",
            "ne": "top_right_corner", "nw": "top_left_corner",
            "se": "bottom_right_corner", "sw": "bottom_left_corner",
        }
        self._bg_window.config(cursor=cursor_map.get(edge, ""))

    def _bg_get_edge(self, x, y):
        """bg_window 가장자리 판별"""
        w = self._bg_window.winfo_width()
        h = self._bg_window.winfo_height()
        edge = ""
        if y < 6: edge += "n"
        elif y > h - 6: edge += "s"
        if x < 6: edge += "w"
        elif x > w - 6: edge += "e"
        return edge if edge else None

    def _bg_mouse_down(self, event):
        """bg_window 클릭 - 드래그 또는 리사이즈 시작"""
        # bg_window가 클릭 시 앞으로 올라오지 않도록 다시 뒤로
        self._bg_window.lower(self.root)
        edge = self._bg_get_edge(event.x, event.y)
        if edge:
            self._bg_resize_edge = edge
            self._bg_resize_data = {
                'x': event.x_root, 'y': event.y_root,
                'w': self.root.winfo_width(), 'h': self.root.winfo_height(),
                'px': self.root.winfo_x(), 'py': self.root.winfo_y()
            }
        else:
            self._bg_resize_edge = None
            self._bg_drag_x = event.x
            self._bg_drag_y = event.y

    def _bg_mouse_drag(self, event):
        """bg_window 드래그 - 양쪽 창 이동 또는 리사이즈"""
        if self._bg_resize_edge:
            d = self._bg_resize_data
            dx = event.x_root - d['x']
            dy = event.y_root - d['y']
            new_x, new_y, new_w, new_h = d['px'], d['py'], d['w'], d['h']
            edge = self._bg_resize_edge
            if "e" in edge: new_w = max(50, d['w'] + dx)
            if "w" in edge:
                new_w = max(50, d['w'] - dx)
                if new_w > 50: new_x = d['px'] + dx
            if "s" in edge: new_h = max(50, d['h'] + dy)
            if "n" in edge:
                new_h = max(50, d['h'] - dy)
                if new_h > 50: new_y = d['py'] + dy
            geo = f"{new_w}x{new_h}+{new_x}+{new_y}"
            self.root.geometry(geo)
            self._bg_window.geometry(geo)
        else:
            x = self._bg_window.winfo_x() + event.x - self._bg_drag_x
            y = self._bg_window.winfo_y() + event.y - self._bg_drag_y
            self.root.geometry(f"+{x}+{y}")
            self._bg_window.geometry(f"+{x}+{y}")

    def _bg_mouse_up(self, event):
        """bg_window 마우스 해제"""
        # z-order 유지
        self._bg_window.lower(self.root)
        self._bg_resize_edge = None

    def _change_opacity(self, delta):
        """배경 투명도 변경"""
        new_opacity = round(self.bg_opacity + delta, 2)
        if new_opacity < 0.1 or new_opacity > 1.0:
            return
        self.bg_opacity = new_opacity
        self._bg_window.attributes("-alpha", new_opacity)
        if hasattr(self, '_rt_bg_window') and self._rt_bg_window.winfo_exists():
            self._rt_bg_window.attributes("-alpha", new_opacity)
        self._opacity_label.config(text=f"{int(new_opacity * 100)}%")

    def _change_font_size(self, delta):
        """자막 폰트 크기 변경"""
        new_size = self.subtitle_font_size + delta
        if new_size < 8 or new_size > 40:
            return
        self.subtitle_font_size = new_size
        self.font_size_label.config(text=str(new_size))
        for tw in self.subtitle_texts.values():
            tw.config(font=("Segoe UI", new_size))
        for rtw in self.realtime_texts.values():
            rtw.config(font=("Segoe UI", new_size))

    def _clear_realtime(self, lang_code):
        """실시간 번역 임시 텍스트 제거"""
        rtw = self.realtime_texts.get(lang_code)
        if rtw and self._realtime_tags.get(lang_code):
            rtw.config(state="normal")
            rtw.delete("1.0", "end")
            rtw.config(state="disabled")
            self._realtime_tags[lang_code] = False
            # 폰트 크기 캐시 초기화
            last_key = f'_rt_last_size_{lang_code}'
            if hasattr(self, last_key):
                delattr(self, last_key)
        # 모든 실시간 태그가 꺼져있으면 대기 텍스트 표시
        if not any(self._realtime_tags.values()):
            self._show_rt_waiting()

    def _show_rt_waiting(self):
        """실시간 창에 대기 상태 표시 (고정 모드용)"""
        for rtw in self.realtime_texts.values():
            rtw.config(state="normal", font=("Segoe UI", self.subtitle_font_size))
            rtw.delete("1.0", "end")
            rtw.insert("1.0", "...", "dim")
            rtw.config(state="disabled")

    def _smooth_scroll_to_end(self, tw):
        """새 확정 자막이 추가되면 부드럽게 끝까지 스크롤"""
        tw.update_idletasks()
        self._scroll_seq = getattr(self, '_scroll_seq', 0) + 1
        seq = self._scroll_seq
        # 즉시 시작 (딜레이 없이 부드럽게)
        self.root.after(16, lambda: self._auto_scroll_tick(tw, seq))

    def _center_scroll(self, tw, new_text_len=0):
        """새 자막 스크롤 처리. 긴 텍스트는 최상단부터 보여주고 2초 후 천천히 끝까지 스크롤"""
        tw.update_idletasks()

        if new_text_len > 50:
            # 긴 텍스트 → 새 자막 시작을 최상단에 배치
            content = tw.get("1.0", "end")
            last_sep = content.rfind("\n\n")
            if last_sep >= 0:
                char_offset = last_sep + 2
                start_index = f"1.0+{char_offset}c"
            else:
                start_index = "1.0"

            tw.yview(start_index)
            tw.update_idletasks()

            # 2초 후 끝까지 무조건 스크롤
            self._scroll_seq = getattr(self, '_scroll_seq', 0) + 1
            seq = self._scroll_seq
            self.root.after(2000, lambda: self._auto_scroll_tick(tw, seq))
        else:
            # 짧은 텍스트 → 끝 보여주기
            tw.see("end")

    def _auto_scroll_tick(self, tw, seq):
        """스크롤 애니메이션: 부드럽게 끝까지 스크롤"""
        if seq != self._scroll_seq:
            return
        try:
            s, e = tw.yview()
            if e >= 0.999:
                tw.see("end")
                return
            # 남은 거리의 15%씩 이동 (easing)
            remaining = 1.0 - e
            step = max(0.005, remaining * 0.15)
            tw.yview_moveto(s + step)
            self.root.after(50, lambda: self._auto_scroll_tick(tw, seq))
        except Exception:
            pass

    def _show_rt_window(self):
        """실시간 자막 창 표시"""
        if not self._rt_visible:
            self._rt_visible = True
            self._rt_window.deiconify()
            self._rt_bg_window.deiconify()
            self._sync_rt_bg_window()
            self._rt_window.lift()
            self._rt_bg_window.lower(self._rt_window)

    def _toggle_rt_pin(self):
        """실시간 창 보이기/숨기기 토글"""
        if self._rt_visible:
            self._rt_visible = False
            self._rt_window.withdraw()
            self._rt_bg_window.withdraw()
            self._rt_pin_btn.config(fg=COLORS['text_dim'])
        else:
            self._rt_visible = True
            self._rt_window.deiconify()
            self._rt_bg_window.deiconify()
            self._sync_rt_bg_window()
            self._rt_window.lift()
            self._rt_bg_window.lower(self._rt_window)
            self._rt_pin_btn.config(fg=COLORS['success'])
            if not any(self._realtime_tags.values()):
                self._show_rt_waiting()

    def _set_realtime_text(self, lang_code, text, tag="realtime"):
        """실시간 텍스트를 고정 영역 안에 맞추어 폰트 축소 (모바일 방식)"""
        rtw = self.realtime_texts.get(lang_code)
        if not rtw:
            return
        self._show_rt_window()
        rtw.config(state="normal")

        # 이전에 축소된 크기가 있으면 그 크기부터 시작 (깜빡임 방지)
        last_key = f'_rt_last_size_{lang_code}'
        last_size = getattr(self, last_key, self.subtitle_font_size)
        # 기본 크기가 바뀌었으면 기본 크기부터
        size = min(self.subtitle_font_size, last_size)
        min_size = 8

        # 먼저 이전 크기로 시도
        rtw.config(font=("Segoe UI", size))
        rtw.delete("1.0", "end")
        rtw.insert("1.0", text, tag)
        rtw.update_idletasks()

        if rtw.bbox("end-1c") is None:
            # 넘치면 더 줄이기
            size -= 1
            while size >= min_size:
                rtw.config(font=("Segoe UI", size))
                rtw.delete("1.0", "end")
                rtw.insert("1.0", text, tag)
                rtw.update_idletasks()
                if rtw.bbox("end-1c") is not None:
                    break
                size -= 1
        elif size < self.subtitle_font_size:
            # 여유 있으면 키워보기
            while size < self.subtitle_font_size:
                size += 1
                rtw.config(font=("Segoe UI", size))
                rtw.delete("1.0", "end")
                rtw.insert("1.0", text, tag)
                rtw.update_idletasks()
                if rtw.bbox("end-1c") is None:
                    size -= 1
                    rtw.config(font=("Segoe UI", size))
                    rtw.delete("1.0", "end")
                    rtw.insert("1.0", text, tag)
                    break

        setattr(self, last_key, size)
        rtw.config(state="disabled")
        self._realtime_tags[lang_code] = True

    def _append_realtime(self, lang_code, text):
        """실시간 번역 임시 텍스트 표시 (별도 영역, 높이 제한+폰트 축소)"""
        self._set_realtime_text(lang_code, text, "realtime")

    def _init_bottom_padding(self, lang_code):
        """확정 자막이 아래서부터 쌓이도록 빈 패딩 삽입"""
        tw = self.subtitle_texts.get(lang_code)
        if not tw:
            return
        tw.update_idletasks()
        # 위젯 높이를 줄 수로 환산하여 빈 줄 삽입
        widget_h = tw.winfo_height()
        font = tw.cget("font")
        import tkinter.font as tkfont
        line_h = tkfont.Font(font=font).metrics("linespace")
        if line_h <= 0:
            line_h = 20
        pad_lines = max(0, widget_h // line_h)
        tw.config(state="normal")
        tw.delete("1.0", "end")
        tw.insert("1.0", "\n" * pad_lines, "pad")
        tw.tag_configure("pad", foreground=COLORS['bg_card'])  # 투명하게
        tw.config(state="disabled")
        tw.see("end")
        if not hasattr(self, '_bottom_pad_lines'):
            self._bottom_pad_lines = {}
        self._bottom_pad_lines[lang_code] = pad_lines

    def _append_final(self, lang_code, text):
        """확정 번역을 누적 추가 — 아래서부터 쌓임"""
        import re
        tw = self.subtitle_texts.get(lang_code)
        if not tw:
            return
        self._clear_realtime(lang_code)

        # 최초 호출 시 패딩 초기화
        if not hasattr(self, '_bottom_pad_lines'):
            self._bottom_pad_lines = {}
        if lang_code not in self._bottom_pad_lines:
            self._init_bottom_padding(lang_code)

        # 문장 단위 줄바꿈: 문장 끝 부호 뒤 공백을 줄바꿈으로 변환
        formatted = re.sub(r'([.!?])\s+', r'\1\n\n', text.strip())
        new_lines = formatted.count('\n') + 1

        tw.config(state="normal")
        # 상단 패딩 줄 제거 (새 자막 줄 수만큼)
        pad_remaining = self._bottom_pad_lines.get(lang_code, 0)
        remove_count = min(new_lines + 1, pad_remaining)  # +1 for spacing
        if remove_count > 0:
            tw.delete("1.0", f"{remove_count + 1}.0")
            self._bottom_pad_lines[lang_code] = pad_remaining - remove_count

        # 자막 추가
        content = tw.get("1.0", "end").strip()
        if content:
            tw.insert("end", "\n\n" + formatted, "final")
        else:
            tw.insert("end", formatted, "final")
        tw.config(state="disabled")
        # 부드럽게 끝까지 스크롤
        self._smooth_scroll_to_end(tw)

    def _show_dim(self, lang_code, text):
        """번역 중 등 임시 메시지 표시"""
        self._set_realtime_text(lang_code, text, "dim")

    def check_queue(self):
        """큐 확인 및 자막 업데이트 (다국어 지원, 누적 표시)"""
        global last_realtime_translation
        try:
            while True:
                msg_type, data = subtitle_queue.get_nowait()

                # 웹 서버로 브로드캐스트 (청중용 TTS)
                if WEB_SERVER_SUPPORT:
                    web_server.broadcast_subtitle(msg_type, data)

                if msg_type == "realtime":
                    if data != last_realtime_translation:
                        last_realtime_translation = data
                        if isinstance(data, dict):
                            for lang_code in self.subtitle_texts:
                                translation = data.get(lang_code, "...")
                                self._append_realtime(lang_code, translation)
                        else:
                            for lang_code in self.subtitle_texts:
                                self._append_realtime(lang_code, str(data))
                        source_info = LANGUAGES.get(source_language, {})
                        self.status_label.config(text=f"{source_info.get('flag', '')} Processing", fg=COLORS['secondary'])

                elif msg_type == "recognized":
                    last_realtime_translation = ''
                    for lang_code in self.subtitle_texts:
                        self._show_dim(lang_code, "Translating...")
                    source_info = LANGUAGES.get(source_language, {})
                    self.status_label.config(text=f"{source_info.get('flag', '')} Translating", fg=COLORS['primary'])
                    threading.Thread(
                        target=self.translate_final, args=(data,), daemon=True
                    ).start()

                elif msg_type == "final":
                    if isinstance(data, dict):
                        for lang_code in self.subtitle_texts:
                            translation = data.get(lang_code, "")
                            if translation:
                                self._append_final(lang_code, translation)
                    else:
                        for lang_code in self.subtitle_texts:
                            self._append_final(lang_code, str(data))
                    source_info = LANGUAGES.get(source_language, {})
                    self.status_label.config(text=f"{source_info.get('flag', '')} Listening", fg=COLORS['success'])
        except queue.Empty:
            pass
        self.root.after(50, self.check_queue)

    def run(self):
        """앱 실행"""
        self.root.mainloop()


# ========================
# 6. 메인 실행
# ========================
def startup_diagnostics():
    """빌드 전/실행 시 환경 점검"""
    errors = []
    warnings = []

    # 1. .env 및 API 키 확인
    if not os.path.exists('.env') and not os.environ.get('OPENAI_API_KEY'):
        errors.append(".env file not found and OPENAI_API_KEY not set")
    if not SPEECH_KEY or SPEECH_KEY == 'your-key-here':
        errors.append("SPEECH_KEY is missing or placeholder")
    if not SPEECH_REGION:
        errors.append("SPEECH_REGION is missing")
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key or api_key.startswith('your-'):
        errors.append("OPENAI_API_KEY is missing or placeholder")

    # 2. 필수 패키지 확인
    required = {
        'azure.cognitiveservices.speech': 'azure-cognitiveservices-speech',
        'openai': 'openai',
        'flask': 'flask',
        'flask_socketio': 'flask-socketio',
        'qrcode': 'qrcode',
    }
    optional = {
        'sounddevice': 'sounddevice (mic selection)',
        'pyngrok': 'pyngrok (external access)',
        'anthropic': 'anthropic (Claude for early confirm)',
    }

    for mod, name in required.items():
        try:
            __import__(mod)
        except ImportError:
            errors.append(f"Missing required package: {name}")

    for mod, name in optional.items():
        try:
            __import__(mod)
        except ImportError:
            warnings.append(f"Missing optional package: {name}")

    # 3. ngrok 토큰 확인
    ngrok_token = os.environ.get('NGROK_AUTH_TOKEN', '')
    if not ngrok_token:
        warnings.append("NGROK_AUTH_TOKEN not set (external access disabled)")

    # 4. 웹 서버 모듈 확인
    if not WEB_SERVER_SUPPORT:
        warnings.append("Web server module not available")

    if errors:
        return False

    return True


def main():

    # 환경 점검
    if not startup_diagnostics():
        input("\nPress Enter to exit...")
        return

    # 다크모드 기본 적용
    set_theme(is_dark_mode)

    while True:
        # 1단계: 설정 화면
        settings = SettingsWindow()
        result = settings.run()

        if result is None:
            break

        # 2단계: 오버레이 시작
        app = SubtitleOverlay()
        app.run()

        if app.go_back:
            continue
        else:
            break


if __name__ == "__main__":
    main()