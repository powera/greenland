"""SQLite session wrapper."""

from typing import Any, Optional, Type, TypeVar

from sqlalchemy.orm import Session as SQLAlchemySession

from wordfreq.storage.backend.base import BaseSession, BaseQuery
from wordfreq.storage.backend.sqlite.query import SQLiteQuery

T = TypeVar("T")


class SQLiteSession(BaseSession):
    """SQLite session implementation that wraps SQLAlchemy Session."""

    def __init__(self, sqlalchemy_session: SQLAlchemySession):
        """Initialize SQLite session.

        Args:
            sqlalchemy_session: The underlying SQLAlchemy session
        """
        self._sqlalchemy_session = sqlalchemy_session

    def query(self, *entities, **kwargs) -> BaseQuery[T]:
        """Create a query for the given model class or column expressions.

        Args:
            *entities: Model class(es) or column expression(s) to query
            **kwargs: Additional keyword arguments for the query

        Returns:
            A SQLiteQuery instance
        """
        sqlalchemy_query = self._sqlalchemy_session.query(*entities, **kwargs)
        # Use the first entity as the model class if it's a type, otherwise None
        model_class = entities[0] if entities and isinstance(entities[0], type) else None
        return SQLiteQuery(sqlalchemy_query, model_class)

    def get(self, model_class: Type[T], id: Any) -> Optional[T]:
        """Get a single instance by primary key.

        Args:
            model_class: The model class
            id: The primary key value

        Returns:
            The instance or None if not found
        """
        return self._sqlalchemy_session.get(model_class, id)

    def add(self, instance: Any) -> None:
        """Add an instance to the session.

        Args:
            instance: The model instance to add
        """
        self._sqlalchemy_session.add(instance)

    def delete(self, instance: Any) -> None:
        """Delete an instance from the session.

        Args:
            instance: The model instance to delete
        """
        self._sqlalchemy_session.delete(instance)

    def commit(self) -> None:
        """Commit all pending changes."""
        self._sqlalchemy_session.commit()

    def rollback(self) -> None:
        """Rollback all pending changes."""
        self._sqlalchemy_session.rollback()

    def flush(self) -> None:
        """Flush pending changes."""
        self._sqlalchemy_session.flush()

    def close(self) -> None:
        """Close the session."""
        self._sqlalchemy_session.close()

    def refresh(self, instance: Any) -> None:
        """Refresh an instance from storage.

        Args:
            instance: The model instance to refresh
        """
        self._sqlalchemy_session.refresh(instance)

    def expunge(self, instance: Any) -> None:
        """Remove an instance from the session.

        Args:
            instance: The model instance to expunge
        """
        self._sqlalchemy_session.expunge(instance)

    def get_bind(self) -> Any:
        """Get the underlying SQLAlchemy engine.

        Returns:
            The SQLAlchemy engine
        """
        return self._sqlalchemy_session.get_bind()
