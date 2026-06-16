#!/usr/bin/env python3
"""Migration: Add pending import synonym candidate table."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.database import create_database_session


def check_table_exists(session: Session, table_name: str) -> bool:
    inspector = inspect(session.bind)
    if inspector is None:
        raise RuntimeError("Cannot inspect database: session has no bound engine")
    return table_name in inspector.get_table_names()


def add_pending_import_synonym_candidates_table(session: Session, dry_run: bool = False) -> bool:
    table_name = "pending_import_synonym_candidates"
    if check_table_exists(session, table_name):
        print(f"Table '{table_name}' already exists")
        return False

    if dry_run:
        print(f"Would create '{table_name}' table")
        return True

    print(f"Creating '{table_name}' table...")
    session.execute(
        text(
            """
            CREATE TABLE pending_import_synonym_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pending_import_id INTEGER NOT NULL REFERENCES pending_imports(id) ON DELETE CASCADE,
                lemma_id INTEGER REFERENCES lemmas(id) ON DELETE SET NULL,
                candidate_text VARCHAR NOT NULL,
                same_pos BOOLEAN NOT NULL DEFAULT 0,
                llm_synonym_category VARCHAR NOT NULL,
                llm_synonym_score FLOAT,
                matched_translation_count INTEGER NOT NULL DEFAULT 0,
                matched_translation_languages TEXT NOT NULL DEFAULT '[]',
                candidate_translations TEXT NOT NULL DEFAULT '{}',
                explanation TEXT,
                is_strong BOOLEAN NOT NULL DEFAULT 0,
                status VARCHAR NOT NULL DEFAULT 'active',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            "CREATE INDEX ix_pending_import_synonym_candidates_pending_import_id "
            "ON pending_import_synonym_candidates (pending_import_id)"
        )
    )
    session.execute(
        text(
            "CREATE INDEX ix_pending_import_synonym_candidates_lemma_id "
            "ON pending_import_synonym_candidates (lemma_id)"
        )
    )
    session.execute(
        text(
            "CREATE INDEX ix_pending_import_synonym_candidates_is_strong "
            "ON pending_import_synonym_candidates (is_strong)"
        )
    )
    session.execute(
        text(
            "CREATE INDEX ix_pending_import_synonym_candidates_status "
            "ON pending_import_synonym_candidates (status)"
        )
    )
    session.commit()
    print("Table created successfully")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Add pending import synonym candidates")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    session = create_database_session(args.db_path)

    try:
        changed = add_pending_import_synonym_candidates_table(session, dry_run=args.dry_run)
        if args.dry_run:
            print("\n** DRY RUN - No changes were made **")
        elif changed:
            print("\n** Migration complete **")
        else:
            print("\n** No changes needed **")
    except Exception as exc:
        print(f"\nError during migration: {exc}")
        import traceback

        traceback.print_exc()
        session.rollback()
        return 1
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
