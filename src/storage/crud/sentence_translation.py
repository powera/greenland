"""CRUD operations for SentenceTranslation model."""

from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.crud.operation_log import (
    SENTENCE_TRANSLATION_CREATE,
    SENTENCE_TRANSLATION_DELETE,
    SENTENCE_TRANSLATION_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.crud.uncertain_llm_result import (
    LLMQuestion,
    clear_uncertain_llm_result,
    confidence_gated,
)
from storage.models.schema import Sentence, SentenceTranslation
from storage.models.uncertain_llm_result import TOPIC_TRANSLATION


def add_sentence_translation(
    session: Session,
    sentence: Sentence,
    language_code: str,
    translation_text: str,
    verified: bool = False,
    source: Optional[str] = None,
) -> SentenceTranslation:
    """Add a translation to a sentence.

    Args:
        session: Database session
        sentence: Sentence object to add translation to
        language_code: ISO 639-1 language code (e.g., "en", "lt", "zh")
        translation_text: The translated sentence text
        verified: Whether this translation has been verified
        source: Who is adding it, for the operation log. None skips logging.

    Returns:
        Created SentenceTranslation object

    Raises:
        IntegrityError: If a translation for this language already exists
    """
    translation = SentenceTranslation(
        sentence_id=sentence.id,
        language_code=language_code,
        translation_text=translation_text,
        verified=verified,
    )
    session.add(translation)
    session.flush()
    # A stored translation, however written, answers the question.
    clear_uncertain_llm_result(session, TOPIC_TRANSLATION, language_code, sentence_id=sentence.id)

    if source is not None:
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_TRANSLATION_CREATE,
            entity_guid=sentence.guid,
            fact={
                "language_code": language_code,
                "new_value": translation_text,
                "verified": verified,
            },
        )

    return translation


def get_sentence_translation(
    session: Session, sentence_id: int, language_code: str
) -> Optional[SentenceTranslation]:
    """Get a specific translation for a sentence.

    Args:
        session: Database session
        sentence_id: ID of the sentence
        language_code: Language code to retrieve

    Returns:
        SentenceTranslation object or None if not found
    """
    result: Optional[SentenceTranslation] = (
        session.query(SentenceTranslation)
        .filter(
            SentenceTranslation.sentence_id == sentence_id,
            SentenceTranslation.language_code == language_code,
        )
        .first()
    )
    return result


def update_sentence_translation(
    session: Session,
    translation: SentenceTranslation,
    translation_text: Optional[str] = None,
    verified: Optional[bool] = None,
    source: Optional[str] = None,
) -> SentenceTranslation:
    """Update a sentence translation.

    Args:
        session: Database session
        translation: SentenceTranslation object to update
        translation_text: New translation text (optional)
        verified: New verification status (optional)
        source: Who is making the edit, for the operation log. None skips logging.

    Returns:
        Updated SentenceTranslation object
    """
    # Captured before the assignments below.
    changes = [
        FieldChange("translation_text", translation.translation_text, translation_text),
        FieldChange("verified", translation.verified, verified),
    ]

    if translation_text is not None:
        translation.translation_text = translation_text
        clear_uncertain_llm_result(
            session,
            TOPIC_TRANSLATION,
            translation.language_code,
            sentence_id=translation.sentence_id,
        )
    if verified is not None:
        translation.verified = verified

    log_field_changes(
        session,
        source=source,
        operation_type=SENTENCE_TRANSLATION_UPDATE,
        entity_guid=translation.sentence.guid,
        # A None argument means "leave this field alone", not "set it to None".
        changes=[change for change in changes if change.new_value is not None],
        extra={"language_code": translation.language_code},
    )

    return translation


def delete_sentence_translation(
    session: Session, translation: SentenceTranslation, source: Optional[str] = None
) -> None:
    """Delete a sentence translation.

    Args:
        session: Database session
        translation: SentenceTranslation object to delete
        source: Who is deleting it, for the operation log. None skips logging.
    """
    if source is not None:
        # Logged before the delete, while the text is still readable.
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_TRANSLATION_DELETE,
            entity_guid=translation.sentence.guid,
            fact={
                "language_code": translation.language_code,
                "old_value": translation.translation_text,
            },
        )

    session.delete(translation)


def get_or_create_sentence_translation(
    session: Session,
    sentence: Sentence,
    language_code: str,
    translation_text: str,
    verified: bool = False,
    source: Optional[str] = None,
) -> tuple[SentenceTranslation, bool]:
    """Get an existing translation or create a new one.

    Args:
        session: Database session
        sentence: Sentence object
        language_code: ISO 639-1 language code
        translation_text: The translated sentence text
        verified: Whether this translation has been verified
        source: Who is creating it, for the operation log. None skips logging.
            Only the create branch logs; returning an existing row is not an edit.

    Returns:
        Tuple of (SentenceTranslation object, created: bool)
        created is True if a new translation was created, False if existing was found
    """
    existing = get_sentence_translation(session, sentence.id, language_code)

    if existing:
        return existing, False

    translation = add_sentence_translation(
        session, sentence, language_code, translation_text, verified, source=source
    )
    return translation, True


@confidence_gated(
    question=lambda a: LLMQuestion(
        TOPIC_TRANSLATION, a["language_code"], sentence_id=a["sentence_id"]
    ),
    value="translation_text",
)
def set_sentence_translation(
    session: Session,
    sentence_id: int,
    language_code: str,
    translation_text: str,
    *,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[SentenceTranslation]:
    """Create or replace one sentence's translation in ``language_code``.

    The writer for a model's sentence translations.  ``confidence``,
    ``min_confidence`` and ``model`` are for an answer rated per language; see
    storage.crud.uncertain_llm_result.confidence_gated.  One below
    min_confidence is recorded as uncertain and not written, so an existing
    translation stays as it is.  Does not log; the caller logs the batch of
    languages it wrote.

    Returns:
        The translation row, or None for an answer below min_confidence.
    """
    existing = get_sentence_translation(session, sentence_id, language_code)
    if existing is not None:
        existing.translation_text = translation_text
        return existing
    translation = SentenceTranslation(
        sentence_id=sentence_id,
        language_code=language_code,
        translation_text=translation_text,
        verified=False,
    )
    session.add(translation)
    return translation


def uncertain_sentence_languages(
    session: Session, sentence_id: int, language_codes: Iterable[str]
) -> List[str]:
    """The languages among ``language_codes`` a model was uncertain of for this sentence."""
    return [
        language_code
        for language_code in language_codes
        if set_sentence_translation.is_uncertain(
            session, sentence_id=sentence_id, language_code=language_code
        )
    ]
