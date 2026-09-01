"""Every SQLite engine must set the same connection pragmas.

The bug these guard against: one of the engine builders was created without the
pragma listener, so it ran at SQLite's default ``busy_timeout=0``.
WAL lets a writer and readers coexist but does not make a second *writer* wait,
so a query-log write that met a lock held by another agent failed immediately
with "database is locked" rather than retrying.  The assertions below read the
pragmas back off a real connection, so a future engine that skips them fails
here instead of in production.
"""

import os
import tempfile
import unittest
from typing import Any

from sqlalchemy import text

from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import _create_engine
from storage.backend.sqlite.storage import SQLiteStorage
from storage.backend.sqlite_pragmas import BUSY_TIMEOUT_MS


def _read_pragmas(engine: Any) -> dict:
    """Return the pragmas actually in effect on a fresh connection."""
    with engine.connect() as conn:
        return {
            "journal_mode": conn.execute(text("PRAGMA journal_mode")).scalar(),
            "busy_timeout": conn.execute(text("PRAGMA busy_timeout")).scalar(),
            "synchronous": conn.execute(text("PRAGMA synchronous")).scalar(),
        }


class SqlitePragmaTests(unittest.TestCase):
    def setUp(self) -> None:
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(handle)

    def tearDown(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.unlink(path)

    def _assert_configured(self, engine: Any, label: str) -> None:
        pragmas = _read_pragmas(engine)
        self.assertEqual(pragmas["journal_mode"], "wal", f"{label}: journal_mode")
        # The regression: this read back 0 on the unconfigured engine.
        self.assertEqual(pragmas["busy_timeout"], BUSY_TIMEOUT_MS, f"{label}: busy_timeout")
        # synchronous=NORMAL is 1.
        self.assertEqual(pragmas["synchronous"], 1, f"{label}: synchronous")

    def test_factory_engine_sets_pragmas(self) -> None:
        self._assert_configured(_create_engine(self.db_path), "factory")

    def test_sqlite_storage_engine_sets_pragmas(self) -> None:
        self._assert_configured(SQLiteStorage(self.db_path).engine, "SQLiteStorage")

    def test_busy_timeout_is_nonzero(self) -> None:
        """A zero timeout is the specific setting that caused the failure."""
        self.assertGreater(BUSY_TIMEOUT_MS, 0)


if __name__ == "__main__":
    unittest.main()
