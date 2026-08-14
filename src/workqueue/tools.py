"""Common utilities for workqueue handlers.

This module provides shared functionality for workqueue handler functions
to eliminate repetitive code.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

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
        use_word2vec=os.environ.get("USE_WORD2VEC", "false").lower() == "true",
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


TaskCallable = TypeVar("TaskCallable", bound=Callable[..., str])


def workqueue_payload_handler() -> (
    Callable[[TaskCallable], Callable[[Session, Dict[str, Any]], str]]
):
    """Wrap a do_* task function into a standard workqueue `(session, payload)` handler.

    The wrapped function keeps direct-call ergonomics for agents during migration
    (for example, `do_generate_forms(session, lemma_id=1, language_code='lt')`) while
    the worker can call the generated `handle_*` wrapper with payload dicts.
    """

    def decorator(func: TaskCallable) -> Callable[[Session, Dict[str, Any]], str]:
        @wraps(func)
        def wrapped(session: Session, payload: Dict[str, Any]) -> str:
            return func(session=session, **payload)

        return wrapped

    return decorator
