"""Database session management utilities."""

import logging
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import constants
from storage.models.schema import Base

logger = logging.getLogger(__name__)


def _configure_sqlite_connection(dbapi_conn: Any, connection_record: Any) -> None:
    """Configure SQLite connection for better concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
    cursor.execute("PRAGMA synchronous=NORMAL")  # Faster, still safe with WAL
    cursor.close()


def create_database_session(db_path: str = constants.WORDFREQ_DB_PATH) -> Session:
    """Create a new database session."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "timeout": 30,
            "check_same_thread": False,
        },
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    event.listens_for(engine, "connect")(_configure_sqlite_connection)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def ensure_tables_exist(session: Session) -> None:
    """
    Ensure tables exist in the database and add any missing columns.

    Args:
        session: Database session
    """
    engine = session.get_bind().engine

    # First create any missing tables
    Base.metadata.create_all(engine)

    # Then check for missing columns and add them
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    """
    Add any missing columns to existing tables based on the current schema.

    Args:
        engine: SQLAlchemy engine
    """
    inspector = inspect(engine)

    # Get all table names from our models
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue  # Table doesn't exist yet, create_all() will handle it

        # Get existing columns in the database
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

        # Get columns defined in the model
        model_columns = {col.name for col in table.columns}

        # Find missing columns
        missing_columns = model_columns - existing_columns

        if missing_columns:
            logger.info(f"Adding missing columns to table '{table_name}': {missing_columns}")

            for col_name in missing_columns:
                column = table.columns[col_name]

                # Build the ALTER TABLE statement
                col_type = column.type.compile(engine.dialect)

                # Handle nullable/default constraints
                nullable_clause = "" if column.nullable else " NOT NULL"
                default_clause = ""

                if column.default is not None:
                    if hasattr(column.default, "arg"):
                        # Scalar default value
                        if isinstance(column.default.arg, str):
                            default_clause = f" DEFAULT '{column.default.arg}'"
                        elif isinstance(column.default.arg, bool):
                            default_clause = f" DEFAULT {1 if column.default.arg else 0}"
                        else:
                            default_clause = f" DEFAULT {column.default.arg}"
                    elif hasattr(column.default, "name"):
                        # Server default (like func.now())
                        if column.default.name == "now":
                            default_clause = " DEFAULT CURRENT_TIMESTAMP"

                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{default_clause}{nullable_clause}"

                try:
                    with engine.connect() as conn:
                        conn.execute(text(alter_sql))
                        conn.commit()
                    logger.info(f"Successfully added column '{col_name}' to table '{table_name}'")
                except Exception as e:
                    logger.error(f"Failed to add column '{col_name}' to table '{table_name}': {e}")
                    logger.error(f"SQL was: {alter_sql}")
                    # Continue with other columns rather than failing completely
