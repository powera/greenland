"""Workqueue handler: Phase-1 sentence translations as OpenAI batches.

Created by the ``/api/llm/sentences/batch_translate`` endpoint.  Starts a
translate-only run of
``workqueue.handlers.sentences.translation.SENTENCE_TRANSLATION_JOB``: the
same Phase-1 request and storage as the live path, for the languages each
sentence is still missing.  ``/api/llm/sentences/batch_decompose`` (or a
``zvirblis submit-batch`` run, which does both phases) adds the words.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import constants
from sentences.candidate_lookup import DEFAULT_SOURCE_LANGUAGES
from workqueue.handlers.sentences.translation import (
    describe_run,
    sentence_translation_state,
    submit_sentence_translation_batch,
)
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

# Decompose targets that are not candidate-lookup pivots.  es-419 shares most
# lemma-level vocabulary with es, so matching on both would double-count one
# piece of evidence; it is translated here only so Phase 3 can decompose it.
_TRANSLATE_ONLY_DEFAULT_TARGETS: List[str] = ["es-419"]


@workqueue_payload_handler()
def handle_sentences_batch_translate_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    target_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Submit Phase-1 sentence translations as an OpenAI batch run.

    ``target_languages`` defaults to :data:`DEFAULT_SOURCE_LANGUAGES` plus
    es-419.  Languages a sentence already has are not asked for again.
    """
    if not sentence_ids:
        raise ValueError("sentence_ids must be a non-empty list")
    requested: List[str] = (
        list(target_languages)
        if target_languages
        else [*DEFAULT_SOURCE_LANGUAGES, *_TRANSLATE_ONLY_DEFAULT_TARGETS]
    )
    states = [
        sentence_translation_state(
            sentence_id,
            requested,
            decompose=False,
            skip_existing_translations=True,
            log_source="barsukas/batch_translate",
        )
        for sentence_id in sentence_ids
    ]
    return describe_run(submit_sentence_translation_batch(session, states, model))
