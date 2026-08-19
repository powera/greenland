"""CRUD operations for the Phrase model.

Phrases (fixed traveler/greeting expressions like "See you later") live in
their own ``phrases`` table, mirroring how sentences live in ``sentences``.
See :mod:`storage.crud.sentence` for the analogous helpers.
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from storage.models.guid_prefixes import PHRASE_SUBTYPE_GUID_PREFIXES
from storage.models.schema import Phrase, PhraseTranslation
from storage.utils.guid import next_sequence_number


def next_phrase_guid(session: Session, phrase_subtype: str) -> str:
    """Return the next available phrase GUID for a subtype (e.g. F01_004).

    Args:
        session: Database session
        phrase_subtype: Phrase subtype (e.g. "greetings", "traveler")

    Retired GUIDs recorded in ``guid_tombstones`` count as taken, so a number
    that once shipped in ``data/release`` is never handed to a new phrase even
    after its row is deleted.

    Returns:
        Unique GUID string (e.g. "F01_004")

    Raises:
        ValueError: If the subtype has no known GUID prefix.
    """
    prefix = PHRASE_SUBTYPE_GUID_PREFIXES.get(phrase_subtype)
    if prefix is None:
        raise ValueError(f"Unknown phrase_subtype: {phrase_subtype!r}")

    max_guid: Optional[str] = (
        session.query(func.max(Phrase.guid))
        .filter(Phrase.guid.like(f"{prefix}\\_%", escape="\\"))
        .scalar()
    )
    seq = next_sequence_number(session, prefix, [max_guid] if max_guid else [])
    return f"{prefix}_{seq:03d}"


def get_phrase_by_guid(session: Session, guid: str) -> Optional[Phrase]:
    """Get a phrase by its GUID (e.g. "F01_003")."""
    result: Optional[Phrase] = session.query(Phrase).filter(Phrase.guid == guid).first()
    return result


def get_phrase_by_id(
    session: Session,
    phrase_id: int,
    include_translations: bool = True,
) -> Optional[Phrase]:
    """Retrieve a phrase by ID, optionally eager-loading its translations."""
    query = session.query(Phrase)
    if include_translations:
        query = query.options(joinedload(Phrase.translations))
    result: Optional[Phrase] = query.filter(Phrase.id == phrase_id).first()
    return result


def add_phrase(
    session: Session,
    phrase_subtype: str,
    label: str,
    definition: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    guid: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Phrase:
    """Create a new phrase.

    Args:
        session: Database session
        phrase_subtype: Phrase subtype (e.g. "greetings", "traveler")
        label: English concept label (e.g. "See you later")
        definition: Optional English definition
        difficulty_level: Trakaido level, or None
        guid: Explicit GUID; auto-generated from the subtype prefix if omitted
        verified: Whether this phrase has been verified
        notes: Optional notes

    Returns:
        Created Phrase object (flushed, so ``id`` is populated).
    """
    phrase = Phrase(
        guid=guid if guid is not None else next_phrase_guid(session, phrase_subtype),
        phrase_subtype=phrase_subtype,
        label=label,
        definition=definition,
        difficulty_level=difficulty_level,
        verified=verified,
        notes=notes,
    )
    session.add(phrase)
    session.flush()
    return phrase


def set_phrase_translation(
    session: Session,
    phrase: Phrase,
    language_code: str,
    translation: str,
    translation_status: Optional[str] = None,
    translation_status_note: Optional[str] = None,
    verified: bool = False,
) -> PhraseTranslation:
    """Create or update a phrase translation for a language.

    Returns the created or updated :class:`PhraseTranslation`.
    """
    existing: Optional[PhraseTranslation] = (
        session.query(PhraseTranslation)
        .filter(
            PhraseTranslation.phrase_id == phrase.id,
            PhraseTranslation.language_code == language_code,
        )
        .first()
    )
    if existing is not None:
        existing.translation = translation
        existing.translation_status = translation_status
        existing.translation_status_note = translation_status_note
        existing.verified = verified
        session.flush()
        return existing

    row = PhraseTranslation(
        phrase_id=phrase.id,
        language_code=language_code,
        translation=translation,
        translation_status=translation_status,
        translation_status_note=translation_status_note,
        verified=verified,
    )
    session.add(row)
    session.flush()
    return row
