"""The ``sentences.import.document`` capability: split a document into sentences.

Discovery only. This splits text into sentences, creates a bare ``Sentence``
with its source-language translation, and enqueues one ``sentences.import`` per
sentence. It makes no LLM calls -- every decision about a sentence belongs to
the per-sentence task, where it can be retried and inspected on its own.

That division is what makes a large document tractable: a 200-sentence document
becomes 200 independently retryable queue entries rather than one long task that
loses everything when sentence 187 fails.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import constants
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from workqueue.task_queue import enqueue_task
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

TASK_TYPE: str = "sentences.import.document"
IMPORT_TASK_TYPE: str = "sentences.import"


def do_import_document(
    session: Any,
    text: Optional[str] = None,
    input_path: Optional[str] = None,
    document_language: str = "en",
    source_name: Optional[str] = None,
    limit: Optional[int] = None,
    target_languages: Optional[List[str]] = None,
    decompose_languages: Optional[List[str]] = None,
    annotate_dependencies: bool = False,
    auto_promote: bool = False,
    tags: Optional[str] = None,
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Split a document and queue one import task per sentence.

    Args:
        session: Database session, owned by the worker.
        text: Document text. Mutually exclusive with ``input_path``.
        input_path: File to read instead of passing text inline.
        document_language: Language the document is written in.
        source_name: Provenance label; defaults to the file name.
        limit: Only take the first N sentences.
        target_languages: Passed through to each sentence's import task.
        decompose_languages: Passed through to each sentence's import task.
        annotate_dependencies: Passed through to each sentence's import task.
        auto_promote: Passed through to each sentence's import task.
        tags: Pre-serialized JSON tag array applied to words staged from this
            document.
        model: LLM model for the per-sentence tasks.

    Returns:
        A one-line summary naming how many sentences were created and queued.
    """
    from agents.genys.agent import GenysAgent

    if text is None and input_path is None:
        raise ValueError("Either text or input_path is required")

    if text is None:
        document_path = Path(str(input_path))
        text = document_path.read_text(encoding="utf-8")
        source_name = source_name or document_path.name

    label = source_name or "inline document"
    sentences = GenysAgent.split_sentences(text, document_language)
    if limit is not None:
        sentences = sentences[:limit]

    if not sentences:
        return f"{label}: no sentences found"

    queued = 0
    for sentence_text in sentences:
        sentence = add_sentence(
            session,
            source_filename=source_name,
            notes=f"Imported by {TASK_TYPE} from {label}",
        )
        add_sentence_translation(
            session,
            sentence=sentence,
            language_code=document_language,
            translation_text=sentence_text,
            verified=False,
        )
        session.flush()

        payload: Dict[str, Any] = {
            "sentence_id": sentence.id,
            "annotate_dependencies": annotate_dependencies,
            "auto_promote": auto_promote,
            "model": model,
            "source": f"{TASK_TYPE}/{label}",
            "tags": tags,
        }
        if target_languages:
            payload["target_languages"] = list(target_languages)
        if decompose_languages:
            payload["decompose_languages"] = list(decompose_languages)

        result = enqueue_task(
            session,
            task_type=IMPORT_TASK_TYPE,
            target_type="sentence",
            target_id=sentence.id,
            payload=payload,
            dedup_key=f"{IMPORT_TASK_TYPE}:{sentence.id}:0",
        )
        if result.created:
            queued += 1

    session.commit()
    logger.info("%s: created %d sentence(s), queued %d", label, len(sentences), queued)
    return f"{label}: {len(sentences)} sentence(s) created, {queued} queued for import"


handle_sentences_import_document = workqueue_payload_handler()(do_import_document)
"""Workqueue entry point for ``sentences.import.document``."""
