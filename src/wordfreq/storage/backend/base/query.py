"""Base query interface for storage backends."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, List, Optional, TypeVar, Union

T = TypeVar("T")


class BaseQuery(ABC, Generic[T]):
    """Abstract base class for query builders.

    This interface provides a SQLAlchemy-compatible query API that can be
    implemented by different storage backends.
    """

    @abstractmethod
    def filter(self, *criterion: Any) -> "BaseQuery[T]":
        """Filter query results by criteria.

        Args:
            *criterion: Filter conditions (SQLAlchemy expressions or backend-specific)

        Returns:
            A new query with the filter applied
        """
        pass

    @abstractmethod
    def filter_by(self, **kwargs: Any) -> "BaseQuery[T]":
        """Filter query results by keyword arguments.

        Args:
            **kwargs: Field name and value pairs

        Returns:
            A new query with the filter applied
        """
        pass

    @abstractmethod
    def order_by(self, *criterion: Any) -> "BaseQuery[T]":
        """Order query results.

        Args:
            *criterion: Order by expressions

        Returns:
            A new query with the ordering applied
        """
        pass

    @abstractmethod
    def limit(self, limit: int) -> "BaseQuery[T]":
        """Limit the number of results.

        Args:
            limit: Maximum number of results

        Returns:
            A new query with the limit applied
        """
        pass

    @abstractmethod
    def offset(self, offset: int) -> "BaseQuery[T]":
        """Skip a number of results.

        Args:
            offset: Number of results to skip

        Returns:
            A new query with the offset applied
        """
        pass

    @abstractmethod
    def all(self) -> List[T]:
        """Execute the query and return all results.

        Returns:
            List of model instances
        """
        pass

    @abstractmethod
    def first(self) -> Optional[T]:
        """Execute the query and return the first result.

        Returns:
            First model instance or None
        """
        pass

    @abstractmethod
    def one(self) -> T:
        """Execute the query and return exactly one result.

        Returns:
            The model instance

        Raises:
            NoResultFound: If no results
            MultipleResultsFound: If more than one result
        """
        pass

    @abstractmethod
    def one_or_none(self) -> Optional[T]:
        """Execute the query and return at most one result.

        Returns:
            The model instance or None

        Raises:
            MultipleResultsFound: If more than one result
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Count the number of results.

        Returns:
            Number of results
        """
        pass

    @abstractmethod
    def exists(self) -> bool:
        """Check if any results exist.

        Returns:
            True if at least one result exists
        """
        pass

    @abstractmethod
    def delete(self, synchronize_session: Union[str, bool] = "auto") -> int:
        """Delete all matching records.

        Args:
            synchronize_session: How to synchronize the session (ignored for JSONL)

        Returns:
            Number of deleted records
        """
        pass

    @abstractmethod
    def update(self, values: dict, synchronize_session: Union[str, bool] = "auto") -> int:
        """Update all matching records.

        Args:
            values: Dictionary of field names and new values
            synchronize_session: How to synchronize the session (ignored for JSONL)

        Returns:
            Number of updated records
        """
        pass

    @abstractmethod
    def join(self, *args, **kwargs) -> "BaseQuery[T]":
        """Join with another table/model.

        For JSONL backend, this may be limited or raise NotImplementedError
        for complex joins.

        Returns:
            A new query with the join applied
        """
        pass

    @abstractmethod
    def distinct(self, *columns) -> "BaseQuery[T]":
        """Return only distinct results.

        Args:
            *columns: Optional columns to make distinct on

        Returns:
            A new query with distinct applied
        """
        pass


class NoResultFound(Exception):
    """Raised when a query expected one result but found none."""

    pass


class MultipleResultsFound(Exception):
    """Raised when a query expected one result but found multiple."""

    pass
