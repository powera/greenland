#!/usr/bin/python3

"""
Helper functions for accessing lemma translations.

This module abstracts away the storage implementation details - some translations
are stored as columns in the Lemma table, while others are stored in the
LemmaTranslation table. Code should use these helper functions instead of
directly accessing translation fields.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Lemma, LemmaTranslation

logger = logging.getLogger(__name__)

# Languages that need a computed sort_key for dictionary ordering.
# CJK languages use transliteration (pinyin, hiragana, jamo); accented Latin
# languages use character remapping (see langtools.collation).
_CJK_SORT_KEY_LANGUAGES = frozenset({"zh", "ja", "ko"})

# Import Latin collation languages so we have the full set.
from langtools.collation import LATIN_SORT_KEY_LANGUAGES  # noqa: E402

_SORT_KEY_LANGUAGES = _CJK_SORT_KEY_LANGUAGES | LATIN_SORT_KEY_LANGUAGES

# Language hierarchy: ordered from most reliable/primary to experimental
# Tier 1: Primary supported languages
# Tier 2: Secondary supported languages (alphabetical: DE IT NL PT SV VI)
# Tier 3: Experimental languages with accuracy/pedagogical issues (alphabetical: GD KO SW)

# Tier 1: Primary supported languages
TIER_1_LANGUAGES = ["lt", "zh", "fr", "es"]

# Tier 2: Secondary supported languages
TIER_2_LANGUAGES = ["de", "it", "nl", "pt", "sv"]

# Tier 3: Experimental languages (lower quality/pedagogical issues)
TIER_3_LANGUAGES = [
    "vi",
    "ja",
    "ko",
    "ro",
    "pl",
    "th",
    "ms",
    "my",
    "km",
    "lo",
    "tl",
    "ta",
    "te",
    "kn",
    "ml",
    "si",
    "uk",
    "bn",
    "sw",
    "ha",
    "yo",
    "ig",
    "am",
    "zu",
    "om",
    "so",
    "xh",
    "sn",
    "hi",
    "ps",
    "fa",
    "ka",
    "hy",
    "az",
    "tr",
    "bg",
    "cs",
    "el",
    "et",
    "fi",
    "ga",
    "hr",
    "hu",
    "lv",
    "mt",
    "sk",
    "sl",
]

# Languages included in data/release read/write operations.
# Only these languages will be exported to and synced from release files.
# Edit this list to add or remove languages from release builds.
RELEASE_LANGUAGES = [
    "en",
    "lt",
    "zh",
    "zh-tw",
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
]

# Languages included in data/release secondary.jsonl files.
# These are Tier 3 languages NOT already in RELEASE_LANGUAGES.
# They are stored separately from base.jsonl to keep the primary release lean.
SECONDARY_RELEASE_LANGUAGES = [lang for lang in TIER_3_LANGUAGES if lang not in RELEASE_LANGUAGES]

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
    "ro",  # Romanian (experimental)
    "pl",  # Polish (experimental)
    "th",  # Thai (experimental)
    "ms",  # Malay (experimental)
    "my",  # Burmese (experimental)
    "km",  # Khmer (experimental)
    "lo",  # Lao (experimental)
    "tl",  # Filipino (experimental)
    "ta",  # Tamil (experimental)
    "te",  # Telugu (experimental)
    "kn",  # Kannada (experimental)
    "ml",  # Malayalam (experimental)
    "si",  # Sinhala (experimental)
    "uk",  # Ukrainian (experimental)
    "bn",  # Bengali (experimental)
    "sw",  # Swahili (experimental)
    "ha",  # Hausa (experimental)
    "yo",  # Yoruba (experimental)
    "ig",  # Igbo (experimental)
    "am",  # Amharic (experimental)
    "zu",  # Zulu (experimental)
    "om",  # Oromo (experimental)
    "so",  # Somali (experimental)
    "xh",  # Xhosa (experimental)
    "sn",  # Shona (experimental)
    "hi",  # Hindi (experimental)
    "ps",  # Pashto (experimental)
    "fa",  # Persian (experimental)
    "ka",  # Georgian (experimental)
    "hy",  # Armenian (experimental)
    "az",  # Azerbaijani (experimental)
    "tr",  # Turkish (experimental)
    "bg",  # Bulgarian (experimental)
    "cs",  # Czech (experimental)
    "el",  # Greek (experimental)
    "et",  # Estonian (experimental)
    "fi",  # Finnish (experimental)
    "ga",  # Irish (experimental)
    "hr",  # Croatian (experimental)
    "hu",  # Hungarian (experimental)
    "lv",  # Latvian (experimental)
    "mt",  # Maltese (experimental)
    "sk",  # Slovak (experimental)
    "sl",  # Slovenian (experimental)
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
    "ro": ("ro", "Romanian", True),
    "pl": ("pl", "Polish", True),
    "th": ("th", "Thai", True),
    "ms": ("ms", "Malay", True),
    "my": ("my", "Burmese", True),
    "km": ("km", "Khmer", True),
    "lo": ("lo", "Lao", True),
    "tl": ("tl", "Filipino", True),
    "ta": ("ta", "Tamil", True),
    "te": ("te", "Telugu", True),
    "kn": ("kn", "Kannada", True),
    "ml": ("ml", "Malayalam", True),
    "si": ("si", "Sinhala", True),
    "uk": ("uk", "Ukrainian", True),
    "bn": ("bn", "Bengali", True),
    "ha": ("ha", "Hausa", True),
    "yo": ("yo", "Yoruba", True),
    "ig": ("ig", "Igbo", True),
    "am": ("am", "Amharic", True),
    "zu": ("zu", "Zulu", True),
    "om": ("om", "Oromo", True),
    "so": ("so", "Somali", True),
    "xh": ("xh", "Xhosa", True),
    "sn": ("sn", "Shona", True),
    "hi": ("hi", "Hindi", True),
    "ps": ("ps", "Pashto", True),
    "fa": ("fa", "Persian", True),
    "ka": ("ka", "Georgian", True),
    "hy": ("hy", "Armenian", True),
    "az": ("az", "Azerbaijani", True),
    "tr": ("tr", "Turkish", True),
    "bg": ("bg", "Bulgarian", True),
    "cs": ("cs", "Czech", True),
    "el": ("el", "Greek", True),
    "et": ("et", "Estonian", True),
    "fi": ("fi", "Finnish", True),
    "ga": ("ga", "Irish", True),
    "hr": ("hr", "Croatian", True),
    "hu": ("hu", "Hungarian", True),
    "lv": ("lv", "Latvian", True),
    "mt": ("mt", "Maltese", True),
    "sk": ("sk", "Slovak", True),
    "sl": ("sl", "Slovenian", True),
}

# Language display names (for use in prompts, UIs, etc.)
# This is derived from LANGUAGE_FIELDS for convenience
LANGUAGE_NAMES = {code: name for code, (_, name, _) in LANGUAGE_FIELDS.items()}

# LLM field name mappings (used for LLM responses)
# Maps LLM field names (e.g., "chinese_translation") to language codes (e.g., "zh")
LLM_FIELD_TO_LANG_CODE = {
    "lithuanian_translation": "lt",
    "chinese_translation": "zh",
    "chinese_taiwan_translation": "zh-tw",
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
    "romanian_translation": "ro",
    "polish_translation": "pl",
    "tamil_translation": "ta",
    "telugu_translation": "te",
    "kannada_translation": "kn",
    "malayalam_translation": "ml",
    "sinhala_translation": "si",
    "ukrainian_translation": "uk",
    "bengali_translation": "bn",
    "thai_translation": "th",
    "malay_translation": "ms",
    "burmese_translation": "my",
    "khmer_translation": "km",
    "lao_translation": "lo",
    "filipino_translation": "tl",
    "hausa_translation": "ha",
    "yoruba_translation": "yo",
    "igbo_translation": "ig",
    "amharic_translation": "am",
    "zulu_translation": "zu",
    "oromo_translation": "om",
    "somali_translation": "so",
    "xhosa_translation": "xh",
    "shona_translation": "sn",
    "hindi_translation": "hi",
    "pashto_translation": "ps",
    "persian_translation": "fa",
    "georgian_translation": "ka",
    "armenian_translation": "hy",
    "azerbaijani_translation": "az",
    "turkish_translation": "tr",
    "bulgarian_translation": "bg",
    "czech_translation": "cs",
    "greek_translation": "el",
    "estonian_translation": "et",
    "finnish_translation": "fi",
    "irish_translation": "ga",
    "croatian_translation": "hr",
    "hungarian_translation": "hu",
    "latvian_translation": "lv",
    "maltese_translation": "mt",
    "slovak_translation": "sk",
    "slovenian_translation": "sl",
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
    """Compute a sort key for dictionary ordering.

    - Chinese (zh): pinyin with tone marks, e.g. "chī" for 吃
    - Japanese (ja): hiragana reading, e.g. "たべる" for 食べる
    - Korean (ko): decomposed jamo
    - Accented Latin languages (lt, es, de, sv, pt, fr, vi): character
      remapping so that accented letters sort in their correct alphabet
      position (e.g. Lithuanian "š" → "s{", sorting after "s" and before "t").

    Returns None for unsupported languages or if the required library is
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
        elif lang_code in LATIN_SORT_KEY_LANGUAGES:
            from langtools.collation import generate_latin_sort_key

            return generate_latin_sort_key(lang_code, translation)
    except Exception as e:
        logger.warning(f"Failed to compute sort_key for {lang_code} '{translation}': {e}")
    return None


def invalidate_audio_for_translation_change(
    session: Session,
    guid: Optional[str],
    lang_code: str,
    old_translation: Optional[str],
    new_translation: str,
) -> List[int]:
    """Mark audio records as needing replacement when a translation changes.

    Finds all AudioQualityReview records for the given guid + language_code
    and sets their status to 'needs_replacement' with a 'translation_mismatch'
    quality issue.

    Args:
        session: Database session
        guid: Lemma GUID (e.g. "N01_001"). If None, no-op.
        lang_code: Language code (e.g. 'lt', 'zh', 'fr')
        old_translation: Previous translation value
        new_translation: New translation value

    Returns:
        List of AudioQualityReview IDs that were invalidated.
    """
    if not guid:
        return []

    # No change — nothing to invalidate
    if old_translation == new_translation:
        return []

    audio_records = (
        session.query(AudioQualityReview)
        .filter(
            AudioQualityReview.guid == guid,
            AudioQualityReview.language_code == lang_code,
            AudioQualityReview.status != "needs_replacement",
        )
        .all()
    )

    invalidated_ids: List[int] = []
    for audio in audio_records:
        audio.status = "needs_replacement"

        # Parse existing quality_issues JSON array and append if needed
        existing_issues: List[str] = []
        if audio.quality_issues:
            try:
                existing_issues = json.loads(audio.quality_issues)
            except (json.JSONDecodeError, TypeError):
                existing_issues = []

        if "translation_mismatch" not in existing_issues:
            existing_issues.append("translation_mismatch")
            audio.quality_issues = json.dumps(existing_issues)

        invalidated_ids.append(audio.id)

    if invalidated_ids:
        logger.info(
            "Invalidated %d audio record(s) for %s/%s: translation changed " "from %r to %r",
            len(invalidated_ids),
            guid,
            lang_code,
            old_translation,
            new_translation,
        )

    return invalidated_ids


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

    # Invalidate any audio records whose expected_text no longer matches
    invalidate_audio_for_translation_change(
        session, lemma.guid, lang_code, old_translation, translation
    )

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
