#!/usr/bin/python3

"""CRUD operations for OperationLog model.

Prefer :func:`log_entity_operation`, :func:`log_field_changes` and
:func:`log_batch_operation` in new code. They identify the entity by GUID rather
than by an integer id, and they take a ``source`` that may be ``None`` -- which
means "the caller did not ask for logging" -- so a CRUD function can call them
unconditionally and keep the opt-in check in one place.

:func:`log_operation` and :func:`log_translation_change` predate that and are
kept for the many existing call sites. Do not reach for
``log_translation_change`` to record a non-translation edit by passing
``field_name`` / ``old_value`` / ``new_value`` through ``**extra_data``; that is
what :func:`log_field_changes` is for.

Naming conventions for new entries:

``operation_type``
    ``{entity}_{verb}``, with the verb one of ``create``, ``update``,
    ``delete``, ``merge``, ``link``, ``promote``, ``import`` -- for example
    ``sentence_create`` or ``sentence_translation_update``.
``source``
    ``{component}/{action}``, e.g. ``sentence-crud/add``.
``fact`` keys
    ``field``, ``old_value``, ``new_value``, ``changes``, ``changed_fields``,
    ``language_code``, ``position``, ``summary``, ``count``, ``counts``.

Operation types written before this convention existed (``translation``,
``synonym_scan``, ``derivative_forms_generated``, ``lemma_tags``,
``mechanical_forms_generated``) are grandfathered: renaming them would orphan
the rows already in the table and, for ``synonym_scan``, break the state reads
in :mod:`words.synonym_coverage`.
"""

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import and_
from sqlalchemy.orm import Session

from storage.models.operation_log import OperationLog

# Fact keys with a fixed meaning across every operation type.
FACT_KEY_ENTITY_KIND = "entity_kind"
FACT_KEY_FIELD = "field"
FACT_KEY_OLD = "old_value"
FACT_KEY_NEW = "new_value"
FACT_KEY_CHANGES = "changes"
FACT_KEY_CHANGED_FIELDS = "changed_fields"
FACT_KEY_COUNT = "count"

# Operation types for the sentence element family.
SENTENCE_CREATE = "sentence_create"
SENTENCE_UPDATE = "sentence_update"
SENTENCE_DELETE = "sentence_delete"
SENTENCE_MERGE = "sentence_merge"
SENTENCE_IMPORT = "sentence_import"
SENTENCE_LINK = "sentence_link"
SENTENCE_TRANSLATION_CREATE = "sentence_translation_create"
SENTENCE_TRANSLATION_UPDATE = "sentence_translation_update"
SENTENCE_TRANSLATION_DELETE = "sentence_translation_delete"
SENTENCE_WORD_CREATE = "sentence_word_create"
SENTENCE_WORD_UPDATE = "sentence_word_update"
SENTENCE_WORD_DELETE = "sentence_word_delete"

# Operation types for the phrase family. ``phrase_update`` predates this module
# and is deliberately reused rather than renamed, as with ``idiom_update``.
PHRASE_CREATE = "phrase_create"
PHRASE_UPDATE = "phrase_update"
PHRASE_DELETE = "phrase_delete"
PHRASE_TRANSLATION_CREATE = "phrase_translation_create"
PHRASE_TRANSLATION_UPDATE = "phrase_translation_update"

# Operation types for the idiom family. ``idiom_update`` predates this module
# and is deliberately reused rather than renamed: the rows already written under
# that name are idiom field edits, which is exactly what it still means.
IDIOM_CREATE = "idiom_create"
IDIOM_UPDATE = "idiom_update"
IDIOM_DELETE = "idiom_delete"
IDIOM_EQUIVALENT_CREATE = "idiom_equivalent_create"
IDIOM_EQUIVALENT_UPDATE = "idiom_equivalent_update"
IDIOM_EQUIVALENT_DELETE = "idiom_equivalent_delete"

# Operation types for the variant and derivative-form families. Neither row
# carries a GUID of its own, so both log against the owning *lemma's* GUID with
# the form's identity in the fact -- the same shape phrase and name
# translations use. A variant is identified within its lemma by
# (variant_kind, variant_key, grammatical_form), a derivative form by
# (language_code, grammatical_form).
VARIANT_CREATE = "variant_create"
VARIANT_UPDATE = "variant_update"
VARIANT_DELETE = "variant_delete"
DERIVATIVE_FORM_CREATE = "derivative_form_create"
DERIVATIVE_FORM_UPDATE = "derivative_form_update"
DERIVATIVE_FORM_DELETE = "derivative_form_delete"

# Operation types for GUID retirement. The entity here is the retired GUID
# itself rather than a row that owns it -- a tombstone exists precisely because
# the thing that held the GUID is gone.
GUID_TOMBSTONE = "guid_tombstone"
GUID_TOMBSTONE_UPDATE = "guid_tombstone_update"

# Operation types for the name family.
NAME_CREATE = "name_create"
NAME_UPDATE = "name_update"
NAME_DELETE = "name_delete"
NAME_TRANSLATION_CREATE = "name_translation_create"
NAME_TRANSLATION_UPDATE = "name_translation_update"


@dataclass(frozen=True)
class FieldChange:
    """One scalar field edit, for :func:`log_field_changes`."""

    field: str
    old_value: Any
    new_value: Any

    @property
    def changed(self) -> bool:
        """Whether this is an actual edit rather than a write of the same value."""
        return bool(self.old_value != self.new_value)

    def to_fact(self) -> dict:
        """Render as the ``changes`` entry stored in the fact JSON."""
        return {
            FACT_KEY_FIELD: self.field,
            FACT_KEY_OLD: self.old_value,
            FACT_KEY_NEW: self.new_value,
        }


def _write_log(
    session: Session,
    *,
    source: str,
    operation_type: str,
    entity_guid: Optional[str],
    fact_data: dict,
    lemma_id: Optional[int] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
) -> OperationLog:
    """Add and flush one entry. Shared tail of the GUID-keyed helpers."""
    if entity_guid:
        # Imported here, not at module scope: storage.guid_router imports
        # storage.crud.lemma, which imports this module. Cheap either way --
        # guid_kind is pure string classification and touches no table.
        from storage.guid_router import guid_kind

        fact_data[FACT_KEY_ENTITY_KIND] = guid_kind(entity_guid)

    # Drop None values to keep the JSON compact. An empty list survives this
    # and is what records "the last value was removed".
    fact_data = {k: v for k, v in fact_data.items() if v is not None}

    log_entry = OperationLog(
        source=source,
        operation_type=operation_type,
        fact=json.dumps(fact_data),
        entity_guid=entity_guid,
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id,
    )

    session.add(log_entry)
    session.flush()
    return log_entry


def log_entity_operation(
    session: Session,
    *,
    source: str,
    operation_type: str,
    entity_guid: Optional[str] = None,
    fact: Optional[Mapping[str, Any]] = None,
    lemma_id: Optional[int] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
) -> OperationLog:
    """Record one operation against one GUID-identified entity.

    The GUID is the entity reference; ``lemma_id`` and friends remain available
    for the integer-keyed queries that predate GUIDs, notably the SERNAS
    synonym-scan state reads in :mod:`words.synonym_coverage`.

    Flushes but does not commit: the entry belongs to the same transaction as
    the write it describes, so a rolled-back write cannot leave a log claiming
    it happened.

    Args:
        session: Database session.
        source: Who performed the operation, as ``{component}/{action}``.
        operation_type: What happened, as ``{entity}_{verb}``.
        entity_guid: GUID of the entity operated on.
        fact: Structured details. Copied, not mutated; ``None`` values dropped.
        lemma_id: Legacy integer reference, when one applies.
        word_token_id: Legacy integer reference, when one applies.
        derivative_form_id: Legacy integer reference, when one applies.

    Returns:
        The OperationLog that was created.
    """
    return _write_log(
        session,
        source=source,
        operation_type=operation_type,
        entity_guid=entity_guid,
        fact_data=dict(fact or {}),
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id,
    )


def log_field_changes(
    session: Session,
    *,
    source: Optional[str],
    operation_type: str,
    entity_guid: Optional[str],
    changes: Sequence[FieldChange],
    extra: Optional[Mapping[str, Any]] = None,
    lemma_id: Optional[int] = None,
) -> Optional[OperationLog]:
    """Record a set of scalar field edits, or nothing at all.

    ``source is None`` means the caller did not ask for logging, so every CRUD
    function can call this unconditionally rather than repeating an ``if
    source:`` guard. Fields whose value did not actually change are dropped, and
    when none remain nothing is written -- a no-op update leaves no entry
    claiming an edit occurred.

    Args:
        session: Database session.
        source: Who performed the edit, or None to skip logging entirely.
        operation_type: What happened, as ``{entity}_update``.
        entity_guid: GUID of the entity that was edited.
        changes: The candidate field edits.
        extra: Additional fact keys, e.g. ``{"language_code": "lt"}``.
        lemma_id: Legacy integer reference, when one applies.

    Returns:
        The OperationLog that was created, or None when nothing was logged.
    """
    if source is None:
        return None

    changed = [change for change in changes if change.changed]
    if not changed:
        return None

    fact_data = dict(extra or {})
    fact_data[FACT_KEY_CHANGES] = [change.to_fact() for change in changed]
    fact_data[FACT_KEY_CHANGED_FIELDS] = [change.field for change in changed]

    return _write_log(
        session,
        source=source,
        operation_type=operation_type,
        entity_guid=entity_guid,
        fact_data=fact_data,
        lemma_id=lemma_id,
    )


def log_batch_operation(
    session: Session,
    *,
    source: Optional[str],
    operation_type: str,
    entity_guid: Optional[str],
    count: int,
    fact: Optional[Mapping[str, Any]] = None,
    lemma_id: Optional[int] = None,
) -> Optional[OperationLog]:
    """Record one entry for a write that touched ``count`` rows.

    For high-volume child rows -- sentence words run 5-15 per language per
    sentence -- one entry per row would swamp the table and tell you nothing the
    batch entry does not. No-ops when ``source`` is None or the batch was empty.

    Args:
        session: Database session.
        source: Who performed the write, or None to skip logging entirely.
        operation_type: What happened, as ``{entity}_{verb}``.
        entity_guid: GUID of the parent entity the rows belong to.
        count: How many rows were written.
        fact: Additional details, e.g. ``{"language_code": "lt"}``.
        lemma_id: Legacy integer reference, when one applies.

    Returns:
        The OperationLog that was created, or None when nothing was logged.
    """
    if source is None or count == 0:
        return None

    fact_data = dict(fact or {})
    fact_data[FACT_KEY_COUNT] = count

    return _write_log(
        session,
        source=source,
        operation_type=operation_type,
        entity_guid=entity_guid,
        fact_data=fact_data,
        lemma_id=lemma_id,
    )


def log_operation(
    session: Session,
    operation_type: str,
    source: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
    fact: Optional[dict] = None,
    lemma_id: Optional[int] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
    entity_guid: Optional[str] = None,
    **extra_data: Any,
) -> OperationLog:
    """
    Log a general operation to the operation log.

    This is a flexible logging function that can handle various operation types.

    Prefer :func:`log_entity_operation` in new code: it identifies the entity by
    GUID instead of aliasing ``entity_id`` into ``lemma_id``, which is why
    conversation entries written through here show up under unrelated lemmas.

    Args:
        session: Database session
        operation_type: Type of operation (e.g., "grammar_fact_generated", "definition_update")
        source: Source of the operation (e.g., "lape-agent", "barsukas-web-interface")
        entity_type: Type of entity being operated on (e.g., "grammar_fact", "lemma")
        entity_id: ID of the entity being operated on
        details: Dictionary of operation details (alternative to fact)
        fact: Dictionary of fact data (alternative to details)
        lemma_id: ID of the lemma being modified
        word_token_id: Optional word token ID
        derivative_form_id: Optional derivative form ID
        entity_guid: GUID of the entity being operated on
        **extra_data: Additional data to include in the fact JSON

    Returns:
        OperationLog object that was created
    """
    # Determine source - if not provided, try to infer from details/fact
    if source is None:
        if details and "source" in details:
            source = details["source"]
        elif fact and isinstance(fact, dict) and "source" in fact:
            source = fact["source"]
        else:
            source = "unknown"

    # Build the fact JSON - use whichever was provided (details or fact).
    # Copied, because the keys added below would otherwise land in the caller's
    # own dict.
    fact_data = dict(details or fact or {})

    # Add entity type if provided
    if entity_type:
        fact_data["entity_type"] = entity_type

    # Add entity_id if provided and not already in lemma_id
    if entity_id and not lemma_id:
        lemma_id = entity_id

    # Add any extra data provided
    fact_data.update(extra_data)

    # Remove None values to keep JSON compact
    fact_data = {k: v for k, v in fact_data.items() if v is not None}

    # Create operation log entry
    log_entry = OperationLog(
        source=source,
        operation_type=operation_type,
        fact=json.dumps(fact_data),
        entity_guid=entity_guid,
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id,
    )

    session.add(log_entry)
    session.flush()
    return log_entry


def log_translation_change(
    session: Session,
    source: str,
    operation_type: str,
    lemma_id: Optional[int] = None,
    language_code: Optional[str] = None,
    old_translation: Optional[str] = None,
    new_translation: Optional[str] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
    entity_guid: Optional[str] = None,
    **extra_data: Any,
) -> OperationLog:
    """
    Log a translation change operation.

    This records a *translation* changing. To record any other kind of field
    edit, use :func:`log_field_changes` rather than passing ``field_name`` /
    ``old_value`` / ``new_value`` through ``**extra_data``: doing that is how
    the same concept ended up spelled three different ways across the table.

    Args:
        session: Database session
        source: Source of the operation (e.g., "voras-agent", "gpt-5.4-mini", "manual-import")
        operation_type: Type of operation (e.g., "translation", "definition", "import")
        lemma_id: ID of the lemma being modified
        language_code: Language code of the translation (e.g., "fr", "es", "de")
        old_translation: Previous translation value (None for new translations)
        new_translation: New translation value (None for deletions)
        word_token_id: Optional word token ID
        derivative_form_id: Optional derivative form ID
        entity_guid: GUID of the entity being operated on
        **extra_data: Additional data to include in the fact JSON

    Returns:
        OperationLog object that was created
    """
    # Build the fact JSON
    fact_data = {
        "language_code": language_code,
        "old_translation": old_translation,
        "new_translation": new_translation,
    }

    # Add any extra data provided
    fact_data.update(extra_data)

    # Remove None values to keep JSON compact
    fact_data = {k: v for k, v in fact_data.items() if v is not None}

    # Create operation log entry
    log_entry = OperationLog(
        source=source,
        operation_type=operation_type,
        fact=json.dumps(fact_data),
        entity_guid=entity_guid,
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id,
    )

    session.add(log_entry)
    session.flush()
    return log_entry


def has_synonym_scan_record(session: Session, lemma_id: int, language_code: str) -> bool:
    """Return True when ŠERNAS has already scanned this lemma/language pair."""
    source = f"sernas-agent:{language_code}"
    return (
        session.query(OperationLog.id)
        .filter(
            and_(
                OperationLog.operation_type == "synonym_scan",
                OperationLog.source == source,
                OperationLog.lemma_id == lemma_id,
            )
        )
        .first()
        is not None
    )


def delete_synonym_scan_records(session: Session, lemma_id: int, language_code: str) -> int:
    """Delete ŠERNAS synonym scan records for a lemma/language pair."""
    source = f"sernas-agent:{language_code}"
    deleted = (
        session.query(OperationLog)
        .filter(
            and_(
                OperationLog.operation_type == "synonym_scan",
                OperationLog.source == source,
                OperationLog.lemma_id == lemma_id,
            )
        )
        .delete(synchronize_session=False)
    )
    return int(deleted)
