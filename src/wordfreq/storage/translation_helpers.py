#!/usr/bin/python3

"""
Helper functions for accessing lemma translations.

This module abstracts away the storage implementation details - some translations
are stored as columns in the Lemma table, while others are stored in the
LemmaTranslation table. Code should use these helper functions instead of
directly accessing translation fields.
"""

from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import Lemma, LemmaTranslation


# Language mappings
# Format: 'code': (field_name_or_code, display_name, use_lemma_translation_table)
# If use_lemma_translation_table is True, field_name_or_code is the language_code for LemmaTranslation table
# If False, field_name_or_code is the column name in Lemma table
LANGUAGE_FIELDS = {
    "en": ("lemma_text", "English", False),  # English uses lemma_text field
    "lt": ("lithuanian_translation", "Lithuanian", False),
    "zh": ("chinese_translation", "Chinese", False),
    "ko": ("korean_translation", "Korean", False),
    "fr": ("french_translation", "French", False),
    "es": ("es", "Spanish", True),
    "de": ("de", "German", True),
    "pt": ("pt", "Portuguese", True),
    "sw": ("swahili_translation", "Swahili", False),
    "vi": ("vietnamese_translation", "Vietnamese", False)
}


def get_translation(session: Session, lemma: Lemma, lang_code: str) -> Optional[str]:
    """
    Get translation for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh')

    Returns:
        Translation string if it exists, None otherwise

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if use_translation_table:
        # Query LemmaTranslation table
        translation_obj = session.query(LemmaTranslation).filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == field_name
        ).first()
        return translation_obj.translation if translation_obj else None
    else:
        # Get from Lemma table column
        return getattr(lemma, field_name, None)


def get_all_translations(session: Session, lemma: Lemma) -> Dict[str, Optional[str]]:
    """
    Get all translations for a lemma.

    Args:
        session: Database session
        lemma: Lemma object

    Returns:
        Dictionary mapping language codes to translation strings.
        Example: {'es': 'comer', 'fr': 'manger', 'zh': '吃', ...}
    """
    translations = {}
    for lang_code in LANGUAGE_FIELDS.keys():
        translations[lang_code] = get_translation(session, lemma, lang_code)
    return translations


def set_translation(session: Session, lemma: Lemma, lang_code: str, translation: str) -> Tuple[Optional[str], str]:
    """
    Set translation for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh')
        translation: Translation string to set

    Returns:
        Tuple of (old_translation, new_translation)

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    # Get old translation for logging
    old_translation = get_translation(session, lemma, lang_code)

    if use_translation_table:
        # Insert or update in LemmaTranslation table
        translation_obj = session.query(LemmaTranslation).filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == field_name
        ).first()

        if translation_obj:
            translation_obj.translation = translation
        else:
            translation_obj = LemmaTranslation(
                lemma_id=lemma.id,
                language_code=field_name,
                translation=translation,
                verified=False
            )
            session.add(translation_obj)
    else:
        # Set on Lemma table column
        setattr(lemma, field_name, translation)

    return old_translation, translation


def has_translation(session: Session, lemma: Lemma, lang_code: str) -> bool:
    """
    Check if a lemma has a translation in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh')

    Returns:
        True if translation exists and is not empty, False otherwise
    """
    translation = get_translation(session, lemma, lang_code)
    return bool(translation and translation.strip())


def get_language_name(lang_code: str) -> str:
    """
    Get the display name for a language code.

    Args:
        lang_code: Language code (e.g., 'es', 'fr', 'zh')

    Returns:
        Display name (e.g., 'Spanish', 'French', 'Chinese')

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    return LANGUAGE_FIELDS[lang_code][1]


def get_supported_languages() -> Dict[str, str]:
    """
    Get all supported language codes and their display names.

    Returns:
        Dictionary mapping language codes to display names.
        Example: {'es': 'Spanish', 'fr': 'French', ...}
    """
    return {code: name for code, (_, name, _) in LANGUAGE_FIELDS.items()}
