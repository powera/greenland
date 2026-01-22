#!/usr/bin/python3

"""
Helper functions for accessing lemma translations.

This module abstracts away the storage implementation details - some translations
are stored as columns in the Lemma table, while others are stored in the
LemmaTranslation table. Code should use these helper functions instead of
directly accessing translation fields.
"""

from typing import Any, Dict, Optional, Tuple, cast

from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import Lemma, LemmaTranslation

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

# Pluricentric language configuration
# These are languages with multiple regional standards that may differ in vocabulary,
# spelling, or usage. The system supports a "base" translation with optional regional
# overrides. Regional codes follow BCP 47 format (e.g., "en-US", "es-MX").
#
# For each base language code:
# - "display_name": Human-readable name for the language family
# - "default_region": The region code to use when no specific region is requested
# - "variants": Dict mapping region codes to their display names
#
# Example usage:
# - Base translation stored with code "en" in LemmaTranslation
# - Regional override "colour" stored with code "en-GB" in LemmaRegionalVariant
# - Export can include both base and all regional variants
PLURICENTRIC_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "en": {
        "display_name": "English",
        "default_region": "en-US",
        "variants": {
            "en-US": "American English",
            "en-GB": "British English",
            "en-AU": "Australian English",
        },
    },
    "es": {
        "display_name": "Spanish",
        "default_region": "es-ES",
        "variants": {
            "es-ES": "Castilian Spanish",
            "es-MX": "Mexican Spanish",
            "es-AR": "Argentine Spanish",
        },
    },
    "pt": {
        "display_name": "Portuguese",
        "default_region": "pt-BR",
        "variants": {
            "pt-PT": "European Portuguese",
            "pt-BR": "Brazilian Portuguese",
        },
    },
    "zh": {
        "display_name": "Chinese",
        "default_region": "zh-CN",
        "variants": {
            "zh-CN": "Mandarin (Simplified)",
            "zh-HK": "Cantonese",
            "zh-TW": "Taiwanese Mandarin",
        },
    },
}

# Language mappings
# Format: 'code': (field_name_or_code, display_name, use_lemma_translation_table)
# If use_lemma_translation_table is True, field_name_or_code is the language_code for LemmaTranslation table
# If False, field_name_or_code is the column name in Lemma table (only used for English)
# Order follows LANGUAGE_HIERARCHY for consistent display across the application
LANGUAGE_FIELDS = {
    "en": ("lemma_text", "English", False),  # English uses lemma_text field
    "lt": ("lt", "Lithuanian", True),
    "zh": ("zh", "Chinese", True),
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

        if translation_obj:
            translation_obj.translation = translation
            if definition is not None:
                translation_obj.definition_text = definition
        else:
            translation_obj = LemmaTranslation(
                lemma_id=lemma.id,
                language_code=field_name,
                translation=translation,
                definition_text=definition,
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


# =============================================================================
# Pluricentric Language Helper Functions
# =============================================================================


def is_pluricentric_language(lang_code: str) -> bool:
    """
    Check if a language code is a pluricentric language (has regional variants).

    Args:
        lang_code: Base language code (e.g., 'en', 'es', 'pt', 'zh')

    Returns:
        True if the language has defined regional variants, False otherwise
    """
    return lang_code in PLURICENTRIC_LANGUAGES


def is_valid_region_code(region_code: str) -> bool:
    """
    Check if a region code is valid (defined in PLURICENTRIC_LANGUAGES).

    Args:
        region_code: Region code (e.g., 'en-US', 'es-MX', 'zh-CN')

    Returns:
        True if the region code is valid, False otherwise
    """
    base_lang = get_base_language(region_code)
    if base_lang is None:
        return False
    variants = cast(Dict[str, str], PLURICENTRIC_LANGUAGES.get(base_lang, {}).get("variants", {}))
    return region_code in variants


def get_base_language(region_code: str) -> Optional[str]:
    """
    Extract the base language code from a region code.

    Args:
        region_code: Region code (e.g., 'en-US', 'es-MX', 'zh-CN')

    Returns:
        Base language code (e.g., 'en', 'es', 'zh') or None if invalid format
    """
    if "-" in region_code:
        return region_code.split("-")[0]
    return None


def get_region_variants(lang_code: str) -> Dict[str, str]:
    """
    Get all regional variants for a pluricentric language.

    Args:
        lang_code: Base language code (e.g., 'en', 'es', 'pt', 'zh')

    Returns:
        Dictionary mapping region codes to display names.
        Empty dict if language is not pluricentric.

    Example:
        >>> get_region_variants('es')
        {'es-ES': 'Castilian Spanish', 'es-MX': 'Mexican Spanish', 'es-AR': 'Argentine Spanish'}
    """
    if lang_code not in PLURICENTRIC_LANGUAGES:
        return {}
    return cast(Dict[str, str], PLURICENTRIC_LANGUAGES[lang_code].get("variants", {}))


def get_default_region(lang_code: str) -> Optional[str]:
    """
    Get the default regional variant for a pluricentric language.

    Args:
        lang_code: Base language code (e.g., 'en', 'es', 'pt', 'zh')

    Returns:
        Default region code (e.g., 'en-US', 'es-ES') or None if not pluricentric
    """
    if lang_code not in PLURICENTRIC_LANGUAGES:
        return None
    return cast(Optional[str], PLURICENTRIC_LANGUAGES[lang_code].get("default_region"))


def get_region_display_name(region_code: str) -> Optional[str]:
    """
    Get the display name for a regional variant.

    Args:
        region_code: Region code (e.g., 'en-GB', 'es-MX', 'zh-HK')

    Returns:
        Display name (e.g., 'British English', 'Mexican Spanish', 'Cantonese')
        or None if not found
    """
    base_lang = get_base_language(region_code)
    if base_lang is None:
        return None
    variants = cast(Dict[str, str], PLURICENTRIC_LANGUAGES.get(base_lang, {}).get("variants", {}))
    return variants.get(region_code)


def get_regional_variant(session: Session, lemma: Lemma, region_code: str) -> Optional[str]:
    """
    Get a regional variant translation for a lemma.

    Falls back to the base translation if no regional override exists.

    Args:
        session: Database session
        lemma: Lemma object
        region_code: Region code (e.g., 'en-GB', 'es-MX', 'zh-CN')

    Returns:
        Regional variant translation, base translation, or None if not found

    Raises:
        ValueError: If region_code is not valid
    """
    if not is_valid_region_code(region_code):
        raise ValueError(f"Invalid region code: {region_code}")

    # Import here to avoid circular imports
    from wordfreq.storage.models.schema import LemmaRegionalVariant

    # Try to get regional override
    variant = (
        session.query(LemmaRegionalVariant)
        .filter(
            LemmaRegionalVariant.lemma_id == lemma.id,
            LemmaRegionalVariant.region_code == region_code,
        )
        .first()
    )

    if variant:
        return cast(str, variant.translation)

    # Fall back to base translation
    base_lang = get_base_language(region_code)
    if base_lang:
        return get_translation(session, lemma, base_lang)
    return None


def set_regional_variant(
    session: Session,
    lemma: Lemma,
    region_code: str,
    translation: str,
    definition: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Set a regional variant translation for a lemma.

    Args:
        session: Database session
        lemma: Lemma object
        region_code: Region code (e.g., 'en-GB', 'es-MX', 'zh-CN')
        translation: Translation string to set
        definition: Optional definition text for this regional variant

    Returns:
        Tuple of (old_translation, new_translation)

    Raises:
        ValueError: If region_code is not valid
    """
    if not is_valid_region_code(region_code):
        raise ValueError(f"Invalid region code: {region_code}")

    # Import here to avoid circular imports
    from wordfreq.storage.models.schema import LemmaRegionalVariant

    # Get old translation for logging
    old_translation = get_regional_variant(session, lemma, region_code)

    # Check if override already exists
    variant = (
        session.query(LemmaRegionalVariant)
        .filter(
            LemmaRegionalVariant.lemma_id == lemma.id,
            LemmaRegionalVariant.region_code == region_code,
        )
        .first()
    )

    if variant:
        variant.translation = translation
        if definition is not None:
            variant.definition_text = definition
    else:
        variant = LemmaRegionalVariant(
            lemma_id=lemma.id,
            region_code=region_code,
            translation=translation,
            definition_text=definition,
            verified=False,
        )
        session.add(variant)

    return old_translation, translation


def get_all_regional_variants(
    session: Session, lemma: Lemma, lang_code: str
) -> Dict[str, Optional[str]]:
    """
    Get all regional variant translations for a lemma in a pluricentric language.

    For each variant, returns the regional override if it exists, otherwise
    returns the base translation.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Base language code (e.g., 'en', 'es', 'pt', 'zh')

    Returns:
        Dictionary mapping region codes to translations.
        Empty dict if language is not pluricentric.

    Example:
        >>> get_all_regional_variants(session, lemma, 'en')
        {'en-US': 'color', 'en-GB': 'colour', 'en-AU': 'colour'}
    """
    if lang_code not in PLURICENTRIC_LANGUAGES:
        return {}

    # Import here to avoid circular imports
    from wordfreq.storage.models.schema import LemmaRegionalVariant

    variants = cast(Dict[str, str], PLURICENTRIC_LANGUAGES[lang_code]["variants"])
    region_codes = list(variants.keys())

    # Get base translation
    base_translation = get_translation(session, lemma, lang_code)

    # Batch fetch all regional overrides for this lemma
    overrides = (
        session.query(LemmaRegionalVariant)
        .filter(
            LemmaRegionalVariant.lemma_id == lemma.id,
            LemmaRegionalVariant.region_code.in_(region_codes),
        )
        .all()
    )

    # Build lookup dict from overrides
    overrides_by_region = {o.region_code: o.translation for o in overrides}

    # Return all variants, using override if exists, else base translation
    result = {}
    for region_code in region_codes:
        result[region_code] = overrides_by_region.get(region_code, base_translation)

    return result


def bulk_get_regional_variants(
    session: Session, lemmas: list, region_code: str
) -> Dict[int, Optional[str]]:
    """
    Get regional variant translations for multiple lemmas in a single query.

    Optimized for bulk operations. Falls back to base translations for lemmas
    without regional overrides.

    Args:
        session: Database session
        lemmas: List of Lemma objects
        region_code: Region code (e.g., 'en-GB', 'es-MX', 'zh-CN')

    Returns:
        Dictionary mapping lemma_id to translation string (or None if not found)

    Raises:
        ValueError: If region_code is not valid
    """
    if not is_valid_region_code(region_code):
        raise ValueError(f"Invalid region code: {region_code}")

    if not lemmas:
        return {}

    # Import here to avoid circular imports
    from wordfreq.storage.models.schema import LemmaRegionalVariant

    lemma_ids = [lemma.id for lemma in lemmas]
    base_lang = get_base_language(region_code)

    # Get base translations
    base_translations = bulk_get_translations(session, lemmas, base_lang) if base_lang else {}

    # Get regional overrides
    overrides = (
        session.query(LemmaRegionalVariant)
        .filter(
            LemmaRegionalVariant.lemma_id.in_(lemma_ids),
            LemmaRegionalVariant.region_code == region_code,
        )
        .all()
    )

    overrides_by_id = {o.lemma_id: o.translation for o in overrides}

    # Merge: use override if exists, else base translation
    result = {}
    for lemma in lemmas:
        if lemma.id in overrides_by_id:
            result[lemma.id] = overrides_by_id[lemma.id]
        else:
            result[lemma.id] = base_translations.get(lemma.id)

    return result


def bulk_get_all_regional_variants(
    session: Session, lemmas: list, lang_code: str
) -> Dict[int, Dict[str, Optional[str]]]:
    """
    Get all regional variant translations for multiple lemmas in a pluricentric language.

    Optimized bulk version of get_all_regional_variants.

    Args:
        session: Database session
        lemmas: List of Lemma objects
        lang_code: Base language code (e.g., 'en', 'es', 'pt', 'zh')

    Returns:
        Dictionary mapping lemma_id to dict of region_code -> translation.
        Empty outer dict if language is not pluricentric.

    Example:
        >>> bulk_get_all_regional_variants(session, lemmas, 'en')
        {
            1: {'en-US': 'color', 'en-GB': 'colour', 'en-AU': 'colour'},
            2: {'en-US': 'center', 'en-GB': 'centre', 'en-AU': 'centre'},
        }
    """
    if lang_code not in PLURICENTRIC_LANGUAGES:
        return {}

    if not lemmas:
        return {}

    # Import here to avoid circular imports
    from wordfreq.storage.models.schema import LemmaRegionalVariant

    variants_config = cast(Dict[str, str], PLURICENTRIC_LANGUAGES[lang_code]["variants"])
    region_codes = list(variants_config.keys())
    lemma_ids = [lemma.id for lemma in lemmas]

    # Get base translations for all lemmas
    base_translations = bulk_get_translations(session, lemmas, lang_code)

    # Batch fetch all regional overrides for all lemmas
    overrides = (
        session.query(LemmaRegionalVariant)
        .filter(
            LemmaRegionalVariant.lemma_id.in_(lemma_ids),
            LemmaRegionalVariant.region_code.in_(region_codes),
        )
        .all()
    )

    # Index overrides by (lemma_id, region_code)
    overrides_index: Dict[Tuple[int, str], str] = {}
    for o in overrides:
        overrides_index[(o.lemma_id, o.region_code)] = o.translation

    # Build result
    result: Dict[int, Dict[str, Optional[str]]] = {}
    for lemma in lemmas:
        base_trans = base_translations.get(lemma.id)
        lemma_variants: Dict[str, Optional[str]] = {}

        for region_code in region_codes:
            override = overrides_index.get((lemma.id, region_code))
            lemma_variants[region_code] = override if override else base_trans

        result[lemma.id] = lemma_variants

    return result
