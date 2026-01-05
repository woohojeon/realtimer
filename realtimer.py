# -*- coding: utf-8 -*-
import azure.cognitiveservices.speech as speechsdk
import tkinter as tk
from tkinter import messagebox
import threading
import queue
from openai import OpenAI
from collections import deque
import os
from dotenv import load_dotenv

# ========================
# 1. API 설정 (환경 변수에서 로드)
# ========================
# .env 파일에서 환경 변수 로드
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

# ========================
# 2. 글로벌 변수
# ========================
subtitle_queue = queue.Queue()
is_listening = False
client = OpenAI(api_key=OPENAI_API_KEY)

# 최근 10문장 저장
history = deque(maxlen=10)

# 번역 방향 ('ko_to_en' 또는 'en_to_ko')
translation_direction = 'ko_to_en'

# 현재 인식 중인 텍스트
current_recognizing = ''

# 현재 처리 중인 문장 인덱스 (recognizing 상태일 때 대체되는 문장)
current_processing_index = -1

# 실시간 번역 모드
real_time_translation = True

# 현재 실시간 번역 중인 텍스트
current_translating = ''

# 마지막 실시간 번역 결과
last_realtime_translation = ''

# ========================
# 3. 색상 테마 정의
# ========================
COLORS = {
    'bg_primary': '#1a1a1a',        # 메인 배경
    'bg_secondary': '#2c2c2c',      # 보조 배경
    'bg_card': '#333333',           # 카드 배경
    'text_primary': '#ffffff',      # 주요 텍스트
    'text_secondary': '#ffffff',    # 보조 텍스트 (영어) b3e5fc
    'text_muted': '#888888',        # 흐린 텍스트
    'accent': '#00bcd4',            # 강조 색상
    'success': '#4caf50',           # 성공 (시작)
    'error': '#666666',             # 에러 (중지) - 더 어둡게
    'warning': '#555555',           # 경고 (종료) - 더 어둡게
    'border': '#404040'             # 테두리
}

# ========================
# 4. 발표용 STT + 번역 시스템
# ========================
class PresentationSTT:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("실시간 발표 통역")
        
        # 기본 파라미터
        self.font_size = tk.IntVar(value=16)
        self.direction = tk.StringVar(value='ko_to_en')
        self.realtime_mode = tk.BooleanVar(value=True)
        
        # 창 속성 개선
        self.root.configure(bg=COLORS['bg_primary'])
        self.root.attributes("-alpha", 0.95)
        self.root.attributes("-topmost", True)
        
        # 화면 오른쪽 위치
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.subtitle_width = 750
        self.root.geometry(f"{self.subtitle_width}x{screen_h}+{screen_w - self.subtitle_width}+0")
        
        # UI 구성
        self.setup_ui()
        self.setup_recognition()
        self.check_queue()
        
        # ESC 종료
        self.root.bind("<Escape>", lambda e: self.quit_app())
        
        # 애니메이션 시작
        self.animate_status()

    def setup_ui(self):
        # 헤더 프레임 (제목 + 상태)
        header_frame = tk.Frame(self.root, bg=COLORS['bg_secondary'], height=60)
        header_frame.pack(side="top", fill="x")
        header_frame.pack_propagate(False)
        
        # 제목
        title_label = tk.Label(header_frame, text="실시간 발표 통역",
                              fg=COLORS['text_primary'], bg=COLORS['bg_secondary'],
                              font=("Arial", 14, "bold"))
        title_label.pack(side="left", padx=20, pady=15)
        
        # LIVE 상태 표시
        self.status_label = tk.Label(header_frame, text="READY", 
                                    fg=COLORS['text_muted'], bg=COLORS['bg_secondary'],
                                    font=("Arial", 10, "bold"))
        self.status_label.pack(side="right", padx=20, pady=15)
        
        # 컨트롤 프레임 (버튼들)
        control_frame = tk.Frame(self.root, bg=COLORS['bg_primary'], height=50)
        control_frame.pack(side="top", fill="x", pady=(0, 10))
        control_frame.pack_propagate(False)
        
        # 버튼 스타일 개선 (더 어둡게)
        button_style = {
            'font': ("Arial", 9, "bold"),
            'width': 8,
            'height': 1,
            'relief': "flat",
            'bd': 0,
            'cursor': 'hand2'
        }
        
        self.start_btn = tk.Button(control_frame, text="START", command=self.start_listening,
                                  bg=COLORS['success'], fg="white", 
                                  activebackground='#45a049', **button_style)
        self.start_btn.pack(side="left", padx=(20, 5), pady=10)
        
        self.stop_btn = tk.Button(control_frame, text="STOP", command=self.stop_listening,
                                 bg=COLORS['error'], fg="white", state="disabled",
                                 activebackground='#555555', **button_style)
        self.stop_btn.pack(side="left", padx=5, pady=10)
        
        self.exit_btn = tk.Button(control_frame, text="EXIT", command=self.quit_app,
                                 bg=COLORS['warning'], fg="white",
                                 activebackground='#444444', **button_style)
        self.exit_btn.pack(side="left", padx=5, pady=10)
        
        # 설정 패널 (Font Size + 번역 방향)
        settings_frame = tk.Frame(self.root, bg=COLORS['bg_card'])
        settings_frame.pack(side="top", fill="x", padx=20, pady=(0, 15))

        # Font Size 조정
        font_control_frame = tk.Frame(settings_frame, bg=COLORS['bg_card'])
        font_control_frame.pack(side="left", padx=10, pady=10)

        tk.Label(font_control_frame, text="Font Size", fg=COLORS['text_muted'],
                bg=COLORS['bg_card'], font=("Arial", 9)).pack()
        font_spinbox = tk.Spinbox(font_control_frame, from_=12, to=28, increment=2,
                                 textvariable=self.font_size, width=6,
                                 command=self.update_font,
                                 bg=COLORS['bg_secondary'], fg=COLORS['text_primary'],
                                 buttonbackground=COLORS['bg_secondary'],
                                 relief="flat", bd=1)
        font_spinbox.pack()

        # 번역 방향 선택
        direction_frame = tk.Frame(settings_frame, bg=COLORS['bg_card'])
        direction_frame.pack(side="right", padx=10, pady=10)

        tk.Label(direction_frame, text="Translation Direction", fg=COLORS['text_muted'],
                bg=COLORS['bg_card'], font=("Arial", 9)).pack()

        direction_buttons_frame = tk.Frame(direction_frame, bg=COLORS['bg_card'])
        direction_buttons_frame.pack()

        ko_to_en_btn = tk.Radiobutton(direction_buttons_frame, text="KO→EN",
                                     variable=self.direction, value='ko_to_en',
                                     command=self.change_direction,
                                     bg=COLORS['bg_card'], fg=COLORS['text_primary'],
                                     selectcolor=COLORS['bg_secondary'],
                                     activebackground=COLORS['bg_card'],
                                     font=("Arial", 9))
        ko_to_en_btn.pack(side="left", padx=(0, 5))

        en_to_ko_btn = tk.Radiobutton(direction_buttons_frame, text="EN→KO",
                                     variable=self.direction, value='en_to_ko',
                                     command=self.change_direction,
                                     bg=COLORS['bg_card'], fg=COLORS['text_primary'],
                                     selectcolor=COLORS['bg_secondary'],
                                     activebackground=COLORS['bg_card'],
                                     font=("Arial", 9))
        en_to_ko_btn.pack(side="left")

        # 실시간 번역 모드 체크박스
        realtime_frame = tk.Frame(settings_frame, bg=COLORS['bg_card'])
        realtime_frame.pack(side="right", padx=(20, 10), pady=10)

        tk.Label(realtime_frame, text="Real-time Translation", fg=COLORS['text_muted'],
                bg=COLORS['bg_card'], font=("Arial", 9)).pack()

        realtime_checkbox = tk.Checkbutton(realtime_frame, text="Enable",
                                          variable=self.realtime_mode,
                                          command=self.toggle_realtime_mode,
                                          bg=COLORS['bg_card'], fg=COLORS['text_primary'],
                                          selectcolor=COLORS['bg_secondary'],
                                          activebackground=COLORS['bg_card'],
                                          font=("Arial", 9))
        realtime_checkbox.pack()
        
        # 자막 표시 영역 (메인)
        main_frame = tk.Frame(self.root, bg=COLORS['bg_primary'])
        main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # 스크롤바 스타일링
        scrollbar = tk.Scrollbar(main_frame, bg=COLORS['bg_secondary'], 
                                troughcolor=COLORS['bg_primary'],
                                activebackground=COLORS['accent'])
        scrollbar.pack(side="right", fill="y")
        
        # 텍스트 영역 개선
        self.subtitle_text = tk.Text(
            main_frame,
            font=("Arial", self.font_size.get()),
            fg=COLORS['text_primary'],
            bg=COLORS['bg_primary'],
            wrap="word",
            yscrollcommand=scrollbar.set,
            relief="flat",
            bd=0,
            padx=15,
            pady=15,
            insertbackground=COLORS['accent'],
            selectbackground=COLORS['accent'],
            selectforeground=COLORS['text_primary']
        )
        self.subtitle_text.pack(fill="both", expand=True)
        scrollbar.config(command=self.subtitle_text.yview)
        
        # 텍스트 태그 설정 (블록 스타일)
        # 완성된 번역문
        self.subtitle_text.tag_config("english",
                                     foreground=COLORS['text_primary'],
                                     background=COLORS['bg_card'],
                                     font=("Arial", self.font_size.get(), "normal"),
                                     spacing1=8, spacing2=8, spacing3=8,
                                     lmargin1=10, lmargin2=10, rmargin=10,
                                     relief="solid", borderwidth=1)
        # 실시간 인식 중 텍스트
        self.subtitle_text.tag_config("recognizing",
                                     foreground=COLORS['text_secondary'],
                                     background=COLORS['bg_secondary'],
                                     font=("Arial", self.font_size.get()-1, "italic"),
                                     spacing1=6, spacing2=6, spacing3=6,
                                     lmargin1=10, lmargin2=10, rmargin=10,
                                     relief="solid", borderwidth=1)
        # 실시간 번역 중 텍스트
        self.subtitle_text.tag_config("translating",
                                     foreground=COLORS['accent'],
                                     background=COLORS['bg_secondary'],
                                     font=("Arial", self.font_size.get()-1, "normal"),
                                     spacing1=6, spacing2=6, spacing3=6,
                                     lmargin1=10, lmargin2=10, rmargin=10,
                                     relief="solid", borderwidth=1)
        # 번역 중 메시지
        self.subtitle_text.tag_config("temp",
                                     foreground=COLORS['text_muted'],
                                     background=COLORS['bg_card'],
                                     font=("Arial", self.font_size.get()-2),
                                     spacing1=6, spacing2=6, spacing3=6,
                                     lmargin1=10, lmargin2=10, rmargin=10,
                                     relief="solid", borderwidth=1)
        
        # 초기 메시지
        self.subtitle_text.insert("end", "발표 음성을 기다리는 중...\n\n", "temp")
        self.subtitle_text.config(state="disabled")

    def animate_status(self):
        """LIVE 상태 애니메이션"""
        if is_listening:
            current_color = self.status_label.cget("fg")
            new_color = COLORS['success'] if current_color == COLORS['error'] else COLORS['error']
            self.status_label.config(fg=new_color, text="LIVE")
        else:
            self.status_label.config(fg=COLORS['text_muted'], text="READY")
        
        self.root.after(1000, self.animate_status)

    def update_font(self):
        """글꼴 크기 변경"""
        size = self.font_size.get()
        self.subtitle_text.tag_config("english",
                                     font=("Arial", size, "normal"),
                                     spacing1=8, spacing2=8, spacing3=8)
        self.subtitle_text.tag_config("recognizing",
                                     font=("Arial", size-1, "italic"),
                                     spacing1=6, spacing2=6, spacing3=6)
        self.subtitle_text.tag_config("translating",
                                     font=("Arial", size-1, "normal"),
                                     spacing1=6, spacing2=6, spacing3=6)
        self.subtitle_text.tag_config("temp",
                                     font=("Arial", size-2),
                                     spacing1=6, spacing2=6, spacing3=6)

    def setup_recognition(self):
        try:
            self.update_speech_config()
            print("STT 준비 완료")
        except Exception as e:
            messagebox.showerror("오류", f"음성 인식 초기화 실패: {str(e)}")

    def update_speech_config(self):
        """STT 언어 설정 업데이트"""
        global translation_direction
        speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)

        if translation_direction == 'ko_to_en':
            speech_config.speech_recognition_language = "ko-KR"
        else:  # en_to_ko
            speech_config.speech_recognition_language = "en-US"

        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )
        self.speech_recognizer.recognized.connect(self.on_recognized)
        self.speech_recognizer.recognizing.connect(self.on_recognizing)

    def change_direction(self):
        """번역 방향 변경"""
        global translation_direction
        translation_direction = self.direction.get()

        # STT 언어 설정 업데이트
        if hasattr(self, 'speech_recognizer'):
            # 인식 중이면 잠시 중지하고 재시작
            was_listening = is_listening
            if was_listening:
                self.stop_listening()

            self.update_speech_config()

            if was_listening:
                self.start_listening()

        # 히스토리 초기화
        history.clear()
        self.update_subtitles()
        print(f"번역 방향 변경: {translation_direction}")

    def toggle_realtime_mode(self):
        """실시간 번역 모드 토글"""
        global real_time_translation
        real_time_translation = self.realtime_mode.get()
        mode_text = "활성화" if real_time_translation else "비활성화"
        print(f"실시간 번역 모드: {mode_text}")

    def realtime_translate(self, source_text):
        """실시간 번역 (빠른 번역, 지속적 업데이트)"""
        try:
            global translation_direction

            # 간단한 맥락 구성 (최근 2개 문장)
            context_pairs = list(history)[-2:] if history else []
            context_text = ""

            if context_pairs:
                context_text = "\nContext: "
                for source, translated in context_pairs:
                    if translation_direction == 'ko_to_en':
                        context_text += f"KR: {source[:50]}... → EN: {translated[:50]}... | "
                    else:
                        context_text += f"EN: {source[:50]}... → KR: {translated[:50]}... | "
                context_text = context_text.rstrip(" | ") + "\n"

            if translation_direction == 'ko_to_en':
                prompt = f"Translate Korean veterinary text to English with context consistency. Output only English translation:{context_text}\n{source_text}"
            else:
                prompt = f"Translate English veterinary text to Korean with context consistency. Output only Korean translation:{context_text}\n{source_text}"

            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=80  # 더 짧게
            )

            translated = resp.choices[0].message.content.strip()
            # 실시간 번역 결과를 큐에 추가
            subtitle_queue.put(("realtime_translation", translated))

        except Exception as e:
            print(f"실시간 번역 오류: {e}")

    def on_recognizing(self, evt):
        if evt.result.text and is_listening:
            global current_recognizing
            current_recognizing = evt.result.text
            # 실시간 업데이트 (누적되지 않고 대체)
            subtitle_queue.put(("recognizing", evt.result.text))

    def on_recognized(self, evt):
        if evt.result.text and is_listening:
            global current_recognizing
            current_recognizing = ''
            subtitle_queue.put(("recognized", evt.result.text))

    def start_listening(self):
        global is_listening
        if not is_listening:
            is_listening = True
            self.start_btn.config(state="disabled", bg=COLORS['text_muted'])
            self.stop_btn.config(state="normal", bg=COLORS['error'])
            self.speech_recognizer.start_continuous_recognition_async()
            print("음성 인식 시작")

    def stop_listening(self):
        global is_listening
        if is_listening:
            is_listening = False
            self.start_btn.config(state="normal", bg=COLORS['success'])
            self.stop_btn.config(state="disabled", bg=COLORS['text_muted'])
            self.speech_recognizer.stop_continuous_recognition_async()
            print("음성 인식 중지")

    def quit_app(self):
        global is_listening
        is_listening = False
        try:
            self.speech_recognizer.stop_continuous_recognition_async()
        except:
            pass
        self.root.quit()
        self.root.destroy()

    def check_queue(self):
        global last_realtime_translation
        try:
            while True:
                msg_type, korean_text = subtitle_queue.get_nowait()
                if msg_type == "recognizing":
                    # 실시간 인식 텍스트 업데이트
                    if self.realtime_mode.get():
                        # 실시간 번역 시작 (텍스트가 충분히 길 때만)
                        if len(korean_text.strip()) > 5:  # 5자 이상일 때만 번역
                            threading.Thread(
                                target=self.realtime_translate, args=(korean_text,), daemon=True
                            ).start()
                    else:
                        self.update_subtitles(temp_text=korean_text)
                elif msg_type == "recognized":
                    # 인식 완료 후 최종 번역 시작
                    last_realtime_translation = ''  # 실시간 번역 초기화
                    self.update_subtitles(is_translating=True)
                    threading.Thread(
                        target=self.translate_and_add, args=(korean_text,), daemon=True
                    ).start()
                elif msg_type == "realtime_translation":
                    # 실시간 번역 결과 업데이트 (다른 번역과 다를 때만)
                    if korean_text != last_realtime_translation:
                        last_realtime_translation = korean_text
                        self.update_subtitles(realtime_translation=korean_text)
        except queue.Empty:
            pass
        self.root.after(50, self.check_queue)

    def translate_and_add(self, source_text):
        try:
            translated_text = self.translate_with_openai(source_text)
            history.append((source_text, translated_text))
            self.update_subtitles()
        except Exception as e:
            print(f"번역 오류: {e}")
            history.append((source_text, "Translation Error"))
            self.update_subtitles()

    def update_subtitles(self, temp_text=None, is_translating=False, realtime_translation=None):
        """자막 업데이트 (블록 스타일 번역문 표시)"""
        global current_processing_index

        self.subtitle_text.config(state="normal")
        self.subtitle_text.delete("1.0", "end")

        # 히스토리 표시 (번역문만, 블록 스타일)
        for i, (source, translated) in enumerate(history):
            # 블록 간격
            if i > 0:
                self.subtitle_text.insert("end", "\n")

            # 번역문만 블록으로 표시
            self.subtitle_text.insert("end", f" {translated} ", "english")
            self.subtitle_text.insert("end", "\n")

        # 실시간 번역 및 인식 상태 표시
        if temp_text or is_translating or realtime_translation:
            if history:
                self.subtitle_text.insert("end", "\n")

            if realtime_translation and self.realtime_mode.get():
                # 실시간 번역 결과만 표시 (한국어 제거)
                self.subtitle_text.insert("end", f" {realtime_translation} ", "translating")
            elif is_translating:
                translate_msg = "번역 중..." if translation_direction == 'ko_to_en' else "Translating..."
                self.subtitle_text.insert("end", f" {translate_msg} ", "temp")
            elif temp_text and not self.realtime_mode.get():
                # 비실시간 모드일 때만 인식 텍스트 표시
                self.subtitle_text.insert("end", f" {temp_text} ", "recognizing")

            self.subtitle_text.insert("end", "\n")

        self.subtitle_text.see("end")
        self.subtitle_text.config(state="disabled")

    def translate_with_openai(self, source_text):
        global translation_direction

        # 이전 대화 맥락 구성 (최근 3개 문장)
        context_pairs = list(history)[-3:] if history else []
        context_text = ""

        if context_pairs:
            context_text = "\nPrevious conversation context:\n"
            for i, (source, translated) in enumerate(context_pairs, 1):
                if translation_direction == 'ko_to_en':
                    context_text += f"{i}. Korean: {source}\n   English: {translated}\n"
                else:
                    context_text += f"{i}. English: {source}\n   Korean: {translated}\n"

        if translation_direction == 'ko_to_en':
            prompt = f"""Translate this Korean veterinary presentation text to natural, professional English. Use proper veterinary terminology and maintain consistency with the conversation context. Output ONLY the English translation, no explanations or additional text:{context_text}

Current text to translate:
{source_text}"""
        else:  # en_to_ko
            prompt = f"""Translate this English veterinary presentation text to natural, professional Korean. Use proper Korean veterinary terminology, maintain academic tone, and keep consistency with the conversation context. Output ONLY the Korean translation, no explanations or additional text:{context_text}

Current text to translate:
{source_text}"""


        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200
        )
        return resp.choices[0].message.content.strip()


# ========================
# 5. API 연결 확인
# ========================
def check_api_connections():
    """API key 연결 상태 확인"""
    print("\n" + "="*50)
    print("API 연결 상태 확인 중...")
    print("="*50)

    results = {
        'openai': False,
        'azure_speech': False
    }

    # OpenAI API 확인
    try:
        test_client = OpenAI(api_key=OPENAI_API_KEY)
        # 간단한 테스트 요청
        response = test_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        results['openai'] = True
        print("[OK] OpenAI API: 연결 성공")
    except Exception as e:
        print(f"[FAIL] OpenAI API: 연결 실패 - {str(e)}")

    # Azure Speech Service 확인
    try:
        speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
        # 간단한 테스트 (synthesizer 생성)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        results['azure_speech'] = True
        print(f"[OK] Azure Speech Service: 연결 성공 (Region: {SPEECH_REGION})")
    except Exception as e:
        print(f"[FAIL] Azure Speech Service: 연결 실패 - {str(e)}")

    print("="*50)

    # 결과 요약
    if all(results.values()):
        print("[OK] 모든 API가 정상적으로 연결되었습니다!")
        print("="*50 + "\n")
        return True
    else:
        print("[FAIL] 일부 API 연결에 문제가 있습니다.")
        print("  API key와 설정을 확인해주세요.")
        print("="*50 + "\n")
        return False


# ========================
# 6. 메인 실행
# ========================
def main():
    print("실시간 발표 통역 시스템 시작")

    # API 연결 확인
    api_status = check_api_connections()

    if not api_status:
        user_input = input("API 연결에 문제가 있지만 계속하시겠습니까? (y/n): ")
        if user_input.lower() != 'y':
            print("프로그램을 종료합니다.")
            return

    app = PresentationSTT()
    app.root.mainloop()


if __name__ == "__main__":
    main()