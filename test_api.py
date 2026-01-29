# -*- coding: utf-8 -*-
import azure.cognitiveservices.speech as speechsdk
from openai import OpenAI
import sys
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# API 키 (.env 파일에서 로드)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

print("=" * 60)
print("API 연결 테스트 시작")
print("=" * 60)

# 1. OpenAI API 테스트
print("\n1. OpenAI API 테스트 중...")
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )
    print("[OK] OpenAI API 연결 성공!")
    print(f"    응답: {response.choices[0].message.content}")
except Exception as e:
    print(f"[FAIL] OpenAI API 연결 실패!")
    print(f"    오류: {str(e)}")

# 2. Azure Speech Service 테스트
print("\n2. Azure Speech Service 테스트 중...")
try:
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.speech_recognition_language = "ko-KR"

    # 마이크 설정
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)

    print("[OK] Azure Speech Service 설정 성공!")
    print(f"    Region: {SPEECH_REGION}")
    print(f"    Language: ko-KR")

    # 간단한 음성 인식 테스트
    print("\n3. 마이크 테스트 중...")
    print("   '안녕하세요'라고 말해보세요 (5초 대기)...")

    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print(f"[OK] 음성 인식 성공!")
        print(f"    인식된 텍스트: {result.text}")
    elif result.reason == speechsdk.ResultReason.NoMatch:
        print("[WARN] 음성이 인식되지 않았습니다.")
        print("    - 마이크가 제대로 연결되어 있는지 확인하세요")
        print("    - 마이크 권한을 확인하세요")
        print("    - 조용한 환경에서 다시 시도하세요")
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        print(f"[FAIL] 음성 인식 취소됨")
        print(f"    취소 이유: {cancellation.reason}")
        if cancellation.reason == speechsdk.CancellationReason.Error:
            try:
                print(f"    오류 상세: {cancellation.error_details}")
            except:
                pass
            # CancellationDetails의 모든 속성 출력
            print(f"    전체 오류 정보:")
            for attr in dir(cancellation):
                if not attr.startswith('_'):
                    try:
                        val = getattr(cancellation, attr)
                        if not callable(val):
                            print(f"      {attr}: {val}")
                    except:
                        pass

except Exception as e:
    print(f"[FAIL] Azure Speech Service 오류!")
    print(f"    오류: {str(e)}")

print("\n" + "=" * 60)
print("테스트 완료")
print("=" * 60)
