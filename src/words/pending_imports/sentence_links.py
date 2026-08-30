"""The link between a sentence and the staged term it is waiting on.

A sentence whose word resolved to no lemma stages that word as a
:class:`~storage.models.imports.PendingImport` and records a
:class:`~storage.models.imports.SentencePendingImport` row pointing at it.
That row is the whole back-link: it is what lets the approval of a staged word
find the sentences that needed it, and what lets the import workflow tell
"already staged" from "not staged yet".

This replaces the older arrangement, where the back-link lived in
``SentenceWordHint.pending_import_id``. See the ``SentencePendingImport``
docstring for why that was flaky. The short version: a hint is unique on
``(sentence_id, position)`` and is written by four components that do not know
about each other, so recording a *second* fact about a slot on it either
collided or was silently dropped.

Legacy hint rows are still read here, so a database staged before the link
table existed keeps working, and are cleaned up when the pending row they
reference is deleted.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Set, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.models.imports import PendingImport, SentencePendingImport
from storage.models.schema import SentenceWord, SentenceWordHint

logger = logging.getLogger(__name__)


def link_sentence_to_pending_import(
    session: Session,
    sentence_id: int,
    pending_import_id: int,
    *,
    english_text: str,
    slot_name: Optional[str] = None,
) -> bool:
    """Record that ``sentence_id`` is waiting on ``pending_import_id``.

    Idempotent: the pair is unique, so re-running a staging pass re-uses the
    existing row rather than raising. Does not commit.

    Returns:
        True when a new link row was written.
    """
    existing = (
        session.query(SentencePendingImport)
        .filter(
            SentencePendingImport.sentence_id == sentence_id,
            SentencePendingImport.pending_import_id == pending_import_id,
        )
        .first()
    )
    if existing is not None:
        # Fill in a slot name learned on a later pass, but never blank one out.
        if slot_name and not existing.slot_name:
            existing.slot_name = slot_name
        return False

    session.add(
        SentencePendingImport(
            sentence_id=sentence_id,
            pending_import_id=pending_import_id,
            english_text=english_text.strip(),
            slot_name=(slot_name or "").strip() or None,
        )
    )
    session.flush()
    return True


def _legacy_hint_sentence_ids(session: Session, pending_import_id: int) -> Set[int]:
    """Sentences linked through the pre-link-table hint column."""
    rows = (
        session.query(SentenceWordHint.sentence_id)
        .filter(SentenceWordHint.pending_import_id == pending_import_id)
        .distinct()
        .all()
    )
    return {int(row[0]) for row in rows if row[0] is not None}


def sentence_ids_waiting_on(session: Session, pending_import_id: int) -> List[int]:
    """Sentences that staged this term and could not link it.

    Once the term becomes a lemma or a name these are the sentences worth
    re-running the import workflow for.
    """
    rows = (
        session.query(SentencePendingImport.sentence_id)
        .filter(SentencePendingImport.pending_import_id == pending_import_id)
        .distinct()
        .all()
    )
    ids = {int(row[0]) for row in rows if row[0] is not None}
    ids |= _legacy_hint_sentence_ids(session, pending_import_id)
    return sorted(ids)


def pending_import_ids_for_sentence(session: Session, sentence_id: int) -> List[int]:
    """Ids of the staged terms this sentence is waiting on that still exist.

    A link to a row that is gone is a promotion that already happened, so it is
    simply absent rather than an error.
    """
    rows = (
        session.query(SentencePendingImport.pending_import_id)
        .filter(SentencePendingImport.sentence_id == sentence_id)
        .all()
    )
    candidate_ids = {int(row[0]) for row in rows if row[0] is not None}

    legacy_rows = (
        session.query(SentenceWordHint.pending_import_id)
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .all()
    )
    candidate_ids |= {int(row[0]) for row in legacy_rows if row[0] is not None}

    if not candidate_ids:
        return []

    alive = {
        int(row[0])
        for row in session.query(PendingImport.id)
        .filter(PendingImport.id.in_(sorted(candidate_ids)))
        .all()
    }
    return sorted(alive)


def pending_imports_for_sentence(session: Session, sentence_id: int) -> List[PendingImport]:
    """The staged terms this sentence is still waiting on."""
    ids = pending_import_ids_for_sentence(session, sentence_id)
    if not ids:
        return []
    return cast(
        List[PendingImport],
        session.query(PendingImport).filter(PendingImport.id.in_(ids)).all(),
    )


def staged_texts_for_sentence(session: Session, sentence_id: int) -> Set[str]:
    """Lowercased glosses this sentence has already staged.

    Includes links to pending rows that no longer exist only through the legacy
    hint path; a live link is what stage STAGE checks against, so a term that
    was approved and deleted correctly stops counting as staged and the
    sentence moves on to LINK.
    """
    texts = {
        str(row[0]).strip().lower()
        for row in session.query(SentencePendingImport.english_text)
        .filter(SentencePendingImport.sentence_id == sentence_id)
        .all()
        if row[0]
    }
    legacy = {
        str(row[0]).strip().lower()
        for row in session.query(SentenceWordHint.english_text)
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .all()
        if row[0]
    }
    return texts | legacy


def count_links_for_sentence(session: Session, sentence_id: int) -> int:
    """How many staged terms this sentence is linked to, live rows only."""
    count = (
        session.query(func.count(SentencePendingImport.id))
        .filter(SentencePendingImport.sentence_id == sentence_id)
        .scalar()
        or 0
    )
    return int(count)


def _linked_texts(session: Session, pending_import_id: int) -> Dict[int, Set[str]]:
    """Per-sentence set of lowercased glosses linked to one pending import."""
    by_sentence: Dict[int, Set[str]] = {}
    rows = (
        session.query(SentencePendingImport)
        .filter(SentencePendingImport.pending_import_id == pending_import_id)
        .all()
    )
    for row in rows:
        text = (row.english_text or "").strip().lower()
        if text:
            by_sentence.setdefault(int(row.sentence_id), set()).add(text)
    return by_sentence


def _apply_to_sentence_words(
    session: Session,
    sentence_id: int,
    texts: Set[str],
    *,
    lemma_id: Optional[int],
    name_id: Optional[int],
) -> int:
    """Attach the resolved lemma or name to every matching word row.

    Rows that already carry a resolution are left alone: an earlier decision,
    including a human's, always wins.
    """
    if not texts or (lemma_id is None and name_id is None):
        return 0

    rows = session.query(SentenceWord).filter(SentenceWord.sentence_id == sentence_id).all()
    updated = 0
    for word in rows:
        text = (word.english_text or "").strip().lower()
        if text not in texts:
            continue
        if word.lemma_id is not None or word.name_id is not None:
            continue
        if lemma_id is not None:
            word.lemma_id = lemma_id
        else:
            word.name_id = name_id
        updated += 1
    return updated


def resolve_sentence_links(
    session: Session,
    pending_import_id: int,
    *,
    lemma_id: Optional[int] = None,
    name_id: Optional[int] = None,
) -> int:
    """Apply an approval outcome to every sentence that was waiting on it.

    Called from :func:`words.pending_imports.approval.delete_pending_import`,
    which is the single place a pending row is removed. The link rows are
    deleted with the pending row by the ORM cascade; what this does first is
    push the outcome onto the sentence data itself, so the word the sentence
    was waiting on is *linked* rather than merely un-staged.

    Doing that here rather than leaving it to a re-queued workflow run is what
    makes approval self-contained: a sentence whose only outstanding word was
    just approved needs no further pass to reach a linked state.

    Args:
        session: Database session; not committed.
        pending_import_id: The pending row being resolved.
        lemma_id: Lemma the term became, when it became one.
        name_id: Name the term became, when it became one.

    Returns:
        The number of sentence word rows updated.
    """
    updated = 0
    for sentence_id, texts in _linked_texts(session, pending_import_id).items():
        updated += _apply_to_sentence_words(
            session, sentence_id, texts, lemma_id=lemma_id, name_id=name_id
        )
    if updated:
        session.flush()
    return updated


def release_legacy_hints(
    session: Session,
    pending_import_id: int,
    *,
    lemma_id: Optional[int] = None,
    name_id: Optional[int] = None,
) -> int:
    """Detach pre-link-table hint rows before their pending row is deleted.

    New staging writes no hint at all, but a database staged before the link
    table existed still holds hints whose ``pending_import_id`` would dangle.
    A hint that can name a lemma or a name is repointed at it; one that cannot
    is removed, since ``ck_word_hint_has_reference`` forbids a row referencing
    nothing.

    Returns:
        The number of hint rows touched.
    """
    hints = (
        session.query(SentenceWordHint)
        .filter(SentenceWordHint.pending_import_id == pending_import_id)
        .all()
    )
    for hint in hints:
        hint.pending_import_id = None
        if lemma_id is not None:
            hint.lemma_id = lemma_id
        elif name_id is not None:
            hint.name_id = name_id
        elif hint.lemma_id is None and hint.name_id is None:
            session.delete(hint)
    if hints:
        session.flush()
    return len(hints)


def backfill_links_from_hints(
    session: Session, sentence_ids: Optional[Sequence[int]] = None
) -> int:
    """Create link rows for hints that still carry a ``pending_import_id``.

    The migration path for a database staged before the link table existed.
    Safe to re-run: :func:`link_sentence_to_pending_import` is idempotent.

    Returns:
        The number of link rows created.
    """
    query = session.query(SentenceWordHint).filter(SentenceWordHint.pending_import_id.isnot(None))
    if sentence_ids is not None:
        query = query.filter(SentenceWordHint.sentence_id.in_(list(sentence_ids)))

    alive = {int(row[0]) for row in session.query(PendingImport.id).all() if row[0] is not None}

    created = 0
    for hint in query.all():
        if hint.pending_import_id is None:
            continue
        pending_id = int(hint.pending_import_id)
        if pending_id not in alive:
            continue
        if link_sentence_to_pending_import(
            session,
            int(hint.sentence_id),
            pending_id,
            english_text=hint.english_text or "",
            slot_name=hint.slot_name,
        ):
            created += 1
    return created
