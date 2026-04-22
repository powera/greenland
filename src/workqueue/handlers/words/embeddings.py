"""Capability handlers for word embedding refresh tasks."""

from __future__ import annotations

from typing import Any, Optional

from storage.backend import get_data_source_config
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler
from words.word2vec import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TEXT_SOURCE,
    rebuild_embeddings,
    refresh_lemma_embedding,
)


def do_refresh_embedding(
    session: Any,
    lemma_id: int,
    lang_code: str = "en",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    text_source: str = DEFAULT_TEXT_SOURCE,
) -> str:
    """Refresh a single lemma embedding."""
    config = get_data_source_config()
    lemma = get_lemma_or_raise(session, lemma_id)
    refresh_lemma_embedding(
        session=session,
        config=config,
        lemma=lemma,
        language_code=lang_code,
        model_name=model_name,
        text_source=text_source,
    )
    session.commit()
    return f"Refreshed embedding for lemma {lemma_id} ({lang_code})"


def do_rebuild_embeddings(
    session: Any,
    lang_code: str = "en",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    text_source: str = DEFAULT_TEXT_SOURCE,
    limit: Optional[int] = None,
) -> str:
    """Refresh a batch of lemma embeddings."""
    config = get_data_source_config()
    stats = rebuild_embeddings(
        session=session,
        config=config,
        language_code=lang_code,
        model_name=model_name,
        text_source=text_source,
        limit=limit,
    )
    session.commit()
    return (
        f"Embedding rebuild complete: processed={stats['processed']} "
        f"refreshed={stats['refreshed']} failed={stats['failed']}"
    )


@workqueue_payload_handler()
def handle_words_embeddings(
    session: Any,
    lemma_id: Optional[int] = None,
    lang_code: str = "en",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    text_source: str = DEFAULT_TEXT_SOURCE,
    limit: Optional[int] = None,
) -> str:
    """Workqueue wrapper for embedding refresh/rebuild."""
    if lemma_id is not None:
        return do_refresh_embedding(
            session=session,
            lemma_id=lemma_id,
            lang_code=lang_code,
            model_name=model_name,
            text_source=text_source,
        )
    return do_rebuild_embeddings(
        session=session,
        lang_code=lang_code,
        model_name=model_name,
        text_source=text_source,
        limit=limit,
    )
