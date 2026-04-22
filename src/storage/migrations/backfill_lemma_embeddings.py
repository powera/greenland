#!/usr/bin/env python3
"""Backfill lemma embeddings in PostgreSQL using pgvector."""

import argparse
import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from words.word2vec import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TEXT_SOURCE,
    rebuild_embeddings,
)


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build config for embedding backfill runs."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=db_path,
    )


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Backfill lemma embeddings (Postgres + pgvector)")
    parser.add_argument(
        "--db-path",
        default="data/wordfreq/linguistics.sqlite",
        help="SQLite database path (kept for interface compatibility; not supported for embeddings)",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL backend (required)",
    )
    parser.add_argument("--lang", default="en", help="Language code for embedding backfill")
    parser.add_argument(
        "--limit", type=int, default=None, help="Optional maximum lemmas to process"
    )
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="OpenAI embedding model")
    parser.add_argument(
        "--text-source",
        default=DEFAULT_TEXT_SOURCE,
        help="Embedding text source: composite|lemma|definition|translation",
    )
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    if config.backend_type != BackendType.POSTGRES:
        raise RuntimeError("Lemma embeddings require --postgres (SQLite is not supported).")

    print(f"Backend: {config.backend_type.value}")
    print(f"Language: {args.lang}")
    print(f"Model: {args.model}")
    print(f"Text source: {args.text_source}")
    print(f"Limit: {args.limit}")

    with create_session(config) as session:
        stats = rebuild_embeddings(
            session=session,
            config=config,
            language_code=args.lang,
            model_name=args.model,
            text_source=args.text_source,
            limit=args.limit,
        )
        session.commit()

    print(
        "Backfill complete: "
        f"processed={stats['processed']} refreshed={stats['refreshed']} failed={stats['failed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
