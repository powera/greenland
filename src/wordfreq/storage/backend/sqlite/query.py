"""SQLite query wrapper."""

from typing import Any, List, Optional, Type, TypeVar, Union

from sqlalchemy.orm import Query as SQLAlchemyQuery

from wordfreq.storage.backend.base.query import (
    BaseQuery,
    NoResultFound,
    MultipleResultsFound,
)

T = TypeVar("T")


class SQLiteQuery(BaseQuery[T]):
    """SQLite query implementation that wraps SQLAlchemy Query."""

    def __init__(self, sqlalchemy_query: SQLAlchemyQuery, model_class: Type[T]):
        """Initialize SQLite query.

        Args:
            sqlalchemy_query: The underlying SQLAlchemy query
            model_class: The model class being queried
        """
        self._sqlalchemy_query = sqlalchemy_query
        self._model_class = model_class

    def filter(self, *criterion: Any) -> "SQLiteQuery[T]":
        """Filter query results by criteria.

        Args:
            *criterion: SQLAlchemy filter conditions

        Returns:
            A new SQLiteQuery with the filter applied
        """
        new_query = self._sqlalchemy_query.filter(*criterion)
        return SQLiteQuery(new_query, self._model_class)

    def filter_by(self, **kwargs: Any) -> "SQLiteQuery[T]":
        """Filter query results by keyword arguments.

        Args:
            **kwargs: Field name and value pairs

        Returns:
            A new SQLiteQuery with the filter applied
        """
        new_query = self._sqlalchemy_query.filter_by(**kwargs)
        return SQLiteQuery(new_query, self._model_class)

    def order_by(self, *criterion: Any) -> "SQLiteQuery[T]":
        """Order query results.

        Args:
            *criterion: Order by expressions

        Returns:
            A new SQLiteQuery with the ordering applied
        """
        new_query = self._sqlalchemy_query.order_by(*criterion)
        return SQLiteQuery(new_query, self._model_class)

    def limit(self, limit: int) -> "SQLiteQuery[T]":
        """Limit the number of results.

        Args:
            limit: Maximum number of results

        Returns:
            A new SQLiteQuery with the limit applied
        """
        new_query = self._sqlalchemy_query.limit(limit)
        return SQLiteQuery(new_query, self._model_class)

    def offset(self, offset: int) -> "SQLiteQuery[T]":
        """Skip a number of results.

        Args:
            offset: Number of results to skip

        Returns:
            A new SQLiteQuery with the offset applied
        """
        new_query = self._sqlalchemy_query.offset(offset)
        return SQLiteQuery(new_query, self._model_class)

    def all(self) -> List[T]:
        """Execute the query and return all results.

        Returns:
            List of model instances
        """
        return self._sqlalchemy_query.all()

    def first(self) -> Optional[T]:
        """Execute the query and return the first result.

        Returns:
            First model instance or None
        """
        return self._sqlalchemy_query.first()

    def one(self) -> T:
        """Execute the query and return exactly one result.

        Returns:
            The model instance

        Raises:
            NoResultFound: If no results
            MultipleResultsFound: If more than one result
        """
        try:
            return self._sqlalchemy_query.one()
        except Exception as e:
            # Map SQLAlchemy exceptions to our base exceptions
            error_name = type(e).__name__
            if "NoResultFound" in error_name:
                raise NoResultFound(str(e))
            elif "MultipleResultsFound" in error_name:
                raise MultipleResultsFound(str(e))
            else:
                raise

    def one_or_none(self) -> Optional[T]:
        """Execute the query and return at most one result.

        Returns:
            The model instance or None

        Raises:
            MultipleResultsFound: If more than one result
        """
        try:
            return self._sqlalchemy_query.one_or_none()
        except Exception as e:
            error_name = type(e).__name__
            if "MultipleResultsFound" in error_name:
                raise MultipleResultsFound(str(e))
            else:
                raise

    def count(self) -> int:
        """Count the number of results.

        Returns:
            Number of results
        """
        return self._sqlalchemy_query.count()

    def exists(self) -> bool:
        """Check if any results exist.

        Returns:
            True if at least one result exists
        """
        return self._sqlalchemy_query.first() is not None

    def delete(self, synchronize_session: Union[str, bool] = "auto") -> int:
        """Delete all matching records.

        Args:
            synchronize_session: How to synchronize the session

        Returns:
            Number of deleted records
        """
        return self._sqlalchemy_query.delete(synchronize_session=synchronize_session)

    def update(self, values: dict, synchronize_session: Union[str, bool] = "auto") -> int:
        """Update all matching records.

        Args:
            values: Dictionary of field names and new values
            synchronize_session: How to synchronize the session

        Returns:
            Number of updated records
        """
        return self._sqlalchemy_query.update(values, synchronize_session=synchronize_session)

    def join(self, *args, **kwargs) -> "SQLiteQuery[T]":
        """Join with another table/model.

        Returns:
            A new SQLiteQuery with the join applied
        """
        new_query = self._sqlalchemy_query.join(*args, **kwargs)
        return SQLiteQuery(new_query, self._model_class)

    def distinct(self, *columns) -> "SQLiteQuery[T]":
        """Return only distinct results.

        Args:
            *columns: Optional columns to make distinct on

        Returns:
            A new query with distinct applied
        """
        if columns:
            new_query = self._sqlalchemy_query.distinct(*columns)
        else:
            new_query = self._sqlalchemy_query.distinct()
        return SQLiteQuery(new_query, self._model_class)

    def get(self, ident: Any) -> Optional[T]:
        """Get a record by primary key.

        Args:
            ident: The primary key value

        Returns:
            The model instance or None if not found
        """
        return self._sqlalchemy_query.get(ident)

    def group_by(self, *criterion: Any) -> "SQLiteQuery[T]":
        """Group query results by one or more columns.

        Args:
            *criterion: Group by expressions

        Returns:
            A new SQLiteQuery with the grouping applied
        """
        new_query = self._sqlalchemy_query.group_by(*criterion)
        return SQLiteQuery(new_query, self._model_class)
