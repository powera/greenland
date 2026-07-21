#!/usr/bin/env python3
"""Migration: Add variant_forms table for alternate spellings.

Stores full paradigms for orthographic variants of a lemma ("grey"/"greyer"/
"greyest" for "gray"), keyed by (variant_kind, variant_key).  See
storage.models.variant_form for the rationale behind a separate table.
"""

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


def add_variant_forms_table(session: Session, dry_run: bool = False) -> bool:
    table_name = "variant_forms"
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
            CREATE TABLE variant_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
                language_code VARCHAR NOT NULL,
                variant_kind VARCHAR NOT NULL,
                variant_key VARCHAR NOT NULL,
                grammatical_form VARCHAR NOT NULL,
                variant_form_text VARCHAR NOT NULL,
                word_token_id INTEGER REFERENCES word_tokens(id),
                is_base_form BOOLEAN NOT NULL DEFAULT 0,
                ipa_pronunciation VARCHAR,
                phonetic_pronunciation VARCHAR,
                verified BOOLEAN NOT NULL DEFAULT 0,
                notes TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_variant_form UNIQUE (
                    lemma_id, language_code, variant_kind, variant_key, grammatical_form
                )
            )
            """
        )
    )
    session.execute(text("CREATE INDEX ix_variant_forms_lemma_id ON variant_forms (lemma_id)"))
    session.execute(
        text("CREATE INDEX ix_variant_forms_language_code ON variant_forms (language_code)")
    )
    session.execute(
        text("CREATE INDEX ix_variant_forms_variant_kind ON variant_forms (variant_kind)")
    )
    # Indexed for reverse lookups: "which lemma is 'grey'?", duplicate
    # detection, and wordlist coverage checks.
    session.execute(
        text(
            "CREATE INDEX ix_variant_forms_variant_form_text "
            "ON variant_forms (variant_form_text)"
        )
    )
    session.commit()
    print("Table created successfully")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Add variant_forms table")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    session = create_database_session(args.db_path)

    try:
        changed = add_variant_forms_table(session, dry_run=args.dry_run)
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
