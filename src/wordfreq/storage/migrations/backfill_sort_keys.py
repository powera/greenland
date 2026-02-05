#!/usr/bin/env python3
"""
Backfill sort_key for existing CJK translations (zh, ja, ko).

Reads all LemmaTranslation rows for Chinese, Japanese, and Korean that
have a NULL sort_key, computes the value, and writes it back.  Safe to
re-run — rows that already have a sort_key are skipped.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from constants import WORDFREQ_DB_PATH
from wordfreq.storage.models.schema import LemmaTranslation
from wordfreq.storage.translation_helpers import compute_sort_key
from wordfreq.storage.utils.session import create_database_session


def backfill(db_path: str, dry_run: bool = False) -> None:
    session = create_database_session(db_path)

    try:
        for lang in ("zh", "ja", "ko"):
            rows = (
                session.query(LemmaTranslation)
                .filter(
                    LemmaTranslation.language_code == lang,
                    LemmaTranslation.sort_key.is_(None),
                )
                .all()
            )
            updated = 0
            skipped = 0
            for row in rows:
                key = compute_sort_key(lang, row.translation)
                if key:
                    if not dry_run:
                        row.sort_key = key
                    updated += 1
                else:
                    skipped += 1

            if not dry_run:
                session.commit()

            print(f"{lang}: {updated} updated, {skipped} skipped (no key computed)")

        if dry_run:
            print("\n** DRY RUN — no changes written **")
        else:
            print("\n** Backfill complete **")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill sort_key for CJK translations")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}\n")
    backfill(args.db_path, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
