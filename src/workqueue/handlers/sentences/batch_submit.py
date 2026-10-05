"""Workqueue handler that sends sentences through the sentence job as OpenAI batches.

Queued by ``zvirblis submit-batch``.  Picks English-only sentences (or takes
``sentence_ids``) and starts a run of
``workqueue.handlers.sentences.translation.SENTENCE_TRANSLATION_JOB``: Phase 1
as one set of batches, then Phases 2+3 once every sentence has its
translations.  The Barsukas batch poller applies the results and submits the
second stage.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import constants
from sqlalchemy import func as sql_func
from storage.models.imports import SentencePendingImport
from storage.models.schema import Sentence, SentenceTranslation, SentenceWordHint
from workqueue.handlers.sentences.translation import (
    describe_run,
    sentence_translation_state,
    submit_sentence_translation_batch,
)
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

_DEFAULT_LANGUAGES: List[str] = ["fr", "zh", "lt", "es", "es-419"]


def _discover_batch_sentence_ids(
    session: Any,
    *,
    limit: Optional[int],
    pattern_id: Optional[str],
    exclude_pending_imports: bool,
) -> List[int]:
    """Find English-only sentences eligible for a translation batch."""
    translation_counts = (
        session.query(Sentence.id.label("sentence_id"))
        .join(SentenceTranslation)
        .group_by(Sentence.id)
        .having(sql_func.count(SentenceTranslation.id) == 1)
        .subquery()
    )
    query = (
        session.query(Sentence.id)
        .join(SentenceTranslation)
        .filter(SentenceTranslation.language_code == "en")
        .filter(Sentence.id.in_(session.query(translation_counts.c.sentence_id)))
        .order_by(Sentence.id)
    )
    if pattern_id:
        query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")
    if exclude_pending_imports:
        # Sentences waiting on a staged word. Legacy hint rows count too, so a
        # database staged before the link table existed is still excluded.
        pending_sentence_ids = session.query(SentencePendingImport.sentence_id).distinct()
        legacy_sentence_ids = (
            session.query(SentenceWordHint.sentence_id)
            .filter(SentenceWordHint.pending_import_id.isnot(None))
            .distinct()
        )
        query = query.filter(
            ~Sentence.id.in_(pending_sentence_ids),
            ~Sentence.id.in_(legacy_sentence_ids),
        )
    if limit is not None:
        query = query.limit(limit)
    return [sentence_id for (sentence_id,) in query.all()]


@workqueue_payload_handler()
def handle_sentences_translate_batch_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    selected_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    limit: Optional[int] = None,
    pattern_id: Optional[str] = None,
    exclude_pending_imports: bool = False,
    **_: Any,
) -> str:
    """Translate and decompose sentences through OpenAI batches.

    Accepts extra kwargs (``batch``, etc.) and ignores them so it is tolerant
    of payload changes made by the route.
    """
    selected_sentence_ids = sentence_ids or _discover_batch_sentence_ids(
        session,
        limit=limit,
        pattern_id=pattern_id,
        exclude_pending_imports=exclude_pending_imports,
    )
    if not selected_sentence_ids:
        return "No untranslated sentences found for batch submission"

    target_languages = selected_languages or _DEFAULT_LANGUAGES
    states = [
        sentence_translation_state(
            sentence_id, target_languages, log_source="agents.zvirblis/batch"
        )
        for sentence_id in selected_sentence_ids
    ]
    report = submit_sentence_translation_batch(session, states, model)
    return describe_run(report)
