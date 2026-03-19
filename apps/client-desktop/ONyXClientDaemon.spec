# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['q:\\ONyX_export\\apps\\client-desktop\\onyx_daemon_service.py'],
    pathex=[],
    binaries=[],
    datas=[('q:\\ONyX_export\\apps\\client-desktop\\bin', 'bin')],
    hiddenimports=['runtime', 'runtime.ipc', 'runtime.models', 'runtime.paths', 'runtime.service', 'runtime.adapters'],
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
    name='ONyXClientDaemon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['q:\\ONyX_export\\apps\\client-desktop\\assets\\icons\\onyx.ico'],
)
