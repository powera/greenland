"""Promote a sentence's staged words into real lemmas.

Staging leaves a sentence pointing at ``PendingImport`` rows through
``SentencePendingImport`` links. Promotion turns those into lemmas (or names,
or concepts) by delegating to
``words.pending_imports.approval.approve_pending_import`` -- the same function
the Approve button in Barsukas calls, unchanged, so the automated path and the
human path cannot drift apart.

**Promotion is off by default.** ``approve_pending_import`` makes an LLM call
and mints a permanent Lemma with a permanent GUID, and it already contains a
refusal path (words with strong synonym candidates) that exists precisely
because the machine is not confident enough to decide alone. Approving in bulk
without review manufactures near-duplicate lemmas, and lemmas are the most
expensive thing in this database to un-make. The switch exists and is safe to
turn on per corpus once ``max_per_run`` has been watched on real input; until
then the workflow reports what is waiting and stops.

On success ``approve_pending_import`` deletes the ``PendingImport`` row, which
takes its sentence links with it after applying the outcome to the sentence's
word rows -- so the word this sentence was waiting on is already linked by the
time promotion returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.backend.config import DataSourceConfig
from storage.models.imports import TARGET_KIND_LEMMA, PendingImport
from words.pending_imports.sentence_links import (
    pending_imports_for_sentence as _pending_imports_for_sentence,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromotionPolicy:
    """When the workflow may turn a staged word into a lemma on its own.

    Attributes:
        auto_promote: Master switch. False means promote nothing and report.
        max_per_run: Ceiling on approvals in a single pass, so a bad corpus
            cannot mint hundreds of lemmas before anyone looks.
        require_pos_type: Skip rows with no part of speech. Those are the ones
            whose approval leans hardest on the LLM, since it must decide both
            the sense and the subtype that determines the GUID. Applies only to
            rows destined to become lemmas.
    """

    auto_promote: bool = False
    max_per_run: int = 10
    require_pos_type: bool = True


@dataclass
class PromotionOutcome:
    """What one promotion pass did."""

    promoted: List[int] = field(default_factory=list)
    deferred: List[int] = field(default_factory=list)
    failed: List[Tuple[int, str]] = field(default_factory=list)
    lemma_ids: List[int] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"promoted={len(self.promoted)} deferred={len(self.deferred)} "
            f"failed={len(self.failed)}"
        )


def pending_imports_for_sentence(session: Session, sentence_id: int) -> List[PendingImport]:
    """The staged words this sentence is still waiting on.

    Thin re-export of :func:`words.pending_imports.sentence_links.
    pending_imports_for_sentence`, kept here because the promotion loop and its
    tests both read it. A link whose pending row no longer exists is a
    promotion that already happened, and is simply absent from the result.
    """
    return _pending_imports_for_sentence(session, sentence_id)


def promote_sentence_pendings(
    session: Session,
    sentence_id: int,
    *,
    policy: PromotionPolicy,
    data_source_config: DataSourceConfig,
    model: str,
    debug: bool = False,
) -> PromotionOutcome:
    """Approve this sentence's staged words into lemmas, if policy allows.

    ``approve_pending_import`` commits internally, so this function does too --
    a partial run leaves the lemmas it already created, which is correct: they
    are real words and re-running must not try to create them twice.

    Args:
        session: Database session.
        sentence_id: Sentence whose staged words to promote.
        policy: What is allowed. With ``auto_promote`` false, every outstanding
            row is deferred and nothing is written.
        data_source_config: Passed through to the approval path for its LLM
            client.
        model: Model for the approval call.
        debug: Verbose logging in the approval path.

    Returns:
        A :class:`PromotionOutcome`. ``deferred`` holds the ids left for a
        human.
    """
    outcome = PromotionOutcome()
    pendings = pending_imports_for_sentence(session, sentence_id)
    if not pendings:
        return outcome

    if not policy.auto_promote:
        outcome.deferred = [int(pending.id) for pending in pendings]
        logger.info(
            "Sentence %s: %d staged word(s) awaiting human approval",
            sentence_id,
            len(outcome.deferred),
        )
        return outcome

    from words.pending_imports.approval import approve_pending_import

    for pending in pendings:
        pending_id = int(pending.id)

        if len(outcome.promoted) >= policy.max_per_run:
            outcome.deferred.append(pending_id)
            continue

        # The pos_type gate exists because approving a *lemma* with no part of
        # speech leans hardest on the LLM: it must decide the sense and the
        # subtype the GUID is built from. A name or a concept is created
        # without an LLM call at all, so the gate does not apply to them.
        needs_pos_type = (pending.target_kind or TARGET_KIND_LEMMA) == TARGET_KIND_LEMMA
        if policy.require_pos_type and needs_pos_type and not pending.pos_type:
            logger.debug(
                "Sentence %s: deferring pending %s (%r) with no pos_type",
                sentence_id,
                pending_id,
                pending.english_word,
            )
            outcome.deferred.append(pending_id)
            continue

        result: Dict[str, Any] = approve_pending_import(
            session,
            pending_id,
            data_source_config,
            model=model,
            debug=debug,
        )

        if not result.get("success"):
            error = str(result.get("error") or "approval failed")
            logger.warning(
                "Sentence %s: pending %s (%r) not promoted: %s",
                sentence_id,
                pending_id,
                pending.english_word,
                error,
            )
            outcome.failed.append((pending_id, error))
            continue

        lemma_id = result.get("lemma_id")
        lemma_id_int = int(lemma_id) if isinstance(lemma_id, int) else None
        # approve_pending_import applies the outcome to the sentence's word rows
        # before deleting the pending row, so no relinking is needed here.
        session.commit()

        outcome.promoted.append(pending_id)
        if lemma_id_int is not None:
            outcome.lemma_ids.append(lemma_id_int)

    logger.info("Promoted for sentence %s: %s", sentence_id, outcome.summary())
    return outcome
