"""Storage backend for database sessions.

This module provides session creation for SQLAlchemy-based storage.
"""

from typing import TYPE_CHECKING, Any

from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import (
    configure_backend,
    create_session,
    get_backend_type,
    get_data_source_config,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

__all__ = [
    "configure_backend",
    "create_session",
    "get_backend_type",
    "get_data_source_config",
    "BackendType",
    "DataSourceConfig",
    "Session",
]


def __getattr__(name: str) -> Any:
    """Lazy import for Session to avoid importing SQLAlchemy at module load time."""
    if name == "Session":
        from sqlalchemy.orm import Session

        return Session
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
