"""Base session interface for storage backends."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar

T = TypeVar("T")


class BaseSession(ABC):
    """Abstract base class for storage sessions.

    This interface provides a SQLAlchemy-compatible API that can be
    implemented by different storage backends (SQLite, JSONL, etc.).
    """

    @abstractmethod
    def query(self, model_class: Type[T]) -> "BaseQuery[T]":
        """Create a query for the given model class.

        Args:
            model_class: The model class to query

        Returns:
            A query object that can be further filtered
        """
        pass

    @abstractmethod
    def get(self, model_class: Type[T], id: Any) -> Optional[T]:
        """Get a single instance by primary key.

        Args:
            model_class: The model class
            id: The primary key value

        Returns:
            The instance or None if not found
        """
        pass

    @abstractmethod
    def add(self, instance: Any) -> None:
        """Add an instance to the session (mark for saving).

        Args:
            instance: The model instance to add
        """
        pass

    @abstractmethod
    def delete(self, instance: Any) -> None:
        """Delete an instance from the session.

        Args:
            instance: The model instance to delete
        """
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit all pending changes to storage."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback all pending changes."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush pending changes (make them visible to queries but don't commit).

        For JSONL backend, this is the same as commit since we don't have transactions.
        For SQLite backend, this flushes to the database without committing the transaction.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the session and release resources."""
        pass

    @abstractmethod
    def refresh(self, instance: Any) -> None:
        """Refresh an instance from storage.

        Args:
            instance: The model instance to refresh
        """
        pass

    @abstractmethod
    def expunge(self, instance: Any) -> None:
        """Remove an instance from the session without deleting it.

        Args:
            instance: The model instance to expunge
        """
        pass

    @abstractmethod
    def get_bind(self) -> Any:
        """Get the underlying storage engine/connection.

        Returns:
            For SQLite: SQLAlchemy engine
            For JSONL: JSONLStorage instance
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()
