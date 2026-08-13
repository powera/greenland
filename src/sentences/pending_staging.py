"""Stage a sentence's unresolved words for later promotion to lemmas.

When linking cannot find a lemma for a word, the word is staged: a
``PendingImport`` row is created for a human (or, with the switch on, the
workflow) to approve into a real lemma. This is the dedup half of what
``agents.genys`` did inline, lifted out so it can run per sentence from any
caller.

It also does the thing genys never did: write a ``SentenceWordHint`` carrying
the new ``pending_import_id``. Without that back-link a staged word has no
route home -- nothing can tell which sentence was waiting on it, so nothing can
re-link the sentence once the word becomes a lemma. That single row is what
closes the import loop.

The dedup cascade, in order, each step cheaper than the one after it:

1. words already handled in this run (the caller's ``seen`` set);
2. words already sitting in ``pending_imports``;
3. an existing ``Lemma`` with the same text (filtered by POS when known);
4. an existing ``DerivativeForm`` in English matching the text.

Steps 3 and 4 are both needed: a word can be absent as a lemma but present as
an inflected form of one, and staging it would create a duplicate of a word the
database already knows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from sentences.analysis import SUBSTRING_MATCH_LANGUAGES
from sentences.import_workflow import PART_OF_SPEECH_MAP
from storage.models.imports import PendingImport
from storage.models.schema import DerivativeForm, Lemma, SentenceWordHint
from wordfreq.tools.sentence_word_linker import ResolvedLemma

logger = logging.getLogger(__name__)


@dataclass
class StagingOutcome:
    """What one staging pass did with the words handed to it."""

    staged: int = 0
    already_pending: int = 0
    already_in_database: int = 0
    skipped: int = 0
    pending_import_ids: List[int] = field(default_factory=list)
    hints_written: int = 0

    def summary(self) -> str:
        return (
            f"staged={self.staged} already_pending={self.already_pending} "
            f"already_in_database={self.already_in_database} skipped={self.skipped}"
        )


def lemma_ids_for_english_gloss(
    session: Session, english_gloss: str, cache: Dict[str, Set[int]]
) -> Set[int]:
    """Lemma ids whose text matches ``english_gloss``, case-insensitively."""
    normalized = english_gloss.strip().lower()
    if normalized in cache:
        return cache[normalized]
    rows = session.query(Lemma.id).filter(func.lower(Lemma.lemma_text) == normalized).all()
    ids = {int(row[0]) for row in rows}
    cache[normalized] = ids
    return ids


def lemma_ids_for_derivative(
    session: Session,
    language_code: str,
    surface_form: str,
    cache: Dict[Tuple[str, str], Set[int]],
) -> Set[int]:
    """Lemma ids owning a derivative form matching ``surface_form``.

    Logographic languages match by substring in both directions, since their
    tokens are not whitespace-delimited and a stored form may be a fragment of
    the surface form or contain it.
    """
    normalized = surface_form.strip().lower()
    cache_key = (language_code, normalized)
    if cache_key in cache:
        return cache[cache_key]

    if language_code in SUBSTRING_MATCH_LANGUAGES:
        rows = (
            session.query(DerivativeForm.lemma_id)
            .filter(
                DerivativeForm.language_code == language_code,
                or_(
                    DerivativeForm.derivative_form_text == surface_form,
                    DerivativeForm.derivative_form_text.contains(surface_form),
                    literal(surface_form).contains(DerivativeForm.derivative_form_text),
                ),
            )
            .all()
        )
    else:
        rows = (
            session.query(DerivativeForm.lemma_id)
            .filter(
                DerivativeForm.language_code == language_code,
                func.lower(DerivativeForm.derivative_form_text) == normalized,
            )
            .all()
        )
    ids = {int(row[0]) for row in rows}
    cache[cache_key] = ids
    return ids


def _filter_by_pos(session: Session, lemma_ids: Set[int], pos_type: Optional[str]) -> Set[int]:
    """Narrow lemma ids to those of one part of speech.

    With no POS to filter by, every match counts -- the word is considered
    known and is not staged.
    """
    if not pos_type or not lemma_ids:
        return lemma_ids
    rows = (
        session.query(Lemma.id)
        .filter(Lemma.id.in_(sorted(lemma_ids)), Lemma.pos_type == pos_type)
        .all()
    )
    return {int(row[0]) for row in rows}


def load_pending_glosses(session: Session) -> Set[str]:
    """Every English word currently staged, lowercased."""
    rows = session.query(PendingImport.english_word).all()
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _next_hint_position(session: Session, sentence_id: int) -> int:
    rows = (
        session.query(SentenceWordHint.position)
        .filter(SentenceWordHint.sentence_id == sentence_id)
        .all()
    )
    positions = [int(row[0]) for row in rows if row[0] is not None]
    return max(positions) + 1 if positions else 0


def _hints_by_text(session: Session, sentence_id: int) -> Dict[str, SentenceWordHint]:
    """Existing hint rows for a sentence, keyed by lowercased English text."""
    rows = (
        session.query(SentenceWordHint)
        .filter(SentenceWordHint.sentence_id == sentence_id)
        .order_by(SentenceWordHint.position)
        .all()
    )
    mapping: Dict[str, SentenceWordHint] = {}
    for hint in rows:
        text = (hint.english_text or "").strip().lower()
        if text and text not in mapping:
            mapping[text] = hint
    return mapping


def stage_unlinked_words(
    session: Session,
    sentence_id: int,
    *,
    unresolved: Sequence[ResolvedLemma],
    source: str,
    document_language: str = "en",
    tags: Optional[str] = None,
    example_sentence: Optional[str] = None,
    notes: Optional[str] = None,
    seen: Optional[Set[str]] = None,
    pending_glosses: Optional[Set[str]] = None,
    gloss_cache: Optional[Dict[str, Set[int]]] = None,
    derivative_cache: Optional[Dict[Tuple[str, str], Set[int]]] = None,
    dry_run: bool = False,
) -> StagingOutcome:
    """Create ``PendingImport`` rows for words that resolved to no lemma.

    Does not commit; the caller owns the transaction.

    Args:
        session: Database session.
        sentence_id: The sentence these words came from. Each staged word gets a
            ``SentenceWordHint`` on this sentence carrying the new pending id.
        unresolved: Resolutions with no lemma, from
            :func:`sentences.link_writer.link_sentence_words`.
        source: Provenance string stored on each row, e.g. ``"genys/report.txt"``.
        document_language: Language the surface form came from.
        tags: Pre-serialized JSON tag array, as ``serialize_tags_for_column``
            produces. Applied to every word staged in this call.
        example_sentence: English sentence text, stored as context for the
            approval step's LLM call.
        notes: Free-text note stored on each row.
        seen: Glosses already handled by this caller, mutated in place. Pass the
            same set across a document so a word repeated in ten sentences is
            staged once.
        pending_glosses: Preloaded set of already-staged glosses, mutated in
            place. Loaded on demand when omitted.
        gloss_cache: Memo for lemma-text lookups, mutated in place.
        derivative_cache: Memo for derivative-form lookups, mutated in place.
        dry_run: Count what would be staged without writing.

    Returns:
        A :class:`StagingOutcome` whose ``pending_import_ids`` are the rows
        created by this call.
    """
    outcome = StagingOutcome()
    if not unresolved:
        return outcome

    seen_glosses = seen if seen is not None else set()
    existing_pending = (
        pending_glosses if pending_glosses is not None else load_pending_glosses(session)
    )
    text_cache: Dict[str, Set[int]] = gloss_cache if gloss_cache is not None else {}
    form_cache: Dict[Tuple[str, str], Set[int]] = (
        derivative_cache if derivative_cache is not None else {}
    )

    existing_hints = _hints_by_text(session, sentence_id)
    next_position = _next_hint_position(session, sentence_id)

    for resolved in unresolved:
        gloss = (resolved.english_text or "").strip()
        if not gloss:
            outcome.skipped += 1
            continue

        normalized = gloss.lower()
        if normalized in seen_glosses:
            outcome.skipped += 1
            continue
        seen_glosses.add(normalized)

        if normalized in existing_pending:
            outcome.already_pending += 1
            continue

        pos_type = PART_OF_SPEECH_MAP.get((resolved.slot_name or "").strip().lower())

        direct = _filter_by_pos(
            session, lemma_ids_for_english_gloss(session, normalized, text_cache), pos_type
        )
        if direct:
            outcome.already_in_database += 1
            continue

        by_form = _filter_by_pos(
            session, lemma_ids_for_derivative(session, "en", normalized, form_cache), pos_type
        )
        if by_form:
            outcome.already_in_database += 1
            continue

        outcome.staged += 1
        if dry_run:
            continue

        pending = PendingImport(
            english_word=gloss,
            definition=gloss,
            disambiguation_translation=gloss,
            disambiguation_language=document_language,
            pos_type=pos_type,
            pos_subtype=None,
            tags=tags,
            source=source,
            frequency_rank=None,
            notes=notes,
            example_sentence=example_sentence,
        )
        session.add(pending)
        # Needed before the hint can reference it.
        session.flush()

        existing_pending.add(normalized)
        outcome.pending_import_ids.append(int(pending.id))

        # The back-link. Without it the sentence has no way to find this word
        # again once it becomes a lemma. A hint may already exist for this slot
        # (written by buivolas or the scene handler); attach to it rather than
        # colliding with its unique (sentence_id, position) key.
        existing_hint = existing_hints.get(normalized)
        if existing_hint is not None:
            if existing_hint.pending_import_id is None and existing_hint.lemma_id is None:
                existing_hint.pending_import_id = pending.id
                outcome.hints_written += 1
        else:
            new_hint = SentenceWordHint(
                sentence_id=sentence_id,
                position=next_position,
                pending_import_id=pending.id,
                english_text=gloss,
                # slot_name is NOT NULL; a word whose part of speech the LLM
                # left blank still needs a row.
                slot_name=(resolved.slot_name or "").strip() or "unknown",
            )
            session.add(new_hint)
            existing_hints[normalized] = new_hint
            next_position += 1
            outcome.hints_written += 1

    if not dry_run:
        session.flush()
    logger.info("Staged from sentence %s: %s", sentence_id, outcome.summary())
    return outcome
