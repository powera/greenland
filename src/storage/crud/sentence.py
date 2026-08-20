"""CRUD operations for Sentence model."""

from typing import Dict, List, Optional, Tuple, cast

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from storage.crud.operation_log import (
    SENTENCE_CREATE,
    SENTENCE_DELETE,
    SENTENCE_MERGE,
    SENTENCE_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.models.guid_prefixes import SENTENCE_GUID_PREFIX
from storage.models.schema import (
    ConversationSentence,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.utils.guid import next_sequence_number


def next_sentence_guid(session: Session) -> str:
    """Return the next available sentence GUID (S_NNNNN).

    Queries the maximum existing sentence GUID and increments the numeric
    portion.  If no sentences exist yet, starts at S_00001.

    Retired GUIDs recorded in ``guid_tombstones`` count as taken, so a number
    that once shipped in ``data/release`` is never handed to a new sentence
    even after its row is deleted.
    """
    max_guid: Optional[str] = session.query(func.max(Sentence.guid)).scalar()
    seq = next_sequence_number(session, SENTENCE_GUID_PREFIX, [max_guid] if max_guid else [])
    return f"{SENTENCE_GUID_PREFIX}_{seq:05d}"


def add_sentence(
    session: Session,
    pattern_type: Optional[str] = None,
    tense: Optional[str] = None,
    source_filename: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> Sentence:
    """Create a new sentence.

    Args:
        session: Database session
        pattern_type: Sentence pattern (e.g., "SVO", "SVAO")
        tense: Verb tense (e.g., "past", "present", "future")
        source_filename: Source file identifier (e.g., "sentence_a1_1")
        verified: Whether this sentence has been verified
        notes: Optional notes about the sentence
        source: Who is creating this, for the operation log. None skips logging.

    Returns:
        Created Sentence object
    """
    sentence = Sentence(
        guid=next_sentence_guid(session),
        pattern_type=pattern_type,
        tense=tense,
        source_filename=source_filename,
        verified=verified,
        notes=notes,
        minimum_level=None,  # Will be calculated later
    )
    session.add(sentence)
    session.flush()

    if source is not None:
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_CREATE,
            entity_guid=sentence.guid,
            fact={
                "pattern_type": pattern_type,
                "tense": tense,
                "source_filename": source_filename,
                "verified": verified,
            },
        )

    return sentence


def get_sentence_by_id(
    session: Session,
    sentence_id: int,
    include_translations: bool = True,
    include_words: bool = True,
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

    result: Optional[Sentence] = query.filter(Sentence.id == sentence_id).first()
    return result


def get_sentences_by_level(
    session: Session, max_level: int, language_code: Optional[str] = None
) -> List[Sentence]:
    """Retrieve sentences up to a certain difficulty level.

    Args:
        session: Database session
        max_level: Maximum difficulty level (inclusive)
        language_code: Optional language code to filter translations

    Returns:
        List of Sentence objects
    """
    query = (
        session.query(Sentence)
        .filter(Sentence.minimum_level.isnot(None), Sentence.minimum_level <= max_level)
        .options(joinedload(Sentence.translations), joinedload(Sentence.words))
    )

    sentences: list[Sentence] = query.all()

    # Filter by language if specified
    if language_code:
        sentences = [
            s for s in sentences if any(t.language_code == language_code for t in s.translations)
        ]

    return sentences


def calculate_minimum_level(session: Session, sentence: Sentence) -> Optional[int]:
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
    words_with_lemmas = (
        session.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence.id, SentenceWord.lemma_id.isnot(None))
        .options(joinedload(SentenceWord.lemma))
        .all()
    )

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
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> Sentence:
    """Update a sentence's metadata.

    Args:
        session: Database session
        sentence: Sentence object to update
        pattern_type: New pattern type (optional)
        tense: New tense (optional)
        verified: New verification status (optional)
        notes: New notes (optional)
        source: Who is making the edit, for the operation log. None skips logging.

    Returns:
        Updated Sentence object
    """
    # Captured before the assignments below, so the log records what actually
    # changed rather than the new value twice.
    changes = [
        FieldChange("pattern_type", sentence.pattern_type, pattern_type),
        FieldChange("tense", sentence.tense, tense),
        FieldChange("verified", sentence.verified, verified),
        FieldChange("notes", sentence.notes, notes),
    ]

    if pattern_type is not None:
        sentence.pattern_type = pattern_type
    if tense is not None:
        sentence.tense = tense
    if verified is not None:
        sentence.verified = verified
    if notes is not None:
        sentence.notes = notes

    log_field_changes(
        session,
        source=source,
        operation_type=SENTENCE_UPDATE,
        entity_guid=sentence.guid,
        # A None argument means "leave this field alone", not "set it to None",
        # so it is not a change even when the stored value is not None.
        changes=[change for change in changes if change.new_value is not None],
    )

    return sentence


def delete_sentence(session: Session, sentence: Sentence, source: Optional[str] = None) -> None:
    """Delete a sentence and all its associated data.

    This will cascade delete all translations and word associations.

    Args:
        session: Database session
        sentence: Sentence object to delete
        source: Who is deleting it, for the operation log. None skips logging.
    """
    if source is not None:
        # Logged before the delete: afterwards the cascade has taken the
        # translations and words with it and there is nothing left to count.
        # The entry outlives the row, which is the point -- resolve_guid_with_history
        # is what turns its GUID back into a story.
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_DELETE,
            entity_guid=sentence.guid,
            fact={
                "pattern_type": sentence.pattern_type,
                "source_filename": sentence.source_filename,
                "translation_count": len(sentence.translations),
                "word_count": len(sentence.words),
            },
        )

    session.delete(sentence)


def find_sentence_by_text(
    session: Session, text: str, language_code: str = "en"
) -> Optional[Sentence]:
    """Find an existing sentence with the exact text in the specified language.

    Args:
        session: Database session
        text: The sentence text to search for
        language_code: Language to match (default: "en")

    Returns:
        Sentence object if found, None otherwise
    """
    translation = (
        session.query(SentenceTranslation)
        .filter(
            SentenceTranslation.language_code == language_code,
            SentenceTranslation.translation_text == text,
        )
        .first()
    )

    if translation:
        result: Optional[Sentence] = (
            session.query(Sentence)
            .options(joinedload(Sentence.translations))
            .get(translation.sentence_id)
        )
        return result

    return None


def find_duplicate_sentences(
    session: Session, language_code: str = "en"
) -> List[Tuple[str, List[Sentence]]]:
    """Find groups of sentences with identical text in the specified language.

    Args:
        session: Database session
        language_code: Language to check for duplicates (default: "en")

    Returns:
        List of tuples (text, [sentences]) for texts that have multiple sentences
    """
    # Find texts that appear in multiple sentences
    duplicate_texts = (
        session.query(SentenceTranslation.translation_text)
        .filter(SentenceTranslation.language_code == language_code)
        .group_by(SentenceTranslation.translation_text)
        .having(func.count(SentenceTranslation.sentence_id) > 1)
        .all()
    )

    results = []
    for (text,) in duplicate_texts:
        # Get all sentences with this text
        sentence_ids = (
            session.query(SentenceTranslation.sentence_id)
            .filter(
                SentenceTranslation.language_code == language_code,
                SentenceTranslation.translation_text == text,
            )
            .all()
        )
        sentence_ids = [sid for (sid,) in sentence_ids]

        sentences = (
            session.query(Sentence)
            .filter(Sentence.id.in_(sentence_ids))
            .options(joinedload(Sentence.translations))
            .all()
        )

        results.append((text, sentences))

    return results


def get_sentence_conversation_count(session: Session, sentence_id: int) -> int:
    """Get the number of conversations a sentence appears in.

    Args:
        session: Database session
        sentence_id: Sentence ID to check

    Returns:
        Number of conversations containing this sentence
    """
    result: int = (
        session.query(ConversationSentence)
        .filter(ConversationSentence.sentence_id == sentence_id)
        .count()
    )
    return result


def merge_duplicate_sentences(
    session: Session,
    keep_id: int,
    duplicate_ids: List[int],
    source: Optional[str] = None,
) -> Dict[str, int]:
    """Merge duplicate sentences into one, updating all conversation references.

    The sentence with keep_id is preserved. All ConversationSentence records
    pointing to duplicate_ids are updated to point to keep_id. Duplicate
    sentences are then deleted.

    Args:
        session: Database session
        keep_id: ID of the sentence to keep
        duplicate_ids: List of sentence IDs to merge into keep_id
        source: Who is merging, for the operation log. None skips logging.

    Returns:
        Dict with merge statistics:
        - conversations_updated: number of conversation links updated
        - sentences_deleted: number of duplicate sentences deleted
        - translations_merged: number of translations copied to kept sentence
    """
    if not duplicate_ids:
        return {"conversations_updated": 0, "sentences_deleted": 0, "translations_merged": 0}

    # Remove keep_id from duplicate_ids if accidentally included
    duplicate_ids = [did for did in duplicate_ids if did != keep_id]

    if not duplicate_ids:
        return {"conversations_updated": 0, "sentences_deleted": 0, "translations_merged": 0}

    keep_sentence = session.query(Sentence).get(keep_id)
    if not keep_sentence:
        raise ValueError(f"Sentence {keep_id} not found")

    # Get existing translation languages for keep_sentence
    keep_languages = {t.language_code for t in keep_sentence.translations}

    stats = {"conversations_updated": 0, "sentences_deleted": 0, "translations_merged": 0}
    merged_guids: List[Optional[str]] = []

    for dup_id in duplicate_ids:
        dup_sentence = (
            session.query(Sentence).options(joinedload(Sentence.translations)).get(dup_id)
        )
        if not dup_sentence:
            continue

        # Update all ConversationSentence records to point to keep_id
        updated = (
            session.query(ConversationSentence)
            .filter(ConversationSentence.sentence_id == dup_id)
            .update({ConversationSentence.sentence_id: keep_id}, synchronize_session="fetch")
        )
        stats["conversations_updated"] += updated

        # Copy any translations that keep_sentence doesn't have
        for trans in dup_sentence.translations:
            if trans.language_code not in keep_languages:
                # Create new translation for keep_sentence
                new_trans = SentenceTranslation(
                    sentence_id=keep_id,
                    language_code=trans.language_code,
                    translation_text=trans.translation_text,
                    verified=trans.verified,
                )
                session.add(new_trans)
                keep_languages.add(trans.language_code)
                stats["translations_merged"] += 1

        if source is not None:
            # One entry per duplicate, keyed to its own GUID: without it a
            # merged-away GUID has no trace of where it went.
            log_entity_operation(
                session,
                source=source,
                operation_type=SENTENCE_DELETE,
                entity_guid=dup_sentence.guid,
                fact={"merged_into": keep_sentence.guid},
            )
            merged_guids.append(dup_sentence.guid)

        # Delete the duplicate sentence (cascades to its translations, words, etc.)
        session.delete(dup_sentence)
        stats["sentences_deleted"] += 1

    # Recalculate minimum_level for kept sentence if needed
    calculate_minimum_level(session, keep_sentence)

    if source is not None:
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_MERGE,
            entity_guid=keep_sentence.guid,
            fact={"merged_guids": merged_guids, "counts": dict(stats)},
        )

    return stats
