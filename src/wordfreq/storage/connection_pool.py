#!/usr/bin/python3

"""
Connection pool for SQLite connections to ensure thread safety.
This module provides a thread-safe connection pool for SQLite databases.
"""

import threading
import logging
from typing import Dict, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe connection pool for SQLite databases."""

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

    def get_engine(self, db_path: str, echo: bool = False) -> Engine:
        """
        Get or create a SQLAlchemy engine for the given database path.

        Args:
            db_path: Path to the SQLite database
            echo: Whether to enable SQLAlchemy echo mode

        Returns:
            SQLAlchemy engine
        """
        with self._lock:
            if db_path not in self._engines:
                # Create a new engine with the 'check_same_thread' flag set to False
                # which is required for SQLite to work in a multi-threaded environment
                conn_str = f"sqlite:///{db_path}"
                engine = create_engine(
                    conn_str, echo=echo, connect_args={"check_same_thread": False}
                )
                self._engines[db_path] = engine
                self._session_factories[db_path] = sessionmaker(bind=engine)
                logger.debug(f"Created new engine for {db_path}")
            return self._engines[db_path]

    def get_session(self, db_path: str, echo: bool = False) -> Session:
        """
        Get a thread-local session for the given database path.

        This method ensures that each thread gets its own session object.

        Args:
            db_path: Path to the SQLite database
            echo: Whether to enable SQLAlchemy echo mode

        Returns:
            Thread-local SQLAlchemy session
        """
        # Initialize thread_local sessions dict if it doesn't exist
        if not hasattr(self._thread_local, "sessions"):
            self._thread_local.sessions = {}

        # Create a new session for this thread if it doesn't exist
        if db_path not in self._thread_local.sessions:
            # Get or create the session factory
            self.get_engine(db_path, echo)

            # Create a new session for this thread
            session = self._session_factories[db_path]()
            self._thread_local.sessions[db_path] = session
            logger.debug(
                f"Created new session for {db_path} in thread {threading.current_thread().name}"
            )

        return self._thread_local.sessions[db_path]

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


def get_session(db_path: str, echo: bool = False) -> Session:
    """
    Get a thread-local session for the given database path.

    This is a convenience function that forwards to the singleton pool.

    Args:
        db_path: Path to the SQLite database
        echo: Whether to enable SQLAlchemy echo mode

    Returns:
        Thread-local SQLAlchemy session
    """
    return pool.get_session(db_path, echo)


def close_thread_sessions():
    """
    Close all sessions for the current thread.

    This is a convenience function that forwards to the singleton pool.
    """
    pool.close_thread_sessions()
