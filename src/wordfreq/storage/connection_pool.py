#!/usr/bin/python3

"""
Connection pool for database connections to ensure thread safety.
This module provides a thread-safe connection pool for SQLite and cloud databases.
"""

import threading
import logging
from typing import Dict, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from wordfreq.storage.utils.database_url import get_database_url, get_engine_options

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe connection pool for SQLite and cloud databases."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern implementation with thread safety."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConnectionPool, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Initialize the connection pool."""
        # Skip initialization if already done
        if self._initialized:
            return

        with self._lock:
            if not self._initialized:
                self._engines: Dict[str, Engine] = {}
                self._session_factories: Dict[str, sessionmaker] = {}
                self._thread_local = threading.local()
                self._initialized = True
                logger.debug("Connection pool initialized")

    def get_engine(self, db_path: Optional[str] = None, echo: bool = False) -> Engine:
        """
        Get or create a SQLAlchemy engine for the given database path or URL.

        This method supports both SQLite file paths and cloud database URLs.
        If DATABASE_URL environment variable is set, it takes precedence.

        Args:
            db_path: Optional path to SQLite database or database URL.
                    If None, uses DATABASE_URL env var or default from constants.
            echo: Whether to enable SQLAlchemy echo mode

        Returns:
            SQLAlchemy engine

        Examples:
            >>> pool.get_engine()  # Uses DATABASE_URL or default
            >>> pool.get_engine('/path/to/db.sqlite')  # SQLite
            >>> pool.get_engine('postgresql://user:pass@host/db')  # PostgreSQL
        """
        with self._lock:
            # Get the database URL (handles env vars and defaults)
            db_url = get_database_url(db_path)

            # Use the URL as the cache key
            cache_key = db_url

            if cache_key not in self._engines:
                # Get database-specific engine options
                url, connect_args = get_engine_options(db_url, echo)

                # Create the engine with appropriate options
                engine = create_engine(url, echo=echo, connect_args=connect_args)

                self._engines[cache_key] = engine
                self._session_factories[cache_key] = sessionmaker(bind=engine)
                logger.debug(f"Created new engine for {cache_key}")

            return self._engines[cache_key]

    def get_session(self, db_path: Optional[str] = None, echo: bool = False) -> Session:
        """
        Get a thread-local session for the given database path or URL.

        This method ensures that each thread gets its own session object.
        Supports both SQLite file paths and cloud database URLs.

        Args:
            db_path: Optional path to SQLite database or database URL.
                    If None, uses DATABASE_URL env var or default from constants.
            echo: Whether to enable SQLAlchemy echo mode

        Returns:
            Thread-local SQLAlchemy session

        Examples:
            >>> pool.get_session()  # Uses DATABASE_URL or default
            >>> pool.get_session('/path/to/db.sqlite')  # SQLite
            >>> pool.get_session('postgresql://user:pass@host/db')  # PostgreSQL
        """
        # Initialize thread_local sessions dict if it doesn't exist
        if not hasattr(self._thread_local, "sessions"):
            self._thread_local.sessions = {}

        # Get the database URL (handles env vars and defaults)
        db_url = get_database_url(db_path)
        cache_key = db_url

        # Create a new session for this thread if it doesn't exist
        if cache_key not in self._thread_local.sessions:
            # Get or create the session factory
            self.get_engine(db_path, echo)

            # Create a new session for this thread
            session = self._session_factories[cache_key]()
            self._thread_local.sessions[cache_key] = session
            logger.debug(
                f"Created new session for {cache_key} in thread {threading.current_thread().name}"
            )

        return self._thread_local.sessions[cache_key]

    def close_thread_sessions(self):
        """Close all sessions for the current thread."""
        if hasattr(self._thread_local, "sessions"):
            for db_path, session in self._thread_local.sessions.items():
                session.close()
                logger.debug(
                    f"Closed session for {db_path} in thread {threading.current_thread().name}"
                )
            self._thread_local.sessions = {}


# Create a global instance
pool = ConnectionPool()


def get_session(db_path: Optional[str] = None, echo: bool = False) -> Session:
    """
    Get a thread-local session for the given database path or URL.

    This is a convenience function that forwards to the singleton pool.
    Supports both SQLite file paths and cloud database URLs.

    Args:
        db_path: Optional path to SQLite database or database URL.
                If None, uses DATABASE_URL env var or default from constants.
        echo: Whether to enable SQLAlchemy echo mode

    Returns:
        Thread-local SQLAlchemy session

    Examples:
        >>> get_session()  # Uses DATABASE_URL or default
        >>> get_session('/path/to/db.sqlite')  # SQLite
        >>> get_session('postgresql://user:pass@host/db')  # PostgreSQL
    """
    return pool.get_session(db_path, echo)


def close_thread_sessions():
    """
    Close all sessions for the current thread.

    This is a convenience function that forwards to the singleton pool.
    """
    pool.close_thread_sessions()
