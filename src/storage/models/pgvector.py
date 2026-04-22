"""Custom SQLAlchemy type for PostgreSQL pgvector columns."""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Sequence

from sqlalchemy.types import UserDefinedType


class PGVector(UserDefinedType):
    """Minimal pgvector column type.

    This type stores values in PostgreSQL's ``vector(N)`` format and supports
    binding from Python sequences of floats.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: object) -> str:
        _ = kw
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, dialect: object) -> Optional[Callable[..., Optional[str]]]:
        _ = dialect

        def process(value: Optional[Sequence[float] | str]) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return _to_pgvector_literal(value)

        return process


def _to_pgvector_literal(values: Iterable[float]) -> str:
    """Serialize a float iterable to pgvector literal syntax."""
    return "[" + ",".join(f"{float(value):.12g}" for value in values) + "]"
