"""Workqueue handler: Phase-3 sentence decompositions as OpenAI batches.

Created by the ``/api/llm/sentences/batch_decompose`` endpoint, which checks
first that every sentence has the translations Phase 3 needs.  Starts a
decompose-only run of
``workqueue.handlers.sentences.translation.SENTENCE_TRANSLATION_JOB``: the
same candidate lookup, Phase-3 request and storage as the live path.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import constants
from workqueue.handlers.sentences.translation import (
    describe_run,
    sentence_translation_state,
    submit_sentence_translation_batch,
)
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

_DEFAULT_DECOMPOSE_LANGUAGES: List[str] = ["en", "fr", "zh", "lt", "es", "es-419"]


@workqueue_payload_handler()
def handle_sentences_batch_decompose_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    decompose_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Submit Phase-3 sentence decompositions as an OpenAI batch run."""
    if not sentence_ids:
        raise ValueError("sentence_ids must be a non-empty list")
    targets: List[str] = (
        list(decompose_languages) if decompose_languages else list(_DEFAULT_DECOMPOSE_LANGUAGES)
    )
    states = [
        sentence_translation_state(
            sentence_id,
            targets,
            translate=False,
            decompose_languages=targets,
            log_source="barsukas/batch_decompose",
        )
        for sentence_id in sentence_ids
    ]
    return describe_run(submit_sentence_translation_batch(session, states, model))
