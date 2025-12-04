"""Factory for creating storage backend sessions."""

from typing import Optional

from wordfreq.storage.backend.base import BaseSession, BaseStorage
from wordfreq.storage.backend.config import BackendConfig, BackendType


_global_config: Optional[BackendConfig] = None
_global_storage: Optional[BaseStorage] = None


def configure_backend(config: BackendConfig) -> None:
    """Configure the global backend.

    Args:
        config: Backend configuration
    """
    global _global_config, _global_storage
    _global_config = config
    _global_storage = None  # Reset storage to force recreation


def get_backend_type() -> BackendType:
    """Get the configured backend type.

    Returns:
        The backend type
    """
    global _global_config
    if _global_config is None:
        _global_config = BackendConfig.from_env()
    return _global_config.backend_type


def get_backend_config() -> BackendConfig:
    """Get the global backend configuration.

    Returns:
        The backend configuration
    """
    global _global_config
    if _global_config is None:
        _global_config = BackendConfig.from_env()
    return _global_config


def get_storage() -> BaseStorage:
    """Get or create the global storage backend.

    Returns:
        The storage backend
    """
    global _global_storage, _global_config

    if _global_storage is None:
        if _global_config is None:
            _global_config = BackendConfig.from_env()

        if _global_config.backend_type == BackendType.SQLITE:
            from wordfreq.storage.backend.sqlite import SQLiteStorage

            _global_storage = SQLiteStorage(_global_config.sqlite_path)
        else:  # JSONL
            from wordfreq.storage.backend.jsonl import JSONLStorage

            _global_storage = JSONLStorage(_global_config.jsonl_data_dir)

        _global_storage.ensure_initialized()

    return _global_storage


def create_session(config: Optional[BackendConfig] = None) -> BaseSession:
    """Create a new storage session.

    Args:
        config: Optional backend configuration. If not provided, uses global config.

    Returns:
        A new session instance
    """
    if config is not None:
        # Create a one-off session with specific config
        if config.backend_type == BackendType.SQLITE:
            from wordfreq.storage.backend.sqlite import SQLiteStorage

            storage = SQLiteStorage(config.sqlite_path)
        else:  # JSONL
            from wordfreq.storage.backend.jsonl import JSONLStorage

            storage = JSONLStorage(config.jsonl_data_dir)

        storage.ensure_initialized()
        return storage.create_session()
    else:
        # Use global storage
        storage = get_storage()
        return storage.create_session()


def create_scoped_session_factory(config: Optional[BackendConfig] = None):
    """Create a scoped session factory compatible with Flask.

    Args:
        config: Optional backend configuration

    Returns:
        A callable that returns sessions (compatible with Flask's scoped_session pattern)
    """

    class SessionFactory:
        """Session factory that creates sessions on demand."""

        def __init__(self, config: Optional[BackendConfig] = None):
            self.config = config

        def __call__(self):
            """Create a new session."""
            return create_session(self.config)

    return SessionFactory(config)
