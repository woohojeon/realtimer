# Real-Time Presentation Interpreter

실시간 발표 통역 시스템 - 한국어/영어 음성을 실시간으로 인식하고 번역하여 화면에 표시합니다.

## 주요 기능

- 실시간 음성 인식 (STT - Speech to Text)
- AI 기반 자동 번역 (한국어 ↔ 영어)
- 실시간 번역 결과 표시
- 발표 맥락을 고려한 번역
- 깔끔한 GUI 인터페이스

## 기술 스택

- **음성 인식**: Azure Cognitive Services Speech SDK
- **번역**: OpenAI GPT-4o
- **GUI**: Python Tkinter

## 필수 요구사항

- Python 3.7 이상
- OpenAI API Key
- Azure Speech Service API Key
- 마이크 (음성 입력용)

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/your-username/realtimer.git
cd realtimer
```

### 2. 가상 환경 생성 (권장)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 API 키를 입력하세요:

```bash
# Windows
copy .env.example .env

# Mac/Linux
cp .env.example .env
```

`.env` 파일을 열어서 다음 정보를 입력:

```env
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# Azure Speech Service Configuration
SPEECH_KEY=your_azure_speech_key_here
SPEECH_REGION=your_azure_region_here
```

#### API 키 발급 방법

**OpenAI API Key:**
1. https://platform.openai.com/ 방문
2. 회원가입 또는 로그인
3. API Keys 메뉴에서 새 키 생성

**Azure Speech Service:**
1. https://portal.azure.com/ 방문
2. Azure Cognitive Services > Speech Service 리소스 생성
3. "키 및 엔드포인트" 메뉴에서 키와 지역 확인

## 사용 방법

### 1. API 연결 테스트

먼저 API가 정상적으로 연결되는지 테스트:

```bash
python test_api.py
```

### 2. 프로그램 실행

```bash
python realtimer.py
```

### 3. 사용 가이드

1. **START 버튼** 클릭하여 음성 인식 시작
2. 마이크에 대고 말하기 (한국어 또는 영어)
3. 실시간으로 인식된 텍스트와 번역 결과 확인
4. **STOP 버튼**으로 인식 중지
5. **ESC 키** 또는 **EXIT 버튼**으로 프로그램 종료

### 설정 옵션

- **Font Size**: 자막 글자 크기 조정 (12~28)
- **Translation Direction**:
  - `KO→EN`: 한국어 → 영어 번역
  - `EN→KO`: 영어 → 한국어 번역
- **Real-time Translation**: 말하는 동안 실시간 번역 표시

## 프로젝트 구조

```
realtimer/
├── realtimer.py          # 메인 프로그램
├── test_api.py           # API 연결 테스트 스크립트
├── requirements.txt      # 의존성 패키지 목록
├── .env                  # 환경 변수 (API 키) - Git에 업로드 금지
├── .env.example          # 환경 변수 템플릿
├── .gitignore            # Git 제외 파일 목록
└── README.md             # 프로젝트 문서
```

## 보안 주의사항

**중요**: `.env` 파일은 절대 Git에 업로드하지 마세요!

- API 키가 포함된 `.env` 파일은 `.gitignore`에 등록되어 있습니다
- `.env.example` 파일만 공유하고, 실제 키는 개인적으로 관리하세요
- API 키가 노출되면 즉시 새로운 키로 교체하세요

## 문제 해결

### 음성 인식이 작동하지 않을 때

1. 마이크가 제대로 연결되어 있는지 확인
2. 마이크 권한 허용 확인
3. Azure Speech Service API 키와 지역 확인
4. `python test_api.py`로 API 연결 상태 테스트

### 번역이 작동하지 않을 때

1. OpenAI API 키 확인
2. OpenAI API 계정 잔액 확인
3. 인터넷 연결 확인

## 라이선스

이 프로젝트는 개인 프로젝트입니다.

## 기여

버그 리포트나 기능 제안은 이슈로 등록해주세요.
