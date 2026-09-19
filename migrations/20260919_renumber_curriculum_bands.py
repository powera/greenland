#!/usr/bin/env python3
"""Renumber curriculum levels into the three banded ranges.

Levels become 1-20 for the curated core, 100-499 for the named units, and
1000-1299 for topic vocabulary (see the band comment in ``src/constants.py``).
The mapping is::

    1-20   unchanged -- the core keeps its numbering
    21-64  -> 100 + (old - 21) * 5

so L21 becomes 100, L22 becomes 105, and L64 becomes 315. Each old level owns
the five numbers after its new one: that is where its single-topic units go
when the level is cut into Animals 5, Disease 4 and the rest.

``-1`` is preserved everywhere. It is the exclusion sentinel, not a level.

Nothing is currently above L64 and the topic band holds no rows, so the
mapping is injective and no collision can arise.

Rerunning is safe. ``new_level`` is idempotent -- a level already inside a
band maps to itself -- so a second run moves nothing. The sentence rollup is
recomputed on *every* run rather than only when levels moved: a first run that
commits the lemma levels and then dies would otherwise leave every
``minimum_level`` stale, and a rerun would see the levels already banded and
conclude there was nothing to do. Recomputing unconditionally writes only the
rows that differ, and is what verifies a previous run finished.

``sentences.minimum_level`` is a rollup of its words' levels rather than an
authored value, so it is recomputed from the moved lemmas instead of mapped.

    GREENLAND_TEST_MODE=1 python migrations/20260919_renumber_curriculum_bands.py --dry-run
    GREENLAND_DISABLE_LLM=1 python migrations/20260919_renumber_curriculum_bands.py

The release tree under ``data/release`` carries the same levels and is NOT
touched here: it is regenerated from the database by the release export, which
is the normal direction. Run that afterwards.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import constants
from storage.backend import DataSourceConfig, create_session
from storage.crud.sentence import calculate_minimum_level
from storage.models.schema import Lemma, LemmaDifficultyOverride, Phrase, Sentence

#: Old levels at or below this keep their number: they are the core.
OLD_CORE_MAX = 20

#: The first old level that moves into the named band.
OLD_NAMED_MIN = 21

#: Spacing between two consecutive old levels in the named band. Each old level
#: owns this many numbers, which is where its single-topic units go.
NAMED_LEVEL_STRIDE = 5


@dataclass(frozen=True)
class MigrationResult:
    """Counts reported by one migration run."""

    lemmas_updated: int
    overrides_updated: int
    phrases_updated: int
    sentences_recomputed: int
    already_migrated: bool


def new_level(old_level: int) -> int:
    """Map one old level to its banded equivalent.

    Levels already inside a band are returned unchanged, so a second run is a
    no-op rather than a second shift.
    """
    if old_level <= 0:
        # -1 is the exclusion sentinel. It is not a level and never moves.
        return old_level
    if old_level <= OLD_CORE_MAX:
        return old_level
    if old_level >= constants.NAMED_DIFFICULTY_LEVEL_MIN:
        # Already migrated.
        return old_level
    return constants.NAMED_DIFFICULTY_LEVEL_MIN + (old_level - OLD_NAMED_MIN) * NAMED_LEVEL_STRIDE


def backup_database(config: DataSourceConfig) -> Optional[Path]:
    """Copy the SQLite file next to itself with a dated suffix."""
    db_path = Path(config.sqlite_path) if config.sqlite_path else None
    if db_path is None or not db_path.exists():
        return None
    stamp = date.today().strftime("%Y%m%d")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}-renumber-bands")
    if backup_path.exists():
        return backup_path
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate(config: DataSourceConfig, *, dry_run: bool) -> MigrationResult:
    """Apply the renumbering, or report what it would do."""
    session = create_session(config)
    try:
        lemmas_updated = 0
        for lemma in session.query(Lemma).filter(Lemma.difficulty_level.isnot(None)):
            current = lemma.difficulty_level
            if current is None:
                continue
            mapped = new_level(current)
            if mapped != current:
                lemmas_updated += 1
                if not dry_run:
                    lemma.difficulty_level = mapped

        overrides_updated = 0
        for override in session.query(LemmaDifficultyOverride):
            mapped = new_level(override.difficulty_level)
            if mapped != override.difficulty_level:
                overrides_updated += 1
                if not dry_run:
                    override.difficulty_level = mapped

        phrases_updated = 0
        for phrase in session.query(Phrase).filter(Phrase.difficulty_level.isnot(None)):
            current = phrase.difficulty_level
            if current is None:
                continue
            mapped = new_level(current)
            if mapped != current:
                phrases_updated += 1
                if not dry_run:
                    phrase.difficulty_level = mapped

        already_migrated = lemmas_updated == 0 and overrides_updated == 0 and phrases_updated == 0

        # The sentence rollup runs on every invocation, not only when levels
        # moved. A first run that commits the lemma levels and then dies leaves
        # every minimum_level stale, and a rerun would see all levels already
        # in-band and conclude there was nothing to do -- so the staleness
        # would never be repaired. Recomputing unconditionally costs one pass
        # and writes only the rows that actually differ, which also makes this
        # the check that a previous run finished.
        sentences_recomputed = 0
        if not dry_run:
            session.flush()
            for sentence in session.query(Sentence):
                # Read the stored value *before* recomputing: the recompute
                # queries the lemmas, which autoflushes the pending level
                # changes, and reading minimum_level afterwards can return a
                # value the ORM has already refreshed. Comparing against that
                # reports every repaired row as unchanged.
                stored_level = sentence.minimum_level
                recomputed = calculate_minimum_level(session, sentence)
                if recomputed != stored_level:
                    sentence.minimum_level = recomputed
                    sentences_recomputed += 1
            session.commit()

        return MigrationResult(
            lemmas_updated=lemmas_updated,
            overrides_updated=overrides_updated,
            phrases_updated=phrases_updated,
            sentences_recomputed=sentences_recomputed,
            already_migrated=already_migrated,
        )
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite database to migrate")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change and write nothing"
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
            print(f"Backed up database to {backup_path}")

    result = migrate(config, dry_run=args.dry_run)

    prefix = "Would update" if args.dry_run else "Updated"
    print(f"{prefix} {result.lemmas_updated} lemma levels")
    print(f"{prefix} {result.overrides_updated} per-language overrides")
    print(f"{prefix} {result.phrases_updated} phrase levels")
    if args.dry_run:
        print("Sentence minimum_level would be recomputed after the lemma levels move")
    else:
        print(f"Recomputed {result.sentences_recomputed} sentence minimum levels")
    if result.already_migrated and result.sentences_recomputed == 0:
        print("Nothing to do: every level is already inside a band.")
        return 0
    if result.already_migrated:
        print("")
        print(
            "Levels were already banded, but sentence rollups were stale -- a "
            "previous run did not finish. They are repaired now."
        )
    if not args.dry_run:
        print("")
        print("Next: regenerate data/release from the database, then re-export wireword.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
