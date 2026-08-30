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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Lemma, LemmaTranslation

logger = logging.getLogger(__name__)

MAX_LLM_LANGUAGES_PER_OPERATION = 10

# Languages that need a computed sort_key for dictionary ordering.
# CJK languages use transliteration (pinyin, hiragana, jamo); accented Latin
# languages use character remapping (see langtools.collation).
_CJK_SORT_KEY_LANGUAGES = frozenset({"zh", "ja", "ko"})

# Import collation languages (Latin + Cyrillic + Brahmic/Thai) so we have
# the full set.  CJK is handled separately via script-specific helpers.
from langtools.collation import SORT_KEY_LANGUAGES as _COLLATION_SORT_KEY_LANGUAGES  # noqa: E402
from langtools.dialect_overrides import (  # noqa: E402
    get_dialects_reading,
    get_sort_key_language,
    get_translation_target_dialects,
    normalize_language_code,
)

_SORT_KEY_LANGUAGES = _CJK_SORT_KEY_LANGUAGES | _COLLATION_SORT_KEY_LANGUAGES

# Language hierarchy: ordered from most reliable/primary to experimental
# Tier 1: Primary supported languages
# Tier 2: Secondary supported languages
# Tier 3: Experimental languages with moderate coverage
# Tier 4: Experimental languages with minimal coverage / lowest quality

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
    "ta",
    "kn",
    "uk",
    "bn",
    "sw",
    "hi",
    "pa",
]

# Tier 4: Additional experimental languages with minimal coverage
TIER_4_LANGUAGES = [
    "la",
    "sa",
    "grc",
    "ar-classical",
    "non",
    "ms",
    "my",
    "km",
    "lo",
    "tl",
    "te",
    "ml",
    "si",
    "ha",
    "yo",
    "ig",
    "am",
    "zu",
    "om",
    "so",
    "xh",
    "sn",
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
    "hu",
    "lv",
    "mt",
    "sk",
    "sl",
    "bs",
    "sr",
    "hr",
    "mk",
    "sq",
    "me",
]

ANCIENT_LANGUAGE_GROUP = [
    "la",
    "sa",
    "grc",
    "ar-classical",
    "non",
]

EXTRA_RELEASE_LANGUAGE_GROUPS = {
    "ancient": ANCIENT_LANGUAGE_GROUP,
}


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
    "es-419",
    "de",
    "it",
    "nl",
    "pt",
    "pt-br",
    "sv",
    "vi",
    "ja",
    "ko",
    "sw",
]

# Languages included in data/release secondary.jsonl files.
# These are Tier 3 and Tier 4 languages NOT already in RELEASE_LANGUAGES or a
# named extra release group. Named groups use <group>.jsonl (for example
# ancient.jsonl) to keep each release file below roughly 20 languages.
SECONDARY_RELEASE_LANGUAGES = [
    lang
    for lang in (TIER_3_LANGUAGES + TIER_4_LANGUAGES)
    if lang not in RELEASE_LANGUAGES
    and all(lang not in group for group in EXTRA_RELEASE_LANGUAGE_GROUPS.values())
]

LANGUAGE_HIERARCHY = [
    "en",  # English (special case - source language)
    "lt",  # Lithuanian
    "zh",  # Chinese
    "zh-tw",  # Chinese (Taiwan, Traditional)
    "fr",  # French
    "es",  # Spanish
    "es-419",  # Spanish (Latin America)
    "de",  # German
    "it",  # Italian
    "nl",  # Dutch
    "pt",  # Portuguese
    "pt-br",  # Portuguese (Brazil)
    "sv",  # Swedish
    "vi",  # Vietnamese
    "ja",  # Japanese (experimental)
    "ko",  # Korean (experimental)
    "ro",  # Romanian (experimental)
    "pl",  # Polish (experimental)
    "th",  # Thai (experimental)
    "la",  # Latin (experimental/classical)
    "sa",  # Sanskrit (experimental/classical)
    "grc",  # Ancient Greek (experimental/classical)
    "ar-classical",  # Classical Arabic, pre-1200 (experimental/classical)
    "non",  # Old Norse (experimental/classical)
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
    "pa",  # Punjabi (experimental, Gurmukhi)
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
    "hu",  # Hungarian (experimental)
    "lv",  # Latvian (experimental)
    "mt",  # Maltese (experimental)
    "sk",  # Slovak (experimental)
    "sl",  # Slovenian (experimental)
    "bs",  # Bosnian (experimental)
    "sr",  # Serbian (experimental, Cyrillic)
    "hr",  # Croatian (experimental, Latin)
    "mk",  # Macedonian (experimental)
    "sq",  # Albanian (experimental)
    "me",  # Montenegrin (experimental)
]

# Language mappings
# This is the storage-side source of truth for supported languages (code,
# display name, table routing). The translation LLM path additionally needs
# prompt data (description, instructions) kept in DEFAULT_TRANSLATION_LANGUAGES
# in wordfreq/translation/constants.py. When adding/removing a language here,
# make the matching change there (and in LLM_FIELD_TO_LANG_CODE below), or the
# active query_translations path will skip it as "unknown".
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
    "es-419": ("es-419", "Spanish (Latin America)", True),  # neutral Latin American variety
    "de": ("de", "German", True),
    "it": ("it", "Italian", True),
    "nl": ("nl", "Dutch", True),
    "pt": ("pt", "Portuguese", True),
    "pt-br": ("pt-br", "Portuguese (Brazil)", True),  # Brazilian Portuguese variant
    "sv": ("sv", "Swedish", True),
    "vi": ("vi", "Vietnamese", True),
    "ja": ("ja", "Japanese", True),
    "ko": ("ko", "Korean", True),
    "la": ("la", "Latin", True),
    "sa": ("sa", "Sanskrit", True),
    "grc": ("grc", "Ancient Greek", True),
    "ar-classical": ("ar-classical", "Classical Arabic (pre-1200)", True),
    "non": ("non", "Old Norse", True),
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
    "pa": ("pa", "Punjabi", True),
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
    "hu": ("hu", "Hungarian", True),
    "lv": ("lv", "Latvian", True),
    "mt": ("mt", "Maltese", True),
    "sk": ("sk", "Slovak", True),
    "sl": ("sl", "Slovenian", True),
    "bs": ("bs", "Bosnian", True),
    "sr": ("sr", "Serbian", True),
    "hr": ("hr", "Croatian", True),
    "mk": ("mk", "Macedonian", True),
    "sq": ("sq", "Albanian", True),
    "me": ("me", "Montenegrin", True),
}

# Language display names (for use in prompts, UIs, etc.)
# This is derived from LANGUAGE_FIELDS for convenience
LANGUAGE_NAMES = {code: name for code, (_, name, _) in LANGUAGE_FIELDS.items()}

# Inverse of LANGUAGE_NAMES, keyed by lowercased display name ("chinese" -> "zh").
LANGUAGE_NAME_TO_CODE = {name.lower(): code for code, name in LANGUAGE_NAMES.items()}

# LLM field name mappings (used for LLM responses)
# Maps LLM field names (e.g., "chinese_translation") to language codes (e.g., "zh")
LLM_FIELD_TO_LANG_CODE = {
    "lithuanian_translation": "lt",
    "chinese_translation": "zh",
    "chinese_taiwan_translation": "zh-tw",
    "korean_translation": "ko",
    "french_translation": "fr",
    "spanish_translation": "es",
    "spanish_latam_translation": "es-419",
    "german_translation": "de",
    "japanese_translation": "ja",
    "latin_translation": "la",
    "sanskrit_translation": "sa",
    "ancient_greek_translation": "grc",
    "classical_arabic_translation": "ar-classical",
    "old_norse_translation": "non",
    "italian_translation": "it",
    "dutch_translation": "nl",
    "portuguese_translation": "pt",
    "portuguese_brazil_translation": "pt-br",
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
    "punjabi_translation": "pa",
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
    "bosnian_translation": "bs",
    "serbian_translation": "sr",  # Serbian (Cyrillic)
    "macedonian_translation": "mk",
    "albanian_translation": "sq",
    "montenegrin_translation": "me",
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


def get_translation_pronunciations(
    session: Session, lemma: Lemma, lang_code: str
) -> Tuple[Optional[str], Optional[str]]:
    """Get lemma/base-form pronunciation for a translation in the specified language."""
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if use_translation_table:
        translation_obj = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.lemma_id == lemma.id,
                LemmaTranslation.language_code == field_name,
            )
            .first()
        )
        if not translation_obj:
            return None, None
        return translation_obj.ipa_pronunciation, translation_obj.phonetic_pronunciation

    return None, None


def set_translation_pronunciations(
    session: Session,
    lemma: Lemma,
    lang_code: str,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Set lemma/base-form pronunciation data for a translation."""
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if not use_translation_table:
        return None, None

    old_ipa, old_phonetic = get_translation_pronunciations(session, lemma, lang_code)
    translation_obj = (
        session.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == field_name,
        )
        .first()
    )

    if translation_obj is None:
        translation_text = get_translation(session, lemma, lang_code)
        if not translation_text:
            raise ValueError(f"Cannot set pronunciation for {lang_code} without translation")
        translation_obj = LemmaTranslation(
            lemma_id=lemma.id,
            language_code=field_name,
            translation=translation_text,
            ipa_pronunciation=ipa_pronunciation,
            phonetic_pronunciation=phonetic_pronunciation,
            verified=False,
        )
        session.add(translation_obj)
    else:
        if ipa_pronunciation is not None:
            translation_obj.ipa_pronunciation = ipa_pronunciation
        if phonetic_pronunciation is not None:
            translation_obj.phonetic_pronunciation = phonetic_pronunciation

    return old_ipa, old_phonetic


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


def has_sort_key(lang_code: str) -> bool:
    """Return True if translations in *lang_code* get a computed sort key.

    Dialects answer for the language their sort key is inherited from, so
    ``zh-tw`` is True (it sorts by pinyin) while ``en-gb`` is False.
    """
    return get_sort_key_language(lang_code) in _SORT_KEY_LANGUAGES


def compute_sort_key(lang_code: str, translation: str) -> Optional[str]:
    """Compute a sort key for dictionary ordering.

    - Chinese (zh): pinyin with tone digits, e.g. "chi1" for 吃.  Digits rather
      than tone marks, so that a byte-ordered comparison sorts alphabetically
      by syllable first and only then by tone.
    - Japanese (ja): hiragana reading, e.g. "たべる" for 食べる
    - Korean (ko): decomposed jamo
    - Accented Latin languages (lt, es, de, sv, pt, fr, vi): character
      remapping so that accented letters sort in their correct alphabet
      position (e.g. Lithuanian "š" → "s{", sorting after "s" and before "t").

    Dialects reuse their parent's algorithm (zh-tw sorts by pinyin like zh,
    es-419 by the Spanish letter remapping), so ``sort_key_lang`` from the
    dialect registry decides which branch runs.

    Returns None for unsupported languages or if the required library is
    unavailable.
    """
    if not has_sort_key(lang_code):
        return None

    if not translation or not translation.strip():
        return None

    lang_code = get_sort_key_language(lang_code)

    try:
        if lang_code == "zh":
            from langtools.zh.pinyin_helper import generate_pinyin_sort_key

            return generate_pinyin_sort_key(translation)
        elif lang_code == "ja":
            from langtools.ja.romaji_helper import generate_hiragana

            return generate_hiragana(translation)
        elif lang_code == "ko":
            from langtools.ko.hangul_helper import decompose_hangul

            return decompose_hangul(translation)
        elif lang_code in _COLLATION_SORT_KEY_LANGUAGES:
            from langtools.collation import generate_sort_key

            return generate_sort_key(lang_code, translation)
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

    Presentation dialects are invalidated alongside the language they read.
    Audio recorded for es-mx speaks es-419's text in a Mexican accent, so it is
    stored under language_code "es-mx" but goes stale the moment the es-419
    word changes -- filtering on the changed code alone would leave it behind,
    still claiming an expected_text nothing says any more.

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

    affected_languages = [normalize_language_code(lang_code)]
    affected_languages.extend(get_dialects_reading(lang_code))

    audio_records = (
        session.query(AudioQualityReview)
        .filter(
            AudioQualityReview.guid == guid,
            AudioQualityReview.language_code.in_(affected_languages),
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
    translation_status: Optional[str] = None,
    translation_status_note: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Set translation for a lemma in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'es', 'fr', 'zh')
        translation: Translation string to set
        definition: Optional definition text in this language
        translation_status: Optional status marker for the translation
        translation_status_note: Optional human-readable note for the status

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
            if translation_status is not None:
                translation_obj.translation_status = translation_status
            if translation_status_note is not None:
                translation_obj.translation_status_note = translation_status_note
            if has_sort_key(lang_code):
                translation_obj.sort_key = sort_key
        else:
            translation_obj = LemmaTranslation(
                lemma_id=lemma.id,
                language_code=field_name,
                translation=translation,
                definition_text=definition,
                translation_status=translation_status,
                translation_status_note=translation_status_note,
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


def get_translation_disambiguation(session: Session, lemma: Lemma, lang_code: str) -> Optional[str]:
    """Get disambiguation for a lemma's translation in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'lt', 'fr', 'zh')

    Returns:
        Disambiguation string if set, None otherwise
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if not use_translation_table:
        # English uses Lemma.disambiguation (concept-level)
        return None

    translation_obj = (
        session.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == field_name,
        )
        .first()
    )
    return translation_obj.disambiguation if translation_obj else None


def set_translation_disambiguation(
    session: Session,
    lemma: Lemma,
    lang_code: str,
    disambiguation: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Set disambiguation for a lemma's translation in the specified language.

    Args:
        session: Database session
        lemma: Lemma object
        lang_code: Language code (e.g., 'lt', 'fr', 'zh')
        disambiguation: Disambiguation string to set, or None to clear

    Returns:
        Tuple of (old_disambiguation, new_disambiguation)

    Raises:
        ValueError: If lang_code is not supported or translation doesn't exist
    """
    if lang_code not in LANGUAGE_FIELDS:
        raise ValueError(f"Unsupported language code: {lang_code}")

    field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]

    if not use_translation_table:
        raise ValueError(
            "Cannot set translation disambiguation for English (use Lemma.disambiguation)"
        )

    translation_obj = (
        session.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == field_name,
        )
        .first()
    )

    if translation_obj is None:
        raise ValueError(f"Cannot set disambiguation for {lang_code} without a translation")

    old_disambiguation = translation_obj.disambiguation
    # Normalize empty string to None
    translation_obj.disambiguation = disambiguation if disambiguation else None

    return old_disambiguation, disambiguation


def get_all_translation_disambiguations(session: Session, lemma: Lemma) -> Dict[str, Optional[str]]:
    """Get all translation disambiguations for a lemma.

    Args:
        session: Database session
        lemma: Lemma object

    Returns:
        Dictionary mapping language codes to disambiguation strings.
    """
    translation_rows = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma.id).all()
    )

    disambiguations: Dict[str, Optional[str]] = {}
    for lang_code in LANGUAGE_FIELDS.keys():
        disambiguations[lang_code] = None

    for row in translation_rows:
        disambiguations[row.language_code] = row.disambiguation

    return disambiguations


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


def has_translation_clause(lang_code: str, translation: Optional[str] = None) -> Any:
    """
    Build a SQLAlchemy filter clause for lemmas that have a translation.

    Use in a query against Lemma, e.g.::

        session.query(Lemma).filter(has_translation_clause("lt"))
        session.query(Lemma).filter(~has_translation_clause("lt"))  # missing it

    Args:
        lang_code: Language code (e.g., 'lt', 'zh')
        translation: If given, match only this exact translation text

    Returns:
        An EXISTS clause correlated to Lemma
    """
    from sqlalchemy import select

    conditions = [
        LemmaTranslation.lemma_id == Lemma.id,
        LemmaTranslation.language_code == lang_code,
    ]
    if translation is None:
        conditions.append(LemmaTranslation.translation != "")
    else:
        conditions.append(LemmaTranslation.translation == translation)

    return select(LemmaTranslation.id).where(*conditions).exists()


def get_language_code(language_name: str) -> Optional[str]:
    """
    Get the language code for a display name. Inverse of get_language_name.

    Args:
        language_name: Display name, case-insensitive (e.g., 'Spanish', 'chinese')

    Returns:
        Language code (e.g., 'es', 'zh'), or None if the name is not recognized
    """
    return LANGUAGE_NAME_TO_CODE.get(language_name.lower())


def get_supported_languages() -> Dict[str, str]:
    """
    Get all supported language codes and their display names.

    Returns:
        Dictionary mapping language codes to display names.
        Example: {'es': 'Spanish', 'fr': 'French', ...}
    """
    return {code: name for code, (_, name, _) in LANGUAGE_FIELDS.items()}


def get_tier_1_and_tier_2_languages() -> List[str]:
    """Return the Tier-1 + Tier-2 language codes in order."""
    return TIER_1_LANGUAGES + TIER_2_LANGUAGES


# Languages generated by default for new content and shown un-expanded on the
# lemma page: English plus Tier 1 + Tier 2, plus the experimental languages that
# are nonetheless first-class for our purposes (ja/ko/sw) and Taiwan Chinese.
# This is the single source of truth for both the translation-generation default
# (Voras) and the lemma-page default-shown set; everything outside it is treated
# as secondary and hidden behind a toggle until requested.
DEFAULT_GENERATION_LANGUAGES = [
    "en",
    *TIER_1_LANGUAGES,
    *TIER_2_LANGUAGES,
    "ja",
    "ko",
    "sw",
    *get_translation_target_dialects(),
]


def get_default_generation_languages() -> List[str]:
    """Return the default set of languages to generate/show, in order."""
    return list(DEFAULT_GENERATION_LANGUAGES)


def normalize_llm_language_codes(
    languages: Optional[List[str]],
    *,
    operation_name: str,
    all_expansion: Optional[List[str]] = None,
    max_languages: Optional[int] = MAX_LLM_LANGUAGES_PER_OPERATION,
) -> List[str]:
    """Normalize language codes for LLM operations.

    - Canonicalizes dialect spellings, so ``pt-BR``/``zh_TW``/``es-US`` from a
      CLI arrive as ``pt-br``/``zh-tw``/``es-419``.
    - Expands ``all`` to ``all_expansion`` when provided.
    - De-duplicates while preserving order.
    - Enforces an upper bound for a single LLM operation.  Pass
      ``max_languages=None`` when the caller splits the result into
      per-request batches itself (see :func:`split_llm_language_batches`);
      otherwise the cap silently drops the tail of the requested set.
    """
    if not languages:
        normalized = []
    else:
        normalized = list(languages)

    if "all" in normalized:
        if all_expansion is None:
            raise ValueError(f"{operation_name} does not support 'all' languages")
        normalized = [lang for lang in normalized if lang != "all"]
        normalized = all_expansion + normalized

    seen: set[str] = set()
    deduped: List[str] = []
    for lang in normalized:
        canonical = normalize_language_code(lang)
        if canonical and canonical not in seen:
            seen.add(canonical)
            deduped.append(canonical)

    if max_languages is not None and len(deduped) > max_languages:
        logger.warning(
            "%s requested %s languages; limiting to first %s",
            operation_name,
            len(deduped),
            max_languages,
        )
        deduped = deduped[:max_languages]

    return deduped


def split_llm_language_batches(languages: List[str]) -> List[List[str]]:
    """Split normalized language codes into LLM-sized batches.

    Preserves the caller's order and caps every batch at
    ``MAX_LLM_LANGUAGES_PER_OPERATION``.

    IDEA (not implemented): instead of a plain chunk-by-N split, we could group
    languages by tier/family before batching (e.g. keep TIER_1_LANGUAGES,
    TIER_2_LANGUAGES, ANCIENT_LANGUAGE_GROUP, and the additional-Asian languages
    each within their own request). Same-family languages share orthography and
    cognates, so co-locating them in one prompt may give the model more useful
    context. This isn't strictly necessary, so we keep the simple split for now.
    """
    if not languages:
        return []
    return [
        languages[index : index + MAX_LLM_LANGUAGES_PER_OPERATION]
        for index in range(0, len(languages), MAX_LLM_LANGUAGES_PER_OPERATION)
    ]


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


#: Canonical ``translation_status`` values. The API validator, the LLM response
#: schema and the term-age scorer all read this, so add a new status here and
#: nowhere else.
TRANSLATION_STATUS_VALUES = {
    "conventional",
    "late_construction",
    "modern_loan",
    "descriptive",
    "modern_reimagining",
    "uncertain",
}

#: The ``translation_status`` a translation is assumed to have when a record
#: says nothing. Every ordinary word in a living language is a conventional
#: rendering, so recording that says nothing a reader did not already assume.
DEFAULT_TRANSLATION_STATUS = "conventional"


def translation_status_is_informative(
    language_code: str,
    status: Optional[str],
    note: Optional[str] = None,
) -> bool:
    """Whether a ``translation_status`` is worth storing and releasing.

    The status field was designed for the ancient languages, where *how* a
    concept is rendered is itself the evidence :mod:`words.term_age` reads:
    Latin ``conventional`` means the Romans had a word for the thing, and
    ``modern_loan`` means they did not. For a living target language that
    contrast does not exist - "Europa" being the established Spanish exonym is
    the unremarkable default - so a bare ``conventional`` there is noise that
    bloats every release record without telling a reader anything.

    Informative, and therefore kept:

    * any status on an :data:`ANCIENT_LANGUAGE_GROUP` language,
      ``conventional`` included, because that group is scored on the contrast;
    * any status other than ``conventional`` in any language, since those mark
      a word that genuinely is unusual (a loan, a coinage, a descriptive
      phrase);
    * a ``conventional`` carrying an explanatory note, which someone wrote on
      purpose.

    Args:
        language_code: The translation's language code.
        status: The status value, or None when unset.
        note: The accompanying ``translation_status_note``, if any.

    Returns:
        True when the status should be persisted and emitted, False when it is
        the assumed default and should be dropped.
    """
    if not status:
        return False
    if status != DEFAULT_TRANSLATION_STATUS:
        return True
    if note:
        return True
    # The ancient group has no dialects, so a direct membership test is exact.
    return normalize_language_code(language_code) in ANCIENT_LANGUAGE_GROUP


def _extract_llm_translation_text(value: Any) -> str:
    """Extract translation text from either legacy string or object response values."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        translation = value.get("translation")
        return translation if isinstance(translation, str) else ""
    return ""


def convert_llm_response_to_lang_codes(llm_response: Dict[str, Any]) -> Dict[str, str]:
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
        LLM_FIELD_TO_LANG_CODE[field_name]: _extract_llm_translation_text(value)
        for field_name, value in llm_response.items()
        if field_name in LLM_FIELD_TO_LANG_CODE
    }


def convert_llm_response_to_translation_metadata(
    llm_response: Dict[str, Any],
) -> Dict[str, Dict[str, Optional[str]]]:
    """Convert LLM response object metadata to language-code keyed metadata.

    A status the reader would have assumed anyway is dropped here rather than
    stored - see :func:`translation_status_is_informative`. The models answer
    ``conventional`` for nearly every living-language word, and keeping those
    would put a metadata block on nearly every record.
    """
    metadata: Dict[str, Dict[str, Optional[str]]] = {}
    for field_name, value in llm_response.items():
        lang_code = LLM_FIELD_TO_LANG_CODE.get(field_name)
        if lang_code is None or not isinstance(value, dict):
            continue
        status_value = value.get("translation_status")
        note_value = value.get("translation_status_note")
        if status_value is not None and not isinstance(status_value, str):
            status_value = None
        if note_value is not None and not isinstance(note_value, str):
            note_value = None
        if status_value and status_value not in TRANSLATION_STATUS_VALUES:
            status_value = "uncertain"
        if not translation_status_is_informative(lang_code, status_value, note_value):
            status_value = None
            note_value = None
        if status_value or note_value:
            metadata[lang_code] = {
                "translation_status": status_value,
                "translation_status_note": note_value,
            }
    return metadata


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
