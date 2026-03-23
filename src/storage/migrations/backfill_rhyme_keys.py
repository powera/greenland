#!/usr/bin/env python3
"""
Backfill: Compute rhyme_key for English derivative forms that have IPA data.

Processes all derivative_forms rows where language_code='en',
ipa_pronunciation IS NOT NULL, and rhyme_key IS NULL, computing and
storing the rhyme key in batches.
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from constants import WORDFREQ_DB_PATH
from langtools.en.rhyme_key import compute_rhyme_key
from storage.database import create_database_session
from storage.models.schema import DerivativeForm

BATCH_SIZE = 500


def backfill_rhyme_keys(db_path: str, *, dry_run: bool = False) -> None:
    """Compute and store rhyme_key for all qualifying English derivative forms."""
    session = create_database_session(db_path)

    try:
        rows = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.language_code == "en",
                DerivativeForm.ipa_pronunciation.isnot(None),
                DerivativeForm.rhyme_key.is_(None),
            )
            .all()
        )

        total = len(rows)
        print(f"Found {total} English derivative forms with IPA but no rhyme_key")

        keyed = 0
        skipped = 0

        for i, df in enumerate(rows):
            rk = compute_rhyme_key(df.ipa_pronunciation, "en")
            if rk:
                if not dry_run:
                    df.rhyme_key = rk
                keyed += 1
            else:
                skipped += 1
                print(
                    f"  SKIP id={df.id} ipa={df.ipa_pronunciation!r} "
                    f"text={df.derivative_form_text!r}"
                )

            if not dry_run and (i + 1) % BATCH_SIZE == 0:
                session.commit()
                print(f"  Committed batch {(i + 1) // BATCH_SIZE} ({i + 1}/{total})")

        if not dry_run:
            session.commit()

        print(f"\nResults: {keyed} keyed, {skipped} skipped, {total} total")
        if dry_run:
            print("** DRY RUN - No changes were made **")
            session.rollback()

    except Exception as e:
        print(f"\nError during backfill: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


def main() -> int:
    """Run the backfill."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill rhyme_key for English derivative forms")
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
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    backfill_rhyme_keys(args.db_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
