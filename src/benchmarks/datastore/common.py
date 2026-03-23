#!/usr/bin/python3

"""Common database utilities and base classes for benchmarks and qualitative tests."""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.sql import func

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH, BENCHMARKS_POSTGRES_SCHEMA

# Cache for PostgreSQL engines to avoid creating multiple connection pools.
_postgres_engine_cache: Dict[str, Engine] = {}
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Model(Base):
    """Model definition."""

    __tablename__ = "model"
    codename: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    launch_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    filesize_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lmstudio_model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_type: Mapped[str] = mapped_column(String, nullable=False, default="local")
    max_benchmark_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # benchmark runs and qual runs are populated in those files.


def _configure_sqlite_connection(dbapi_conn, connection_record):
    """Configure SQLite connection for better concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _migrate_sqlite_schema(conn) -> None:
    """Apply additive schema migrations for SQLite benchmark databases."""
    result = conn.execute(text("PRAGMA table_info(benchmark)"))
    existing_cols = {row[1] for row in result}
    if "category" not in existing_cols:
        conn.execute(text("ALTER TABLE benchmark ADD COLUMN category TEXT"))

    model_result = conn.execute(text("PRAGMA table_info(model)"))
    model_cols = {row[1] for row in model_result}
    if "lmstudio_model_name" not in model_cols:
        conn.execute(text("ALTER TABLE model ADD COLUMN lmstudio_model_name TEXT"))
    if "max_benchmark_tier" not in model_cols:
        conn.execute(text("ALTER TABLE model ADD COLUMN max_benchmark_tier INTEGER DEFAULT 1"))

    run_detail_result = conn.execute(text("PRAGMA table_info(run_detail)"))
    run_detail_cols = {row[1] for row in run_detail_result}
    if "tokens_used" not in run_detail_cols:
        conn.execute(text("ALTER TABLE run_detail ADD COLUMN tokens_used INTEGER"))
    if "tokens_in" not in run_detail_cols:
        conn.execute(text("ALTER TABLE run_detail ADD COLUMN tokens_in INTEGER"))
    if "tokens_out" not in run_detail_cols:
        conn.execute(text("ALTER TABLE run_detail ADD COLUMN tokens_out INTEGER"))

    question_result = conn.execute(text("PRAGMA table_info(question)"))
    question_cols = {row[1] for row in question_result}
    if "is_excluded" not in question_cols:
        conn.execute(text("ALTER TABLE question ADD COLUMN is_excluded INTEGER DEFAULT 0 NOT NULL"))
    if "exclusion_reason" not in question_cols:
        conn.execute(text("ALTER TABLE question ADD COLUMN exclusion_reason TEXT"))


def _migrate_postgres_schema(conn) -> None:
    """Apply additive schema migrations for PostgreSQL benchmark databases."""
    schema = BENCHMARKS_POSTGRES_SCHEMA
    existing_columns = {
        (row[0], row[1])
        for row in conn.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name IN ('benchmark', 'model', 'run_detail', 'question')
                """
            ),
            {"schema": schema},
        )
    }

    statements = [
        (("benchmark", "category"), "ALTER TABLE benchmark ADD COLUMN category TEXT"),
        (
            ("model", "lmstudio_model_name"),
            "ALTER TABLE model ADD COLUMN lmstudio_model_name TEXT",
        ),
        (
            ("model", "max_benchmark_tier"),
            "ALTER TABLE model ADD COLUMN max_benchmark_tier INTEGER DEFAULT 1",
        ),
        (("run_detail", "tokens_used"), "ALTER TABLE run_detail ADD COLUMN tokens_used INTEGER"),
        (("run_detail", "tokens_in"), "ALTER TABLE run_detail ADD COLUMN tokens_in INTEGER"),
        (("run_detail", "tokens_out"), "ALTER TABLE run_detail ADD COLUMN tokens_out INTEGER"),
        (
            ("question", "is_excluded"),
            "ALTER TABLE question ADD COLUMN is_excluded BOOLEAN DEFAULT FALSE NOT NULL",
        ),
        (
            ("question", "exclusion_reason"),
            "ALTER TABLE question ADD COLUMN exclusion_reason TEXT",
        ),
    ]
    for column_key, statement in statements:
        if column_key not in existing_columns:
            conn.execute(text(statement))


def create_dev_session():
    """Create a database session for development.

    Uses the default benchmarks database path from benchmark_constants.
    """
    db_path = BENCHMARKS_DB_PATH
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"timeout": 30, "check_same_thread": False},
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    event.listens_for(engine, "connect")(_configure_sqlite_connection)
    Session = sessionmaker(bind=engine)
    return Session()


def create_database_and_session(db_path=None):
    """Create a SQLite database engine and session.

    Args:
        db_path: Path to database file (default: benchmark_constants.BENCHMARKS_DB_PATH)

    Returns:
        SQLAlchemy session
    """
    if db_path is None:
        db_path = str(BENCHMARKS_DB_PATH)

    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"timeout": 30, "check_same_thread": False},
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    event.listens_for(engine, "connect")(_configure_sqlite_connection)
    Base.metadata.create_all(engine)

    # Migrate existing databases to add new columns that may not exist yet
    with engine.connect() as conn:
        _migrate_sqlite_schema(conn)
        conn.commit()

    Session = sessionmaker(bind=engine)
    return Session()


def create_postgres_session(postgres_url: str):
    """Create a database session for a PostgreSQL (Supabase) backend.

    Engines are cached by URL so that multiple calls reuse the same connection
    pool. On first use the benchmarks schema is created (if absent) and all
    ORM tables are created via Base.metadata.create_all.

    Args:
        postgres_url: Full PostgreSQL connection URL (including search_path option)

    Returns:
        SQLAlchemy session
    """
    if postgres_url not in _postgres_engine_cache:
        _postgres_engine_cache[postgres_url] = _initialize_postgres_engine(postgres_url)
    else:
        try:
            _probe_postgres_engine(_postgres_engine_cache[postgres_url])
        except SQLAlchemyError:
            logger.warning(
                "Cached PostgreSQL engine health check failed; disposing pool and retrying with a new engine.",
                exc_info=True,
            )
            _postgres_engine_cache[postgres_url].dispose()
            _postgres_engine_cache[postgres_url] = _initialize_postgres_engine(postgres_url)

    session_factory = sessionmaker(bind=_postgres_engine_cache[postgres_url])
    return session_factory()


def _probe_postgres_engine(engine: Engine) -> None:
    """Run a quick connectivity probe to detect dead pooled connections."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _initialize_postgres_engine(postgres_url: str) -> Engine:
    """Create and initialize a PostgreSQL engine for benchmarks storage."""
    # When using an IPv4 transaction-mode pooler (e.g. Supabase PgBouncer),
    # the pooler itself manages connections.  Keep SQLAlchemy's client-side
    # pool small so we don't exhaust the pooler's connection limit:
    #   pool_size=2 — a small number of kept-alive connections
    #   max_overflow=3 — burst allowance beyond pool_size
    # Sessions MUST be closed explicitly (call session.close()) so connections
    # are returned promptly rather than waiting for GC.
    base_engine = create_engine(
        postgres_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=2,
        max_overflow=3,
    )

    # PgBouncer (Supabase pooler) silently drops the options=
    # search_path parameter from connection URLs, so we must set
    # search_path explicitly on every new connection.
    #
    # We also apply schema_translate_map so every ORM-generated SQL statement
    # uses an explicit benchmarks.<table> schema prefix instead of depending on
    # the backend's default schema.
    schema = BENCHMARKS_POSTGRES_SCHEMA
    engine = base_engine.execution_options(schema_translate_map={None: schema})

    @event.listens_for(base_engine, "connect")
    def _set_search_path(dbapi_conn: Any, connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute(f"SET search_path TO {schema}")
        cursor.close()

    # Ensure the benchmarks schema exists before creating tables.
    with base_engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        conn.commit()

    # Import benchmarks models so all ORM classes are registered with
    # Base before create_all (Benchmark, Question, Run, RunDetail).
    import benchmarks.datastore.benchmarks  # noqa: F401

    Base.metadata.create_all(engine)
    with base_engine.connect() as conn:
        _migrate_postgres_schema(conn)
        conn.commit()

    return engine


def create_session_from_config(config):
    """Create a database session from a BenchmarkConfig object.

    Args:
        config: BenchmarkConfig instance

    Returns:
        SQLAlchemy session
    """
    if getattr(config, "postgres_url", None):
        return create_postgres_session(config.postgres_url)
    return create_database_and_session(config.db_path)


def insert_model(
    session,
    codename: str,
    displayname: str,
    launch_date: Optional[str] = None,
    filesize_mb: Optional[int] = None,
    license_name: Optional[str] = None,
    model_path: Optional[str] = None,
    lmstudio_model_name: Optional[str] = None,
    model_type: str = "local",
    max_benchmark_tier: int = 1,
):
    """Insert a new model into the database."""
    try:
        new_model = Model(
            codename=codename,
            displayname=displayname,
            launch_date=launch_date,
            filesize_mb=filesize_mb,
            license_name=license_name,
            model_path=model_path,
            lmstudio_model_name=lmstudio_model_name,
            model_type=model_type,
            max_benchmark_tier=max_benchmark_tier,
        )
        session.add(new_model)
        session.commit()
        return True, f"Model '{codename}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Model '{codename}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting model: {str(e)}"


def upsert_model(
    session,
    codename: str,
    displayname: str,
    launch_date: Optional[str] = None,
    filesize_mb: Optional[int] = None,
    license_name: Optional[str] = None,
    model_path: Optional[str] = None,
    lmstudio_model_name: Optional[str] = None,
    model_type: str = "local",
    max_benchmark_tier: int = 1,
) -> Tuple[bool, str]:
    """Insert a model, or update it if the codename already exists."""
    try:
        existing = session.query(Model).filter(Model.codename == codename).first()
        if existing is not None:
            existing.displayname = displayname
            existing.launch_date = launch_date
            existing.filesize_mb = filesize_mb
            existing.license_name = license_name
            existing.model_path = model_path
            existing.lmstudio_model_name = lmstudio_model_name
            existing.model_type = model_type
            existing.max_benchmark_tier = max_benchmark_tier
            session.commit()
            return True, f"Model '{codename}' successfully updated"

        new_model = Model(
            codename=codename,
            displayname=displayname,
            launch_date=launch_date,
            filesize_mb=filesize_mb,
            license_name=license_name,
            model_path=model_path,
            lmstudio_model_name=lmstudio_model_name,
            model_type=model_type,
            max_benchmark_tier=max_benchmark_tier,
        )
        session.add(new_model)
        session.commit()
        return True, f"Model '{codename}' successfully inserted"

    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error upserting model: {str(e)}"


def list_all_models(session):
    """List all models in the database.

    :param session: SQLAlchemy session
    :return: List of model details
    """
    models = session.query(Model).order_by(Model.displayname).all()
    return [
        {
            "codename": model.codename,
            "displayname": model.displayname,
            "launch_date": model.launch_date,
            "filesize_mb": model.filesize_mb,
            "license_name": model.license_name,
            "model_path": model.model_path,
            "lmstudio_model_name": model.lmstudio_model_name,
            "model_type": model.model_type,
            "max_benchmark_tier": model.max_benchmark_tier,
        }
        for model in models
    ]


def get_model_by_codename(session, codename: str):
    """Get model details by codename.

    :param session: SQLAlchemy session
    :param codename: Model codename
    :return: Model details dictionary or None
    """
    model = session.query(Model).filter(Model.codename == codename).first()
    if not model:
        return None

    return {
        "codename": model.codename,
        "displayname": model.displayname,
        "launch_date": model.launch_date,
        "filesize_mb": model.filesize_mb,
        "license_name": model.license_name,
        "model_path": model.model_path,
        "lmstudio_model_name": model.lmstudio_model_name,
        "model_type": model.model_type,
        "max_benchmark_tier": model.max_benchmark_tier,
    }


def get_default_model_codename(session):
    """Get the default model codename from the database.

    :param session: SQLAlchemy session
    :return: Default model codename or None
    """
    # Get the first model from the database as the default
    model = session.query(Model).first()
    return model.codename if model else None


def decode_json(text: Optional[str]) -> Dict[str, Any]:
    """Safely decode JSON text with proper Unicode handling."""
    if text is None:
        return {}
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {"result": result}
    except json.JSONDecodeError:
        return {"result": text}
