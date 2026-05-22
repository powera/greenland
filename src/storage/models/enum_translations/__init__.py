"""Translations of POS subtype enum values into source languages.

Subtypes (food, occupation, building_structure, etc.) are exposed to learners
as the "group" field in wireword exports. Each source-language module here
provides a dict mapping subtype value -> display string in that language.

This is intentionally hard-coded source for now; a Barsukas-backed translation
flow may replace it later.
"""

from typing import Dict, Optional

from storage.models.enum_translations import de, en, es, fr, zh

# Registry of source language -> subtype display map.
# When a language is missing, English is used as the fallback.
_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": en.SUBTYPE_DISPLAY,
    "de": de.SUBTYPE_DISPLAY,
    "es": es.SUBTYPE_DISPLAY,
    "fr": fr.SUBTYPE_DISPLAY,
    "zh": zh.SUBTYPE_DISPLAY,
}


def get_subtype_display_name(subtype: Optional[str], source_language: str) -> str:
    """Return the display name for *subtype* in *source_language*.

    Falls back to English, then to a title-cased version of the raw subtype.
    """
    if not subtype:
        return _TRANSLATIONS["en"].get("__other__", "Other")

    lang_map = _TRANSLATIONS.get(source_language)
    if lang_map and subtype in lang_map:
        return lang_map[subtype]

    en_map = _TRANSLATIONS["en"]
    if subtype in en_map:
        return en_map[subtype]

    return subtype.replace("_", " ").title()
