"""Translation-related query functions."""

from typing import List

from wordfreq.storage.models.schema import Lemma


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
        'chinese': Lemma.chinese_translation,
        'french': Lemma.french_translation,
        'korean': Lemma.korean_translation,
        'swahili': Lemma.swahili_translation,
        'lithuanian': Lemma.lithuanian_translation,
        'vietnamese': Lemma.vietnamese_translation
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
    translation_text: str
) -> bool:
    """Update translation for a specific language in a lemma."""
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if not lemma:
        return False

    language = language.lower()
    if language == 'chinese':
        lemma.chinese_translation = translation_text
    elif language == 'french':
        lemma.french_translation = translation_text
    elif language == 'korean':
        lemma.korean_translation = translation_text
    elif language == 'swahili':
        lemma.swahili_translation = translation_text
    elif language == 'lithuanian':
        lemma.lithuanian_translation = translation_text
    elif language == 'vietnamese':
        lemma.vietnamese_translation = translation_text
    else:
        return False

    session.commit()
    return True


# Language-specific convenience functions
def get_definitions_without_korean_translations(session, limit: int = 100):
    """Get lemmas that need Korean translations."""
    return get_lemmas_without_translation(session, 'korean', limit)


def get_definitions_without_swahili_translations(session, limit: int = 100):
    """Get lemmas that need Swahili translations."""
    return get_lemmas_without_translation(session, 'swahili', limit)


def get_definitions_without_lithuanian_translations(session, limit: int = 100):
    """Get lemmas that need Lithuanian translations."""
    return get_lemmas_without_translation(session, 'lithuanian', limit)


def get_definitions_without_vietnamese_translations(session, limit: int = 100):
    """Get lemmas that need Vietnamese translations."""
    return get_lemmas_without_translation(session, 'vietnamese', limit)


def get_definitions_without_french_translations(session, limit: int = 100):
    """Get lemmas that need French translations."""
    return get_lemmas_without_translation(session, 'french', limit)


def get_definitions_without_chinese_translations(session, limit: int = 100):
    """Get lemmas that need Chinese translations."""
    return get_lemmas_without_translation(session, 'chinese', limit)


def update_chinese_translation(session, lemma_id: int, chinese_translation: str):
    """Update Chinese translation for a lemma."""
    return update_lemma_translation(session, lemma_id, 'chinese', chinese_translation)


def update_korean_translation(session, lemma_id: int, korean_translation: str):
    """Update Korean translation for a lemma."""
    return update_lemma_translation(session, lemma_id, 'korean', korean_translation)
