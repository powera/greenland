"""Connection pragmas shared by every SQLite engine in the project.

There is more than one place that builds a SQLite engine -- the
``DataSourceConfig`` path in :mod:`storage.backend.factory` and the thread-local
pool in :mod:`storage.connection_pool` -- and they must agree on these settings.
When they did not, the pool's engine ran with SQLite's default
``busy_timeout=0``: WAL lets a writer and readers coexist, but it does not make
a *second* writer wait, so any write that met a held lock failed instantly with
"database is locked" instead of retrying.  That is what made a concurrent
gandras import and voras run collide on the query log.

Anything that creates a SQLite engine should call :func:`apply_sqlite_pragmas`
on it rather than repeating the pragma list.
"""

from typing import Any

# Wait this long for a held write lock before raising "database is locked".
# SQLite's default is 0 -- fail immediately -- which is wrong for a project that
# routinely runs a long-lived agent alongside an interactive one.
BUSY_TIMEOUT_MS = 30000


def apply_sqlite_pragmas(engine: Any) -> None:
    """Register the connect-time pragmas every SQLite connection needs.

    Args:
        engine: A SQLAlchemy engine bound to SQLite.  Registering the listener
            on a non-SQLite engine would emit invalid SQL, so call this only on
            the SQLite branch of engine construction.
    """
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        # WAL lets readers proceed during a write.
        cursor.execute("PRAGMA journal_mode=WAL")
        # ...and busy_timeout makes a second *writer* wait rather than fail.
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # Safe to relax under WAL: a crash can lose the last commit, not the db.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
