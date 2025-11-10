"""CRUD operations for Sentence model."""

from typing import Optional, List
from sqlalchemy.orm import Session, joinedload

from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord, Lemma


def add_sentence(
    session: Session,
    pattern_type: Optional[str] = None,
    tense: Optional[str] = None,
    source_filename: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None
) -> Sentence:
    """Create a new sentence.

    Args:
        session: Database session
        pattern_type: Sentence pattern (e.g., "SVO", "SVAO")
        tense: Verb tense (e.g., "past", "present", "future")
        source_filename: Source file identifier (e.g., "sentence_a1_1")
        verified: Whether this sentence has been verified
        notes: Optional notes about the sentence

    Returns:
        Created Sentence object
    """
    sentence = Sentence(
        pattern_type=pattern_type,
        tense=tense,
        source_filename=source_filename,
        verified=verified,
        notes=notes,
        minimum_level=None  # Will be calculated later
    )
    session.add(sentence)
    session.flush()
    return sentence


def get_sentence_by_id(
    session: Session,
    sentence_id: int,
    include_translations: bool = True,
    include_words: bool = True
) -> Optional[Sentence]:
    """Retrieve a sentence by ID with optional eager loading.

    Args:
        session: Database session
        sentence_id: Sentence ID to retrieve
        include_translations: Whether to eager load translations
        include_words: Whether to eager load words

    Returns:
        Sentence object or None if not found
    """
    query = session.query(Sentence)

    if include_translations:
        query = query.options(joinedload(Sentence.translations))
    if include_words:
        query = query.options(joinedload(Sentence.words).joinedload(SentenceWord.lemma))

    return query.filter(Sentence.id == sentence_id).first()


def get_sentences_by_level(
    session: Session,
    max_level: int,
    language_code: Optional[str] = None
) -> List[Sentence]:
    """Retrieve sentences up to a certain difficulty level.

    Args:
        session: Database session
        max_level: Maximum difficulty level (inclusive)
        language_code: Optional language code to filter translations

    Returns:
        List of Sentence objects
    """
    query = session.query(Sentence).filter(
        Sentence.minimum_level.isnot(None),
        Sentence.minimum_level <= max_level
    ).options(
        joinedload(Sentence.translations),
        joinedload(Sentence.words)
    )

    sentences = query.all()

    # Filter by language if specified
    if language_code:
        sentences = [
            s for s in sentences
            if any(t.language_code == language_code for t in s.translations)
        ]

    return sentences


def calculate_minimum_level(
    session: Session,
    sentence: Sentence
) -> Optional[int]:
    """Calculate and update the minimum difficulty level for a sentence.

    The minimum level is the maximum difficulty of all words (lemmas) used
    in the sentence. This ensures learners know all words before seeing the sentence.

    Args:
        session: Database session
        sentence: Sentence object to calculate level for

    Returns:
        Calculated minimum level, or None if no words have levels
    """
    # Get all words for this sentence that have associated lemmas
    words_with_lemmas = session.query(SentenceWord).filter(
        SentenceWord.sentence_id == sentence.id,
        SentenceWord.lemma_id.isnot(None)
    ).options(joinedload(SentenceWord.lemma)).all()

    if not words_with_lemmas:
        sentence.minimum_level = None
        return None

    # Find the maximum difficulty level among all lemmas
    max_level = None
    for word in words_with_lemmas:
        if word.lemma and word.lemma.difficulty_level is not None:
            if max_level is None or word.lemma.difficulty_level > max_level:
                max_level = word.lemma.difficulty_level

    sentence.minimum_level = max_level
    return max_level


def update_sentence(
    session: Session,
    sentence: Sentence,
    pattern_type: Optional[str] = None,
    tense: Optional[str] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None
) -> Sentence:
    """Update a sentence's metadata.

    Args:
        session: Database session
        sentence: Sentence object to update
        pattern_type: New pattern type (optional)
        tense: New tense (optional)
        verified: New verification status (optional)
        notes: New notes (optional)

    Returns:
        Updated Sentence object
    """
    if pattern_type is not None:
        sentence.pattern_type = pattern_type
    if tense is not None:
        sentence.tense = tense
    if verified is not None:
        sentence.verified = verified
    if notes is not None:
        sentence.notes = notes

    return sentence


def delete_sentence(
    session: Session,
    sentence: Sentence
) -> None:
    """Delete a sentence and all its associated data.

    This will cascade delete all translations and word associations.

    Args:
        session: Database session
        sentence: Sentence object to delete
    """
    session.delete(sentence)
