"""Common utilities for workqueue handlers.

This module provides shared functionality for workqueue handler functions
in barsukas/*/wq_worker.py modules to eliminate repetitive code.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Optional

from barsukas.config import Config
import constants
from sqlalchemy.orm import Session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import Lemma


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
    from wordfreq.storage.models.schema import Lemma

    lemma = session.get(Lemma, lemma_id)
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


def lemma_handler(func: Callable) -> Callable:
    """
    Decorator that injects lemma lookup and session commit into handler.

    Transforms a function with signature:
        func(session, lemma, payload) -> str

    Into a standard workqueue handler:
        handle_func(session, payload) -> str

    That extracts lemma_id, looks up lemma, calls function, and commits.

    Example:
        >>> @lemma_handler
        >>> def handle_add_missing_translations(session, lemma, payload):
        >>>     added_count, errors = generate_missing_translations_for_lemma(session, lemma)
        >>>     if errors and added_count == 0:
        >>>         raise RuntimeError("; ".join(errors))
        >>>     return f"Added {added_count} translation(s)"
    """
    @wraps(func)
    def wrapper(session: Session, payload: Dict[str, Any]) -> str:
        lemma_id = payload["lemma_id"]
        lemma = get_lemma_or_raise(session, lemma_id)

        result = func(session, lemma, payload)

        session.commit()

        return result

    return wrapper


def workqueue_handler(
    task_name: str,
    payload_defaults: Optional[Dict[str, Any]] = None,
    result_formatter: Optional[Callable[[Any], str]] = None,
) -> Callable:
    """
    Decorator to auto-generate workqueue handler from business logic function.

    This decorator keeps the original business logic function unchanged (for CLI use)
    and creates a handle_{task_name}(session, payload) function for workqueue use.

    The decorator handles:
    - Extracting lemma_id from payload and looking up lemma
    - Extracting additional payload parameters
    - Calling the business logic function
    - Formatting the result into a string message
    - Committing the session

    Args:
        task_name: Name of the workqueue task (e.g., "add_missing_translations")
        payload_defaults: Optional dict of default values for payload parameters
                         (e.g., {"lang_code": "en"})
        result_formatter: Optional function to format return value into string message
                         If None, assumes business logic returns a string or has simple repr

    Example:
        >>> @workqueue_handler(
        >>>     "add_missing_translations",
        >>>     result_formatter=lambda r: f"Added {r[0]} translation(s)"
        >>> )
        >>> def generate_missing_translations_for_lemma(
        >>>     session, lemma, config=None, **kwargs
        >>> ):
        >>>     # business logic unchanged - still called by CLI agents
        >>>     return added_count, errors
        >>>
        >>> # Auto-generates: handle_add_missing_translations(session, payload)

    The generated handler is attached to the original function as ._handler and
    can be accessed for registration in TASK_HANDLERS.
    """
    if payload_defaults is None:
        payload_defaults = {}

    def decorator(func: Callable) -> Callable:
        # Keep original function unchanged for CLI use
        @wraps(func)
        def original_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Create the workqueue handler function
        def handler(session: Session, payload: Dict[str, Any]) -> str:
            # Extract lemma_id and get lemma
            lemma_id = payload["lemma_id"]
            lemma = get_lemma_or_raise(session, lemma_id)

            # Extract additional payload parameters with defaults
            kwargs = {}
            for key, default_value in payload_defaults.items():
                kwargs[key] = payload.get(key, default_value)

            # Call business logic function
            # Most business logic functions take (session, lemma, config=None, **kwargs)
            result = func(session, lemma, **kwargs)

            # Format result message
            if result_formatter:
                message = result_formatter(result)
            elif isinstance(result, str):
                message = result
            else:
                # Default: convert to string
                message = str(result)

            # Commit session
            session.commit()

            return message

        # Attach handler to original function for registration
        handler.__name__ = f"handle_{task_name}"
        original_wrapper._handler = handler
        original_wrapper._task_name = task_name

        return original_wrapper

    return decorator
