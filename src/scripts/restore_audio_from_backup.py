#!/usr/bin/env python3
"""Restore ``audio_quality_reviews`` rows from an older database snapshot.

Rebuilding the database from ``data/release`` recovers only the *approved*
audio: the release round-trip filters on
``APPROVED_AUDIO_RELEASE_STATUSES`` (``storage/migrate.py``). In practice the
staging audio is what gets served -- most rows sit at ``pending_review`` and are
used, and only a few files are ever actively rejected -- so a release-only
rebuild silently drops the bulk of the served recordings.

This script copies those rows back out of a pre-rebuild snapshot. The MP3s
themselves are untouched: they already live in S3 under their ``manifest_md5``
names, so this restores metadata only and spends nothing.

**Rows are matched by GUID, never by integer id.** A rebuild renumbers both
``lemmas`` and ``sentences``, so ``lemma_id`` and ``sentence_id`` from the old
snapshot point at different words in the new database -- copying rows on those
columns attaches recordings to the wrong entries. Lemma audio is keyed by
``AudioQualityReview.guid``, and sentence audio is re-pointed by joining
old ``sentence_id`` -> old ``sentences.guid`` -> new ``sentences.id``.

Rows are skipped when:

* ``status`` is ``needs_replacement`` -- deliberately rejected audio.
* The GUID no longer resolves to a row in the target database -- the word or
  sentence was retired since the snapshot.
* An equivalent row already exists in the target. The existing row wins: it
  came from ``data/release``, which is the authority.

Usage::

    PYTHONPATH=src python src/scripts/restore_audio_from_backup.py \\
        --source-db data/wordfreq/linguistics.sqlite.bak.pre_rebuild_20260722 \\
        --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend.factory import create_session
from storage.models.schema import AudioQualityReview, Lemma, Sentence

# Audio that was reviewed and rejected must not come back.
SKIPPED_STATUS = "needs_replacement"

# Columns copied verbatim onto the restored row. ``lemma_id`` and
# ``sentence_id`` are deliberately absent: both are renumbered by a rebuild and
# are recomputed from the GUID instead.
COPIED_COLUMNS: Tuple[str, ...] = (
    "guid",
    "language_code",
    "voice_name",
    "grammatical_form",
    "filename",
    "expected_text",
    "manifest_md5",
    "s3_staging_url",
    "s3_staging_manifest_url",
    "s3_prod_url",
    "staging_agent",
    "status",
    "quality_issues",
    "notes",
    "reviewed_at",
    "reviewed_by",
    "accepted_at",
    "accepted_by",
)


def _identity(
    guid: Optional[str],
    sentence_key: Optional[str],
    language_code: str,
    voice_name: str,
    grammatical_form: Optional[str],
) -> Tuple[str, str, str, str, str]:
    """Return the comparable identity of an audio row.

    Mirrors the two unique constraints on ``audio_quality_reviews`` (one for
    lemma audio, one for sentence audio), with ``None`` folded to ``""`` so a
    NULL ``grammatical_form`` compares equal across databases.
    """
    return (
        guid or "",
        sentence_key or "",
        language_code or "",
        voice_name or "",
        grammatical_form or "",
    )


def _open_source_session(source_db: Path) -> Session:
    """Open a read-only session against the snapshot database."""
    engine = create_engine(f"sqlite:///file:{source_db}?mode=ro&uri=true")
    return sessionmaker(bind=engine)()


def restore(source_db: Path, target_session: Session, dry_run: bool) -> Dict[str, int]:
    """Copy missing audio rows from ``source_db`` into ``target_session``."""
    stats: Dict[str, int] = {
        "source_rows": 0,
        "skipped_rejected": 0,
        "skipped_unresolved": 0,
        "skipped_existing": 0,
        "restored_lemma": 0,
        "restored_sentence": 0,
    }

    # GUID -> id maps for the *target*, so restored rows point at the right
    # rows in the rebuilt database rather than at the snapshot's numbering.
    lemma_id_by_guid: Dict[str, int] = {
        guid: lemma_id
        for guid, lemma_id in target_session.query(Lemma.guid, Lemma.id).filter(
            Lemma.guid.isnot(None)
        )
    }
    sentence_id_by_guid: Dict[str, int] = {
        guid: sentence_id
        for guid, sentence_id in target_session.query(Sentence.guid, Sentence.id).filter(
            Sentence.guid.isnot(None)
        )
    }

    source_session = _open_source_session(source_db)
    try:
        # The snapshot's own sentence_id -> guid map, to translate its ids.
        source_sentence_guid_by_id: Dict[int, str] = {
            sentence_id: guid
            for sentence_id, guid in source_session.query(Sentence.id, Sentence.guid).filter(
                Sentence.guid.isnot(None)
            )
        }

        target_sentence_guid_by_id: Dict[int, str] = {
            sentence_id: guid for guid, sentence_id in sentence_id_by_guid.items()
        }

        existing: set[Tuple[str, str, str, str, str]] = set()
        for row in target_session.query(AudioQualityReview).all():
            existing_sentence_guid: Optional[str] = None
            if row.sentence_id is not None:
                existing_sentence_guid = target_sentence_guid_by_id.get(row.sentence_id)
            existing.add(
                _identity(
                    row.guid,
                    existing_sentence_guid,
                    row.language_code,
                    row.voice_name,
                    row.grammatical_form,
                )
            )

        to_add: List[AudioQualityReview] = []
        for row in source_session.query(AudioQualityReview).all():
            stats["source_rows"] += 1

            if row.status == SKIPPED_STATUS:
                stats["skipped_rejected"] += 1
                continue

            target_lemma_id: Optional[int] = None
            target_sentence_id: Optional[int] = None
            sentence_guid = None

            if row.sentence_id is not None:
                sentence_guid = source_sentence_guid_by_id.get(row.sentence_id)
                if sentence_guid is None:
                    stats["skipped_unresolved"] += 1
                    continue
                target_sentence_id = sentence_id_by_guid.get(sentence_guid)
                if target_sentence_id is None:
                    stats["skipped_unresolved"] += 1
                    continue
            else:
                if row.guid is None:
                    stats["skipped_unresolved"] += 1
                    continue
                target_lemma_id = lemma_id_by_guid.get(row.guid)
                if target_lemma_id is None:
                    stats["skipped_unresolved"] += 1
                    continue

            identity = _identity(
                row.guid, sentence_guid, row.language_code, row.voice_name, row.grammatical_form
            )
            if identity in existing:
                # data/release already supplied this row and is the authority.
                stats["skipped_existing"] += 1
                continue

            restored = AudioQualityReview(
                **{column: getattr(row, column) for column in COPIED_COLUMNS}
            )
            restored.lemma_id = target_lemma_id
            restored.sentence_id = target_sentence_id
            to_add.append(restored)
            existing.add(identity)

            if target_sentence_id is not None:
                stats["restored_sentence"] += 1
            else:
                stats["restored_lemma"] += 1
    finally:
        source_session.close()

    if dry_run:
        return stats

    target_session.add_all(to_add)
    target_session.commit()
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-db",
        type=Path,
        required=True,
        help="Snapshot database to copy audio rows out of",
    )
    add_common_args(parser)
    add_backend_args(parser)
    args = parser.parse_args(argv)

    source_db: Path = args.source_db.resolve()
    if not source_db.is_file():
        parser.error(f"Source database not found: {source_db}")

    target_session = create_session(get_data_source_config(args))
    try:
        stats = restore(source_db, target_session, dry_run=args.dry_run)
    finally:
        target_session.close()

    prefix = "Dry run: would restore" if args.dry_run else "Restored"
    print(f"Source rows scanned:            {stats['source_rows']}")
    print(f"  skipped ({SKIPPED_STATUS}):   {stats['skipped_rejected']}")
    print(f"  skipped (guid not in target): {stats['skipped_unresolved']}")
    print(f"  skipped (already present):    {stats['skipped_existing']}")
    print(f"{prefix} {stats['restored_lemma']} lemma audio rows")
    print(f"{prefix} {stats['restored_sentence']} sentence audio rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
