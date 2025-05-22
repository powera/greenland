#!/usr/bin/python3

"""Unit tests for the ConnectionPool class."""

import unittest
import threading
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock

# Add the src directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from wordfreq.connection_pool import ConnectionPool, get_session, close_thread_sessions


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
        self.patch_logger = patch('wordfreq.connection_pool.logger')
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
        self.assertTrue(hasattr(pool1, '_engines'))
        self.assertTrue(hasattr(pool1, '_session_factories'))
        self.assertTrue(hasattr(pool1, '_thread_local'))

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
        self.assertTrue(hasattr(pool._thread_local, 'sessions'))
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
        session1.close = MagicMock()
        session2.close = MagicMock()
        
        # Close all sessions
        pool.close_thread_sessions()
        
        # Verify close was called on both sessions
        session1.close.assert_called_once()
        session2.close.assert_called_once()
        
        # Verify sessions dict is empty
        self.assertEqual(pool._thread_local.sessions, {})

    def test_multiple_threads_concurrency(self):
        """Test that multiple threads can use the connection pool concurrently."""
        # Create a shared pool
        pool = ConnectionPool()
        
        # Track success/failure for each thread
        results = {}
        
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
        # Get a session using the convenience function
        session1 = get_session(self.db_path)
        
        # Verify we can get the same session again
        session2 = get_session(self.db_path)
        self.assertIs(session1, session2, "Should return the same session for the same thread and db_path")
        
        # Create a different session for a different db
        different_db_path = os.path.join(self.temp_dir.name, "different.db")
        different_session = get_session(different_db_path)
        self.assertIsNot(session1, different_session, "Should return different sessions for different db_paths")
        
        # Mock the session.close methods to verify they're called
        session1.close = MagicMock()
        different_session.close = MagicMock()
        
        # Close sessions using the convenience function
        close_thread_sessions()
        
        # Verify close was called on both sessions
        session1.close.assert_called_once()
        different_session.close.assert_called_once()
        
        # Verify we get a new session after closing
        new_session = get_session(self.db_path)
        self.assertIsNot(session1, new_session, "Should return a new session after closing")


if __name__ == "__main__":
    unittest.main()