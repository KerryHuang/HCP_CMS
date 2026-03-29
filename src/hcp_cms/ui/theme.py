"""主題系統 — ColorPalette 定義與 ThemeManager。"""

from __future__ import annotations

from dataclasses import dataclass


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
    bg_primary="#f8fafc",
    bg_secondary="#ffffff",
    bg_sidebar="#f1f5f9",
    bg_code="#f1f5f9",
    bg_hover="#e2e8f0",
    text_primary="#0f172a",
    text_secondary="#1e293b",
    text_tertiary="#475569",
    text_muted="#64748b",
    text_faint="#94a3b8",
    accent="#2563eb",
    accent_button="#2563eb",
    accent_button_hover="#1d4ed8",
    border_primary="#cbd5e1",
    border_secondary="#e2e8f0",
    success="#16a34a",
    error="#dc2626",
    warning="#d97706",
)
