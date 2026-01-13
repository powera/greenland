"""Storage backend abstraction layer.

This module provides a unified interface for different storage backends
(SQLite, JSONL) allowing the application to work with either backend
transparently.
"""

from typing import Optional

from wordfreq.storage.backend.base import BaseSession
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session, get_backend_type

__all__ = ["create_session", "get_backend_type", "BaseSession", "BackendType", "DataSourceConfig"]
