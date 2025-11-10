"""CRUD operations for SentenceTranslation model."""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from wordfreq.storage.models.schema import Sentence, SentenceTranslation


def add_sentence_translation(
    session: Session,
    sentence: Sentence,
    language_code: str,
    translation_text: str,
    verified: bool = False
) -> SentenceTranslation:
    """Add a translation to a sentence.

    Args:
        session: Database session
        sentence: Sentence object to add translation to
        language_code: ISO 639-1 language code (e.g., "en", "lt", "zh")
        translation_text: The translated sentence text
        verified: Whether this translation has been verified

    Returns:
        Created SentenceTranslation object

    Raises:
        IntegrityError: If a translation for this language already exists
    """
    translation = SentenceTranslation(
        sentence_id=sentence.id,
        language_code=language_code,
        translation_text=translation_text,
        verified=verified
    )
    session.add(translation)
    session.flush()
    return translation


def get_sentence_translation(
    session: Session,
    sentence_id: int,
    language_code: str
) -> Optional[SentenceTranslation]:
    """Get a specific translation for a sentence.

    Args:
        session: Database session
        sentence_id: ID of the sentence
        language_code: Language code to retrieve

    Returns:
        SentenceTranslation object or None if not found
    """
    return session.query(SentenceTranslation).filter(
        SentenceTranslation.sentence_id == sentence_id,
        SentenceTranslation.language_code == language_code
    ).first()


def update_sentence_translation(
    session: Session,
    translation: SentenceTranslation,
    translation_text: Optional[str] = None,
    verified: Optional[bool] = None
) -> SentenceTranslation:
    """Update a sentence translation.

    Args:
        session: Database session
        translation: SentenceTranslation object to update
        translation_text: New translation text (optional)
        verified: New verification status (optional)

    Returns:
        Updated SentenceTranslation object
    """
    if translation_text is not None:
        translation.translation_text = translation_text
    if verified is not None:
        translation.verified = verified

    return translation


def delete_sentence_translation(
    session: Session,
    translation: SentenceTranslation
) -> None:
    """Delete a sentence translation.

    Args:
        session: Database session
        translation: SentenceTranslation object to delete
    """
    session.delete(translation)


def get_or_create_sentence_translation(
    session: Session,
    sentence: Sentence,
    language_code: str,
    translation_text: str,
    verified: bool = False
) -> tuple[SentenceTranslation, bool]:
    """Get an existing translation or create a new one.

    Args:
        session: Database session
        sentence: Sentence object
        language_code: ISO 639-1 language code
        translation_text: The translated sentence text
        verified: Whether this translation has been verified

    Returns:
        Tuple of (SentenceTranslation object, created: bool)
        created is True if a new translation was created, False if existing was found
    """
    existing = get_sentence_translation(session, sentence.id, language_code)

    if existing:
        return existing, False

    translation = add_sentence_translation(
        session, sentence, language_code, translation_text, verified
    )
    return translation, True
