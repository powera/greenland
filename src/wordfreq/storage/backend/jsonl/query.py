"""JSONL query implementation."""

import operator
from typing import Any, Callable, List, Optional, Type, TypeVar, Union

from wordfreq.storage.backend.base.query import (
    BaseQuery,
    NoResultFound,
    MultipleResultsFound,
)

T = TypeVar("T")


class JSONLQuery(BaseQuery[T]):
    """JSONL query implementation using in-memory filtering."""

    def __init__(self, data: List[T], model_class: Type[T], session: "JSONLSession"):
        """Initialize JSONL query.

        Args:
            data: The data to query
            model_class: The model class being queried
            session: The session this query belongs to
        """
        self._data = data
        self._model_class = model_class
        self._session = session
        self._filters: List[Callable[[T], bool]] = []
        self._order_by_funcs: List[tuple] = []  # (key_func, reverse)
        self._limit_value: Optional[int] = None
        self._offset_value: int = 0

    def filter(self, *criterion: Any) -> "JSONLQuery[T]":
        """Filter query results by criteria.

        For JSONL backend, criterion should be a callable that takes an instance
        and returns a boolean, or a SQLAlchemy-style expression that we'll evaluate.

        Args:
            *criterion: Filter conditions

        Returns:
            A new JSONLQuery with the filter applied
        """
        new_query = self._clone()

        for crit in criterion:
            if callable(crit):
                new_query._filters.append(crit)
            else:
                # Try to evaluate SQLAlchemy-style expressions
                new_query._filters.append(lambda x, c=crit: self._evaluate_criterion(x, c))

        return new_query

    def filter_by(self, **kwargs: Any) -> "JSONLQuery[T]":
        """Filter query results by keyword arguments.

        Args:
            **kwargs: Field name and value pairs

        Returns:
            A new JSONLQuery with the filter applied
        """
        new_query = self._clone()

        for key, value in kwargs.items():
            new_query._filters.append(lambda x, k=key, v=value: getattr(x, k, None) == v)

        return new_query

    def order_by(self, *criterion: Any) -> "JSONLQuery[T]":
        """Order query results.

        Args:
            *criterion: Order by expressions (attribute names or callables)

        Returns:
            A new JSONLQuery with the ordering applied
        """
        new_query = self._clone()

        for crit in criterion:
            if isinstance(crit, str):
                # Simple attribute name
                reverse = crit.startswith("-")
                attr_name = crit[1:] if reverse else crit
                new_query._order_by_funcs.append((lambda x, a=attr_name: getattr(x, a, None), reverse))
            elif callable(crit):
                # Custom key function
                new_query._order_by_funcs.append((crit, False))
            else:
                # Try to extract attribute from SQLAlchemy-style expression
                new_query._order_by_funcs.append((self._extract_order_key(crit), False))

        return new_query

    def limit(self, limit: int) -> "JSONLQuery[T]":
        """Limit the number of results.

        Args:
            limit: Maximum number of results

        Returns:
            A new JSONLQuery with the limit applied
        """
        new_query = self._clone()
        new_query._limit_value = limit
        return new_query

    def offset(self, offset: int) -> "JSONLQuery[T]":
        """Skip a number of results.

        Args:
            offset: Number of results to skip

        Returns:
            A new JSONLQuery with the offset applied
        """
        new_query = self._clone()
        new_query._offset_value = offset
        return new_query

    def all(self) -> List[T]:
        """Execute the query and return all results.

        Returns:
            List of model instances
        """
        return list(self._execute())

    def first(self) -> Optional[T]:
        """Execute the query and return the first result.

        Returns:
            First model instance or None
        """
        results = self._execute()
        try:
            return next(results)
        except StopIteration:
            return None

    def one(self) -> T:
        """Execute the query and return exactly one result.

        Returns:
            The model instance

        Raises:
            NoResultFound: If no results
            MultipleResultsFound: If more than one result
        """
        results = list(self._execute())

        if len(results) == 0:
            raise NoResultFound(f"No results found for {self._model_class.__name__}")
        elif len(results) > 1:
            raise MultipleResultsFound(
                f"Multiple results found for {self._model_class.__name__}: {len(results)}"
            )

        return results[0]

    def one_or_none(self) -> Optional[T]:
        """Execute the query and return at most one result.

        Returns:
            The model instance or None

        Raises:
            MultipleResultsFound: If more than one result
        """
        results = list(self._execute())

        if len(results) > 1:
            raise MultipleResultsFound(
                f"Multiple results found for {self._model_class.__name__}: {len(results)}"
            )

        return results[0] if results else None

    def count(self) -> int:
        """Count the number of results.

        Returns:
            Number of results
        """
        return len(list(self._execute()))

    def exists(self) -> bool:
        """Check if any results exist.

        Returns:
            True if at least one result exists
        """
        return self.first() is not None

    def get(self, id: Any) -> Optional[T]:
        """Get a single instance by primary key.

        This is a convenience method equivalent to session.get(model_class, id).

        Args:
            id: The primary key value

        Returns:
            The instance or None if not found
        """
        return self._session.get(self._model_class, id)

    def delete(self, synchronize_session: Union[str, bool] = "auto") -> int:
        """Delete all matching records.

        Args:
            synchronize_session: Ignored for JSONL backend

        Returns:
            Number of deleted records
        """
        results = list(self._execute())

        for instance in results:
            self._session.delete(instance)

        return len(results)

    def update(self, values: dict, synchronize_session: Union[str, bool] = "auto") -> int:
        """Update all matching records.

        Args:
            values: Dictionary of field names and new values
            synchronize_session: Ignored for JSONL backend

        Returns:
            Number of updated records
        """
        results = list(self._execute())

        for instance in results:
            for key, value in values.items():
                setattr(instance, key, value)
            self._session.add(instance)

        return len(results)

    def join(self, *args, **kwargs) -> "JSONLQuery[T]":
        """Join with another table/model.

        For JSONL backend, joins are limited. This method is provided for
        compatibility but may raise NotImplementedError for complex joins.

        Returns:
            A new JSONLQuery
        """
        # For simple cases, return self
        # For complex joins, this would need custom implementation
        return self._clone()

    def distinct(self, *columns) -> "JSONLQuery[T]":
        """Return only distinct results.

        Args:
            *columns: Optional columns to make distinct on

        Returns:
            A new query with distinct applied
        """
        new_query = self._clone()

        # Apply distinct by tracking seen values
        if columns:
            # Distinct on specific columns
            seen = set()

            def distinct_filter(x):
                key = tuple(getattr(x, col, None) for col in columns)
                if key in seen:
                    return False
                seen.add(key)
                return True

            new_query._filters.append(distinct_filter)
        else:
            # Distinct on entire object (by identity)
            seen_ids = set()

            def distinct_filter(x):
                obj_id = id(x)
                if obj_id in seen_ids:
                    return False
                seen_ids.add(obj_id)
                return True

            new_query._filters.append(distinct_filter)

        return new_query

    def _execute(self):
        """Execute the query and yield results."""
        # Start with all data
        results = self._data

        # Apply filters
        for filter_func in self._filters:
            results = [x for x in results if filter_func(x)]

        # Apply ordering
        if self._order_by_funcs:
            for key_func, reverse in reversed(self._order_by_funcs):
                try:
                    results = sorted(results, key=key_func, reverse=reverse)
                except (TypeError, AttributeError):
                    # If sorting fails, skip it
                    pass

        # Apply offset and limit
        if self._offset_value:
            results = results[self._offset_value :]

        if self._limit_value is not None:
            results = results[: self._limit_value]

        return iter(results)

    def _clone(self) -> "JSONLQuery[T]":
        """Create a copy of this query."""
        new_query = JSONLQuery(self._data, self._model_class, self._session)
        new_query._filters = self._filters.copy()
        new_query._order_by_funcs = self._order_by_funcs.copy()
        new_query._limit_value = self._limit_value
        new_query._offset_value = self._offset_value
        return new_query

    def _evaluate_criterion(self, instance: T, criterion: Any) -> bool:
        """Evaluate a SQLAlchemy-style criterion against an instance.

        Args:
            instance: The model instance
            criterion: The criterion to evaluate

        Returns:
            True if the instance matches the criterion
        """
        # Try to evaluate SQLAlchemy-style expressions
        # This is a simplified implementation
        try:
            # Check if it's a comparison expression
            if hasattr(criterion, "left") and hasattr(criterion, "right"):
                left_val = self._get_value(instance, criterion.left)
                right_val = self._get_value(instance, criterion.right)

                # Determine the operator
                op_type = type(criterion).__name__

                if op_type == "BinaryExpression":
                    op = criterion.operator
                    if op == operator.eq:
                        return left_val == right_val
                    elif op == operator.ne:
                        return left_val != right_val
                    elif op == operator.lt:
                        return left_val < right_val
                    elif op == operator.le:
                        return left_val <= right_val
                    elif op == operator.gt:
                        return left_val > right_val
                    elif op == operator.ge:
                        return left_val >= right_val

            return True
        except Exception:
            return True

    def _get_value(self, instance: T, expr: Any) -> Any:
        """Get a value from an instance using an expression.

        Args:
            instance: The model instance
            expr: The expression

        Returns:
            The value
        """
        # If it's an attribute, get it from the instance
        if hasattr(expr, "key"):
            return getattr(instance, expr.key, None)
        # If it's a literal value
        return expr

    def _extract_order_key(self, criterion: Any) -> Callable:
        """Extract a sort key function from a criterion.

        Args:
            criterion: The order criterion

        Returns:
            A callable that extracts the sort key
        """
        # Try to extract attribute name
        if hasattr(criterion, "key"):
            attr_name = criterion.key
            return lambda x: getattr(x, attr_name, None)

        # Default to identity
        return lambda x: x
