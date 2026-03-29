"""主題系統 — ColorPalette 定義與 ThemeManager。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class ColorPalette:
    """語義化色彩組定義。"""

    # 背景
    bg_primary: str
    bg_secondary: str
    bg_sidebar: str
    bg_code: str
    bg_hover: str

    # 文字
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_muted: str
    text_faint: str

    # 強調色
    accent: str
    accent_button: str
    accent_button_hover: str

    # 邊框
    border_primary: str
    border_secondary: str

    # 狀態色
    success: str
    error: str
    warning: str


DARK_PALETTE = ColorPalette(
    bg_primary="#111827",
    bg_secondary="#1e293b",
    bg_sidebar="#0f172a",
    bg_code="#0f172a",
    bg_hover="#273344",
    text_primary="#f1f5f9",
    text_secondary="#e2e8f0",
    text_tertiary="#94a3b8",
    text_muted="#64748b",
    text_faint="#475569",
    accent="#60a5fa",
    accent_button="#1e40af",
    accent_button_hover="#2563eb",
    border_primary="#334155",
    border_secondary="#1e293b",
    success="#4ade80",
    error="#ef4444",
    warning="#fbbf24",
)

LIGHT_PALETTE = ColorPalette(
    bg_primary="#eef2f7",
    bg_secondary="#ffffff",
    bg_sidebar="#dfe6ee",
    bg_code="#e8ecf1",
    bg_hover="#d5dce6",
    text_primary="#0f172a",
    text_secondary="#1e293b",
    text_tertiary="#1e293b",
    text_muted="#334155",
    text_faint="#475569",
    accent="#1d4ed8",
    accent_button="#1e40af",
    accent_button_hover="#1d4ed8",
    border_primary="#b0bec5",
    border_secondary="#cfd8dc",
    success="#15803d",
    error="#dc2626",
    warning="#b45309",
)


class ThemeManager(QObject):
    """主題管理器 — 管理深色/淺色切換、設定持久化、系統偵測。"""

    theme_changed = Signal(ColorPalette)

    _VALID_MODES = ("dark", "light", "system")

    def __init__(self, config_dir: Path) -> None:
        super().__init__()
        self._config_path = config_dir / "config.json"
        self._mode: str = "system"
        self._palette: ColorPalette = DARK_PALETTE
        self._load_config()
        self._resolve_palette()

    def current_mode(self) -> str:
        """取得當前模式字串。"""
        return self._mode

    def current_palette(self) -> ColorPalette:
        """取得當前色彩組。"""
        return self._palette

    def set_theme(self, mode: str) -> None:
        """切換主題模式。無效值會被忽略。"""
        if mode not in self._VALID_MODES:
            return
        if mode == self._mode:
            return
        self._mode = mode
        self._resolve_palette()
        self._save_config()
        self.theme_changed.emit(self._palette)

    def refresh_system_theme(self) -> None:
        """重新偵測系統主題（僅在 mode='system' 時有效）。"""
        if self._mode != "system":
            return
        old_palette = self._palette
        self._resolve_palette()
        if self._palette != old_palette:
            self.theme_changed.emit(self._palette)

    def _resolve_palette(self) -> None:
        """根據當前模式決定使用哪組色彩。"""
        if self._mode == "light":
            self._palette = LIGHT_PALETTE
        elif self._mode == "dark":
            self._palette = DARK_PALETTE
        else:
            self._palette = LIGHT_PALETTE if self._detect_system_light() else DARK_PALETTE

    def _detect_system_light(self) -> bool:
        """偵測 Windows 系統是否為淺色模式。"""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 1
        except Exception:
            return False

    def _load_config(self) -> None:
        """從 config.json 載入偏好。"""
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            mode = data.get("theme", "system")
            if mode in self._VALID_MODES:
                self._mode = mode
            else:
                self._mode = "system"
        except Exception:
            self._mode = "system"
        self._save_config()

    def _save_config(self) -> None:
        """儲存偏好到 config.json。"""
        data = {"theme": self._mode}
        self._config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
