#!/usr/bin/env python3
"""Add ``PendingImport.queried_word`` and backfill it from the staging note.

When ``add_word`` asks about a term and the LLM answers with a different
headword, the pending row is filed under the *answer*: "pro se" is queued as
"without a lawyer", "bona fide" as "in good faith". That is deliberate -- the
entry reads as the thing a reviewer would look for, and it dedups against an
existing lemma of that name -- but it lost the word that was asked about, and
the importers' preflight matches on ``english_word``. A re-glossed word
therefore looks absent from the queue on the next run, so it is re-sent to the
LLM and paid for again, and the server files a second pending row.

The queried word was recorded only in the note prose, behind the fixed
``DIVERGENT_TERM_NOTE`` prefix that ``words.add_word.source_word_from_note``
parses -- the comment on that constant says recovering it is what a later step
would need. This is that step: the model declares the column, ``add_word``
writes it going forward, and this run recovers it for the rows already queued.
The column itself is added by the session layer, which reconciles a table
against its model on connect; this migration only fills it.

The note is left exactly as it is. It is prose a reviewer reads ("is 'without
a lawyer' the headword for this sense, is 'pro se' a variant of it, or are both
separate lemmas?"), and stripping the term out of it would make the question
unreadable. The duplication is the price of that, and it is one-directional:
the column is authoritative for machines, the note stays for humans.

Only rows whose note yields a source word are filled, and only when it differs
from ``english_word``. A row queued for a catch-all subtype or a prominence tie
names no source word and is left NULL, which is correct: for those rows
``english_word`` already *is* the word that was asked about.

Rerunning is safe. A row that already carries a ``queried_word`` is skipped, so
a second run writes nothing; ``--refresh`` re-parses those too.

    GREENLAND_TEST_MODE=1 python migrations/20260919_backfill_pending_queried_word.py --dry-run
    GREENLAND_DISABLE_LLM=1 python migrations/20260919_backfill_pending_queried_word.py

No LLM call is made: the source word is parsed out of a string already in the
database, so this runs safely under either kill switch.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.backend import DataSourceConfig, create_session
from storage.models.imports import PendingImport
from words.add_word import source_word_from_note

#: How many filled rows to record for the run summary.
_SAMPLE_LIMIT = 15


@dataclass
class MigrationResult:
    """What one run of this migration did."""

    #: Rows examined.
    examined: int = 0
    #: Rows given a ``queried_word``.
    filled: int = 0
    #: Rows whose note named no source word (queued for a non-divergent reason).
    no_source_word: int = 0
    #: Rows whose note named the word they are already filed under.
    same_as_english_word: int = 0
    #: Rows that already carried a value, skipped without ``--refresh``.
    already_set: int = 0
    #: ``(queried_word, english_word)`` for the first few fills.
    samples: List[Tuple[str, str]] = field(default_factory=list)


def backup_database(config: DataSourceConfig) -> Optional[Path]:
    """Copy the SQLite file next to itself with a dated suffix."""
    if config.sqlite_path is None:
        return None
    db_path = Path(config.sqlite_path)
    if not db_path.exists():
        return None
    stamp = date.today().strftime("%Y%m%d")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}-pending-queried-word")
    if backup_path.exists():
        return backup_path
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate(config: DataSourceConfig, *, dry_run: bool, refresh: bool) -> MigrationResult:
    """Fill ``queried_word`` for every divergent row that lacks one."""
    result = MigrationResult()
    session = create_session(config)
    try:
        query = session.query(PendingImport)
        if not refresh:
            query = query.filter(PendingImport.queried_word.is_(None))

        for pending in query.all():
            result.examined += 1
            if pending.queried_word and not refresh:
                result.already_set += 1
                continue

            source_word = source_word_from_note(pending.notes)
            if not source_word:
                result.no_source_word += 1
                continue
            if source_word.casefold() == (pending.english_word or "").casefold():
                result.same_as_english_word += 1
                continue

            if not dry_run:
                pending.queried_word = source_word
            result.filled += 1
            if len(result.samples) < _SAMPLE_LIMIT:
                result.samples.append((source_word, pending.english_word))

        if not dry_run:
            session.commit()
    finally:
        session.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite database to migrate")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change, write nothing"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Also re-parse rows that already carry a queried_word",
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip the dated database backup")
    args = parser.parse_args()

    config = (
        DataSourceConfig(sqlite_path=str(args.db_path))
        if args.db_path is not None
        else DataSourceConfig()
    )

    if not args.dry_run and not args.no_backup:
        backup_path = backup_database(config)
        if backup_path is not None:
            print(f"Backup: {backup_path}")

    result = migrate(config, dry_run=args.dry_run, refresh=args.refresh)

    print(f"Examined: {result.examined}")
    print(f"Filled: {result.filled}")
    print(f"  no source word in note: {result.no_source_word}")
    print(f"  note names the filed word: {result.same_as_english_word}")
    if result.already_set:
        print(f"  already set: {result.already_set}")
    if result.samples:
        print("Samples (queried -> filed as):")
        for queried, english in result.samples:
            print(f"  {queried!r} -> {english!r}")
    if args.dry_run:
        print("\nDry run: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
