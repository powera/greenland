#!/usr/bin/python3

"""Tests for how database sessions are created and owned.

``storage.backend.create_session`` builds a *new* Session on a *cached*
Engine.  That split is the whole contract: the engine holds the connection
pool (a real one for PostgreSQL -- pool_size, max_overflow, pre-ping), while
each caller gets its own unit of work to open, use, and close.

This replaces the old ``storage.connection_pool``, which cached *Sessions*
per thread and handed the same object to every caller.  Sharing a Session
that way meant a caller closing "its" session cleared the identity map and
discarded uncommitted work belonging to whoever else was holding it, and
nothing raised, because a closed Session reopens lazily.
"""

import os
import tempfile
import unittest

from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig


class TestCreateSessionOwnership(unittest.TestCase):
    """Each create_session call returns a session its caller owns."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_each_call_returns_a_distinct_session(self) -> None:
        first = create_session(self.config)
        second = create_session(self.config)
        try:
            self.assertIsNot(
                first,
                second,
                "sessions must not be shared between callers -- closing one "
                "would then discard the other's uncommitted work",
            )
        finally:
            first.close()
            second.close()

    def test_closing_one_session_does_not_disturb_another(self) -> None:
        """The property the shared-session pool could not provide."""
        from sqlalchemy import text

        keeper = create_session(self.config)
        try:
            other = create_session(self.config)
            other.close()
            # keeper is unaffected by an unrelated caller closing its own.
            self.assertEqual(keeper.execute(text("select 1")).scalar(), 1)
        finally:
            keeper.close()

    def test_sessions_share_a_cached_engine(self) -> None:
        """Connection pooling lives on the engine, which *is* reused."""
        first = create_session(self.config)
        second = create_session(self.config)
        try:
            self.assertIs(
                first.get_bind(),
                second.get_bind(),
                "engines are cached, so connection setup is not repeated",
            )
        finally:
            first.close()
            second.close()


class TestNoSharedSessionCache(unittest.TestCase):
    """The shared per-thread Session cache must not come back."""

    def test_connection_pool_module_is_gone(self) -> None:
        with self.assertRaises(ImportError):
            import storage.connection_pool  # noqa: F401

    def test_corpus_helpers_own_the_sessions_they_close(self) -> None:
        """corpus.py closes its fallback session, so it must create its own.

        These helpers take an optional session and build one when the caller
        passes none, closing it in a ``finally``.  That is only correct while
        the fallback is ``create_session``; taking it from a shared cache made
        them close a session other callers were still using.
        """
        import inspect

        import wordfreq.frequency.corpus as corpus

        source = inspect.getsource(corpus)
        self.assertNotIn("connection_pool", source)
        self.assertIn("create_session(session_config)", source)


if __name__ == "__main__":
    unittest.main()
