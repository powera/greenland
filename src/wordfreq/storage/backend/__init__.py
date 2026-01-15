"""Storage backend for database sessions.

This module provides session creation for SQLAlchemy-based storage.
"""

from sqlalchemy.orm import Session

from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import (
    create_session,
    get_backend_type,
    get_data_source_config,
)

__all__ = [
    "create_session",
    "get_backend_type",
    "get_data_source_config",
    "BackendType",
    "DataSourceConfig",
    "Session",
]
