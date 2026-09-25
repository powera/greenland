"""Preview or apply the core-curriculum polysemy rule.

In the core (levels 1-30) a headword is taught in its most natural sense only;
its other senses belong to the named unit of their subtype (level 100+). Two
cases keep more than one sense in the core:

* a noun/adjective or noun/verb pair -- "square" the shape and the adjective,
  "fear" the feeling and the verb -- where teaching both forms side by side is
  the point;
* two genuinely core meanings, listed by hand in :data:`CORE_POLYSEMY_ALLOWED`.
  This is deliberately short: river bank can wait for the named band.

Family-generator variants (male/female cousin) are reserved by that generator
and exempt.

Anything less clear is reported and left alone: tied prominence labels, a
cross-POS pair that is not a word form pairing (after as preposition and
conjunction), or a lesser sense sitting in the hand-curated levels 1-5. The
fix for those is to correct ``sense_prominence`` in Barsukas and re-run.

The full relevel (``curriculum_relevel.py``) applies the same rule and packs
the moved senses into named units. Run standalone, this module moves each one
to the named level that already holds most of its subtype.
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy.orm import Session

import constants
from reports.curriculum_bands import (
    PRESERVED_LEVEL_MAX,
    PROMINENCE_ORDER,
    PlannedMove,
    WarningRow,
    apply_moves,
    backup_database,
    band_of,
    current_level,
    family_reserved_level,
    subtype_key,
)
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import Lemma

SOURCE = "curriculum/core-polysemy"

# Headwords with two senses that both belong in the core. Edit by hand.
#
# fish: the animal and the food are a hairy distinction, and both are basic.
# left: "left vs right" and "what's left" are both everyday meanings.
CORE_POLYSEMY_ALLOWED: frozenset[str] = frozenset({"fish", "left"})

# Cross-POS pairs taught together as forms of one word.
PAIRED_POS_TYPES: frozenset[frozenset[str]] = frozenset(
    {frozenset({"noun", "adjective"}), frozenset({"noun", "verb"})}
)


def _prominence_rank(lemma: Lemma) -> int:
    return PROMINENCE_ORDER.get(lemma.sense_prominence, 1)


def _active_lemmas(session: Session) -> list[Lemma]:
    return (
        session.query(Lemma)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.difficulty_level.between(
                constants.MIN_DIFFICULTY_LEVEL,
                constants.GENERAL_DIFFICULTY_LEVEL_MAX,
            ),
        )
        .all()
    )


def plan_core_polysemy(lemmas: Sequence[Lemma]) -> tuple[list[Lemma], list[WarningRow]]:
    """Return the core senses that should leave the core, and the unclear cases."""
    by_headword: dict[str, list[Lemma]] = defaultdict(list)
    for lemma in lemmas:
        if band_of(lemma.difficulty_level) == "core" and family_reserved_level(lemma) is None:
            by_headword[lemma.lemma_text.casefold()].append(lemma)

    leaving: list[Lemma] = []
    warnings: list[WarningRow] = []
    for headword, senses in sorted(by_headword.items()):
        if len(senses) < 2 or headword in CORE_POLYSEMY_ALLOWED:
            continue
        keeper = min(
            senses,
            key=lambda lemma: (_prominence_rank(lemma), current_level(lemma), lemma.guid or ""),
        )
        for sense in sorted(senses, key=lambda lemma: lemma.guid or ""):
            if sense is keeper:
                continue
            reason: Optional[str] = None
            if sense.pos_type != keeper.pos_type:
                if frozenset({sense.pos_type, keeper.pos_type}) in PAIRED_POS_TYPES:
                    continue
                reason = f"{keeper.pos_type}/{sense.pos_type} is not a word form pairing"
            elif _prominence_rank(sense) == _prominence_rank(keeper):
                reason = f"tied prominence ({sense.sense_prominence or 'common'})"
            elif current_level(sense) <= PRESERVED_LEVEL_MAX:
                reason = f"lesser sense is in hand-curated level {current_level(sense)}"
            if reason is None:
                leaving.append(sense)
                continue
            warnings.append(
                WarningRow(
                    "core-polysemy-unclear",
                    sense.lemma_text,
                    f"{keeper.guid};{sense.guid}",
                    f"kept both in core: {reason}",
                )
            )
    return leaving, warnings


def named_destinations(lemmas: Sequence[Lemma]) -> dict[tuple[str, str], int]:
    """The named level holding the most lemmas of each subtype."""
    counts: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    for lemma in lemmas:
        if band_of(lemma.difficulty_level) == "named":
            counts[subtype_key(lemma)][current_level(lemma)] += 1
    return {
        key: min(level_counts, key=lambda level: (-level_counts[level], level))
        for key, level_counts in counts.items()
    }


def plan_moves(lemmas: Sequence[Lemma]) -> tuple[list[PlannedMove], list[WarningRow]]:
    """Move each leaving sense to the named level that holds most of its subtype."""
    leaving, warnings = plan_core_polysemy(lemmas)
    destinations = named_destinations(lemmas)
    moves: list[PlannedMove] = []
    for lemma in leaving:
        destination = destinations.get(subtype_key(lemma))
        if destination is None:
            warnings.append(
                WarningRow(
                    "core-polysemy-unclear",
                    lemma.lemma_text,
                    lemma.guid or "",
                    f"no named level holds {'/'.join(subtype_key(lemma))}; left in core",
                )
            )
            continue
        moves.append(
            PlannedMove(
                lemma_id=lemma.id,
                guid=lemma.guid or "",
                old_level=current_level(lemma),
                new_level=destination,
                reason="core polysemy",
            )
        )
    return sorted(moves, key=lambda move: (move.old_level, move.guid)), warnings


def main() -> None:
    """Preview the polysemy moves, or back up and apply them transactionally."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    args = parser.parse_args()
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=str(args.db_path),
    )
    session = create_session(config)
    try:
        moves, warnings = plan_moves(_active_lemmas(session))
        for warning in warnings:
            print(f"warning {warning.headword} ({warning.guids}): {warning.details}")
        for move in moves:
            print(f"{move.guid}: {move.old_level} -> {move.new_level} ({move.reason})")
        print(f"Planned {len(moves)} total moves")
        if not args.apply or not moves:
            print("Dry run only" if not args.apply else "No changes needed")
            return
        backup_path = backup_database(args.db_path, "core-polysemy")
        print(f"Created backup {backup_path}")
        apply_moves(session, moves, source=SOURCE)
        session.commit()
        print(f"Applied {len(moves)} total moves")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
