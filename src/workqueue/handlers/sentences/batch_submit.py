"""Workqueue handler that submits sentence-decomposition prompts to OpenAI Batch.

Created by the ``/api/llm/sentences/decompose`` endpoint when ``batch=True``.

The handler builds one ``/v1/chat/completions`` request per sentence and queues
them into the shared ``clients.batch_queue.BatchQueue`` (SQLite) tagged with
``agent_name="barsukas_decompose"`` and ``operation_type="decompose_sentence"``.
Once all are queued it calls ``BatchQueueManager.submit_batch`` to push them to
the OpenAI Batch API.

The Barsukas background batch-poller (see ``barsukas.batch_poller``) periodically
checks pending batches and, on completion, applies results via
``sentences.batch_completion.apply_sentence_translation_results``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import constants
from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.openai.batch_client import OpenAIBatchClient
from sentences.translate_and_decompose import lookup_candidate_lemmas
from sentences.translation import build_response_schema, build_translation_prompt
from storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWord
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

_DEFAULT_LANGUAGES: List[str] = ["fr", "zh", "lt", "es", "bn", "uk", "kn"]
_AGENT_NAME = "barsukas_decompose"
_OPERATION_TYPE = "decompose_sentence"
_BATCH_ENDPOINT = "/v1/chat/completions"


def _pick_source_language(existing_languages: set[str]) -> str:
    """Pick the source language for the prompt.

    Prefer English when an English translation already exists; otherwise pick
    any existing translation. Raises ``ValueError`` if there are none.
    """
    if not existing_languages:
        raise ValueError("Sentence has no translations; cannot determine source language")
    if "en" in existing_languages:
        return "en"
    return next(iter(existing_languages))


@workqueue_payload_handler()
def handle_sentences_translate_batch_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    selected_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Submit a batch of sentence decomposition requests to OpenAI Batch.

    Accepts extra kwargs (``batch``, etc.) and ignores them so it is tolerant
    of payload changes made by the route.
    """
    if not sentence_ids:
        raise ValueError("sentence_ids must be a non-empty list")

    target_languages = selected_languages or _DEFAULT_LANGUAGES

    batch_session = create_batch_database_session()
    batch_client = OpenAIBatchClient()
    manager = BatchQueueManager(batch_session, batch_client)

    queued: List[Any] = []
    skipped: List[int] = []

    try:
        for sentence_id in sentence_ids:
            sentence = session.get(Sentence, sentence_id)
            if sentence is None:
                logger.warning("Sentence %s not found; skipping", sentence_id)
                skipped.append(sentence_id)
                continue

            existing_translations: Dict[str, str] = {
                row.language_code: row.translation_text
                for row in session.query(SentenceTranslation)
                .filter_by(sentence_id=sentence_id)
                .all()
            }
            existing_languages = set(existing_translations.keys())
            if not existing_languages:
                logger.warning("Sentence %s has no translations; cannot build prompt", sentence_id)
                skipped.append(sentence_id)
                continue

            source_language = _pick_source_language(existing_languages)

            english_words = (
                session.query(SentenceWord)
                .filter_by(sentence_id=sentence_id, language_code="en")
                .all()
            )
            include_english = len(english_words) == 0

            request_targets = [lang for lang in target_languages if lang != source_language]

            candidates = lookup_candidate_lemmas(
                session=session,
                translations=existing_translations,
                source_languages=list(existing_translations.keys()),
            )
            candidate_lemma_models: List[Lemma] = []
            for candidate in candidates:
                lemma_model = session.query(Lemma).filter_by(guid=candidate.guid).first()
                if lemma_model is not None:
                    candidate_lemma_models.append(lemma_model)

            try:
                context, prompt = build_translation_prompt(
                    sentence,
                    request_targets,
                    session,
                    include_english=include_english,
                    source_language=source_language,
                    candidate_lemmas=candidate_lemma_models,
                )
            except ValueError as exc:
                logger.warning(
                    "Skipping sentence %s (could not build prompt): %s", sentence_id, exc
                )
                skipped.append(sentence_id)
                continue

            schema = build_response_schema(request_targets, include_english)
            full_prompt = f"{context}\n\n{prompt}"

            request_body: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": full_prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceDecomposition",
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
            if model.startswith("gpt-5.4-mini") or model.startswith("gpt-5-nano"):
                request_body["reasoning_effort"] = "minimal"

            custom_id = f"barsukas_decompose_{sentence_id}"
            metadata = BatchRequestMetadata(
                custom_id=custom_id,
                agent_name=_AGENT_NAME,
                operation_type=_OPERATION_TYPE,
                entity_id=sentence_id,
                entity_type="sentence",
            )

            try:
                record = manager.queue_request(
                    custom_id=custom_id,
                    request_body=request_body,
                    metadata=metadata,
                    endpoint=_BATCH_ENDPOINT,
                )
                queued.append(record)
            except ValueError as exc:
                logger.warning("Skipping sentence %s (custom_id conflict): %s", sentence_id, exc)
                skipped.append(sentence_id)

        if not queued:
            return (
                f"No requests queued (skipped={len(skipped)}). "
                f"Sentence IDs requiring source translations may be missing them."
            )

        pending = manager.get_pending_requests(
            agent_name=_AGENT_NAME, operation_type=_OPERATION_TYPE
        )
        batch_id, file_id = manager.submit_batch(
            pending,
            batch_metadata={"agent": _AGENT_NAME, "operation": _OPERATION_TYPE},
        )
        logger.info(
            "Submitted OpenAI batch %s with %s request(s) (file=%s)",
            batch_id,
            len(pending),
            file_id,
        )
        msg = f"Submitted batch {batch_id} with {len(pending)} request(s)"
        if skipped:
            msg += f"; skipped {len(skipped)} sentence(s): {skipped}"
        return msg
    finally:
        batch_session.close()
