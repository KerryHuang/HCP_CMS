"""主題系統單元測試。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hcp_cms.ui.theme import DARK_PALETTE, LIGHT_PALETTE, ColorPalette, ThemeManager


class TestColorPalette:
    """ColorPalette dataclass 結構驗證。"""

    def test_dark_palette_is_color_palette(self) -> None:
        assert isinstance(DARK_PALETTE, ColorPalette)

    def test_light_palette_is_color_palette(self) -> None:
        assert isinstance(LIGHT_PALETTE, ColorPalette)

    def test_all_fields_are_hex_color(self) -> None:
        """所有欄位值必須是 #xxxxxx 格式。"""
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for palette in (DARK_PALETTE, LIGHT_PALETTE):
            for field_name in ColorPalette.__dataclass_fields__:
                value = getattr(palette, field_name)
                assert hex_pattern.match(value), f"{palette} 的 {field_name} 值 '{value}' 不是有效的 hex 色碼"

    def test_dark_and_light_differ(self) -> None:
        """深色和淺色主題的主背景色必須不同。"""
        assert DARK_PALETTE.bg_primary != LIGHT_PALETTE.bg_primary
        assert DARK_PALETTE.text_primary != LIGHT_PALETTE.text_primary


class TestThemeManager:
    """ThemeManager 主題管理器測試。"""

    def test_default_mode_is_system(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        assert mgr.current_mode() == "system"

    def test_set_dark(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        assert mgr.current_mode() == "dark"
        assert mgr.current_palette() == DARK_PALETTE

    def test_set_light(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("light")
        assert mgr.current_mode() == "light"
        assert mgr.current_palette() == LIGHT_PALETTE

    def test_signal_emitted(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        received: list[ColorPalette] = []
        mgr.theme_changed.connect(received.append)
        mgr.set_theme("light")
        assert len(received) == 1
        assert received[0] == LIGHT_PALETTE

    def test_signal_not_emitted_when_same_mode(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        received: list[ColorPalette] = []
        mgr.theme_changed.connect(received.append)
        mgr.set_theme("dark")
        assert len(received) == 0

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        mgr1 = ThemeManager(tmp_path)
        mgr1.set_theme("light")

        mgr2 = ThemeManager(tmp_path)
        assert mgr2.current_mode() == "light"

    def test_invalid_config_falls_back_to_system(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json", encoding="utf-8")
        mgr = ThemeManager(tmp_path)
        assert mgr.current_mode() == "system"

    def test_missing_config_creates_default(self, tmp_path: Path) -> None:
        ThemeManager(tmp_path)
        config_path = tmp_path / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["theme"] == "system"

    def test_invalid_mode_ignored(self, tmp_path: Path) -> None:
        mgr = ThemeManager(tmp_path)
        mgr.set_theme("dark")
        mgr.set_theme("invalid_mode")
        assert mgr.current_mode() == "dark"
