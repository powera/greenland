#!/usr/bin/env python3
"""
Backfill sort_key for existing LemmaTranslation rows.

Iterates over every language that ``compute_sort_key`` supports (CJK plus
Latin, Cyrillic, Brahmic, and Thai), finds rows where ``sort_key`` is NULL,
computes the value, and writes it back.  Safe to re-run — rows that
already have a sort_key are skipped via the NULL filter.
"""

import sys
from pathlib import Path
from typing import List, Optional

if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from constants import WORDFREQ_DB_PATH
from langtools.collation import SORT_KEY_LANGUAGES
from storage.models.schema import LemmaTranslation
from storage.translation_helpers import compute_sort_key
from storage.utils.session import create_database_session

# CJK is handled separately by compute_sort_key; collation.SORT_KEY_LANGUAGES
# covers everything else (Latin + Cyrillic + Brahmic + Thai).
_CJK_LANGUAGES: List[str] = ["zh", "ja", "ko"]


def _all_supported_languages() -> List[str]:
    return _CJK_LANGUAGES + sorted(SORT_KEY_LANGUAGES)


def backfill(db_path: str, dry_run: bool = False, languages: Optional[List[str]] = None) -> None:
    session = create_database_session(db_path)
    target_languages = languages if languages else _all_supported_languages()

    try:
        for lang in target_languages:
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

            if updated or skipped:
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

    parser = argparse.ArgumentParser(description="Backfill sort_key for translations")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Restrict backfill to these language codes (default: all supported)",
    )
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print(f"Languages: {args.languages or 'all supported'}\n")
    backfill(args.db_path, args.dry_run, args.languages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
