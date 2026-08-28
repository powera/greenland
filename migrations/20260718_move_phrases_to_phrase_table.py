#!/usr/bin/env python3
"""
Migration: Move phrases out of the ``lemmas`` table into the ``phrases``
table (and their translations into ``phrase_translations``).

Phrases (fixed traveler/greeting expressions like "See you later") used to be
stored as ``Lemma`` rows with ``pos_type="phrase"`` and a ``pos_subtype`` of
``greetings``/``traveler``. They now have their own ``Phrase`` /
``PhraseTranslation`` tables, so they no longer leak into lemma queries.

For each ``pos_type="phrase"`` lemma this migration:
  1. Creates a ``Phrase`` row (guid, subtype, label, definition, difficulty,
     verified, notes) if one with that GUID does not already exist.
  2. Copies each ``LemmaTranslation`` into a ``PhraseTranslation``.
  3. Deletes the source lemma (its translations / derivative forms cascade).

It is idempotent: re-running skips GUIDs already present in ``phrases`` and
simply removes any leftover phrase-type lemmas.

Usage:
    python migrations/20260718_move_phrases_to_phrase_table.py
    python migrations/20260718_move_phrases_to_phrase_table.py --postgres
    python migrations/20260718_move_phrases_to_phrase_table.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma, Phrase, PhraseTranslation


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


def migrate(config: DataSourceConfig, *, dry_run: bool = False) -> int:
    """Move phrase lemmas into the phrases table. Returns the number moved."""
    session = create_session(config)
    try:
        existing_phrase_guids = {
            guid for (guid,) in session.query(Phrase.guid).filter(Phrase.guid.isnot(None)).all()
        }

        phrase_lemmas = session.query(Lemma).filter(Lemma.pos_type == "phrase").all()
        print(f"Found {len(phrase_lemmas)} phrase-type lemma(s) to migrate.")

        moved = 0
        for lemma in phrase_lemmas:
            subtype = lemma.pos_subtype or "greetings"

            if lemma.guid and lemma.guid in existing_phrase_guids:
                print(f"  {lemma.guid}: already in phrases table; removing stale lemma.")
            else:
                if dry_run:
                    print(f"  Would move {lemma.guid} ({lemma.lemma_text!r}, subtype={subtype}).")
                else:
                    phrase = Phrase(
                        guid=lemma.guid,
                        phrase_subtype=subtype,
                        label=lemma.lemma_text,
                        definition=lemma.definition_text,
                        difficulty_level=lemma.difficulty_level,
                        verified=lemma.verified,
                        notes=lemma.notes,
                    )
                    session.add(phrase)
                    session.flush()  # assign phrase.id
                    for trans in lemma.translations:
                        session.add(
                            PhraseTranslation(
                                phrase_id=phrase.id,
                                language_code=trans.language_code,
                                translation=trans.translation,
                                translation_status=trans.translation_status,
                                translation_status_note=trans.translation_status_note,
                                verified=trans.verified,
                            )
                        )
                    if lemma.guid:
                        existing_phrase_guids.add(lemma.guid)

            if not dry_run:
                session.delete(lemma)
            moved += 1

        if dry_run:
            print(f"Dry run: would migrate {moved} phrase(s). Rolling back.")
            session.rollback()
        else:
            session.commit()
            print(f"Migrated {moved} phrase(s).")
        return moved
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Move phrases from lemmas into the phrases table")
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

    migrate(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
