"""Translation-related query functions."""

from typing import List, Optional, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from storage.crud.operation_log import log_translation_change
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import get_language_code, set_translation


def get_lemmas_without_translation(
    session: Session, language: str, limit: int = 100
) -> List[Lemma]:
    """
    Get lemmas that need translations for a specific language.

    Args:
        session: Database session
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        limit: Maximum number of lemmas to return

    Returns:
        List of Lemma objects without the specified translation
    """
    lang_code = get_language_code(language)
    if lang_code is None:
        raise ValueError(f"Unsupported language: {language}")

    has_translation = (
        select(LemmaTranslation.id)
        .where(
            LemmaTranslation.lemma_id == Lemma.id,
            LemmaTranslation.language_code == lang_code,
            LemmaTranslation.translation != "",
        )
        .exists()
    )

    return cast(List[Lemma], session.query(Lemma).filter(~has_translation).limit(limit).all())


def update_lemma_translation(
    session: Session,
    lemma_id: int,
    language: str,
    translation_text: str,
    source: Optional[str] = None,
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

    lang_code = get_language_code(language)
    if lang_code is None:
        return False

    # Translations live in LemmaTranslation; set_translation returns the
    # previous value so the change can still be logged.
    old_translation, _ = set_translation(session, lemma, lang_code, translation_text)

    # Log the change
    log_translation_change(
        session=session,
        source=source or f"translation-query/update_{language}",
        operation_type="translation",
        lemma_id=lemma.id,
        language_code=lang_code,
        old_translation=old_translation,
        new_translation=translation_text,
    )

    session.commit()
    return True


# Language-specific convenience functions
def get_definitions_without_korean_translations(session: Session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need Korean translations."""
    return get_lemmas_without_translation(session, "korean", limit)


def get_definitions_without_swahili_translations(session: Session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need Swahili translations."""
    return get_lemmas_without_translation(session, "swahili", limit)


def get_definitions_without_lithuanian_translations(
    session: Session, limit: int = 100
) -> List[Lemma]:
    """Get lemmas that need Lithuanian translations."""
    return get_lemmas_without_translation(session, "lithuanian", limit)


def get_definitions_without_vietnamese_translations(
    session: Session, limit: int = 100
) -> List[Lemma]:
    """Get lemmas that need Vietnamese translations."""
    return get_lemmas_without_translation(session, "vietnamese", limit)


def get_definitions_without_french_translations(session: Session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need French translations."""
    return get_lemmas_without_translation(session, "french", limit)


def get_definitions_without_chinese_translations(session: Session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need Chinese translations."""
    return get_lemmas_without_translation(session, "chinese", limit)


def update_chinese_translation(session: Session, lemma_id: int, chinese_translation: str) -> bool:
    """Update Chinese translation for a lemma."""
    return update_lemma_translation(session, lemma_id, "chinese", chinese_translation)


def update_korean_translation(session: Session, lemma_id: int, korean_translation: str) -> bool:
    """Update Korean translation for a lemma."""
    return update_lemma_translation(session, lemma_id, "korean", korean_translation)
