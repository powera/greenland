"""CRUD operations for idioms and their language equivalents."""

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from storage.models.guid_prefixes import IDIOM_GUID_PREFIX
from storage.models.idiom import (
    IDIOM_EQUIVALENCE_KINDS,
    Idiom,
    IdiomEquivalent,
)
from storage.translation_helpers import get_supported_languages


def _required_text(value: str, field_name: str) -> str:
    normalized_value = " ".join(value.split())
    if not normalized_value:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized_value


def _validate_language_code(language_code: str) -> str:
    normalized_code = language_code.strip().lower()
    if normalized_code not in get_supported_languages():
        raise ValueError(f"Unsupported language code: {language_code!r}")
    return normalized_code


def _validate_equivalence_kind(equivalence_kind: str) -> str:
    if equivalence_kind not in IDIOM_EQUIVALENCE_KINDS:
        raise ValueError(f"Unknown idiom equivalence kind: {equivalence_kind!r}")
    return equivalence_kind


def next_idiom_guid(session: Session) -> str:
    """Return the next GUID in the idiom namespace."""
    max_guid: Optional[str] = (
        session.query(func.max(Idiom.guid))
        .filter(Idiom.guid.like(f"{IDIOM_GUID_PREFIX}\\_%", escape="\\"))
        .scalar()
    )
    if max_guid is None:
        return f"{IDIOM_GUID_PREFIX}_001"
    sequence = int(max_guid.rsplit("_", 1)[1]) + 1
    return f"{IDIOM_GUID_PREFIX}_{sequence:03d}"


def create_idiom(
    session: Session,
    *,
    source_language_code: str,
    expression: str,
    meaning: str,
    usage_note: Optional[str] = None,
    register: Optional[str] = None,
    region: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    guid: Optional[str] = None,
    source_model: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Idiom:
    """Create and flush an idiom without committing the caller's transaction."""
    idiom = Idiom(
        guid=guid or next_idiom_guid(session),
        source_language_code=_validate_language_code(source_language_code),
        expression=_required_text(expression, "expression"),
        meaning=_required_text(meaning, "meaning"),
        usage_note=usage_note,
        register=register,
        region=region,
        difficulty_level=difficulty_level,
        source_model=source_model,
        confidence=confidence,
        verified=verified,
        notes=notes,
    )
    session.add(idiom)
    session.flush()
    return idiom


def get_idiom_by_id(session: Session, idiom_id: int) -> Optional[Idiom]:
    """Return an idiom with its equivalents, or None."""
    result: Optional[Idiom] = (
        session.query(Idiom)
        .options(joinedload(Idiom.equivalents))
        .filter(Idiom.id == idiom_id)
        .first()
    )
    return result


def get_idiom_by_guid(session: Session, guid: str) -> Optional[Idiom]:
    """Return an idiom by release GUID, or None."""
    result: Optional[Idiom] = (
        session.query(Idiom)
        .options(joinedload(Idiom.equivalents))
        .filter(Idiom.guid == guid)
        .first()
    )
    return result


def list_idioms(
    session: Session,
    source_language_code: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Tuple[List[Idiom], int]:
    """Return a page of idioms and the total matching count.

    Ordered by GUID then id so unGUIDed drafts sort last but stay stable. The
    total is computed before pagination so callers can render page counts.
    """
    query = session.query(Idiom)
    if source_language_code:
        query = query.filter(Idiom.source_language_code == source_language_code)

    total = query.count()

    # selectinload rather than joinedload: a joined collection multiplies parent
    # rows, so LIMIT would cut mid-idiom and return fewer than a full page.
    query = query.options(selectinload(Idiom.equivalents)).order_by(Idiom.guid, Idiom.id)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    return query.all(), total


def list_idiom_source_languages(session: Session) -> List[str]:
    """Return the distinct source languages that have at least one idiom."""
    rows = session.query(Idiom.source_language_code).distinct().all()
    return sorted(row[0] for row in rows if row[0])


def add_idiom_equivalent(
    session: Session,
    idiom: Idiom,
    *,
    language_code: str,
    expression: str,
    equivalence_kind: str,
    literal_gloss: Optional[str] = None,
    usage_note: Optional[str] = None,
    register: Optional[str] = None,
    region: Optional[str] = None,
    source_model: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
) -> IdiomEquivalent:
    """Add and flush one equivalent without imposing one-row-per-language."""
    equivalent = IdiomEquivalent(
        idiom_id=idiom.id,
        language_code=_validate_language_code(language_code),
        expression=_required_text(expression, "equivalent expression"),
        equivalence_kind=_validate_equivalence_kind(equivalence_kind),
        literal_gloss=literal_gloss,
        usage_note=usage_note,
        register=register,
        region=region,
        source_model=source_model,
        confidence=confidence,
        verified=verified,
    )
    session.add(equivalent)
    session.flush()
    return equivalent


def update_idiom(
    session: Session,
    idiom: Idiom,
    *,
    expression: Optional[str] = None,
    meaning: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Idiom:
    """Update common idiom fields without committing the transaction."""
    if expression is not None:
        idiom.expression = _required_text(expression, "expression")
    if meaning is not None:
        idiom.meaning = _required_text(meaning, "meaning")
    if difficulty_level is not None:
        idiom.difficulty_level = difficulty_level
    if verified is not None:
        idiom.verified = verified
    if notes is not None:
        idiom.notes = notes
    session.flush()
    return idiom


def update_idiom_equivalent(
    session: Session,
    equivalent: IdiomEquivalent,
    *,
    expression: Optional[str] = None,
    equivalence_kind: Optional[str] = None,
    verified: Optional[bool] = None,
    usage_note: Optional[str] = None,
) -> IdiomEquivalent:
    """Update common equivalent fields without committing the transaction."""
    if expression is not None:
        equivalent.expression = _required_text(expression, "equivalent expression")
    if equivalence_kind is not None:
        equivalent.equivalence_kind = _validate_equivalence_kind(equivalence_kind)
    if verified is not None:
        equivalent.verified = verified
    if usage_note is not None:
        equivalent.usage_note = usage_note
    session.flush()
    return equivalent


def delete_idiom(session: Session, idiom: Idiom) -> None:
    """Delete an idiom; configured cascade also removes its equivalents."""
    session.delete(idiom)


def delete_idiom_equivalent(session: Session, equivalent: IdiomEquivalent) -> None:
    """Delete one language equivalent."""
    session.delete(equivalent)
