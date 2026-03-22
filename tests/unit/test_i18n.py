"""Tests for i18n translation."""

from hcp_cms.i18n.translator import get_current_language, load_language, set_language, tr


class TestTranslator:
    def test_default_language_is_chinese(self):
        load_language("zh_TW")
        assert get_current_language() == "zh_TW"

    def test_translate_chinese(self):
        load_language("zh_TW")
        assert tr("app.title") == "HCP CMS v2.0"
        assert tr("nav.dashboard") == "📊 儀表板"
        assert tr("case.processing") == "處理中"

    def test_translate_english(self):
        load_language("en")
        assert tr("nav.dashboard") == "📊 Dashboard"
        assert tr("case.processing") == "Processing"

    def test_missing_key_returns_key(self):
        load_language("zh_TW")
        assert tr("nonexistent.key") == "nonexistent.key"

    def test_switch_language(self):
        set_language("zh_TW")
        assert tr("nav.cases") == "📋 案件管理"
        set_language("en")
        assert tr("nav.cases") == "📋 Cases"

    def test_load_nonexistent_language(self):
        # Should not crash, just use whatever is loaded
        load_language("xx_XX")
        assert get_current_language() == "xx_XX"
