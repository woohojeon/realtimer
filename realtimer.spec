# -*- mode: python ; coding: utf-8 -*-
"""
Lecture Lens (realtimer) PyInstaller spec file
"""

import os
import sys

# 사용자 site-packages 경로
USER_SITE = os.path.join(os.environ['APPDATA'], 'Python', 'Python313', 'site-packages')

# ========================
# Data files (templates, static, .env)
# ========================
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('logo.png', '.'),
    ('.env', '.'),
]

# ========================
# Native binaries
# ========================
binaries = []

# Azure Speech SDK DLLs
azure_speech_dir = os.path.join(USER_SITE, 'azure', 'cognitiveservices', 'speech')
if os.path.isdir(azure_speech_dir):
    for f in os.listdir(azure_speech_dir):
        if f.endswith('.dll'):
            binaries.append((os.path.join(azure_speech_dir, f), 'azure/cognitiveservices/speech'))

# sounddevice PortAudio DLLs
portaudio_dir = os.path.join(USER_SITE, '_sounddevice_data', 'portaudio-binaries')
if os.path.isdir(portaudio_dir):
    for f in os.listdir(portaudio_dir):
        if f.endswith('.dll'):
            binaries.append((os.path.join(portaudio_dir, f), '_sounddevice_data/portaudio-binaries'))

# ========================
# tkinterdnd2 전체 패키지 (tkdnd DLL 포함)
# ========================
tkdnd_dir = os.path.join(USER_SITE, 'tkinterdnd2')
if os.path.isdir(tkdnd_dir):
    datas.append((tkdnd_dir, 'tkinterdnd2'))

# _sounddevice_data 전체 (메타데이터 포함)
sd_data_dir = os.path.join(USER_SITE, '_sounddevice_data')
if os.path.isdir(sd_data_dir):
    datas.append((sd_data_dir, '_sounddevice_data'))

# ========================
# Hidden imports
# ========================
hiddenimports = [
    # Flask & SocketIO
    'flask',
    'flask_socketio',
    'engineio',
    'engineio.async_drivers',
    'engineio.async_drivers.threading',
    'socketio',
    'bidict',
    # Web & QR
    'qrcode',
    'qrcode.image.pil',
    'PIL',
    'PIL.Image',
    # Azure Speech
    'azure',
    'azure.cognitiveservices',
    'azure.cognitiveservices.speech',
    # OpenAI
    'openai',
    'httpx',
    'httpcore',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'h11',
    'certifi',
    'distro',
    # Audio
    'sounddevice',
    '_sounddevice_data',
    # PDF
    'pdfplumber',
    'pdfminer',
    'pdfminer.high_level',
    # DnD
    'tkinterdnd2',
    # ngrok
    'pyngrok',
    'pyngrok.ngrok',
    'pyngrok.conf',
    # dotenv
    'dotenv',
    # Web server module
    'web_server',
    # Werkzeug
    'werkzeug',
    'werkzeug.serving',
    'werkzeug.debug',
    # Jinja2
    'jinja2',
    'jinja2.ext',
    'markupsafe',
]

# ========================
# Excludes (불필요한 대형 패키지)
# ========================
excludes = [
    'scipy',
    'sklearn',
    'torch',
    'torchvision',
    'torchaudio',
    'matplotlib',
    'pandas',
    'numpy.testing',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'setuptools',
    'pip',
]

# ========================
# Analysis
# ========================
a = Analysis(
    ['realtimer.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# ========================
# PYZ (compressed archive)
# ========================
pyz = PYZ(a.pure)

# ========================
# EXE
# ========================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LectureLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # 디버깅용 콘솔 표시 (배포 시 False로 변경)
    icon='logo.png',     # .ico 파일이 있으면 교체
)

# ========================
# COLLECT (폴더 모드)
# ========================
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='LectureLens',
)
