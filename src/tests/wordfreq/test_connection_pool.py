#!/usr/bin/python3

"""Unit tests for the ConnectionPool class."""

import os
import sys
import tempfile
import threading
import unittest
from typing import Dict, Union
from unittest.mock import patch

# Add the src directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from storage.backend.config import BackendType, DataSourceConfig
from storage.connection_pool import ConnectionPool, close_thread_sessions, get_session


class TestConnectionPool(unittest.TestCase):
    """Tests for the ConnectionPool class."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary directory for test database files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")

        # Reset the singleton instance for each test
        ConnectionPool._instance = None
        ConnectionPool._initialized = False

        # Create a patch for the logger to avoid logging during tests
        self.patch_logger = patch("storage.connection_pool.logger")
        self.mock_logger = self.patch_logger.start()

    def tearDown(self):
        """Clean up after test."""
        # Stop patches
        self.patch_logger.stop()

        # Clean up temporary directory
        self.temp_dir.cleanup()

        # Reset the singleton instance after each test
        ConnectionPool._instance = None

    def test_singleton_pattern(self):
        """Test that ConnectionPool implements the singleton pattern correctly."""
        # Create two instances
        pool1 = ConnectionPool()
        pool2 = ConnectionPool()

        # Verify they are the same instance
        self.assertIs(pool1, pool2)

        # Verify the singleton instance is initialized
        self.assertTrue(pool1._initialized)
        self.assertTrue(hasattr(pool1, "_engines"))
        self.assertTrue(hasattr(pool1, "_session_factories"))
        self.assertTrue(hasattr(pool1, "_thread_local"))

    def test_get_engine_creates_engine(self):
        """Test that get_engine creates a new engine when one doesn't exist."""
        pool = ConnectionPool()

        # Verify no engines exist initially
        self.assertEqual(len(pool._engines), 0)

        # Get an engine
        engine = pool.get_engine(self.db_path)

        # Verify an engine was created
        self.assertEqual(len(pool._engines), 1)
        self.assertIn(self.db_path, pool._engines)
        self.assertEqual(engine, pool._engines[self.db_path])

        # Verify a session factory was also created
        self.assertIn(self.db_path, pool._session_factories)

    def test_get_session_creates_session(self):
        """Test that get_session creates a new session when one doesn't exist."""
        pool = ConnectionPool()

        # Get a session
        session = pool.get_session(self.db_path)

        # Verify a session was created
        self.assertTrue(hasattr(pool._thread_local, "sessions"))
        self.assertIn(self.db_path, pool._thread_local.sessions)
        self.assertEqual(session, pool._thread_local.sessions[self.db_path])

        # Verify an engine was also created
        self.assertIn(self.db_path, pool._engines)

    def test_thread_local_sessions(self):
        """Test that sessions are thread-local."""
        pool = ConnectionPool()

        # Create a session in the main thread
        main_session = pool.get_session(self.db_path)

        # Store sessions from threads
        thread_sessions = {}

        def thread_func(thread_id):
            # Get a session in this thread
            thread_session = pool.get_session(self.db_path)
            thread_sessions[thread_id] = thread_session

        # Create and run threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify each thread got a different session
        for i in range(3):
            self.assertIsNot(main_session, thread_sessions[i])

        # Verify thread sessions are different from each other
        self.assertIsNot(thread_sessions[0], thread_sessions[1])
        self.assertIsNot(thread_sessions[1], thread_sessions[2])
        self.assertIsNot(thread_sessions[0], thread_sessions[2])

    def test_close_thread_sessions(self):
        """Test that close_thread_sessions closes all sessions for the current thread."""
        pool = ConnectionPool()

        # Create multiple sessions
        session1 = pool.get_session(self.db_path)
        session2 = pool.get_session(os.path.join(self.temp_dir.name, "test2.db"))

        # Mock the session.close method to verify it's called
        with (
            patch.object(session1, "close") as close_session1,
            patch.object(session2, "close") as close_session2,
        ):
            # Close all sessions
            pool.close_thread_sessions()

        # Verify close was called on both sessions
        close_session1.assert_called_once()
        close_session2.assert_called_once()

        # Verify sessions dict is empty
        self.assertEqual(pool._thread_local.sessions, {})

    def test_multiple_threads_concurrency(self):
        """Test that multiple threads can use the connection pool concurrently."""
        # Create a shared pool
        pool = ConnectionPool()

        # Track success/failure for each thread: True, or the failure message.
        results: Dict[int, Union[bool, str]] = {}

        def thread_func(thread_id):
            try:
                # Get a session
                session = pool.get_session(self.db_path)

                # Use the session (just verify it exists)
                self.assertIsNotNone(session)

                # Close the session
                pool.close_thread_sessions()

                # Record success
                results[thread_id] = True
            except Exception as e:
                # Record failure
                results[thread_id] = str(e)

        # Create and run threads
        threads = []
        for i in range(10):  # Use 10 threads to stress test
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all threads succeeded
        for i in range(10):
            self.assertTrue(results[i], f"Thread {i} failed: {results[i]}")

    def test_convenience_functions(self):
        """Test the convenience functions get_session and close_thread_sessions."""
        config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=self.db_path)

        # Get a session using the convenience function
        session1 = get_session(config)

        # Verify we can get the same session again
        session2 = get_session(config)
        self.assertIs(
            session1, session2, "Should return the same session for the same thread and db_path"
        )

        # Create a different session for a different db
        different_db_path = os.path.join(self.temp_dir.name, "different.db")
        different_config = DataSourceConfig(
            backend_type=BackendType.SQLITE, sqlite_path=different_db_path
        )
        different_session = get_session(different_config)
        self.assertIsNot(
            session1, different_session, "Should return different sessions for different db_paths"
        )

        # Mock the session.close methods to verify they're called
        with (
            patch.object(session1, "close") as close_session1,
            patch.object(different_session, "close") as close_different_session,
        ):
            # Close sessions using the convenience function
            close_thread_sessions()

        # Verify close was called on both sessions
        close_session1.assert_called_once()
        close_different_session.assert_called_once()

        # Verify we get a new session after closing
        new_session = get_session(config)
        self.assertIsNot(session1, new_session, "Should return a new session after closing")


class TestPooledSessionOwnership(unittest.TestCase):
    """The pool owns the sessions it hands out; callers must not close them.

    ``get_session`` returns a *shared* thread-local session, so a caller that
    closes it closes an object the pool still caches and hands to the next
    caller.  Code that wants a session of its own calls
    ``storage.backend.create_session`` instead, which builds a fresh one.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        ConnectionPool._instance = None
        ConnectionPool._initialized = False
        self.config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=self.db_path)

    def tearDown(self):
        close_thread_sessions()
        self.temp_dir.cleanup()
        ConnectionPool._instance = None

    def test_pooled_session_is_shared_not_owned(self) -> None:
        """Two callers on one thread get the same object, so neither owns it."""
        self.assertIs(get_session(self.config), get_session(self.config))

    def test_closing_a_pooled_session_leaves_it_cached(self) -> None:
        """Closing a pooled session does not evict it -- which is the bug.

        A closed SQLAlchemy session reopens lazily, so this fails quietly
        rather than raising: the next caller receives an object whose state
        was discarded out from under it.  ``close_thread_sessions`` is the
        supported way to release pooled sessions.
        """
        session = get_session(self.config)
        session.close()
        self.assertIs(
            get_session(self.config),
            session,
            "a directly-closed session is still handed to the next caller",
        )

    def test_create_session_returns_an_owned_session(self) -> None:
        """The factory hands out a fresh session that its caller may close."""
        from storage.backend import create_session

        owned = create_session(self.config)
        try:
            self.assertIsNot(owned, get_session(self.config))
            self.assertIsNot(owned, create_session(self.config))
        finally:
            owned.close()


class TestCorpusHelpersDoNotClosePooledSessions(unittest.TestCase):
    """wordfreq.frequency.corpus must not close sessions it does not own.

    Its helpers take an optional session and fall back to making their own,
    closing it in a ``finally`` when they do.  That is only correct while the
    fallback is the factory: taking it from the pool made them close a shared
    session (see :class:`TestPooledSessionOwnership`).
    """

    def test_corpus_module_does_not_use_the_connection_pool(self) -> None:
        import inspect

        import wordfreq.frequency.corpus as corpus

        source = inspect.getsource(corpus)
        self.assertNotIn(
            "connection_pool.get_session",
            source,
            "corpus.py closes the sessions it creates, so it must use "
            "storage.backend.create_session rather than the shared pool",
        )


if __name__ == "__main__":
    unittest.main()
