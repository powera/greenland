"""Persist the results of sentence word-to-lemma resolution.

``wordfreq.tools.sentence_word_linker.resolve_lemmas_for_sentence`` decides
which lemma each word slot refers to, using a cascade of six strategies. It is a
pure function: it returns its verdicts and writes nothing. This module is the
writer half.

Two tables receive the result, meaning different things:

* ``SentenceWord.lemma_id`` is the authoritative link, written only when the
  resolution is confident enough. It is keyed on ``(sentence_id,
  language_code, position)``, so a single slot maps to one row per language.
* ``SentenceWordHint`` records intent at generation time, keyed on
  ``(sentence_id, position)`` -- one row per *slot*, which is the granularity
  the resolver works at. It records lemmas only; a sentence remembers which
  staged word it is waiting on through ``SentencePendingImport`` instead (see
  :mod:`words.pending_imports.sentence_links`).

Slots are identified by lowercased English text, not by position. The resolver
groups that way, and a sentence containing the same word twice ("the cat saw
the cat") therefore collapses to a single slot. Writing back by text rather
than position keeps the two halves consistent about that.

Two invariants make re-running safe, which the import workflow's promote/link
loop depends on:

* an existing non-NULL ``lemma_id`` is never overwritten -- earlier decisions,
  including a human's, always win;
* a hint row is never deleted, only inserted or upgraded to name a lemma.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from storage.crud.operation_log import SENTENCE_LINK, log_entity_operation
from storage.models.schema import Lemma, Sentence, SentenceWord, SentenceWordHint
from words.pending_imports.sentence_links import release_legacy_hints
from wordfreq.tools.sentence_word_linker import ResolvedLemma, resolve_lemmas_for_sentence

logger = logging.getLogger(__name__)

# Minimum confidence required before a lemma link is written.
#
# The resolver's ladder runs 1.0 (guid) / 0.95 (source lemma) / 0.9 (exact text,
# or text+derivative overlap) / 0.85 (single ilike or derivative match) / 0.75
# (several ilike matches narrowed to one undisambiguated candidate) / 0.7 (LLM
# choice) / 0.5 (ambiguous, arbitrarily taking the first candidate).
#
# 0.75 admits everything down to the narrowed-multiple case and rejects the 0.5
# tier, which is the one that would silently attach a wrong lemma. The 0.7 LLM
# tier sits below the line on purpose: LLM disambiguation is off by default
# here, and enabling it should lower this threshold in the same change rather
# than have the constant quietly admit it in advance.
LINK_CONFIDENCE_THRESHOLD: float = 0.75


@dataclass
class LinkOutcome:
    """What one linking pass changed."""

    linked: int = 0
    ambiguous: int = 0
    unresolved: List[ResolvedLemma] = field(default_factory=list)
    hints_written: int = 0
    already_linked: int = 0

    def summary(self) -> str:
        return (
            f"linked={self.linked} ambiguous={self.ambiguous} "
            f"unresolved={len(self.unresolved)} hints={self.hints_written}"
        )


def _next_hint_position(session: Session, sentence_id: int) -> int:
    """First unused hint position for a sentence.

    Hint positions are slot ordinals and are unique per sentence, but the rows
    may have been written by another component (buivolas, the scene handler)
    with its own numbering. Appending after the highest existing position keeps
    this writer from colliding with theirs.
    """
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


def _apply_lemma_to_words(
    session: Session, sentence_id: int, english_text: str, lemma: Lemma
) -> tuple[int, int]:
    """Attach ``lemma`` to every language's row for one slot.

    Returns ``(newly_linked, already_linked)``. Rows that already carry a lemma
    are left exactly as they are.
    """
    normalized = english_text.strip().lower()
    if not normalized:
        return (0, 0)

    rows = session.query(SentenceWord).filter(SentenceWord.sentence_id == sentence_id).all()

    newly_linked = 0
    already_linked = 0
    for word in rows:
        if (word.english_text or "").strip().lower() != normalized:
            continue
        if word.lemma_id is not None:
            already_linked += 1
            continue
        word.lemma_id = lemma.id
        newly_linked += 1
    return (newly_linked, already_linked)


def _write_hint(
    session: Session,
    sentence_id: int,
    *,
    existing: Optional[SentenceWordHint],
    english_text: str,
    slot_name: Optional[str],
    lemma: Lemma,
    next_position: int,
) -> bool:
    """Record a resolved slot as a hint. Returns True when a row was written.

    An existing hint is upgraded in place rather than duplicated: a row that was
    holding a ``pending_import_id`` now names the lemma that pending became.
    """
    if existing is not None:
        if existing.lemma_id == lemma.id:
            return False
        existing.lemma_id = lemma.id
        return True

    session.add(
        SentenceWordHint(
            sentence_id=sentence_id,
            position=next_position,
            lemma_id=lemma.id,
            english_text=english_text,
            # slot_name is NOT NULL; a resolution carrying no part of speech
            # still needs a row.
            slot_name=(slot_name or "").strip() or "unknown",
        )
    )
    return True


def link_sentence_words(
    session: Session,
    sentence_id: int,
    *,
    use_llm_disambiguation: bool = False,
    confidence_threshold: float = LINK_CONFIDENCE_THRESHOLD,
    write_hints: bool = True,
    source_lemma: Optional[Lemma] = None,
    min_derivative_languages: int = 2,
    source: Optional[str] = None,
) -> LinkOutcome:
    """Resolve this sentence's words to lemmas and persist the confident ones.

    Does not commit; the caller owns the transaction.

    Args:
        session: Database session.
        sentence_id: Sentence to link.
        use_llm_disambiguation: Allow the resolver's LLM strategy. Off by
            default -- its results land below ``LINK_CONFIDENCE_THRESHOLD``, so
            enabling it without also lowering the threshold changes nothing.
        confidence_threshold: Minimum confidence for a write.
        write_hints: Also record each confident link as a ``SentenceWordHint``.
        source_lemma: Prefer this lemma when a slot's text matches it.
        min_derivative_languages: Languages that must agree for the
            cross-language derivative-form strategy to fire.
        source: Who is linking, for the operation log. None skips logging.

    Returns:
        A :class:`LinkOutcome`. Its ``unresolved`` list is what the staging step
        consumes -- those are the words with no lemma in the database.
    """
    resolutions = resolve_lemmas_for_sentence(
        session,
        sentence_id,
        use_llm_disambiguation=use_llm_disambiguation,
        min_derivative_languages=min_derivative_languages,
        source_lemma=source_lemma,
    )

    outcome = LinkOutcome()
    existing_hints = _hints_by_text(session, sentence_id)
    next_position = _next_hint_position(session, sentence_id)
    seen_texts: set[str] = set()

    for resolved in resolutions:
        text = (resolved.english_text or "").strip()
        normalized = text.lower()
        if not normalized or normalized in seen_texts:
            continue
        seen_texts.add(normalized)

        if resolved.lemma is None:
            if resolved.method != "grammatical_word":
                outcome.unresolved.append(resolved)
            continue

        if resolved.confidence < confidence_threshold:
            # A real candidate exists but the resolver could not choose between
            # several. Writing the first one would be a guess that later looks
            # like a decision, so the slot is left for a human instead.
            outcome.ambiguous += 1
            logger.debug(
                "Sentence %s slot %r: confidence %.2f below %.2f (%s), not linking",
                sentence_id,
                text,
                resolved.confidence,
                confidence_threshold,
                resolved.method,
            )
            continue

        newly_linked, already_linked = _apply_lemma_to_words(
            session, sentence_id, text, resolved.lemma
        )
        outcome.linked += newly_linked
        outcome.already_linked += already_linked

        if write_hints:
            wrote = _write_hint(
                session,
                sentence_id,
                existing=existing_hints.get(normalized),
                english_text=text,
                slot_name=resolved.slot_name,
                lemma=resolved.lemma,
                next_position=next_position,
            )
            if wrote and normalized not in existing_hints:
                next_position += 1
            if wrote:
                outcome.hints_written += 1

    session.flush()

    if source is not None:
        sentence = session.get(Sentence, sentence_id)
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_LINK,
            entity_guid=sentence.guid if sentence else None,
            fact={
                "linked": outcome.linked,
                "ambiguous": outcome.ambiguous,
                "unresolved": len(outcome.unresolved),
                "hints_written": outcome.hints_written,
                "already_linked": outcome.already_linked,
            },
        )

    logger.info("Linked sentence %s: %s", sentence_id, outcome.summary())
    return outcome


def release_sentence_word_hints(
    session: Session, pending_import_id: int, lemma_id: Optional[int] = None
) -> int:
    """Detach pre-link-table hint rows before their pending import is deleted.

    Compatibility wrapper over
    :func:`words.pending_imports.sentence_links.release_legacy_hints`, which is
    called by ``delete_pending_import`` -- the single place a pending row is
    now removed. Staging no longer writes hints carrying a
    ``pending_import_id``, so this only matters for databases staged before the
    link table existed.

    Args:
        session: Database session. Not committed; the caller owns the
            transaction.
        pending_import_id: The pending row about to be deleted.
        lemma_id: Lemma the pending became, when it became one. Rejection
            passes None, since the word resolved to no lemma at all.

    Returns:
        The number of hint rows touched.
    """
    return release_legacy_hints(session, pending_import_id, lemma_id=lemma_id)
