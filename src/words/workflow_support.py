"""Shared support functions for word-level workflows."""

from __future__ import annotations

import os

import constants
from barsukas.config import Config
from sqlalchemy.orm import Session

from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma


def build_default_config() -> DataSourceConfig:
    """Build the default configuration used by local word workflows."""
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        use_word2vec=os.environ.get("USE_WORD2VEC", "false").lower() == "true",
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def get_lemma_or_raise(session: Session, lemma_id: int) -> Lemma:
    """Return a lemma by ID or raise a user-facing validation error."""
    lemma = session.get(Lemma, lemma_id)
    if lemma is None:
        raise ValueError(f"Lemma {lemma_id} not found")
    return lemma
