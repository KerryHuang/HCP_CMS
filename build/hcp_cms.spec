# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

src_dir = Path("src/hcp_cms")
i18n_dir = src_dir / "i18n"

# Collect data files
datas = [
    (str(i18n_dir / "zh_TW.json"), "hcp_cms/i18n"),
    (str(i18n_dir / "en.json"), "hcp_cms/i18n"),
]

# jieba dictionary data
import jieba
jieba_dir = Path(jieba.__file__).parent
datas.append((str(jieba_dir), "jieba"))

a = Analysis(
    ["src/hcp_cms/app.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "jieba",
        "openpyxl",
        "extract_msg",
        "exchangelib",
        "keyring",
        "keyring.backends",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="HCP_CMS",
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
)
