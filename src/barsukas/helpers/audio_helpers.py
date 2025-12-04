"""Audio-specific helper functions for the Barsukas UI."""

from typing import Optional

from wordfreq.storage.models.schema import Lemma


def link_audio_to_lemma(
    session, guid: str, expected_text: str, language_code: str
) -> Optional[int]:
    """
    Hybrid approach to link audio file to lemma.

    1. Try to match by GUID
    2. Fallback to matching by text in appropriate language translation field

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text that should be spoken
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Lemma ID if found, None otherwise
    """
    # Try GUID match first
    lemma = session.query(Lemma).filter_by(guid=guid).first()
    if lemma:
        return lemma.id

    # Fallback to text matching based on language
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # For table-based translations (es, de, pt), query LemmaTranslation
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(language_code=language_code, translation=expected_text)
            .first()
        )
        if translation:
            return translation.lemma_id

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        lemma = session.query(Lemma).filter(getattr(Lemma, column_name) == expected_text).first()
        if lemma:
            return lemma.id

    return None


def validate_audio_translation(session, guid: str, expected_text: str, language_code: str) -> dict:
    """
    Validate that audio file's expected text matches the current translation in the database.

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text from audio file manifest
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Dict with validation results: {
            "valid": bool,
            "current_translation": str or None,
            "mismatch": bool,
            "lemma_found": bool
        }
    """
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # Try to find lemma by GUID
    lemma = session.query(Lemma).filter_by(guid=guid).first()

    if not lemma:
        return {
            "valid": False,
            "current_translation": None,
            "mismatch": False,
            "lemma_found": False,
        }

    # Get current translation from database
    current_translation = None

    # For table-based translations (es, de, pt)
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .first()
        )
        if translation:
            current_translation = translation.translation

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        current_translation = getattr(lemma, column_name, None)

    # Check if they match
    if current_translation is None:
        return {"valid": False, "current_translation": None, "mismatch": False, "lemma_found": True}

    mismatch = current_translation != expected_text

    return {
        "valid": not mismatch,
        "current_translation": current_translation,
        "mismatch": mismatch,
        "lemma_found": True,
    }
