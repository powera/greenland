#!/usr/bin/python3
"""Migration: add cost_usd column to run_detail table.

Run this once against an existing benchmarks.db to add the cost_usd column.
New databases created via load_schema.py will already include this column.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH


def migrate() -> None:
    db_path = str(BENCHMARKS_DB_PATH)
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check whether the column already exists
    cursor.execute("PRAGMA table_info(run_detail)")
    columns = [row[1] for row in cursor.fetchall()]

    if "cost_usd" in columns:
        print("Column 'cost_usd' already exists in run_detail — nothing to do.")
    else:
        cursor.execute("ALTER TABLE run_detail ADD COLUMN cost_usd REAL")
        conn.commit()
        print("Column 'cost_usd' added to run_detail.")

    conn.close()


if __name__ == "__main__":
    migrate()
