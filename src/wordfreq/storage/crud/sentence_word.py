"""CRUD operations for SentenceWord model."""

from typing import Optional, List
from sqlalchemy.orm import Session, joinedload

from wordfreq.storage.models.schema import Sentence, SentenceWord, Lemma


def add_sentence_word(
    session: Session,
    sentence: Sentence,
    position: int,
    word_role: str,
    language_code: str,
    lemma: Optional[Lemma] = None,
    english_text: Optional[str] = None,
    target_language_text: Optional[str] = None,
    grammatical_form: Optional[str] = None,
    grammatical_case: Optional[str] = None,
    declined_form: Optional[str] = None,
) -> SentenceWord:
    """Add a word usage record to a sentence.

    Args:
        session: Database session
        sentence: Sentence object
        position: Position in the sentence (0-indexed)
        word_role: Semantic role (e.g., "subject", "verb", "object", "pronoun")
        language_code: Language code (e.g., 'lt', 'fr', 'zh')
        lemma: Optional Lemma object this word refers to
        english_text: English form of the word
        target_language_text: Base form in target language
        grammatical_form: Grammatical form (e.g., "1s_past", "gerund")
        grammatical_case: Grammatical case (e.g., "accusative", "nominative")
        declined_form: Actual declined/conjugated form used in sentence

    Returns:
        Created SentenceWord object
    """
    sentence_word = SentenceWord(
        sentence_id=sentence.id,
        lemma_id=lemma.id if lemma else None,
        position=position,
        word_role=word_role,
        language_code=language_code,
        english_text=english_text,
        target_language_text=target_language_text,
        grammatical_form=grammatical_form,
        grammatical_case=grammatical_case,
        declined_form=declined_form,
    )
    session.add(sentence_word)
    session.flush()
    return sentence_word


def get_sentence_words(
    session: Session, sentence_id: int, include_lemmas: bool = True
) -> List[SentenceWord]:
    """Get all words for a sentence, ordered by position.

    Args:
        session: Database session
        sentence_id: ID of the sentence
        include_lemmas: Whether to eager load associated lemmas

    Returns:
        List of SentenceWord objects ordered by position
    """
    query = session.query(SentenceWord).filter(SentenceWord.sentence_id == sentence_id)

    if include_lemmas:
        query = query.options(joinedload(SentenceWord.lemma))

    return query.order_by(SentenceWord.position).all()


def get_lemmas_for_sentence(session: Session, sentence_id: int) -> List[Lemma]:
    """Get all lemmas (vocabulary words) used in a sentence.

    Args:
        session: Database session
        sentence_id: ID of the sentence

    Returns:
        List of Lemma objects (excludes words without lemma_id)
    """
    sentence_words = (
        session.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence_id, SentenceWord.lemma_id.isnot(None))
        .options(joinedload(SentenceWord.lemma))
        .all()
    )

    return [sw.lemma for sw in sentence_words if sw.lemma]


def update_sentence_word(
    session: Session,
    sentence_word: SentenceWord,
    word_role: Optional[str] = None,
    lemma: Optional[Lemma] = None,
    english_text: Optional[str] = None,
    target_language_text: Optional[str] = None,
    grammatical_form: Optional[str] = None,
    grammatical_case: Optional[str] = None,
    declined_form: Optional[str] = None,
) -> SentenceWord:
    """Update a sentence word record.

    Args:
        session: Database session
        sentence_word: SentenceWord object to update
        word_role: New word role (optional)
        lemma: New lemma association (optional)
        english_text: New English text (optional)
        target_language_text: New target language text (optional)
        grammatical_form: New grammatical form (optional)
        grammatical_case: New grammatical case (optional)
        declined_form: New declined form (optional)

    Returns:
        Updated SentenceWord object
    """
    if word_role is not None:
        sentence_word.word_role = word_role
    if lemma is not None:
        sentence_word.lemma_id = lemma.id
    if english_text is not None:
        sentence_word.english_text = english_text
    if target_language_text is not None:
        sentence_word.target_language_text = target_language_text
    if grammatical_form is not None:
        sentence_word.grammatical_form = grammatical_form
    if grammatical_case is not None:
        sentence_word.grammatical_case = grammatical_case
    if declined_form is not None:
        sentence_word.declined_form = declined_form

    return sentence_word


def delete_sentence_word(session: Session, sentence_word: SentenceWord) -> None:
    """Delete a sentence word record.

    Args:
        session: Database session
        sentence_word: SentenceWord object to delete
    """
    session.delete(sentence_word)


def find_lemma_by_guid(session: Session, guid: str) -> Optional[Lemma]:
    """Find a lemma by its GUID.

    Helper function for linking sentence words to lemmas during import.

    Args:
        session: Database session
        guid: GUID to search for (e.g., "N07_008")

    Returns:
        Lemma object or None if not found
    """
    return session.query(Lemma).filter(Lemma.guid == guid).first()
