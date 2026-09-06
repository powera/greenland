"""Workqueue handler that submits Phase-1 sentence translations to OpenAI Batch.

Created by the ``/api/llm/sentences/batch_translate`` endpoint. The handler
builds one ``/v1/chat/completions`` request per sentence whose response is a
sentence-level translation into every requested target language (no per-word
breakdown). Requests are tagged ``agent_name="barsukas_translate"`` so the
batch poller can distinguish Phase-1 results from Phase-3 results and apply
them differently.

The corresponding Phase-3 step is queued by the caller via
``/api/llm/sentences/batch_decompose`` once translations are present in the
main DB.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import constants
from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.lib import limit_from_estimate, schema_from_dict, to_openai_schema
from clients.openai.batch_client import OpenAIBatchClient
from clients.openai.client import is_gpt5_nano_or_mini_model, reasoning_effort_for_model
from sentences.candidate_lookup import DEFAULT_SOURCE_LANGUAGES
from sentences.decomposition import build_name_rendering_lines
from sentences.token_estimates import estimate_translation_output_tokens
from sentences.translate_and_decompose import build_phase1_prompt, format_conversation_context
from storage.crud.conversation import get_sentence_conversation_context
from storage.models.schema import Sentence, SentenceTranslation
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

_AGENT_NAME = "barsukas_translate"
_OPERATION_TYPE = "batch_translate_sentence"
_BATCH_ENDPOINT = "/v1/chat/completions"


def _pick_source_language(existing_languages: set[str]) -> str:
    if not existing_languages:
        raise ValueError("Sentence has no translations; cannot determine source language")
    if "en" in existing_languages:
        return "en"
    return next(iter(existing_languages))


@workqueue_payload_handler()
def handle_sentences_batch_translate_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    target_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Submit a batch of Phase-1 sentence-translation requests to OpenAI Batch.

    ``target_languages`` defaults to :data:`DEFAULT_SOURCE_LANGUAGES` (minus the
    source) so the candidate-lemma pool used by Phase 3 has rich coverage.
    """
    if not sentence_ids:
        raise ValueError("sentence_ids must be a non-empty list")

    requested_targets: List[str] = (
        list(target_languages) if target_languages else list(DEFAULT_SOURCE_LANGUAGES)
    )

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

            existing = session.query(SentenceTranslation).filter_by(sentence_id=sentence_id).all()
            if not existing:
                logger.warning(
                    "Sentence %s has no translations; cannot pick source language",
                    sentence_id,
                )
                skipped.append(sentence_id)
                continue

            existing_languages = {row.language_code for row in existing}
            source_language = _pick_source_language(existing_languages)
            source_translation = next(
                row.translation_text for row in existing if row.language_code == source_language
            )

            phase1_targets = [
                lang
                for lang in requested_targets
                if lang != source_language and lang not in existing_languages
            ]
            # Always include English when missing: Phase 3 lemma-decomposition
            # uses the English translation as its scoring anchor, so a Phase-1
            # batch that skips English produces a sentence Phase 3 can't decompose.
            if (
                source_language != "en"
                and "en" not in existing_languages
                and "en" not in phase1_targets
            ):
                phase1_targets.insert(0, "en")
            if not phase1_targets:
                logger.info(
                    "Sentence %s already has every requested target translation; skipping",
                    sentence_id,
                )
                skipped.append(sentence_id)
                continue

            # Same dialog context the synchronous path passes, so a batched
            # dialog line is not translated blind to what it answers.
            context_obj = get_sentence_conversation_context(
                session, sentence_id, language_code=source_language
            )
            conversation_context = (
                format_conversation_context(context_obj) or None
                if context_obj is not None
                else None
            )

            # Pin the established spelling of any names the sentence casts, so a
            # batched translation does not re-invent one per call.
            name_rendering_lines = build_name_rendering_lines(sentence, phase1_targets, session)

            built = build_phase1_prompt(
                sentence_text=source_translation,
                source_language=source_language,
                target_languages=phase1_targets,
                conversation_context=conversation_context,
                name_renderings="\n".join(name_rendering_lines) or None,
            )
            if built is None:
                logger.warning(
                    "Sentence %s: no usable target languages after normalization", sentence_id
                )
                skipped.append(sentence_id)
                continue
            _context, _prompt, full_prompt, schema, _normalized_targets = built

            max_completion_tokens = limit_from_estimate(
                estimate_translation_output_tokens(
                    source_text=source_translation,
                    source_language=source_language,
                    target_languages=_normalized_targets or phase1_targets,
                )
            )
            request_body: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": full_prompt}],
                "max_completion_tokens": max_completion_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentencePhase1Translation",
                        "strict": True,
                        "schema": to_openai_schema(schema_from_dict(schema)),
                    },
                },
            }
            if is_gpt5_nano_or_mini_model(model):
                effort = reasoning_effort_for_model(model, "minimal")
                if effort is not None:
                    request_body["reasoning_effort"] = effort

            custom_id = f"barsukas_translate_{sentence_id}_{uuid.uuid4().hex[:8]}"
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
                f"No Phase-1 requests queued (skipped={len(skipped)}). "
                f"Sentence IDs may already have all requested translations."
            )

        pending = manager.get_pending_requests(
            agent_name=_AGENT_NAME, operation_type=_OPERATION_TYPE
        )
        batch_id, file_id = manager.submit_batch(
            pending,
            batch_metadata={"agent": _AGENT_NAME, "operation": _OPERATION_TYPE},
        )
        logger.info(
            "Submitted OpenAI Phase-1 batch %s with %s request(s) (file=%s)",
            batch_id,
            len(pending),
            file_id,
        )
        msg = f"Submitted Phase-1 batch {batch_id} with {len(pending)} request(s)"
        if skipped:
            msg += f"; skipped {len(skipped)} sentence(s): {skipped}"
        return msg
    finally:
        batch_session.close()
