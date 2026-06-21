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

    def __init__(self, dimensions: Optional[int] = None) -> None:
        # ``dimensions`` is optional so the type can also be instantiated with
        # no arguments during reflection (see ``_register_reflection_type``),
        # where the column's dimension is not needed.
        self.dimensions = dimensions

    def get_col_spec(self, **kw: object) -> str:
        _ = kw
        if self.dimensions is None:
            return "VECTOR"
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


def _register_reflection_type() -> None:
    """Teach the PostgreSQL dialect to reflect ``vector`` columns as PGVector.

    Without this, ``Inspector.get_columns()`` on a table with a pgvector column
    logs ``SAWarning: Did not recognize type 'vector'`` and falls back to
    ``NullType``. Registering the name in the dialect's ``ischema_names`` maps
    the reflected ``vector`` type back to :class:`PGVector`. Best-effort: if the
    PostgreSQL dialect is unavailable (e.g. psycopg2 not installed in a
    SQLite-only environment) the import simply does nothing.
    """
    try:
        from sqlalchemy.dialects.postgresql.base import PGDialect
    except Exception:  # pragma: no cover - postgres dialect not importable
        return

    PGDialect.ischema_names.setdefault("vector", PGVector)


_register_reflection_type()
