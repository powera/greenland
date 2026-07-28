#!/usr/bin/python3

"""Read and modify the free-form tag list on a :class:`Lemma`.

``Lemma.tags`` is a JSON array of strings (``["nuclear_family", "female"]``).
:func:`storage.crud.lemma.create_lemma` can set that array at creation time, but
nothing could add or remove a single tag afterwards -- these helpers fill that
gap and are the only supported way to mutate tags on an existing lemma.

Tags are free-form: there is no controlled vocabulary, so an unrecognized tag is
stored as-is rather than rejected.  They are normalized (stripped, lowercased,
deduplicated, sorted) so that ``Legal`` and ``legal`` cannot both accumulate on
one lemma and so a tag query does not have to account for casing.

Removal is a hard delete -- the tag is gone from the array, not flagged.  Every
mutation is written to the operation log with both the old and the new array, so
the removal remains auditable even though the tag itself does not survive.
"""

import json
import logging
from typing import Any, List, Optional, Sequence

from sqlalchemy.orm import Session

from storage.crud.operation_log import log_operation
from storage.models.imports import PendingImport
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)

#: ``operation_type`` recorded for every tag mutation.
TAG_OPERATION_TYPE = "lemma_tags"


def normalize_tag(tag: str) -> str:
    """Return the canonical form of a single tag (stripped and lowercased)."""
    return tag.strip().lower()


def normalize_tags(tags: Sequence[str]) -> List[str]:
    """Normalize, drop empties, deduplicate, and sort ``tags``."""
    normalized = {normalize_tag(tag) for tag in tags}
    normalized.discard("")
    return sorted(normalized)


def decode_tags(raw: Optional[str], context: str = "row") -> List[str]:
    """Decode a stored tags column into a normalized list.

    NULL and the empty array both yield ``[]``.  A value that is not valid JSON
    is treated as a single legacy tag rather than raising: the barsukas edit form
    stored the raw input string for a period, so such values may exist in older
    databases and must remain readable.
    """
    if not raw:
        return []

    try:
        parsed: Any = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("%s has non-JSON tags %r; treating it as a single tag", context, raw)
        return normalize_tags([str(raw)])

    if isinstance(parsed, str):
        return normalize_tags([parsed])
    if isinstance(parsed, list):
        return normalize_tags([str(item) for item in parsed])

    logger.warning("%s has unexpected tags JSON %r; treating it as a single tag", context, raw)
    return normalize_tags([str(parsed)])


def read_tags(lemma: Lemma) -> List[str]:
    """Return ``lemma``'s tags as a normalized list."""
    return decode_tags(lemma.tags, context=f"Lemma {lemma.id}")


def read_pending_import_tags(pending_import: PendingImport) -> List[str]:
    """Return a staged import's tags as a normalized list.

    ``PendingImport.tags`` holds the tags to apply to the lemma the import
    eventually becomes; the column has the same JSON-array shape as
    ``Lemma.tags``.
    """
    return decode_tags(pending_import.tags, context=f"PendingImport {pending_import.id}")


def _serialize_tags(tags: Sequence[str]) -> Optional[str]:
    """Encode ``tags`` for storage, collapsing the empty list to NULL.

    ``create_lemma`` leaves the column NULL when given no tags; keeping that
    representation means "no tags" has one encoding rather than two.
    """
    if not tags:
        return None
    return json.dumps(list(tags), ensure_ascii=False)


def serialize_tags_for_column(tags: Sequence[str]) -> Optional[str]:
    """Public wrapper over the storage encoding, for callers that assign directly.

    The barsukas lemma edit form applies its own change log over every field it
    touches, so it sets ``Lemma.tags`` itself rather than going through
    :func:`set_tags`; it still needs the canonical encoding.
    """
    return _serialize_tags(normalize_tags(tags))


def parse_tags_input(raw: str) -> List[str]:
    """Parse a human-entered tag string into a normalized tag list.

    Accepts either a JSON array (``["legal", "archaic"]``) or a plain
    comma-separated list (``legal, archaic``).  Raises :class:`ValueError` for
    input that parses as JSON but is not an array of scalars, so a typo such as
    ``{"legal": true}`` is reported rather than silently stored.
    """
    text = raw.strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed: Any = json.loads(text)
        except ValueError as error:
            raise ValueError(f"not valid JSON ({error})") from error
        if not isinstance(parsed, list):
            raise ValueError("JSON tags must be an array")
        for item in parsed:
            if isinstance(item, (dict, list)):
                raise ValueError("JSON tags must be an array of strings")
        return normalize_tags([str(item) for item in parsed])

    if text.startswith("{"):
        raise ValueError("JSON tags must be an array, not an object")

    return normalize_tags(text.split(","))


def _log_tag_change(
    session: Session,
    lemma: Lemma,
    source: str,
    old_tags: List[str],
    new_tags: List[str],
) -> None:
    """Record a tag mutation, including the tags added and removed."""
    added = [tag for tag in new_tags if tag not in old_tags]
    removed = [tag for tag in old_tags if tag not in new_tags]

    # log_operation() drops None values from the fact JSON, so the arrays are
    # always passed as lists -- an empty list survives that filter and is what
    # records a lemma's last tag being removed.
    log_operation(
        session,
        operation_type=TAG_OPERATION_TYPE,
        source=source,
        entity_type="lemma",
        lemma_id=lemma.id,
        details={
            "old_tags": old_tags,
            "new_tags": new_tags,
            "added_tags": added,
            "removed_tags": removed,
        },
    )


def set_tags(
    session: Session,
    lemma: Lemma,
    tags: Sequence[str],
    source: str = "barsukas-web-interface",
) -> List[str]:
    """Replace ``lemma``'s tags with ``tags`` and return the stored list."""
    old_tags = read_tags(lemma)
    new_tags = normalize_tags(tags)

    if new_tags == old_tags:
        return old_tags

    lemma.tags = _serialize_tags(new_tags)
    _log_tag_change(session, lemma, source, old_tags, new_tags)
    return new_tags


def add_tags(
    session: Session,
    lemma: Lemma,
    tags: Sequence[str],
    source: str = "barsukas-web-interface",
) -> List[str]:
    """Add ``tags`` to ``lemma``, keeping any tags already present.

    Returns the full tag list after the addition.  Adding a tag the lemma already
    carries is a no-op and is not logged.
    """
    old_tags = read_tags(lemma)
    return set_tags(session, lemma, old_tags + list(tags), source=source)


def remove_tags(
    session: Session,
    lemma: Lemma,
    tags: Sequence[str],
    source: str = "barsukas-web-interface",
) -> List[str]:
    """Hard-delete ``tags`` from ``lemma`` and return the remaining list.

    Removing a tag the lemma does not carry is a no-op and is not logged.
    """
    old_tags = read_tags(lemma)
    doomed = set(normalize_tags(tags))
    return set_tags(session, lemma, [tag for tag in old_tags if tag not in doomed], source=source)
