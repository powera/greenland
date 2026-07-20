"""Factory for creating SQLAlchemy database sessions."""

import threading
from typing import TYPE_CHECKING, Any, Callable, Optional

from storage.backend.config import BackendType, DataSourceConfig

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session, sessionmaker

_global_config: Optional[DataSourceConfig] = None
_global_engine: Optional["Engine"] = None
_global_session_factory: Optional["sessionmaker"] = None

# Cache engines by connection string to avoid creating new connections per request
_engine_cache: dict[str, "Engine"] = {}
_engine_initialized: set[str] = set()  # Track which engines have had tables ensured

# Guards engine creation and the create_all() that follows it. Barsukas runs
# Flask, the task worker, and the batch poller as threads in one process, so
# without this two threads can both see an uncached engine, both run
# create_all(), and the loser raises "table ... already exists".
_engine_lock = threading.Lock()

# Cache JSONL storage instances to avoid re-loading data from disk on every request.
# Since JSONL mode is read-only, the storage can be safely shared across sessions.
_jsonl_storage_cache: dict[str, Any] = {}  # data_dir -> JSONLStorage


def _create_engine(db_path: str, readonly: bool = False) -> "Engine":
    """Create a SQLAlchemy engine with appropriate settings.

    Args:
        db_path: Path to the database file (for SQLite) or connection string
        readonly: For PostgreSQL, open every connection in a read-only
            transaction so the server rejects any write or DDL. Ignored for
            SQLite (there is no per-connection read-only mode used here).

    Returns:
        Configured SQLAlchemy engine
    """
    from sqlalchemy import create_engine, event

    # Determine if this is SQLite or another database
    if db_path.startswith("postgresql://") or db_path.startswith("mysql://"):
        # For other databases, use the path as-is
        connection_string = db_path
        engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,  # Keep 5 connections ready in the pool
            max_overflow=10,  # Allow up to 15 total connections during bursts
        )

        if db_path.startswith("postgresql://"):
            # PgBouncer (Supabase pooler) silently drops the options=
            # search_path parameter from connection URLs, so we must set
            # search_path explicitly on every new connection.
            import constants as _constants

            pg_schema = _constants.POSTGRES_SCHEMA

            @event.listens_for(engine, "connect")
            def _set_pg_search_path(dbapi_conn: Any, connection_record: Any) -> None:
                cursor = dbapi_conn.cursor()
                cursor.execute(f"SET search_path TO {pg_schema}")
                if readonly:
                    # Enforce read-only at the server: any INSERT/UPDATE/DELETE
                    # or DDL on this connection fails. This is our DB-layer
                    # guard since there is no dedicated read-only role.
                    cursor.execute("SET default_transaction_read_only = on")
                cursor.close()

    else:
        # SQLite - use file path
        connection_string = f"sqlite:///{db_path}"
        engine = create_engine(
            connection_string,
            connect_args={
                "timeout": 30,
                "check_same_thread": False,
            },
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        # Enable WAL mode for SQLite for better concurrency
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


def _ensure_tables_exist(engine: "Engine") -> None:
    """Ensure database tables exist.

    Args:
        engine: SQLAlchemy engine
    """
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    # Import models package to ensure ALL models (including OperationLog,
    # GrammarFact, etc.) are registered with Base.metadata before create_all.
    # Without this, tables for models not yet imported would be silently skipped.
    import storage.models  # noqa: F401
    from storage.models.schema import Base

    from sqlalchemy.exc import OperationalError

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    try:
        Base.metadata.create_all(engine)
    except OperationalError as create_error:
        # create_all(checkfirst=True) inspects the schema first, but a second
        # connection with a stale WAL view (e.g. the metrics-instrumentation
        # probe session opening concurrently on first run) can still race and
        # lose to another creator, raising "table ... already exists". That is
        # benign: the table now exists, which is all we wanted.
        if "already exists" not in str(create_error).lower():
            raise

    # Add missing columns to existing tables
    from storage.utils.session import ensure_tables_exist

    with Session(engine) as session:
        ensure_tables_exist(session)
        if engine.dialect.name == "postgresql":
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_lemma_embeddings_model_lang "
                    "ON lemma_embeddings (model_name, language_code)"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_lemma_embeddings_vector_cosine "
                    "ON lemma_embeddings USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            )
            session.commit()


def configure_backend(config: DataSourceConfig) -> None:
    """Configure the global backend.

    Args:
        config: Data source configuration
    """
    global _global_config, _global_engine, _global_session_factory
    _global_config = config
    _global_engine = None
    _global_session_factory = None


def get_data_source_config() -> DataSourceConfig:
    """Get the global data source configuration.

    Returns:
        The data source configuration; a default SQLite configuration if
        configure_backend() has not been called.
    """
    global _global_config
    if _global_config is None:
        _global_config = DataSourceConfig(backend_type=BackendType.SQLITE)
    return _global_config


def get_configured_backend_config() -> Optional[DataSourceConfig]:
    """Get the global config only if configure_backend() was actually called.

    Unlike get_data_source_config(), this never invents a default: callers that
    need to know whether the process declared its main database (e.g. the S3
    staging prefix) get None when it has not.
    """
    return _global_config


def get_backend_type() -> "BackendType":
    """Get the configured backend type.

    Returns:
        The backend type (for display/logging purposes)
    """
    return get_data_source_config().backend_type


def _get_engine() -> "Engine":
    """Get or create the global database engine.

    Returns:
        SQLAlchemy engine
    """
    global _global_engine, _global_config

    # See _engine_lock: creation and the create_all() that follows must be
    # atomic, or concurrent threads race to create the same tables.
    with _engine_lock:
        if _global_engine is None:
            if _global_config is None:
                _global_config = DataSourceConfig(backend_type=BackendType.SQLITE)

            # Choose the correct path based on backend type
            if _global_config.backend_type == BackendType.POSTGRES:
                assert (
                    _global_config.postgres_url is not None
                ), "postgres_url must be set for POSTGRES backend"
                engine = _create_engine(_global_config.postgres_url)
            else:
                assert (
                    _global_config.sqlite_path is not None
                ), "sqlite_path must be set for SQLITE backend"
                engine = _create_engine(_global_config.sqlite_path)

            _ensure_tables_exist(engine)
            # Publish only after the schema is ready, so another thread cannot
            # observe a half-initialized engine.
            _global_engine = engine

    return _global_engine


def _get_session_factory() -> "sessionmaker":
    """Get or create the global session factory.

    Returns:
        SQLAlchemy sessionmaker
    """
    from sqlalchemy.orm import sessionmaker

    global _global_session_factory

    if _global_session_factory is None:
        engine = _get_engine()
        _global_session_factory = sessionmaker(bind=engine)

    return _global_session_factory


def _get_cached_engine(db_path: str, readonly: bool = False) -> "Engine":
    """Get or create a cached engine for the given connection string.

    This avoids creating new database connections on every request, which is
    especially important for PostgreSQL where connection setup is expensive.

    Args:
        db_path: Database connection string or file path
        readonly: If True, build a read-only engine (PostgreSQL connections open
            in a read-only transaction) and skip table-ensuring, which is itself
            DDL and would fail on a read-only connection. The same db_path can
            therefore have both a writable and a read-only engine cached.

    Returns:
        Cached SQLAlchemy engine
    """
    global _engine_cache, _engine_initialized

    # Key by (db_path, readonly) so a read-only engine never aliases a writable
    # one for the same database.
    cache_key = f"{db_path}\x00readonly" if readonly else db_path

    # Held across _ensure_tables_exist(): the check and the DDL must be atomic
    # together, or concurrent threads race to create the same tables.
    with _engine_lock:
        if cache_key not in _engine_cache:
            _engine_cache[cache_key] = _create_engine(db_path, readonly=readonly)

        engine = _engine_cache[cache_key]

        # Only ensure tables exist once per engine. Read-only engines must never run
        # the table-ensuring DDL; the schema is owned by the writable callers.
        if not readonly and cache_key not in _engine_initialized:
            _ensure_tables_exist(engine)
            _engine_initialized.add(cache_key)

    return engine


def create_session(config: Optional[DataSourceConfig] = None, readonly: bool = False) -> "Session":
    """Create a new database session.

    Args:
        config: Optional data source configuration. If not provided, uses global config.
        readonly: If True (only honored when an explicit config is given), use a
            read-only engine. For PostgreSQL this opens the connection in a
            read-only transaction so writes/DDL are rejected at the server.

    Returns:
        A new SQLAlchemy Session instance (or JSONLSession for JSONL backend)
    """
    from sqlalchemy.orm import sessionmaker

    if config is not None:
        # Create a session with specific config, using cached engine
        if config.backend_type == BackendType.JSONL:
            # JSONL backend uses its own session implementation.
            # Cache the storage instance so JSONL data is loaded once and
            # the in-memory SQLite DB is reused across requests.
            from storage.backend.jsonl import JSONLSession, JSONLStorage

            assert config.jsonl_data_dir is not None, "jsonl_data_dir must be set for JSONL backend"
            data_dir = config.jsonl_data_dir
            if data_dir not in _jsonl_storage_cache:
                storage = JSONLStorage(data_dir)
                storage.ensure_initialized()
                _jsonl_storage_cache[data_dir] = storage
            return _jsonl_storage_cache[data_dir].create_session()  # type: ignore[no-any-return]
        elif config.backend_type == BackendType.POSTGRES:
            assert config.postgres_url is not None, "postgres_url must be set for POSTGRES backend"
            db_path = config.postgres_url
        else:
            assert config.sqlite_path is not None, "sqlite_path must be set for SQLITE backend"
            db_path = config.sqlite_path

        # Use cached engine to avoid connection overhead on every request
        engine = _get_cached_engine(db_path, readonly=readonly)
        factory = sessionmaker(bind=engine)
        return factory()
    else:
        # Use global session factory
        factory = _get_session_factory()
        return factory()


def create_scoped_session_factory(
    config: Optional[DataSourceConfig] = None,
) -> Callable[[], "Session"]:
    """Create a scoped session factory compatible with Flask.

    Args:
        config: Optional data source configuration

    Returns:
        A callable that returns sessions
    """

    class SessionFactory:
        """Session factory that creates sessions on demand."""

        def __init__(self, config: Optional[DataSourceConfig] = None) -> None:
            self.config = config

        def __call__(self) -> "Session":
            """Create a new session."""
            return create_session(self.config)

    return SessionFactory(config)
