#!/usr/bin/python3

"""Database URL utilities for supporting both SQLite and cloud databases."""

import os
import logging
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_database_url(db_path: Optional[str] = None) -> str:
    """
    Get the database URL to use for connections.

    Priority order:
    1. DATABASE_URL environment variable (for cloud databases)
    2. WORDFREQ_DATABASE_URL environment variable (legacy/alternative)
    3. db_path parameter (converts to SQLite URL)
    4. Default SQLite path from constants

    Args:
        db_path: Optional path to SQLite database file

    Returns:
        Database URL string (e.g., 'postgresql://...', 'sqlite:///...')

    Examples:
        >>> get_database_url()  # Uses DATABASE_URL env var or default
        'postgresql://user:pass@host:5432/db'

        >>> get_database_url('/path/to/db.sqlite')
        'sqlite:////path/to/db.sqlite'
    """
    # Check environment variables first
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        logger.debug(f"Using DATABASE_URL from environment")
        return db_url

    db_url = os.environ.get("WORDFREQ_DATABASE_URL")
    if db_url:
        logger.debug(f"Using WORDFREQ_DATABASE_URL from environment")
        return db_url

    # Fall back to SQLite with provided or default path
    if db_path:
        return f"sqlite:///{db_path}"

    # Import here to avoid circular dependencies
    import constants

    return f"sqlite:///{constants.WORDFREQ_DB_PATH}"


def parse_database_url(db_url: str) -> Dict[str, Any]:
    """
    Parse a database URL and extract useful information.

    Args:
        db_url: Database URL string

    Returns:
        Dictionary with parsed components:
        - scheme: Database type (sqlite, postgresql, mysql, etc.)
        - is_sqlite: Boolean indicating if it's SQLite
        - is_postgres: Boolean indicating if it's PostgreSQL
        - is_mysql: Boolean indicating if it's MySQL
        - hostname: Database host
        - port: Database port
        - database: Database name
        - username: Database username
        - password: Database password (if present)

    Examples:
        >>> parse_database_url('postgresql://user:pass@localhost:5432/mydb')
        {
            'scheme': 'postgresql',
            'is_sqlite': False,
            'is_postgres': True,
            'is_mysql': False,
            'hostname': 'localhost',
            'port': 5432,
            'database': 'mydb',
            'username': 'user',
            'password': 'pass'
        }

        >>> parse_database_url('sqlite:///path/to/db.sqlite')
        {
            'scheme': 'sqlite',
            'is_sqlite': True,
            'is_postgres': False,
            'is_mysql': False,
            'hostname': None,
            'port': None,
            'database': '/path/to/db.sqlite',
            'username': None,
            'password': None
        }
    """
    parsed = urlparse(db_url)

    # Extract scheme (database type)
    scheme = parsed.scheme.split("+")[0] if "+" in parsed.scheme else parsed.scheme

    # Determine database type
    is_sqlite = scheme == "sqlite"
    is_postgres = scheme in ("postgres", "postgresql")
    is_mysql = scheme in ("mysql", "mariadb")

    # For SQLite, the database path is in the path component
    if is_sqlite:
        database = parsed.path
    else:
        # For other databases, remove leading slash
        database = parsed.path[1:] if parsed.path.startswith("/") else parsed.path

    return {
        "scheme": scheme,
        "is_sqlite": is_sqlite,
        "is_postgres": is_postgres,
        "is_mysql": is_mysql,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "database": database,
        "username": parsed.username,
        "password": parsed.password,
    }


def get_engine_options(db_url: str, echo: bool = False) -> Tuple[str, Dict[str, Any]]:
    """
    Get the appropriate engine options for a given database URL.

    This function returns the URL and connection arguments optimized for the
    specific database type.

    Args:
        db_url: Database URL string
        echo: Whether to enable SQLAlchemy echo mode (SQL logging)

    Returns:
        Tuple of (url, connect_args) where:
        - url: The database URL (potentially modified)
        - connect_args: Dictionary of database-specific connection arguments

    Examples:
        >>> url, args = get_engine_options('sqlite:///db.sqlite')
        >>> args['check_same_thread']
        False

        >>> url, args = get_engine_options('postgresql://localhost/mydb')
        >>> args.get('check_same_thread')
        None
    """
    db_info = parse_database_url(db_url)
    connect_args: Dict[str, Any] = {}

    # SQLite-specific options
    if db_info["is_sqlite"]:
        # Required for SQLite in multi-threaded environments
        connect_args["check_same_thread"] = False
        logger.debug("Using SQLite with check_same_thread=False")

    # PostgreSQL-specific options
    elif db_info["is_postgres"]:
        # Connection pooling options for PostgreSQL
        connect_args["connect_timeout"] = 10
        logger.debug("Using PostgreSQL with connect_timeout=10")

    # MySQL-specific options
    elif db_info["is_mysql"]:
        # Connection pooling options for MySQL
        connect_args["connect_timeout"] = 10
        logger.debug("Using MySQL with connect_timeout=10")

    return db_url, connect_args


def is_sqlite(db_url: Optional[str] = None) -> bool:
    """
    Check if the database URL is for SQLite.

    Args:
        db_url: Optional database URL. If None, uses get_database_url()

    Returns:
        True if the database is SQLite, False otherwise

    Examples:
        >>> is_sqlite('sqlite:///db.sqlite')
        True

        >>> is_sqlite('postgresql://localhost/mydb')
        False
    """
    if db_url is None:
        db_url = get_database_url()

    db_info = parse_database_url(db_url)
    return db_info["is_sqlite"]


def is_cloud_database(db_url: Optional[str] = None) -> bool:
    """
    Check if the database URL is for a cloud/remote database (not SQLite).

    Args:
        db_url: Optional database URL. If None, uses get_database_url()

    Returns:
        True if the database is a cloud/remote database, False for SQLite

    Examples:
        >>> is_cloud_database('postgresql://localhost/mydb')
        True

        >>> is_cloud_database('sqlite:///db.sqlite')
        False
    """
    return not is_sqlite(db_url)


__all__ = [
    "get_database_url",
    "parse_database_url",
    "get_engine_options",
    "is_sqlite",
    "is_cloud_database",
]
