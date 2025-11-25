"""Translation-related query functions."""

from typing import List

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.operation_log import log_translation_change


def get_lemmas_without_translation(session, language: str, limit: int = 100) -> List[Lemma]:
    """
    Get lemmas that need translations for a specific language.

    Args:
        session: Database session
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        limit: Maximum number of lemmas to return

    Returns:
        List of Lemma objects without the specified translation
    """
    language = language.lower()
    column_map = {
        "chinese": Lemma.chinese_translation,
        "french": Lemma.french_translation,
        "korean": Lemma.korean_translation,
        "swahili": Lemma.swahili_translation,
        "lithuanian": Lemma.lithuanian_translation,
        "vietnamese": Lemma.vietnamese_translation
    }

    if language not in column_map:
        raise ValueError(f"Unsupported language: {language}. Supported languages: {', '.join(column_map.keys())}")

    return session.query(Lemma).filter(
        column_map[language].is_(None)
    ).limit(limit).all()


def update_lemma_translation(
    session,
    lemma_id: int,
    language: str,
    translation_text: str,
    source: str = None
) -> bool:
    """Update translation for a specific language in a lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma to update
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        translation_text: New translation text
        source: Source of the update (for operation logging)
    """
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if not lemma:
        return False

    language = language.lower()

    # Map language names to field names and language codes
    language_map = {
        "chinese": ("chinese_translation", "zh"),
        "french": ("french_translation", "fr"),
        "korean": ("korean_translation", "ko"),
        "swahili": ("swahili_translation", "sw"),
        "lithuanian": ("lithuanian_translation", "lt"),
        "vietnamese": ("vietnamese_translation", "vi")
    }

    if language not in language_map:
        return False

    field_name, lang_code = language_map[language]

    # Get old value for logging
    old_translation = getattr(lemma, field_name, None)

    # Update the translation
    setattr(lemma, field_name, translation_text)

    # Log the change
    log_translation_change(
        session=session,
        source=source or f"translation-query/update_{language}",
        operation_type="translation",
        lemma_id=lemma.id,
        language_code=lang_code,
        old_translation=old_translation,
        new_translation=translation_text
    )

    session.commit()
    return True


# Language-specific convenience functions
def get_definitions_without_korean_translations(session, limit: int = 100):
    """Get lemmas that need Korean translations."""
    return get_lemmas_without_translation(session, "korean", limit)


def get_definitions_without_swahili_translations(session, limit: int = 100):
    """Get lemmas that need Swahili translations."""
    return get_lemmas_without_translation(session, "swahili", limit)


def get_definitions_without_lithuanian_translations(session, limit: int = 100):
    """Get lemmas that need Lithuanian translations."""
    return get_lemmas_without_translation(session, "lithuanian", limit)


def get_definitions_without_vietnamese_translations(session, limit: int = 100):
    """Get lemmas that need Vietnamese translations."""
    return get_lemmas_without_translation(session, "vietnamese", limit)


def get_definitions_without_french_translations(session, limit: int = 100):
    """Get lemmas that need French translations."""
    return get_lemmas_without_translation(session, "french", limit)


def get_definitions_without_chinese_translations(session, limit: int = 100):
    """Get lemmas that need Chinese translations."""
    return get_lemmas_without_translation(session, "chinese", limit)


def update_chinese_translation(session, lemma_id: int, chinese_translation: str):
    """Update Chinese translation for a lemma."""
    return update_lemma_translation(session, lemma_id, "chinese", chinese_translation)


def update_korean_translation(session, lemma_id: int, korean_translation: str):
    """Update Korean translation for a lemma."""
    return update_lemma_translation(session, lemma_id, "korean", korean_translation)
