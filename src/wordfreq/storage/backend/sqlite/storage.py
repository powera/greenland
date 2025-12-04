"""SQLite storage backend."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wordfreq.storage.backend.base import BaseStorage, BaseSession
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
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.SessionFactory = sessionmaker(bind=self.engine)

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
            ensure_tables_exist(session._sqlalchemy_session)

    def close(self) -> None:
        """Close the storage backend."""
        self.engine.dispose()
