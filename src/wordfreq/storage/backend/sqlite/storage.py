"""SQLite storage backend."""

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from wordfreq.storage.backend.base import BaseSession, BaseStorage
from wordfreq.storage.backend.sqlite.session import SQLiteSession
from wordfreq.storage.models.schema import Base


class SQLiteStorage(BaseStorage):
    """SQLite storage backend implementation."""

    def __init__(self, db_path: str):
        """Initialize SQLite storage.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path

        # Create engine with settings optimized for concurrent access
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "timeout": 30,  # Wait up to 30 seconds for locks
                "check_same_thread": False,  # Allow multi-threaded access
            },
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        # Enable WAL mode for better concurrency (allows concurrent reads during writes)
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
            cursor.execute("PRAGMA synchronous=NORMAL")  # Faster, still safe with WAL
            cursor.close()

        self.SessionFactory: Any = sessionmaker(bind=self.engine)

    def create_session(self) -> BaseSession:
        """Create a new SQLite session.

        Returns:
            A new SQLiteSession instance
        """
        sqlalchemy_session = self.SessionFactory()
        return SQLiteSession(sqlalchemy_session)

    def ensure_initialized(self) -> None:
        """Ensure database tables exist."""
        # Import here to avoid circular imports
        from wordfreq.storage.utils.session import ensure_tables_exist

        # Create all tables
        Base.metadata.create_all(self.engine)

        # Add missing columns to existing tables
        with self.create_session() as session:
            # session is guaranteed to be SQLiteSession, which has _sqlalchemy_session
            if isinstance(session, SQLiteSession):
                ensure_tables_exist(session._sqlalchemy_session)  # type: ignore
            else:
                # Fallback for other session types
                pass

    def close(self) -> None:
        """Close the storage backend."""
        self.engine.dispose()
