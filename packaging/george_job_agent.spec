# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent

datas = [
    (str(root / "agent" / "templates"), "agent/templates"),
    (str(root / "agent" / "cv" / "templates"), "agent/cv/templates"),
    (str(root / "agent" / "cover_letter" / "templates"), "agent/cover_letter/templates"),
    (str(root / "workspace" / "memory"), "workspace/memory"),
    (str(root / "workspace" / "roles"), "workspace/roles"),
    (str(root / "workspace" / "tracker"), "workspace/tracker"),
    (str(root / "cv_variations"), "cv_variations"),
]

a = Analysis(
    [str(root / "agent" / "desktop" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "playwright.sync_api",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GeorgeJobAgent",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GeorgeJobAgent",
)
