"""UI 層跨平台共用函式。"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def open_file(path: Path) -> None:
    """跨平台開啟檔案（Windows: startfile, macOS: open, Linux: xdg-open）。"""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
