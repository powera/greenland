"""CRUD helpers for lemma embedding storage and nearest-neighbor lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from storage.models.schema import Lemma, LemmaEmbedding, LemmaTranslation


@dataclass
class LemmaEmbeddingMatch:
    """Nearest-neighbor match payload for semantic lookup."""

    lemma_id: int
    lemma_text: str
    definition_text: str
    language_code: str
    text_source: str
    source_text: str
    distance: float
    similarity: float


def _vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(value):.12g}" for value in values) + "]"


def upsert_lemma_embedding(
    session: Session,
    *,
    lemma_id: int,
    language_code: str,
    text_source: str,
    source_text: str,
    model_name: str,
    embedding: List[float],
    embedding_dim: int,
) -> LemmaEmbedding:
    """Create or update a lemma embedding row."""
    existing = (
        session.query(LemmaEmbedding)
        .filter(
            LemmaEmbedding.lemma_id == lemma_id,
            LemmaEmbedding.language_code == language_code,
            LemmaEmbedding.text_source == text_source,
            LemmaEmbedding.model_name == model_name,
        )
        .first()
    )

    vector_literal = _vector_literal(embedding)
    vector_norm = sum(component * component for component in embedding) ** 0.5

    if existing is None:
        row = LemmaEmbedding(
            lemma_id=lemma_id,
            language_code=language_code,
            text_source=text_source,
            source_text=source_text,
            model_name=model_name,
            embedding_dim=embedding_dim,
            embedding=vector_literal,
            embedding_norm=vector_norm,
        )
        session.add(row)
        session.flush()
        return row

    existing.source_text = source_text
    existing.embedding_dim = embedding_dim
    existing.embedding = vector_literal
    existing.embedding_norm = vector_norm
    session.flush()
    return existing


def nearest_lemma_embeddings(
    session: Session,
    *,
    query_embedding: List[float],
    language_code: str,
    model_name: str,
    limit: int = 20,
    exclude_lemma_id: Optional[int] = None,
    pos_type: Optional[str] = None,
    min_similarity: Optional[float] = None,
) -> List[LemmaEmbeddingMatch]:
    """Search nearest embeddings using pgvector cosine distance."""
    params: dict[str, object] = {
        "query_vector": _vector_literal(query_embedding),
        "language_code": language_code,
        "model_name": model_name,
        "limit": limit,
    }

    where_fragments: list[str] = [
        "e.language_code = :language_code",
        "e.model_name = :model_name",
    ]
    if exclude_lemma_id is not None:
        where_fragments.append("e.lemma_id != :exclude_lemma_id")
        params["exclude_lemma_id"] = exclude_lemma_id
    if pos_type is not None:
        where_fragments.append("l.pos_type = :pos_type")
        params["pos_type"] = pos_type
    if min_similarity is not None:
        where_fragments.append(
            "(1 - (e.embedding <=> CAST(:query_vector AS vector))) >= :min_similarity"
        )
        params["min_similarity"] = min_similarity

    sql = text(
        f"""
        SELECT
            e.lemma_id,
            l.lemma_text,
            l.definition_text,
            e.language_code,
            e.text_source,
            e.source_text,
            (e.embedding <=> CAST(:query_vector AS vector)) AS distance,
            (1 - (e.embedding <=> CAST(:query_vector AS vector))) AS similarity
        FROM lemma_embeddings e
        JOIN lemmas l ON l.id = e.lemma_id
        WHERE {" AND ".join(where_fragments)}
        ORDER BY e.embedding <=> CAST(:query_vector AS vector)
        LIMIT :limit
        """
    )

    rows = session.execute(sql, params).all()
    matches: list[LemmaEmbeddingMatch] = []
    for row in rows:
        matches.append(
            LemmaEmbeddingMatch(
                lemma_id=int(row.lemma_id),
                lemma_text=str(row.lemma_text),
                definition_text=str(row.definition_text),
                language_code=str(row.language_code),
                text_source=str(row.text_source),
                source_text=str(row.source_text),
                distance=float(row.distance),
                similarity=float(row.similarity),
            )
        )

    return matches


def get_lemmas_for_embedding_refresh(
    session: Session,
    *,
    language_code: str,
    limit: Optional[int] = None,
) -> List[Lemma]:
    """Fetch lemmas eligible for embedding generation.

    Fixed phrases (see ``NON_LEXEME_POS_TYPES``) are excluded: they are not single
    concepts and should not appear as semantic-similarity candidates.
    """
    from storage.translation_helpers import NON_LEXEME_POS_TYPES

    query = session.query(Lemma).filter(Lemma.pos_type.notin_(NON_LEXEME_POS_TYPES))
    if language_code != "en":
        query = query.join(
            LemmaTranslation,
            (LemmaTranslation.lemma_id == Lemma.id)
            & (LemmaTranslation.language_code == language_code),
        ).filter(LemmaTranslation.translation.isnot(None), LemmaTranslation.translation != "")

    query = query.order_by(Lemma.id.asc())
    if limit is not None:
        query = query.limit(limit)
    result: list[Lemma] = query.all()
    return result
