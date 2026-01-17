"""Factory for creating SQLAlchemy database sessions."""

from typing import Any, Callable, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import Base

_global_config: Optional[DataSourceConfig] = None
_global_engine: Optional[Engine] = None
_global_session_factory: Optional[sessionmaker] = None

# Cache engines by connection string to avoid creating new connections per request
_engine_cache: dict[str, Engine] = {}
_engine_initialized: set[str] = set()  # Track which engines have had tables ensured


def _create_engine(db_path: str) -> Engine:
    """Create a SQLAlchemy engine with appropriate settings.

    Args:
        db_path: Path to the database file (for SQLite) or connection string

    Returns:
        Configured SQLAlchemy engine
    """
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


def _ensure_tables_exist(engine: Engine) -> None:
    """Ensure database tables exist.

    Args:
        engine: SQLAlchemy engine
    """
    Base.metadata.create_all(engine)

    # Add missing columns to existing tables
    from wordfreq.storage.utils.session import ensure_tables_exist

    with Session(engine) as session:
        ensure_tables_exist(session)


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
        The data source configuration
    """
    global _global_config
    if _global_config is None:
        _global_config = DataSourceConfig.from_env()
    return _global_config


def get_backend_type() -> "BackendType":
    """Get the configured backend type.

    Returns:
        The backend type (for display/logging purposes)
    """
    return get_data_source_config().backend_type


def _get_engine() -> Engine:
    """Get or create the global database engine.

    Returns:
        SQLAlchemy engine
    """
    global _global_engine, _global_config

    if _global_engine is None:
        if _global_config is None:
            _global_config = DataSourceConfig.from_env()

        # Choose the correct path based on backend type
        if _global_config.backend_type == BackendType.POSTGRES:
            assert (
                _global_config.postgres_url is not None
            ), "postgres_url must be set for POSTGRES backend"
            _global_engine = _create_engine(_global_config.postgres_url)
        else:
            assert (
                _global_config.sqlite_path is not None
            ), "sqlite_path must be set for SQLITE backend"
            _global_engine = _create_engine(_global_config.sqlite_path)

        _ensure_tables_exist(_global_engine)

    return _global_engine


def _get_session_factory() -> sessionmaker:
    """Get or create the global session factory.

    Returns:
        SQLAlchemy sessionmaker
    """
    global _global_session_factory

    if _global_session_factory is None:
        engine = _get_engine()
        _global_session_factory = sessionmaker(bind=engine)

    return _global_session_factory


def _get_cached_engine(db_path: str) -> Engine:
    """Get or create a cached engine for the given connection string.

    This avoids creating new database connections on every request, which is
    especially important for PostgreSQL where connection setup is expensive.

    Args:
        db_path: Database connection string or file path

    Returns:
        Cached SQLAlchemy engine
    """
    global _engine_cache, _engine_initialized

    if db_path not in _engine_cache:
        _engine_cache[db_path] = _create_engine(db_path)

    engine = _engine_cache[db_path]

    # Only ensure tables exist once per engine
    if db_path not in _engine_initialized:
        _ensure_tables_exist(engine)
        _engine_initialized.add(db_path)

    return engine


def create_session(config: Optional[DataSourceConfig] = None) -> Session:
    """Create a new database session.

    Args:
        config: Optional data source configuration. If not provided, uses global config.

    Returns:
        A new SQLAlchemy Session instance (or JSONLSession for JSONL backend)
    """
    if config is not None:
        # Create a session with specific config, using cached engine
        if config.backend_type == BackendType.JSONL:
            # JSONL backend uses its own session implementation
            from wordfreq.storage.backend.jsonl import JSONLSession, JSONLStorage

            assert config.jsonl_data_dir is not None, "jsonl_data_dir must be set for JSONL backend"
            storage = JSONLStorage(config.jsonl_data_dir)
            storage.ensure_initialized()
            return storage.create_session()  # type: ignore[return-value]
        elif config.backend_type == BackendType.POSTGRES:
            assert config.postgres_url is not None, "postgres_url must be set for POSTGRES backend"
            db_path = config.postgres_url
        else:
            assert config.sqlite_path is not None, "sqlite_path must be set for SQLITE backend"
            db_path = config.sqlite_path

        # Use cached engine to avoid connection overhead on every request
        engine = _get_cached_engine(db_path)
        factory = sessionmaker(bind=engine)
        return factory()
    else:
        # Use global session factory
        factory = _get_session_factory()
        return factory()


def create_scoped_session_factory(
    config: Optional[DataSourceConfig] = None,
) -> Callable[[], Session]:
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

        def __call__(self) -> Session:
            """Create a new session."""
            return create_session(self.config)

    return SessionFactory(config)
