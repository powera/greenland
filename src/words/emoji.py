#!/usr/bin/python3

"""Assigning a representative emoji to a lemma.

An emoji is *optional* and only assigned when it depicts the concept directly.
The bar is deliberately high, because a learner is expected to read the glyph
as the word without being told:

- **Good** - the emoji is a picture of the thing: cow for "cow", apple for
  "apple", to run for "run".
- **Borderline** - the emoji is a conventional sign for the concept rather than
  a picture of it: a crying face for "sad", a stop sign for "stop". Allowed,
  but only when nothing depicts the concept better.
- **Not allowed** - the emoji is an association, a symbol, or a rebus:
  a snowflake for "cold", a dollar sign for "money", a lightbulb for "idea".
  These read as puzzles, not as the word.

Most lemmas have no emoji, and that is the expected outcome. See
:data:`ASSIGNMENT_GUIDANCE` for the text handed to reviewers and to the LLM.

Storage
-------
:class:`~storage.models.emoji.Emoji` is the source of truth: one row per glyph,
carrying its review decision and, when assigned, its ``lemma_id``. Because the
glyph is that table's unique key, "an emoji belongs to at most one lemma" is a
database constraint rather than a check this module has to remember to run.

``Lemma.emoji`` remains as a derived JSON mirror, because it is what the
release round trip (:mod:`storage.release.lemma`) reads and writes. Every
function here that changes an assignment refreshes the mirror for the affected
lemmas, so the two never drift. Order within the mirror carries primacy: the
first entry is the primary glyph (:func:`primary_emoji`).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from storage.models.emoji import (
    EMOJI_STATUS_ASSIGNED,
    EMOJI_STATUS_MISSING_LEMMA,
    EMOJI_STATUS_NO_MATCH,
    EMOJI_STATUS_UNDECIDED,
    Emoji,
)
from storage.models.schema import Lemma
from storage.release.lemma import decode_db_emoji, encode_db_emoji, normalize_emoji_entry

# Entry types carried in an emoji list entry's "type" field.
EMOJI_TYPE_UNICODE = "unicode"
EMOJI_TYPE_IMAGE = "image"

# Guidance shared by the Barsukas review page and the LLM proposal prompt, so
# the two apply the same bar. Kept as prose because that is how it is consumed.
ASSIGNMENT_GUIDANCE = """\
Assign an emoji only when the emoji is a picture of the concept itself.

Good:    cow -> the cow emoji; apple -> the apple emoji; rain -> the rain cloud.
OK:      sad -> a crying face; stop -> a stop sign. Conventional signs are
         acceptable only when nothing depicts the concept more directly.
No:      cold -> a snowflake; money -> a dollar sign; idea -> a lightbulb.
         An association or a symbol is not a depiction.

Most words have no suitable emoji. "No emoji" is the correct, common answer -
prefer it over a stretch."""


class EmojiConflictError(ValueError):
    """An emoji is already assigned to a different lemma."""

    def __init__(self, value: str, holder: Lemma) -> None:
        holder_name = holder.guid or holder.lemma_text
        super().__init__(f"Emoji {value!r} is already assigned to {holder_name}")
        self.value = value
        self.holder = holder


def emoji_name(value: str) -> Optional[str]:
    """The Unicode name of a single-codepoint emoji, or None.

    Multi-codepoint sequences (ZWJ sequences, flags, skin-tone modifiers) have
    no single Unicode name, so this returns None for them rather than guessing.
    Callers use it for display only.
    """
    stripped = value.strip()
    if len(stripped) != 1:
        return None
    try:
        return unicodedata.name(stripped)
    except ValueError:
        return None


def normalize_emoji_input(raw: str) -> List[Dict[str, str]]:
    """Parse reviewer/agent input into a normalized emoji list.

    Accepts whitespace- or comma-separated glyphs, the form the edit form and
    the agent both produce. Order is preserved because it is meaningful, and
    duplicates within the input are dropped (keeping the first occurrence) so a
    lemma never lists the same glyph twice.
    """
    entries: List[Dict[str, str]] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        entry = normalize_emoji_entry(token)
        if entry is None or entry["value"] in seen:
            continue
        seen.add(entry["value"])
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Reading an assignment
# ---------------------------------------------------------------------------


def lemma_emoji(lemma: Lemma) -> List[Dict[str, str]]:
    """The emoji entries assigned to a lemma (empty when none).

    Reads the ``Lemma.emoji`` mirror rather than the table, so template and
    export paths do not each issue a query. The mirror is kept current by every
    writer in this module.
    """
    return decode_db_emoji(lemma.emoji)


def primary_emoji(lemma: Lemma) -> Optional[str]:
    """The single glyph representing this lemma, or None.

    This is the first entry of the list - see the module docstring on ordering.
    Consumers that can show only one emoji should call this rather than
    indexing the list themselves.
    """
    entries = lemma_emoji(lemma)
    return entries[0]["value"] if entries else None


def emoji_values(lemma: Lemma) -> List[str]:
    """Every glyph assigned to a lemma, primary first."""
    return [entry["value"] for entry in lemma_emoji(lemma)]


def emoji_rows_for_lemma(session: Session, lemma_id: int) -> List[Emoji]:
    """The assigned :class:`Emoji` rows of a lemma, in mirror order.

    The mirror carries primacy, so rows are returned in the order the mirror
    lists them; any row missing from the mirror (only possible mid-repair)
    sorts last by glyph.
    """
    rows = (
        session.query(Emoji)
        .filter(Emoji.lemma_id == lemma_id, Emoji.status == EMOJI_STATUS_ASSIGNED)
        .all()
    )
    lemma = session.get(Lemma, lemma_id)
    order = {value: index for index, value in enumerate(emoji_values(lemma))} if lemma else {}
    rows.sort(key=lambda row: (order.get(row.value, len(order)), row.value))
    return rows


# ---------------------------------------------------------------------------
# Writing an assignment
# ---------------------------------------------------------------------------


def refresh_lemma_mirror(
    session: Session, lemma: Lemma, order: Optional[Sequence[str]] = None
) -> None:
    """Rewrite ``Lemma.emoji`` from the table rows assigned to this lemma.

    ``order`` optionally states the intended glyph order (primary first); any
    assigned glyph it omits is appended. Without it the existing mirror order
    is preserved, so refreshing after an unrelated change does not silently
    promote a different glyph to primary.
    """
    assigned = {
        row.value
        for row in session.query(Emoji).filter(
            Emoji.lemma_id == lemma.id, Emoji.status == EMOJI_STATUS_ASSIGNED
        )
    }
    preferred = list(order) if order is not None else emoji_values(lemma)

    ordered = [value for value in preferred if value in assigned]
    ordered.extend(sorted(assigned - set(ordered)))

    lemma.emoji = encode_db_emoji([{"type": EMOJI_TYPE_UNICODE, "value": v} for v in ordered])


def get_or_create_emoji(session: Session, value: str) -> Emoji:
    """The :class:`Emoji` row for a glyph, creating an undecided one if absent.

    A glyph outside the seeded catalog (a ZWJ sequence a reviewer typed by
    hand) is still assignable; it simply gets a row on first use.
    """
    row = session.query(Emoji).filter(Emoji.value == value).one_or_none()
    if row is None:
        row = Emoji(
            value=value,
            unicode_name=emoji_name(value),
            status=EMOJI_STATUS_UNDECIDED,
        )
        session.add(row)
        session.flush()
    return row


def assign_emoji(
    session: Session, lemma: Lemma, entries: Sequence[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Set a lemma's emoji list, enforcing global uniqueness.

    Returns the normalized list that was stored. Passing an empty sequence
    clears the assignment, releasing each glyph back to ``undecided``. Raises
    :class:`EmojiConflictError` if any glyph is held by another lemma; nothing
    is written in that case.

    The caller commits, and is responsible for logging the change.
    """
    normalized: List[Dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        cleaned = normalize_emoji_entry(entry)
        if cleaned is None or cleaned["value"] in seen:
            continue
        seen.add(cleaned["value"])
        normalized.append(cleaned)

    wanted = [entry["value"] for entry in normalized]

    # Reject before writing anything, so a conflict leaves the lemma untouched.
    for value in wanted:
        row = session.query(Emoji).filter(Emoji.value == value).one_or_none()
        if row is not None and row.lemma_id is not None and row.lemma_id != lemma.id:
            holder = session.get(Lemma, row.lemma_id)
            if holder is not None:
                raise EmojiConflictError(value, holder)

    # Release glyphs this lemma no longer claims.
    for row in session.query(Emoji).filter(
        Emoji.lemma_id == lemma.id, Emoji.status == EMOJI_STATUS_ASSIGNED
    ):
        if row.value not in seen:
            row.lemma_id = None
            row.status = EMOJI_STATUS_UNDECIDED

    for value in wanted:
        row = get_or_create_emoji(session, value)
        row.lemma_id = lemma.id
        row.status = EMOJI_STATUS_ASSIGNED
        row.pending_import_id = None

    session.flush()
    refresh_lemma_mirror(session, lemma, order=wanted)
    return normalized


def mark_no_match(session: Session, value: str, *, notes: Optional[str] = None) -> Emoji:
    """Record that no lemma depicts this glyph, so the walk skips it hereafter.

    Clears any previous assignment, refreshing that lemma's mirror.
    """
    row = get_or_create_emoji(session, value)
    previous = session.get(Lemma, row.lemma_id) if row.lemma_id else None

    row.status = EMOJI_STATUS_NO_MATCH
    row.lemma_id = None
    row.pending_import_id = None
    if notes is not None:
        row.notes = notes

    session.flush()
    if previous is not None:
        refresh_lemma_mirror(session, previous)
    return row


def mark_missing_lemma(
    session: Session,
    value: str,
    *,
    pending_import_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Emoji:
    """Record that the glyph has one clear concept the database lacks a word for.

    ``pending_import_id`` links the staged term, so the glyph can be attached
    once that term is approved into a lemma (see
    :func:`attach_pending_emoji_to_lemma`).
    """
    row = get_or_create_emoji(session, value)
    previous = session.get(Lemma, row.lemma_id) if row.lemma_id else None

    row.status = EMOJI_STATUS_MISSING_LEMMA
    row.lemma_id = None
    row.pending_import_id = pending_import_id
    if notes is not None:
        row.notes = notes

    session.flush()
    if previous is not None:
        refresh_lemma_mirror(session, previous)
    return row


def attach_pending_emoji_to_lemma(session: Session, pending_import_id: int, lemma: Lemma) -> int:
    """Assign glyphs staged against a pending import to the lemma it became.

    Called from the pending-import approval path: a glyph parked as
    ``missing_lemma`` becomes a real assignment as soon as its word exists.
    Returns the number of glyphs attached. Any glyph that has since been taken
    by another lemma is left alone rather than stolen.
    """
    rows = (
        session.query(Emoji)
        .filter(
            Emoji.pending_import_id == pending_import_id,
            Emoji.status == EMOJI_STATUS_MISSING_LEMMA,
        )
        .all()
    )
    attached = 0
    for row in rows:
        if row.lemma_id is not None and row.lemma_id != lemma.id:
            continue
        row.lemma_id = lemma.id
        row.status = EMOJI_STATUS_ASSIGNED
        row.pending_import_id = None
        attached += 1

    if attached:
        session.flush()
        refresh_lemma_mirror(session, lemma)
    return attached


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def find_emoji_holders(
    session: Session, values: Iterable[str], *, exclude_lemma_id: Optional[int] = None
) -> Dict[str, Lemma]:
    """Map each of ``values`` already assigned to the lemma holding it.

    ``exclude_lemma_id`` skips one lemma, so re-saving a lemma's own emoji is
    not reported as a conflict with itself.
    """
    wanted = [value for value in values if value]
    if not wanted:
        return {}

    holders: Dict[str, Lemma] = {}
    rows = session.query(Emoji).filter(Emoji.value.in_(wanted), Emoji.lemma_id.isnot(None)).all()
    for row in rows:
        if exclude_lemma_id is not None and row.lemma_id == exclude_lemma_id:
            continue
        holder = session.get(Lemma, row.lemma_id)
        if holder is not None:
            holders[row.value] = holder
    return holders


@dataclass
class MirrorDrift:
    """A lemma whose ``Lemma.emoji`` mirror disagrees with the emoji table."""

    lemma: Lemma
    mirror_values: List[str]
    table_values: List[str]


def find_mirror_drift(session: Session) -> List[MirrorDrift]:
    """Lemmas whose mirror disagrees with the table, as a set.

    The writers here keep the two consistent, but a release import writes
    ``Lemma.emoji`` directly (that is the round trip's job), so drift is
    possible and is reported rather than assumed away. Order is ignored:
    the mirror alone decides primacy, so a reordering is not drift.
    """
    by_lemma: Dict[int, List[str]] = {}
    for row in session.query(Emoji).filter(Emoji.status == EMOJI_STATUS_ASSIGNED):
        if row.lemma_id is not None:
            by_lemma.setdefault(row.lemma_id, []).append(row.value)

    drift: List[MirrorDrift] = []
    lemma_ids = set(by_lemma)
    for mirrored_lemma in session.query(Lemma).filter(Lemma.emoji.isnot(None)):
        lemma_ids.add(mirrored_lemma.id)

    for lemma_id in sorted(lemma_ids):
        checked_lemma: Optional[Lemma] = session.get(Lemma, lemma_id)
        if checked_lemma is None:
            continue
        mirror = emoji_values(checked_lemma)
        table = sorted(by_lemma.get(lemma_id, []))
        if sorted(mirror) != table:
            drift.append(MirrorDrift(lemma=checked_lemma, mirror_values=mirror, table_values=table))
    return drift


def assigned_emoji_values(session: Session) -> Dict[str, Lemma]:
    """Every assigned glyph mapped to its lemma."""
    assigned: Dict[str, Lemma] = {}
    for row in session.query(Emoji).filter(Emoji.status == EMOJI_STATUS_ASSIGNED):
        if row.lemma_id is None:
            continue
        lemma = session.get(Lemma, row.lemma_id)
        if lemma is not None:
            assigned[row.value] = lemma
    return assigned


def status_counts(session: Session) -> Dict[str, int]:
    """How many glyphs sit in each review status, for the progress display."""
    counts: Dict[str, int] = {
        EMOJI_STATUS_UNDECIDED: 0,
        EMOJI_STATUS_ASSIGNED: 0,
        EMOJI_STATUS_NO_MATCH: 0,
        EMOJI_STATUS_MISSING_LEMMA: 0,
    }
    for row in session.query(Emoji):
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts
