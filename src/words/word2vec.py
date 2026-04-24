#!/usr/bin/python3

"""PostgreSQL pgvector helpers for lemma embedding refresh and similarity."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests
from sqlalchemy.orm import Session

from clients.keys import load_key
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.lemma_embedding import (
    LemmaEmbeddingMatch,
    get_lemmas_for_embedding_refresh,
    nearest_lemma_embeddings,
    upsert_lemma_embedding,
)
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

OPENAI_EMBEDDING_API_BASE = "https://api.openai.com/v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIM = 1536
DEFAULT_TEXT_SOURCE = "composite"


class EmbeddingBackendError(RuntimeError):
    """Raised when embedding operations are attempted on unsupported backend."""


@dataclass
class SynonymSuggestion:
    """Suggestion payload for manual synonym candidate review."""

    lemma_id: int
    lemma_text: str
    definition_text: str
    language_code: str
    text_source: str
    source_text: str
    distance: float
    similarity: float


def _require_postgres(config: DataSourceConfig) -> None:
    if config.backend_type != BackendType.POSTGRES:
        raise EmbeddingBackendError(
            "word2vec requires BackendType.POSTGRES with pgvector; SQLite is not supported."
        )
    if not config.use_word2vec:
        raise EmbeddingBackendError(
            "word2vec is disabled. Re-run with --use_word2vec (or USE_WORD2VEC=true)."
        )


def _get_openai_embedding(text: str, model_name: str, timeout_seconds: int = 30) -> List[float]:
    api_key = load_key("openai", required=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"input": text, "model": model_name}

    response = requests.post(
        f"{OPENAI_EMBEDDING_API_BASE}/embeddings",
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    parsed = response.json()
    data = parsed.get("data", [])
    if not data:
        raise RuntimeError("OpenAI embeddings endpoint returned empty data list.")

    embedding = data[0].get("embedding")
    if not isinstance(embedding, list):
        raise RuntimeError("OpenAI embeddings response did not include a numeric embedding list.")
    return [float(component) for component in embedding]


def build_embedding_input(
    lemma: Lemma,
    language_code: str,
    session: Session,
    text_source: str = DEFAULT_TEXT_SOURCE,
) -> str:
    """Build canonical embedding text from lemma data."""
    if language_code == "en":
        localized_word = lemma.lemma_text
    else:
        localized_word = get_translation(session, lemma, language_code) or lemma.lemma_text

    if text_source == "lemma":
        return localized_word
    if text_source == "definition":
        return lemma.definition_text
    if text_source == "translation":
        return localized_word

    return (
        f"word: {localized_word}\n"
        f"english: {lemma.lemma_text}\n"
        f"definition: {lemma.definition_text}\n"
        f"pos: {lemma.pos_type}"
    )


def refresh_lemma_embedding(
    session: Session,
    *,
    config: DataSourceConfig,
    lemma: Lemma,
    language_code: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    text_source: str = DEFAULT_TEXT_SOURCE,
) -> int:
    """Generate and upsert a single lemma embedding."""
    _require_postgres(config)

    source_text = build_embedding_input(
        lemma=lemma,
        language_code=language_code,
        session=session,
        text_source=text_source,
    )
    vector = _get_openai_embedding(source_text, model_name=model_name)
    if len(vector) != DEFAULT_EMBEDDING_DIM:
        raise ValueError(
            f"Unexpected embedding length {len(vector)} for model {model_name}; "
            f"expected {DEFAULT_EMBEDDING_DIM}."
        )

    row = upsert_lemma_embedding(
        session,
        lemma_id=lemma.id,
        language_code=language_code,
        text_source=text_source,
        source_text=source_text,
        model_name=model_name,
        embedding=vector,
        embedding_dim=len(vector),
    )
    return row.id


def rebuild_embeddings(
    session: Session,
    *,
    config: DataSourceConfig,
    language_code: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    text_source: str = DEFAULT_TEXT_SOURCE,
    limit: Optional[int] = None,
) -> dict[str, int]:
    """Batch-refresh embeddings for lemmas in a language."""
    _require_postgres(config)
    lemmas = get_lemmas_for_embedding_refresh(session, language_code=language_code, limit=limit)

    refreshed = 0
    failed = 0
    for lemma in lemmas:
        try:
            refresh_lemma_embedding(
                session=session,
                config=config,
                lemma=lemma,
                language_code=language_code,
                model_name=model_name,
                text_source=text_source,
            )
            refreshed += 1
        except Exception as error:
            failed += 1
            logger.warning(
                "Failed embedding refresh for lemma_id=%s language=%s: %s",
                lemma.id,
                language_code,
                error,
            )

    return {"processed": len(lemmas), "refreshed": refreshed, "failed": failed}


def suggest_similar_lemmas(
    session: Session,
    *,
    config: DataSourceConfig,
    query_text: str,
    language_code: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    top_k: int = 20,
    exclude_lemma_id: Optional[int] = None,
    pos_type: Optional[str] = None,
    min_similarity: Optional[float] = None,
) -> List[SynonymSuggestion]:
    """Return top semantic candidates for manual synonym selection."""
    _require_postgres(config)
    query_embedding = _get_openai_embedding(query_text, model_name=model_name)
    matches: List[LemmaEmbeddingMatch] = nearest_lemma_embeddings(
        session,
        query_embedding=query_embedding,
        language_code=language_code,
        model_name=model_name,
        limit=top_k,
        exclude_lemma_id=exclude_lemma_id,
        pos_type=pos_type,
        min_similarity=min_similarity,
    )
    return [
        SynonymSuggestion(
            lemma_id=match.lemma_id,
            lemma_text=match.lemma_text,
            definition_text=match.definition_text,
            language_code=match.language_code,
            text_source=match.text_source,
            source_text=match.source_text,
            distance=match.distance,
            similarity=match.similarity,
        )
        for match in matches
    ]
