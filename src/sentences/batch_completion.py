"""Shared logic to apply OpenAI Batch results for sentence translations.

Used by both:
- ``agents/common/batch.py`` (CLI ``batch complete --batch-id <id>``)
- ``barsukas`` background batch poller

The batch's request bodies must target ``/v1/chat/completions`` with a JSON
schema response_format (see ``sentences.translation.build_response_schema``).
Each request's ``entity_id`` is the sentence id whose translations should be
written by ``sentences.translation.store_translation_results``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable

from clients.batch_queue import BatchQueue
from sentences.translation import store_translation_results

logger = logging.getLogger(__name__)


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
            content = response["body"]["choices"][0]["message"]["content"]
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
