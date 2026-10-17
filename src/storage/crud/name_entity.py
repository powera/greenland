"""CRUD operations for the Name / NameTranslation models.

Lookups normalize through :func:`~storage.models.name_entity.normalize_name_text`
so "  George " and "George" resolve to the same row. Matching is
case-sensitive by design (see the model docstring): "Mark" the name and "mark"
the lemma are different entries, and losing that distinction would let a
name silently resolve to vocabulary.
"""

import logging
from typing import Any, List, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from langtools.en.inflection import build_possessive_forms
from storage.crud.operation_log import (
    NAME_CREATE,
    NAME_DELETE,
    NAME_DERIVATIVE_FORM_CREATE,
    NAME_TRANSLATION_CREATE,
    NAME_TRANSLATION_UPDATE,
    NAME_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.models.guid_prefixes import NAME_KIND_GUID_PREFIXES
from storage.models.name_entity import (
    NAME_GENDERS,
    NAME_KINDS,
    Name,
    NameDerivativeForm,
    NameTranslation,
    normalize_name_text,
)
from storage.token_forms import link_form_to_word_token

# grammatical_form values for a name's English forms. They are the proper-noun
# lemma slots (the values langtools.en.mechanical writes for "Shanghai"), so a
# name's forms and a lemma's read alike.
NAME_EN_BASE_FORM: str = "noun/en_singular"
NAME_EN_POSSESSIVE_FORM: str = "noun/en_possessive_singular"

logger = logging.getLogger(__name__)

# Sentinel for "argument not supplied" on updates of nullable fields, where
# None is a meaningful value (e.g. clearing a gender hint).
_UNSET: Any = object()


def get_name_by_id(session: Session, name_id: int) -> Optional[Name]:
    """Return a name by its internal id, or None."""
    return cast(Optional[Name], session.query(Name).filter(Name.id == name_id).first())


def find_name(session: Session, name_text: str, kind: Optional[str] = None) -> Optional[Name]:
    """Find a name by its text, optionally constrained to one kind.

    Args:
        session: Database session.
        name_text: Name as written in English; normalized before lookup.
        kind: Optional NAME_KINDS entry. When omitted, the first name with
            matching text is returned (kinds rarely collide in practice).

    Returns:
        The matching Name, or None.
    """
    normalized = normalize_name_text(name_text)
    if not normalized:
        return None
    query = session.query(Name).filter(Name.name_text == normalized)
    if kind is not None:
        query = query.filter(Name.kind == kind)
    return cast(Optional[Name], query.first())


def find_name_by_form(session: Session, text: str, language_code: str = "en") -> Optional[Name]:
    """Find a name by its text or by any of its forms ("John" or "John's").

    A superset of :func:`find_name` for callers matching a surface token from
    running text, where the possessive is as likely as the bare name. Matching
    stays case-sensitive, so "john" finds nothing.

    Args:
        session: Database session.
        text: Surface text; normalized before lookup.
        language_code: Language of the form to match.

    Returns:
        The matching Name, or None.
    """
    normalized = normalize_name_text(text)
    if not normalized:
        return None
    by_text = find_name(session, normalized)
    if by_text is not None:
        return by_text
    return cast(
        Optional[Name],
        session.query(Name)
        .join(NameDerivativeForm, NameDerivativeForm.name_id == Name.id)
        .filter(
            NameDerivativeForm.language_code == language_code,
            NameDerivativeForm.derivative_form_text == normalized,
        )
        .order_by(Name.id)
        .first(),
    )


def add_name_derivative_form(
    session: Session,
    name: Name,
    *,
    derivative_form_text: str,
    language_code: str,
    grammatical_form: str,
    is_base_form: bool = False,
    source: Optional[str] = None,
) -> NameDerivativeForm:
    """Add one form of a name, or return the existing identical row.

    Idempotent on the table's unique key. A new row is linked to its
    ``WordToken`` at once when one exists (exact case only; see
    ``storage.token_forms``).

    Args:
        session: Database session (the caller commits).
        name: The owning name (must be flushed).
        derivative_form_text: The form as written ("John's").
        language_code: Language of the form.
        grammatical_form: Slot in the DerivativeForm vocabulary.
        is_base_form: Whether this is the name's own spelling.
        source: Who is creating this, for the operation log. None skips logging.

    Returns:
        The NameDerivativeForm row.
    """
    form_text = normalize_name_text(derivative_form_text)
    if not form_text:
        raise ValueError("A name form needs non-empty text")
    existing = (
        session.query(NameDerivativeForm)
        .filter(
            NameDerivativeForm.name_id == name.id,
            NameDerivativeForm.language_code == language_code,
            NameDerivativeForm.grammatical_form == grammatical_form,
            NameDerivativeForm.derivative_form_text == form_text,
        )
        .first()
    )
    if existing is not None:
        return cast(NameDerivativeForm, existing)

    form = NameDerivativeForm(
        name_id=name.id,
        derivative_form_text=form_text,
        language_code=language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
    )
    session.add(form)
    link_form_to_word_token(session, form)
    session.flush()

    if source is not None:
        log_entity_operation(
            session,
            source=source,
            operation_type=NAME_DERIVATIVE_FORM_CREATE,
            entity_guid=name.guid,
            word_token_id=form.word_token_id,
            fact={
                "language_code": language_code,
                "form": form_text,
                "grammatical_form": grammatical_form,
                "is_base_form": is_base_form,
            },
        )
    return form


def attach_name_forms(
    session: Session, name: Name, source: Optional[str] = None
) -> List[NameDerivativeForm]:
    """Write a name's mechanically derivable English forms.

    The base form (the name's own text) and the singular possessive ("John's",
    "James's"); a name has no plural. Both are rule-built with no LLM call,
    which is why the release export withholds them and import regenerates them.
    Safe to re-run.

    Returns:
        The name's English forms, base form first.
    """
    forms = [
        add_name_derivative_form(
            session,
            name,
            derivative_form_text=name.name_text,
            language_code="en",
            grammatical_form=NAME_EN_BASE_FORM,
            is_base_form=True,
            source=source,
        )
    ]
    possessives = build_possessive_forms(name.name_text) or {}
    possessive = possessives.get("possessive_singular")
    if possessive:
        forms.append(
            add_name_derivative_form(
                session,
                name,
                derivative_form_text=possessive,
                language_code="en",
                grammatical_form=NAME_EN_POSSESSIVE_FORM,
                source=source,
            )
        )
    return forms


def list_names(
    session: Session,
    *,
    kind: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Name]:
    """List names, optionally filtered by kind and a text search."""
    query = session.query(Name)
    if kind:
        query = query.filter(Name.kind == kind)
    if search:
        query = query.filter(Name.name_text.ilike(f"%{search.strip()}%"))
    query = query.order_by(Name.name_text, Name.kind)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return cast(List[Name], query.all())


def count_names(
    session: Session, *, kind: Optional[str] = None, search: Optional[str] = None
) -> int:
    """Count names matching the same filters :func:`list_names` accepts."""
    query = session.query(Name)
    if kind:
        query = query.filter(Name.kind == kind)
    if search:
        query = query.filter(Name.name_text.ilike(f"%{search.strip()}%"))
    return cast(int, query.count())


def create_name(
    session: Session,
    *,
    name_text: str,
    kind: str,
    disambiguation: Optional[str] = None,
    gender: Optional[str] = None,
    source_model: Optional[str] = None,
    confidence: float = 0.0,
    notes: Optional[str] = None,
    verified: bool = False,
    guid: Optional[str] = None,
    source: Optional[str] = None,
) -> Name:
    """Create a name row.

    A GUID is allocated from the kind's namespace (``E01`` given names, ``E04``
    places, ...) unless one is supplied, matching
    :func:`storage.crud.idiom.create_idiom` and
    :func:`storage.crud.phrase.add_phrase`. Names used to be created GUID-less
    and numbered only at release-sync time, which left them unaddressable by
    every GUID-keyed path -- including the operation log.

    Args:
        session: Database session (the caller commits).
        name_text: Name as written in English.
        kind: One of NAME_KINDS.
        disambiguation: Optional role note ("the pharmacist").
        gender: Optional NAME_GENDERS entry.
        source_model: Model that proposed the name, when LLM-generated.
        confidence: 0-1 score from the generator.
        notes: Free-form notes.
        verified: Whether a human has confirmed the entry.
        guid: Explicit GUID; allocated from the kind's prefix when omitted.
            Importers pass the GUID from the release record so no number is
            spent on a row that is about to carry a different one.
        source: Who is creating this, for the operation log. None skips logging.

    Returns:
        The created Name (flushed, so its id is populated).

    Raises:
        ValueError: If the name text is empty, the kind is outside NAME_KINDS,
            or the gender is outside NAME_GENDERS.
    """
    normalized = normalize_name_text(name_text)
    if not normalized:
        raise ValueError("A name needs non-empty text")
    if kind not in NAME_KINDS:
        raise ValueError(f"Unknown name kind {kind!r}; expected one of {', '.join(NAME_KINDS)}")
    if gender is not None and gender not in NAME_GENDERS:
        raise ValueError(f"Unknown gender {gender!r}; expected one of {', '.join(NAME_GENDERS)}")

    name = Name(
        name_text=normalized,
        kind=kind,
        disambiguation=disambiguation or None,
        gender=gender,
        source_model=source_model,
        confidence=confidence,
        notes=notes,
        verified=verified,
        guid=guid if guid is not None else next_name_guid(session, kind),
    )
    session.add(name)
    session.flush()

    if source is not None:
        log_entity_operation(
            session,
            source=source,
            operation_type=NAME_CREATE,
            entity_guid=name.guid,
            fact={
                "name_text": normalized,
                "kind": kind,
                "gender": gender,
                "source_model": source_model,
                "verified": verified,
            },
        )

    attach_name_forms(session, name, source=source)
    return name


def get_or_create_name(
    session: Session,
    *,
    name_text: str,
    kind: str,
    gender: Optional[str] = None,
    source_model: Optional[str] = None,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> tuple[Name, bool]:
    """Return the existing name with this (text, kind), creating it when absent.

    This is the entry point the dialog generator uses: a scene's cast is
    registered once and reused by every later scene that casts the same
    character, which is what keeps ``Džordžas`` stable across dialogs.

    Args:
        source: Who is creating this, for the operation log. Passed through only
            on the create branch -- reusing an existing name is not a write
            worth an entry, and the gender backfill below is a hint, not an edit.

    Returns:
        Tuple of (name, created) where ``created`` is True when a new row was
        inserted.
    """
    existing = find_name(session, name_text, kind=kind)
    if existing is not None:
        # Fill in a gender hint learned later without overwriting a curated one.
        if gender and not existing.gender:
            existing.gender = gender
        return existing, False

    name = create_name(
        session,
        name_text=name_text,
        kind=kind,
        gender=gender,
        source_model=source_model,
        notes=notes,
        source=source,
    )
    return name, True


def update_name(
    session: Session,
    name: Name,
    *,
    kind: Any = _UNSET,
    disambiguation: Any = _UNSET,
    gender: Any = _UNSET,
    notes: Any = _UNSET,
    verified: Any = _UNSET,
    source: Optional[str] = None,
) -> Name:
    """Update the supplied fields of a name, leaving omitted ones untouched.

    Args:
        source: Who is making the edit, for the operation log. None skips logging.

    Raises:
        ValueError: If a supplied kind or gender is outside its vocabulary.
    """
    # Which fields the caller actually supplied, with their values as they
    # stand now. Unlike the other update helpers, omission is _UNSET rather
    # than None here, so a supplied None is a real edit (clearing a gender
    # hint) and must not be filtered out. The new values are read back off the
    # object after the assignments, because several are normalized on the way
    # in ("" becomes None, verified is coerced to bool) and comparing the raw
    # argument against the stored value would report edits that did not happen.
    supplied_fields = [
        field
        for field, supplied in (
            ("kind", kind),
            ("disambiguation", disambiguation),
            ("gender", gender),
            ("notes", notes),
            ("verified", verified),
        )
        if supplied is not _UNSET
    ]
    old_values = {field: getattr(name, field) for field in supplied_fields}

    if kind is not _UNSET:
        if kind not in NAME_KINDS:
            raise ValueError(f"Unknown name kind {kind!r}")
        name.kind = kind
    if disambiguation is not _UNSET:
        name.disambiguation = disambiguation or None
    if gender is not _UNSET:
        if gender is not None and gender not in NAME_GENDERS:
            raise ValueError(f"Unknown gender {gender!r}")
        name.gender = gender
    if notes is not _UNSET:
        name.notes = notes or None
    if verified is not _UNSET:
        name.verified = bool(verified)
    session.flush()

    log_field_changes(
        session,
        source=source,
        operation_type=NAME_UPDATE,
        entity_guid=name.guid,
        changes=[
            FieldChange(field, old_values[field], getattr(name, field)) for field in supplied_fields
        ],
    )

    return name


def delete_name(session: Session, name: Name, source: Optional[str] = None) -> None:
    """Delete a name and its translations.

    Args:
        source: Who is deleting it, for the operation log. None skips logging.
    """
    if source is not None:
        # Logged before the delete, while the row and its translations are
        # still there to describe. The entry outlives them, which is the point.
        log_entity_operation(
            session,
            source=source,
            operation_type=NAME_DELETE,
            entity_guid=name.guid,
            fact={
                "name_text": name.name_text,
                "kind": name.kind,
                "translation_count": len(get_name_renderings(session, name)),
            },
        )

    session.delete(name)
    session.flush()


def name_kind_guid_prefix(kind: str) -> str:
    """Return the GUID prefix for a name kind.

    Raises:
        ValueError: If the kind has no allocated prefix.
    """
    prefix = NAME_KIND_GUID_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(
            f"No GUID prefix allocated for name kind {kind!r}; "
            "add one to NAME_KIND_GUID_PREFIXES"
        )
    return prefix


def next_name_guid(session: Session, kind: str) -> str:
    """Return the next free GUID in a name kind's namespace (e.g. ``E01_004``).

    Numbering continues from ``MAX(guid)`` within the kind, matching
    :func:`storage.crud.idiom.next_idiom_guid`. Gaps in the middle of a
    namespace are therefore preserved, but deleting the *highest* name frees its
    number for reuse - the release file, not the database, is the record of
    which GUIDs have been spent.
    """
    prefix = name_kind_guid_prefix(kind)
    max_guid: Optional[str] = (
        session.query(func.max(Name.guid))
        .filter(Name.guid.like(f"{prefix}\\_%", escape="\\"))
        .scalar()
    )
    if max_guid is None:
        return f"{prefix}_001"
    return f"{prefix}_{int(max_guid.rsplit('_', 1)[1]) + 1:03d}"


def assign_name_guid(session: Session, name: Name) -> str:
    """Give a name a GUID if it has none, and return the GUID it now carries."""
    if not name.guid:
        name.guid = next_name_guid(session, name.kind)
        session.flush()
    return cast(str, name.guid)


def get_name_by_guid(session: Session, guid: str) -> Optional[Name]:
    """Return a name by its release GUID, or None."""
    return cast(Optional[Name], session.query(Name).filter(Name.guid == guid).first())


def get_name_translation(
    session: Session, name: Name, language_code: str
) -> Optional[NameTranslation]:
    """Return the rendering of a name in one language, or None."""
    return cast(
        Optional[NameTranslation],
        session.query(NameTranslation)
        .filter(
            NameTranslation.name_id == name.id,
            NameTranslation.language_code == language_code,
        )
        .first(),
    )


def set_name_translation(
    session: Session,
    name: Name,
    *,
    language_code: str,
    translation: str,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    sort_key: Optional[str] = None,
    notes: Optional[str] = None,
    verified: bool = False,
    source: Optional[str] = None,
) -> NameTranslation:
    """Create or update how a name is written in one language.

    Args:
        session: Database session (the caller commits).
        name: The name being rendered.
        language_code: Target language, e.g. "lt".
        translation: The rendering ("Džordžas").
        ipa_pronunciation: Optional IPA.
        phonetic_pronunciation: Optional simplified pronunciation.
        sort_key: Optional romanized sort key (pinyin, kana).
        notes: Optional free-text note about the rendering. Ships in the release
            record's ``translation_metadata``, so it has to be settable here or
            an imported name would differ from its own file forever.
        verified: Whether a human confirmed the rendering.
        source: Who is writing this, for the operation log. None skips logging.
            Logged against the *name's* GUID with ``language_code`` in the fact,
            since rendering rows carry no GUID of their own.

    Returns:
        The created or updated NameTranslation.

    Raises:
        ValueError: If the rendering is empty.
    """
    rendered = translation.strip()
    if not rendered:
        raise ValueError(f"Empty rendering for {name.name_text!r} in {language_code!r}")

    row = get_name_translation(session, name, language_code)
    created = row is None
    # Captured before the assignments below, on the update branch only.
    old_translation = None if row is None else row.translation
    old_verified = None if row is None else row.verified

    if row is None:
        row = NameTranslation(
            name_id=name.id,
            language_code=language_code,
            translation=rendered,
        )
        session.add(row)

    row.translation = rendered
    if ipa_pronunciation is not None:
        row.ipa_pronunciation = ipa_pronunciation
    if phonetic_pronunciation is not None:
        row.phonetic_pronunciation = phonetic_pronunciation
    if sort_key is not None:
        row.sort_key = sort_key
    if notes is not None:
        row.notes = notes
    row.verified = verified
    session.flush()

    if created:
        if source is not None:
            log_entity_operation(
                session,
                source=source,
                operation_type=NAME_TRANSLATION_CREATE,
                entity_guid=name.guid,
                fact={
                    "language_code": language_code,
                    "new_value": rendered,
                    "verified": verified,
                },
            )
    else:
        log_field_changes(
            session,
            source=source,
            operation_type=NAME_TRANSLATION_UPDATE,
            entity_guid=name.guid,
            changes=[
                FieldChange("translation", old_translation, rendered),
                FieldChange("verified", old_verified, verified),
            ],
            extra={"language_code": language_code},
        )

    return row


def get_name_renderings(session: Session, name: Name) -> dict[str, str]:
    """Return ``{language_code: rendering}`` for every language this name has."""
    rows = session.query(NameTranslation).filter(NameTranslation.name_id == name.id).all()
    return {row.language_code: row.translation for row in rows}
