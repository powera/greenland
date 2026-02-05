#!/usr/bin/python3

"""
Helper functions for accessing lemma translations.

This module abstracts away the storage implementation details - some translations
are stored as columns in the Lemma table, while others are stored in the
LemmaTranslation table. Code should use these helper functions instead of
directly accessing translation fields.
"""

import logging
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import Lemma, LemmaTranslation

logger = logging.getLogger(__name__)

# Languages that need a computed sort_key for dictionary ordering.
_SORT_KEY_LANGUAGES = frozenset({"zh", "ja", "ko"})

# Language hierarchy: ordered from most reliable/primary to experimental
# Tier 1: Primary supported languages
# Tier 2: Secondary supported languages (alphabetical: DE IT NL PT SV VI)
# Tier 3: Experimental languages with accuracy/pedagogical issues (alphabetical: GD KO SW)

# Tier 1: Primary supported languages
TIER_1_LANGUAGES = ["lt", "zh", "fr", "es"]

# Tier 2: Secondary supported languages
TIER_2_LANGUAGES = ["de", "it", "nl", "pt", "sv", "vi"]

# Tier 3: Experimental languages (lower quality/pedagogical issues)
TIER_3_LANGUAGES = ["ja", "ko", "sw"]

LANGUAGE_HIERARCHY = [
    "en",  # English (special case - source language)
    "lt",  # Lithuanian
    "zh",  # Chinese
    "fr",  # French
    "es",  # Spanish
    "de",  # German
    "it",  # Italian
    "nl",  # Dutch
    "pt",  # Portuguese
    "sv",  # Swedish
    "vi",  # Vietnamese
    "ja",  # Japanese (experimental)
    "ko",  # Korean (experimental)
    "sw",  # Swahili (experimental)
]

# Language mappings
# Format: 'code': (field_name_or_code, display_name, use_lemma_translation_table)
# If use_lemma_translation_table is True, field_name_or_code is the language_code for LemmaTranslation table
# If False, field_name_or_code is the column name in Lemma table (only used for English)
# Order follows LANGUAGE_HIERARCHY for consistent display across the application
LANGUAGE_FIELDS = {
    "en": ("lemma_text", "English", False),  # English uses lemma_text field
    "lt": ("lt", "Lithuanian", True),
    "zh": ("zh", "Chinese", True),
    "zh-tw": ("zh-tw", "Chinese (Taiwan)", True),  # Taiwan-specific Chinese variant
    "fr": ("fr", "French", True),
    "es": ("es", "Spanish", True),
    "de": ("de", "German", True),
    "it": ("it", "Italian", True),
    "nl": ("nl", "Dutch", True),
    "pt": ("pt", "Portuguese", True),
    "sv": ("sv", "Swedish", True),
    "vi": ("vi", "Vietnamese", True),
    "ja": ("ja", "Japanese", True),
    "ko": ("ko", "Korean", True),
    "sw": ("sw", "Swahili", True),
}

# Language display names (for use in prompts, UIs, etc.)
# This is derived from LANGUAGE_FIELDS for convenience
LANGUAGE_NAMES = {code: name for code, (_, name, _) in LANGUAGE_FIELDS.items()}

# LLM field name mappings (used for LLM responses)
# Maps LLM field names (e.g., "chinese_translation") to language codes (e.g., "zh")
LLM_FIELD_TO_LANG_CODE = {
    "lithuanian_translation": "lt",
    "chinese_translation": "zh",
    "korean_translation": "ko",
    "french_translation": "fr",
    "spanish_translation": "es",
    "german_translation": "de",
    "japanese_translation": "ja",
    "italian_translation": "it",
    "dutch_translation": "nl",
    "portuguese_translation": "pt",
    "swahili_translation": "sw",
    "swedish_translation": "sv",
    "vietnamese_translation": "vi",
}

# Reverse mapping: language codes to LLM field names
LANG_CODE_TO_LLM_FIELD = {v: k for k, v in LLM_FIELD_TO_LANG_CODE.items()}


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
        translation_obj = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == field_name
            )
            .first()
        )
        return translation_obj.translation if translation_obj else None
    else:
        # Get from Lemma table column (English uses lemma_text)
        return getattr(lemma, field_name, None)


def get_definition(session: Session, lemma: Lemma, lang_code: str) -> Optional[str]:
    """
    Get definition for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh', 'en')

    Returns:
        Definition string if it exists, None otherwise

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if use_translation_table:
        # Query LemmaTranslation table
        translation_obj = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == field_name
            )
            .first()
        )
        return translation_obj.definition_text if translation_obj else None
    else:
        # For English, fall back to definition_text on Lemma table
        return lemma.definition_text if lemma else None


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
    # Start with English from lemma_text (doesn't need DB query)
    translations: Dict[str, Optional[str]] = {"en": lemma.lemma_text}

    # Batch fetch all translations from LemmaTranslation table in ONE query
    translation_rows = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma.id).all()
    )

    # Build lookup dict from results
    translation_by_lang = {t.language_code: t.translation for t in translation_rows}

    # Populate all language codes
    for lang_code in LANGUAGE_FIELDS.keys():
        if lang_code == "en":
            continue  # Already set above
        translations[lang_code] = translation_by_lang.get(lang_code)

    return translations


def get_all_definitions(session: Session, lemma: Lemma) -> Dict[str, Optional[str]]:
    """
    Get all definitions for a lemma.

    Args:
        session: Database session
        lemma: Lemma object

    Returns:
        Dictionary mapping language codes to definition strings.
        Example: {'en': 'to eat', 'es': 'comer algo', ...}
    """
    # Start with English from lemma's definition_text
    definitions: Dict[str, Optional[str]] = {"en": lemma.definition_text if lemma else None}

    # Batch fetch all definitions from LemmaTranslation table in ONE query
    translation_rows = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma.id).all()
    )

    # Build lookup dict from results
    definition_by_lang = {t.language_code: t.definition_text for t in translation_rows}

    # Populate all language codes
    for lang_code in LANGUAGE_FIELDS.keys():
        if lang_code == "en":
            continue  # Already set above
        definitions[lang_code] = definition_by_lang.get(lang_code)

    return definitions


def compute_sort_key(lang_code: str, translation: str) -> Optional[str]:
    """Compute a romanized/phonetic sort key for CJK translations.

    - Chinese (zh): pinyin with tone marks, e.g. "chī" for 吃
    - Japanese (ja): hiragana reading, e.g. "たべる" for 食べる
    - Korean (ko): the translation itself (Hangul already sorts correctly)

    Returns None for non-CJK languages or if the required library is
    unavailable.
    """
    if lang_code not in _SORT_KEY_LANGUAGES:
        return None

    if not translation or not translation.strip():
        return None

    try:
        if lang_code == "zh":
            from langtools.zh.pinyin_helper import generate_pinyin

            return generate_pinyin(translation)
        elif lang_code == "ja":
            from langtools.ja.romaji_helper import generate_hiragana

            return generate_hiragana(translation)
        elif lang_code == "ko":
            from langtools.ko.hangul_helper import decompose_hangul

            return decompose_hangul(translation)
    except Exception as e:
        logger.warning(f"Failed to compute sort_key for {lang_code} '{translation}': {e}")
    return None


def set_translation(
    session: Session,
    lemma: Lemma,
    lang_code: str,
    translation: str,
    definition: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Set translation for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh')
        translation: Translation string to set
        definition: Optional definition text in this language

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
        translation_obj = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == field_name
            )
            .first()
        )

        sort_key = compute_sort_key(lang_code, translation)

        if translation_obj:
            translation_obj.translation = translation
            if definition is not None:
                translation_obj.definition_text = definition
            if lang_code in _SORT_KEY_LANGUAGES:
                translation_obj.sort_key = sort_key
        else:
            translation_obj = LemmaTranslation(
                lemma_id=lemma.id,
                language_code=field_name,
                translation=translation,
                definition_text=definition,
                sort_key=sort_key,
                verified=False,
            )
            session.add(translation_obj)
    else:
        # Set on Lemma table column (English uses lemma_text)
        setattr(lemma, field_name, translation)
        if definition is not None and hasattr(lemma, "definition_text"):
            lemma.definition_text = definition

    return old_translation, translation


def set_definition(
    session: Session, lemma: Lemma, lang_code: str, definition: str
) -> Tuple[Optional[str], str]:
    """
    Set definition for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh', 'en')
        definition: Definition text to set

    Returns:
        Tuple of (old_definition, new_definition)

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    # Get old definition for logging
    old_definition = get_definition(session, lemma, lang_code)

    if use_translation_table:
        # Insert or update in LemmaTranslation table
        translation_obj = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == field_name
            )
            .first()
        )

        if translation_obj:
            translation_obj.definition_text = definition
        else:
            # Need to create a row - but we need a translation too
            # Use lemma_text as placeholder if English, otherwise raise error
            if lang_code == "en":
                translation = lemma.lemma_text
            else:
                raise ValueError(f"Cannot set definition for {lang_code} without translation")

            translation_obj = LemmaTranslation(
                lemma_id=lemma.id,
                language_code=field_name,
                translation=translation,
                definition_text=definition,
                verified=False,
            )
            session.add(translation_obj)
    else:
        # For English, set on Lemma table
        if hasattr(lemma, "definition_text"):
            lemma.definition_text = definition

    return old_definition, definition


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


def get_languages_in_hierarchy() -> list:
    """
    Get all supported languages in hierarchy order.

    Returns:
        List of dicts with 'code' and 'name' keys, ordered by LANGUAGE_HIERARCHY.
        Example: [{'code': 'en', 'name': 'English'}, {'code': 'lt', 'name': 'Lithuanian'}, ...]
    """
    return [{"code": code, "name": LANGUAGE_FIELDS[code][1]} for code in LANGUAGE_HIERARCHY]


def llm_field_to_lang_code(field_name: str) -> Optional[str]:
    """
    Convert LLM field name to language code.

    Args:
        field_name: LLM field name (e.g., 'chinese_translation')

    Returns:
        Language code (e.g., 'zh') or None if not found
    """
    return LLM_FIELD_TO_LANG_CODE.get(field_name)


def lang_code_to_llm_field(lang_code: str) -> Optional[str]:
    """
    Convert language code to LLM field name.

    Args:
        lang_code: Language code (e.g., 'zh')

    Returns:
        LLM field name (e.g., 'chinese_translation') or None if not found
    """
    return LANG_CODE_TO_LLM_FIELD.get(lang_code)


def convert_llm_response_to_lang_codes(llm_response: Dict[str, str]) -> Dict[str, str]:
    """
    Convert LLM response with field names to language code format.

    Args:
        llm_response: Dictionary with LLM field names as keys
                     (e.g., {'chinese_translation': '吃', 'french_translation': 'manger'})

    Returns:
        Dictionary with language codes as keys
        (e.g., {'zh': '吃', 'fr': 'manger'})
    """
    return {
        LLM_FIELD_TO_LANG_CODE[field_name]: translation
        for field_name, translation in llm_response.items()
        if field_name in LLM_FIELD_TO_LANG_CODE
    }


def bulk_get_translations(
    session: Session, lemmas: list, lang_code: str
) -> Dict[int, Optional[str]]:
    """
    Get translations for multiple lemmas in a single query.

    This is an optimized version of get_translation for bulk operations,
    reducing N+1 query problems when processing many lemmas.

    Args:
        session: Database session
        lemmas: List of Lemma objects
        lang_code: Language code (e.g., 'es', 'fr', 'zh')

    Returns:
        Dictionary mapping lemma_id to translation string (or None if not found)

    Raises:
        ValueError: If lang_code is not supported
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    if not lemmas:
        return {}

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if use_translation_table:
        # Batch query LemmaTranslation table
        lemma_ids = [lemma.id for lemma in lemmas]
        translation_rows = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id.in_(lemma_ids),
                LemmaTranslation.language_code == field_name,
            )
            .all()
        )
        return {t.lemma_id: t.translation for t in translation_rows}
    else:
        # Get from Lemma table column (English uses lemma_text)
        return {lemma.id: getattr(lemma, field_name, None) for lemma in lemmas}


def get_reference_translation(
    session: Session,
    lemma: Lemma,
    exclude_languages: Optional[list] = None,
    prefer_languages: Optional[list] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Find a reference translation for use in LLM queries.

    This is useful when generating missing translations - we can provide an existing
    translation in another language as context to improve LLM accuracy.

    Args:
        session: Database session
        lemma: Lemma object
        exclude_languages: Language codes to exclude (e.g., languages we're trying to generate)
        prefer_languages: Ordered list of language codes to prefer. If not provided,
                         defaults to ["lt", "zh", "ko", "fr", "es", "de", "pt", "sw", "vi", "en"]

    Returns:
        Tuple of (language_code, translation) for the reference translation.
        Returns (None, None) if no suitable translation found.

    Example:
        # Get a reference translation, excluding Spanish and German (which we're generating)
        lang_code, translation = get_reference_translation(
            session, lemma, exclude_languages=["es", "de"]
        )
        if translation:
            # Use this as context for LLM query
            llm_response = client.query_translations(
                english_word=lemma.lemma_text,
                reference_translation=(lang_code, translation),
                ...
            )
    """
    if exclude_languages is None:
        exclude_languages = []

    if prefer_languages is None:
        # Default preference follows LANGUAGE_HIERARCHY (excluding English where applicable)
        # LT, ZH, FR, ES are primary, then tier 2 (DE IT NL PT SV VI), then experimental (GD KO SW)
        # English is last as a fallback
        prefer_languages = [
            "lt",
            "zh",
            "fr",
            "es",
            "de",
            "it",
            "nl",
            "pt",
            "sv",
            "vi",
            "ja",
            "ko",
            "sw",
            "en",
        ]

    # Search through languages in preference order
    for lang_code in prefer_languages:
        if lang_code in exclude_languages:
            continue

        translation = get_translation(session, lemma, lang_code)
        if translation and translation.strip():
            return lang_code, translation

    # No reference translation found
    return None, None
