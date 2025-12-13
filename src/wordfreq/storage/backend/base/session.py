"""Base session interface for storage backends."""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Query as SQLAlchemyQuery

T = TypeVar("T")


class BaseSession(ABC):
    """Abstract base class for storage sessions.

    This interface provides a SQLAlchemy-compatible API that can be
    implemented by different storage backends (SQLite, JSONL, etc.).

    All backends return raw SQLAlchemy Query objects for querying.
    The difference between backends is in persistence (commit/rollback).
    """

    @abstractmethod
    def query(self, *entities, **kwargs) -> "SQLAlchemyQuery":
        """Create a query for the given model class or entities.

        Args:
            *entities: Model class(es) or column expression(s) to query
            **kwargs: Additional keyword arguments for the query

        Returns:
            A raw SQLAlchemy Query object (no wrapper)
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
