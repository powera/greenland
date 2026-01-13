#!/usr/bin/python3
"""Create benchmark database schema using SQLAlchemy.

This script creates all tables defined in the SQLAlchemy models.
The old SQL schema file is no longer used.
"""

import sys
from pathlib import Path

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH
from benchmarks.datastore.common import create_database_and_session


def create_tables():
    """Create all benchmark tables using SQLAlchemy.

    This uses Base.metadata.create_all() which is called automatically
    by create_database_and_session().
    """
    db_path = BENCHMARKS_DB_PATH
    print(f"Creating database schema at: {db_path}")

    # This creates all tables defined in SQLAlchemy models
    session = create_database_and_session(str(db_path))
    session.close()

    print("Database and schema created successfully.")
    print(f"Database file: {db_path}")


if __name__ == "__main__":
    create_tables()
