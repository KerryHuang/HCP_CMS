"""主題系統單元測試。"""

from __future__ import annotations

import re

from hcp_cms.ui.theme import DARK_PALETTE, LIGHT_PALETTE, ColorPalette


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
