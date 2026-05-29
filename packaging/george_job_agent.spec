# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent

datas = [
    (str(root / "agent" / "desktop" / "assets"), "agent/desktop/assets"),
    (str(root / "agent" / "desktop" / "theme"), "agent/desktop/theme"),
    (str(root / "agent" / "templates"), "agent/templates"),
    (str(root / "agent" / "cv" / "templates"), "agent/cv/templates"),
    (str(root / "agent" / "cover_letter" / "templates"), "agent/cover_letter/templates"),
    (str(root / "cv_variations"), "cv_variations"),
]

# Bundle workspace seed directories only when they exist (populated after first run
# or manually).  On a fresh clone these will be absent and the app uses
# workspace_seed.py to copy them from _MEIPASS at first launch instead.
for _workspace_subdir, _bundle_dest in [
    ("workspace/memory", "workspace/memory"),
    ("workspace/roles", "workspace/roles"),
    ("workspace/tracker", "workspace/tracker"),
]:
    _src = root / _workspace_subdir
    if _src.is_dir() and any(_src.iterdir()):
        datas.append((str(_src), _bundle_dest))
    else:
        import sys as _sys
        print(
            f"[spec] Skipping '{_workspace_subdir}' — directory missing or empty. "
            "The bundled app will seed it on first launch via workspace_seed.py.",
            file=_sys.stderr,
        )


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
    icon=str(root / "agent" / "desktop" / "assets" / "app.ico"),
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
