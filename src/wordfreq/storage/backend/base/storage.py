"""Base storage interface for storage backends."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseStorage(ABC):
    """Abstract base class for storage backends.

    This interface provides methods for initializing and managing
    the underlying storage system.
    """

    @abstractmethod
    def create_session(self) -> "BaseSession":
        """Create a new session for this storage backend.

        Returns:
            A new session instance
        """
        pass

    @abstractmethod
    def ensure_initialized(self) -> None:
        """Ensure the storage backend is properly initialized.

        For SQLite: Ensure tables exist
        For JSONL: Ensure directory structure exists
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the storage backend and release resources."""
        pass

    def __enter__(self):
        """Context manager entry."""
        self.ensure_initialized()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
