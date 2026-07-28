"""Shared logic to apply OpenAI Batch results for sentence translations.

Used by both:
- ``agents/common/batch.py`` (CLI ``batch complete --batch-id <id>``)
- ``barsukas`` background batch poller

The batch's request bodies must target ``/v1/chat/completions`` with a JSON
schema response_format. Each request's ``entity_id`` is the sentence id whose
translations should be written by
``sentences.translation.store_translation_results``.

Two flavors are exposed:

- :func:`apply_sentence_translation_results` for legacy batches whose schema
  combines per-language translations *and* per-word breakdowns in one call
  (used by the deprecated single-shot batch and Phase-3 batches).
- :func:`apply_phase1_translation_results` for the new Phase-1-only batches
  that produce sentence-level translations alone; word breakdowns are filled
  in later by a Phase-3 batch.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable

from clients.batch_queue import BatchQueue
from sentences.translation import store_translation_results

logger = logging.getLogger(__name__)

# Agent names used by the sentence batch pipeline. Kept here so route handlers
# and the background poller dispatch the same way without importing each other.
TRANSLATE_AGENT_NAME = "barsukas_translate"
DECOMPOSE_AGENT_NAME = "barsukas_decompose"


def _extract_batch_content(response: Dict[str, Any]) -> str:
    """Pull the message content out of one batch result, refusing truncated ones.

    ``finish_reason`` sits right next to the content and says whether the model
    finished or ran out of room. Without this check a response cut off at the
    token limit fails later on ``json.loads`` and is logged as an unspecified
    parse error -- which, for a batch applied hours after submission, gives no
    hint that the fix is a larger limit rather than a bad schema.

    Raises:
        ValueError: If the response was truncated or is missing its content.
    """
    choice = response["body"]["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        raise ValueError(
            "Response truncated at the output token limit (finish_reason='length'); "
            "the request needs a larger max_completion_tokens"
        )
    content = choice["message"]["content"]
    if not content:
        raise ValueError(f"Empty response content (finish_reason={finish_reason!r})")
    return str(content)


def apply_results_for_agent(
    agent_name: str, requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    """Dispatch to the right apply_* function based on the agent name.

    The Phase-1 (translate-only) and combined/Phase-3 batches have different
    response schemas; the agent name on each BatchQueue row tells us which.
    """
    if agent_name == TRANSLATE_AGENT_NAME:
        return apply_phase1_translation_results(requests, session, batch_id)
    return apply_sentence_translation_results(requests, session, batch_id)


def apply_sentence_translation_results(
    requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    """Apply completed OpenAI Batch results for sentence translation requests.

    Args:
        requests: Iterable of completed ``BatchQueue`` rows whose ``response_body``
            is the OpenAI batch result envelope and whose ``entity_id`` is the
            sentence id.
        session: SQLAlchemy session against the main linguistic database.
        batch_id: OpenAI batch ID, used for log messages only.

    Returns:
        ``{"updated": int, "failed": int}`` counters.
    """
    sentences_updated = 0
    failed = 0

    for req in requests:
        sentence_id = req.entity_id
        if not sentence_id:
            continue

        try:
            if not req.response_body:
                continue
            response = json.loads(req.response_body)
            content = _extract_batch_content(response)
            translations = json.loads(content)

            store_translation_results(sentence_id, translations, session)
            sentences_updated += 1

        except Exception as exc:
            failed += 1
            logger.error(
                "Failed to apply sentence translations for sentence %s (batch %s): %s",
                sentence_id,
                batch_id,
                exc,
            )
            session.rollback()

    return {"updated": sentences_updated, "failed": failed}


def apply_phase1_translation_results(
    requests: Iterable[BatchQueue], session: Any, batch_id: str
) -> Dict[str, int]:
    """Apply completed Phase-1 batch results (translations only, no word breakdown).

    The response payload is ``{lang: text, ...}`` per the Phase-1 schema. We
    strip out any accidental ``words_<lang>`` keys before forwarding to
    :func:`sentences.translation.store_translation_results`, which is shape-
    tolerant and only writes ``SentenceTranslation`` rows when no ``words_*``
    keys are present.
    """
    sentences_updated = 0
    failed = 0

    for req in requests:
        sentence_id = req.entity_id
        if not sentence_id:
            continue

        try:
            if not req.response_body:
                continue
            response = json.loads(req.response_body)
            content = _extract_batch_content(response)
            translations = json.loads(content)

            translations_only = {
                key: value
                for key, value in translations.items()
                if not str(key).startswith("words_")
            }
            store_translation_results(sentence_id, translations_only, session)
            sentences_updated += 1

        except Exception as exc:
            failed += 1
            logger.error(
                "Failed to apply Phase-1 translations for sentence %s (batch %s): %s",
                sentence_id,
                batch_id,
                exc,
            )
            session.rollback()

    return {"updated": sentences_updated, "failed": failed}
