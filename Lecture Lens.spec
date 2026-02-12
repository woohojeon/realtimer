# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['realtimer.py'],
    pathex=[],
    binaries=[],
    datas=[('.env', '.'), ('glossary.json', '.'), ('templates', 'templates'), ('static', 'static')],
    hiddenimports=['engineio.async_drivers.threading', 'azure.cognitiveservices.speech'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Lecture Lens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
