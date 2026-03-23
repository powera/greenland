#!/usr/bin/env python3
"""
Backfill: Compute rhyme_key for supported-language derivative forms that have IPA data.

Processes all derivative_forms rows where language_code is supported by the
shared rhyme-key helpers, ipa_pronunciation IS NOT NULL, and rhyme_key IS NULL,
computing and storing the rhyme key in batches.
"""

import argparse
import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from constants import WORDFREQ_DB_PATH
from langtools.rhyme_keys import RHYME_KEY_LANGUAGES
from storage.rhyme_keys import compute_rhyme_key_from_ipa
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import DerivativeForm

BATCH_SIZE = 500


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )

    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=db_path,
    )


def backfill_rhyme_keys(config: DataSourceConfig, *, dry_run: bool = False) -> None:
    """Compute and store rhyme_key for all qualifying derivative forms."""
    session = create_session(config)

    try:
        rows = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.language_code.in_(sorted(RHYME_KEY_LANGUAGES)),
                DerivativeForm.ipa_pronunciation.isnot(None),
                DerivativeForm.rhyme_key.is_(None),
            )
            .all()
        )

        total = len(rows)
        print(f"Found {total} supported-language derivative forms with IPA but no rhyme_key")

        keyed = 0
        skipped = 0

        for row_index, derivative_form in enumerate(rows):
            ipa_pronunciation = derivative_form.ipa_pronunciation
            if ipa_pronunciation is None:
                skipped += 1
                print(
                    f"  SKIP id={derivative_form.id} ipa={derivative_form.ipa_pronunciation!r} "
                    f"text={derivative_form.derivative_form_text!r}"
                )
                continue

            rhyme_key_value = compute_rhyme_key_from_ipa(
                ipa_pronunciation, derivative_form.language_code
            )
            if rhyme_key_value:
                if not dry_run:
                    derivative_form.rhyme_key = rhyme_key_value
                keyed += 1
            else:
                skipped += 1
                print(
                    f"  SKIP id={derivative_form.id} ipa={derivative_form.ipa_pronunciation!r} "
                    f"text={derivative_form.derivative_form_text!r}"
                )

            if not dry_run and (row_index + 1) % BATCH_SIZE == 0:
                session.commit()
                print(
                    f"  Committed batch {(row_index + 1) // BATCH_SIZE} "
                    f"({row_index + 1}/{total})"
                )

        if not dry_run:
            session.commit()

        print(f"\nResults: {keyed} keyed, {skipped} skipped, {total} total")
        if dry_run:
            print("** DRY RUN - No changes were made **")
            session.rollback()

    except Exception as error:
        print(f"\nError during backfill: {error}")
        import traceback

        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


def main() -> int:
    """Run the backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill rhyme_key for supported derivative forms"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--db-path",
        default=WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL instead of SQLite",
    )
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    database_label = config.postgres_url if args.postgres else config.sqlite_path

    print(f"Database: {database_label}")
    print(f"Backend: {config.backend_type.value}")
    print(f"Dry run: {args.dry_run}")
    print()

    backfill_rhyme_keys(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
