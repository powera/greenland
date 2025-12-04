"""Storage backend abstraction layer.

This module provides a unified interface for different storage backends
(SQLite, JSONL) allowing the application to work with either backend
transparently.
"""

from wordfreq.storage.backend.factory import create_session, get_backend_type

__all__ = ["create_session", "get_backend_type"]
