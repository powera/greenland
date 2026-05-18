"""Workqueue handler that submits Phase-3 sentence decomposition to OpenAI Batch.

Created by the ``/api/llm/sentences/batch_decompose`` endpoint. Requires that
the sentences already have translations in every language needed for the
candidate-lemma lookup pool — the API route enforces this; this handler
re-validates defensively.

Builds one ``/v1/chat/completions`` request per sentence whose response is a
combined multi-language word-level decomposition (the Phase 3 output of the
synchronous pipeline). Requests are tagged ``agent_name="barsukas_decompose"``
so the existing batch poller's completion path applies them to the main DB.
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
from clients.lib import schema_from_dict, to_openai_schema
from clients.openai.batch_client import OpenAIBatchClient
from clients.openai.client import is_gpt5_nano_or_mini_model, reasoning_effort_for_model
from sentences.candidate_lookup import DEFAULT_SOURCE_LANGUAGES, CandidateLemma
from sentences.decomposition import (
    build_multi_language_decomposition_context,
    build_multi_language_decomposition_prompt,
    build_multi_language_decomposition_schema,
)
from sentences.translate_and_decompose import lookup_candidate_lemmas
from storage.models.schema import Sentence, SentenceTranslation
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

_AGENT_NAME = "barsukas_decompose"
_OPERATION_TYPE = "decompose_sentence"
_BATCH_ENDPOINT = "/v1/chat/completions"

_DEFAULT_DECOMPOSE_LANGUAGES: List[str] = ["en", "fr", "zh", "lt", "es"]


def _candidates_for_prompt(candidates: List[CandidateLemma]) -> List[Dict[str, Any]]:
    return [
        {
            "guid": c.guid,
            "lemma": c.lemma_text,
            "disambiguation": c.disambiguation,
            "pos": c.pos,
            "definition": c.definition,
            "translations": c.translations,
        }
        for c in candidates
    ]


@workqueue_payload_handler()
def handle_sentences_batch_decompose_submit(
    session: Any,
    sentence_ids: Optional[List[int]] = None,
    decompose_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Submit a batch of Phase-3 sentence-decomposition requests to OpenAI Batch."""
    if not sentence_ids:
        raise ValueError("sentence_ids must be a non-empty list")

    decompose_targets: List[str] = (
        list(decompose_languages) if decompose_languages else list(_DEFAULT_DECOMPOSE_LANGUAGES)
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

            translations: Dict[str, str] = {
                row.language_code: row.translation_text
                for row in session.query(SentenceTranslation)
                .filter_by(sentence_id=sentence_id)
                .all()
            }
            if not translations:
                logger.warning(
                    "Sentence %s has no translations; cannot decompose (Phase 1 missing)",
                    sentence_id,
                )
                skipped.append(sentence_id)
                continue

            missing_decompose = [lang for lang in decompose_targets if lang not in translations]
            if missing_decompose:
                logger.warning(
                    "Sentence %s missing translations for decompose targets %s; skipping",
                    sentence_id,
                    missing_decompose,
                )
                skipped.append(sentence_id)
                continue

            anchor_language = "en" if "en" in translations else next(iter(translations.keys()))
            anchor_text = translations[anchor_language]

            target_translations: Dict[str, str] = {
                lang: translations[lang] for lang in decompose_targets
            }

            helper_translations = [
                {"language_code": lang, "translation": text}
                for lang, text in translations.items()
                if lang not in target_translations and lang != anchor_language
            ]

            candidates = lookup_candidate_lemmas(
                session=session,
                translations=translations,
                source_languages=list(translations.keys()),
            )

            prompt = build_multi_language_decomposition_prompt(
                source_sentence=anchor_text,
                source_language=anchor_language,
                target_translations=target_translations,
                helper_translations=helper_translations,
                candidate_lemmas=_candidates_for_prompt(candidates),
            )
            context = build_multi_language_decomposition_context()
            schema = build_multi_language_decomposition_schema(
                target_languages=list(target_translations.keys())
            )
            full_prompt = f"{context}\n\n{prompt}"

            request_body: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": full_prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceDecomposition",
                        "strict": True,
                        "schema": to_openai_schema(schema_from_dict(schema)),
                    },
                },
            }
            if is_gpt5_nano_or_mini_model(model):
                effort = reasoning_effort_for_model(model, "minimal")
                if effort is not None:
                    request_body["reasoning_effort"] = effort

            custom_id = f"barsukas_decompose_{sentence_id}_{uuid.uuid4().hex[:8]}"
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
                f"No Phase-3 requests queued (skipped={len(skipped)}). "
                f"Sentence IDs may be missing required translations."
            )

        pending = manager.get_pending_requests(
            agent_name=_AGENT_NAME, operation_type=_OPERATION_TYPE
        )
        batch_id, file_id = manager.submit_batch(
            pending,
            batch_metadata={"agent": _AGENT_NAME, "operation": _OPERATION_TYPE},
        )
        logger.info(
            "Submitted OpenAI Phase-3 batch %s with %s request(s) (file=%s)",
            batch_id,
            len(pending),
            file_id,
        )
        msg = f"Submitted Phase-3 batch {batch_id} with {len(pending)} request(s)"
        if skipped:
            msg += f"; skipped {len(skipped)} sentence(s): {skipped}"
        return msg
    finally:
        batch_session.close()
