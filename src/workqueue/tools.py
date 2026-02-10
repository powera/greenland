"""Common utilities for workqueue handlers.

This module provides shared functionality for workqueue handler functions
to eliminate repetitive code.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from barsukas.config import Config
import constants
from sqlalchemy.orm import Session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma


def build_default_config() -> DataSourceConfig:
    """
    Build default DataSourceConfig for workqueue handlers.

    This uses the standard Barsukas configuration (Config.DB_PATH,
    Config.DEBUG, constants.DEFAULT_MODEL).

    Returns:
        DataSourceConfig with standard settings

    Example:
        >>> config = build_default_config()
        >>> client = LinguisticClient(config=config)
    """
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def get_lemma_or_raise(session: Session, lemma_id: int) -> Lemma:
    """
    Retrieve a lemma by ID or raise ValueError if not found.

    This standardizes the lemma lookup pattern used across workqueue handlers.

    Args:
        session: Database session
        lemma_id: ID of the lemma to retrieve

    Returns:
        Lemma object

    Raises:
        ValueError: If lemma with given ID does not exist

    Example:
        >>> lemma = get_lemma_or_raise(session, payload["lemma_id"])
    """
    from storage.models.schema import Lemma

    lemma: Optional[Lemma] = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")
    return lemma


def extract_payload_param(
    payload: Dict[str, Any],
    key: str,
    default: Optional[Any] = None,
    required: bool = False,
) -> Any:
    """
    Extract a parameter from workqueue payload with optional default.

    Args:
        payload: Workqueue task payload dictionary
        key: Parameter key to extract
        default: Default value if key not present (only used if not required)
        required: If True, raises ValueError when key is missing

    Returns:
        Parameter value from payload or default

    Raises:
        ValueError: If required=True and key not in payload

    Example:
        >>> lemma_id = extract_payload_param(payload, "lemma_id", required=True)
        >>> lang_code = extract_payload_param(payload, "lang_code", default="en")
    """
    if required and key not in payload:
        raise ValueError(f"Required parameter '{key}' missing from payload")
    return payload.get(key, default)


def commit_or_raise(session: Session, error_prefix: str = "Database error") -> None:
    """
    Commit session or raise RuntimeError with context.

    This provides consistent error handling for session commits in workqueue handlers.

    Args:
        session: Database session to commit
        error_prefix: Prefix for error message if commit fails

    Raises:
        RuntimeError: If commit fails, with original exception message

    Example:
        >>> # Process lemma...
        >>> commit_or_raise(session, "Failed to save translations")
    """
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise RuntimeError(f"{error_prefix}: {e}") from e
