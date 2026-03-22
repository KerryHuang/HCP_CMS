"""i18n translation engine."""

from __future__ import annotations

import json
from pathlib import Path

_TRANSLATIONS: dict[str, dict[str, str]] = {}
_CURRENT_LANG = "zh_TW"
_I18N_DIR = Path(__file__).parent


def load_language(lang: str = "zh_TW") -> None:
    """Load a language file."""
    global _CURRENT_LANG
    lang_file = _I18N_DIR / f"{lang}.json"
    if lang_file.exists():
        with open(lang_file, encoding="utf-8") as f:
            _TRANSLATIONS[lang] = json.load(f)
    _CURRENT_LANG = lang


def tr(key: str) -> str:
    """Translate a key to current language. Returns key if not found."""
    if _CURRENT_LANG not in _TRANSLATIONS:
        load_language(_CURRENT_LANG)
    return _TRANSLATIONS.get(_CURRENT_LANG, {}).get(key, key)


def get_current_language() -> str:
    """Get current language code."""
    return _CURRENT_LANG


def set_language(lang: str) -> None:
    """Switch language."""
    load_language(lang)
