"""國際化 — JSON 語系檔"""

import json
from pathlib import Path

_current_locale = "zh_TW"
_translations: dict[str, str] = {}


def load_locale(locale: str = "zh_TW") -> None:
    """載入語系檔"""
    global _current_locale, _translations
    _current_locale = locale
    locale_file = Path(__file__).parent / f"{locale}.json"
    if locale_file.exists():
        _translations = json.loads(locale_file.read_text(encoding="utf-8"))


def t(key: str) -> str:
    """翻譯函式"""
    return _translations.get(key, key)
