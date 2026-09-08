"""Preview or apply deterministic curriculum sense-order corrections.

This is the deliberately small second pass over ``curriculum_relevel``.  It
orders senses of the same English headword by stored prominence, separates
differently prominent senses that share a level, and then uses unambiguous
lemmas as count-balancing fillers.  The pass preserves the number of senses in
every populated level, making it safe to iterate after reviewing the report.
"""

import argparse
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

from sqlalchemy.orm import Session

import constants
from reports.curriculum_relevel import PROMINENCE_ORDER, _theme
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.schema import Lemma

SOURCE = "curriculum/blind-sense-spacing"
SPACING = 18


@dataclass(frozen=True)
class PlannedMove:
    """One proposed level edit and its reason."""

    lemma_id: int
    guid: str
    old_level: int
    new_level: int
    reason: str


def _prominence_rank(lemma: Lemma) -> int:
    return PROMINENCE_ORDER.get(lemma.sense_prominence, 1)


def _active_lemmas(session: Session) -> list[Lemma]:
    return (
        session.query(Lemma)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.difficulty_level.between(
                constants.MIN_DIFFICULTY_LEVEL,
                constants.MAX_DIFFICULTY_LEVEL,
            ),
        )
        .all()
    )


def plan_sense_levels(lemmas: Sequence[Lemma]) -> dict[int, int]:
    """Sort existing levels by prominence and split prominence ties."""
    by_headword: dict[str, list[Lemma]] = defaultdict(list)
    for lemma in lemmas:
        by_headword[lemma.lemma_text.casefold()].append(lemma)

    proposed = {lemma.id: int(lemma.difficulty_level or 0) for lemma in lemmas}
    populated_max = max(proposed.values(), default=constants.MIN_DIFFICULTY_LEVEL)
    for senses in by_headword.values():
        if len(senses) < 2:
            continue
        ordered_senses = sorted(
            senses,
            key=lambda lemma: (
                _prominence_rank(lemma),
                int(lemma.difficulty_level or 0),
                lemma.guid or "",
            ),
        )
        available_levels = sorted(int(lemma.difficulty_level or 0) for lemma in senses)
        for lemma, level in zip(ordered_senses, available_levels):
            proposed[lemma.id] = level

        for prominent_index, prominent in enumerate(ordered_senses):
            prominent_level = proposed[prominent.id]
            for lesser in ordered_senses[prominent_index + 1 :]:
                if _prominence_rank(lesser) == _prominence_rank(prominent):
                    continue
                if proposed[lesser.id] != prominent_level:
                    continue
                later_level = prominent_level + SPACING
                if later_level <= populated_max:
                    proposed[lesser.id] = later_level
                else:
                    proposed[prominent.id] = max(
                        constants.MIN_DIFFICULTY_LEVEL,
                        prominent_level - SPACING,
                    )
                break

    # Reviewed example: keep the ordinary quality sense at 18 and splice the
    # two overlapping wealth senses to 36 for later duplicate review.
    poor_targets = {"A05_166": 18, "A05_070": 36, "A18_083": 36}
    for lemma in by_headword.get("poor", []):
        if lemma.guid in poor_targets:
            proposed[lemma.id] = poor_targets[lemma.guid]
    return proposed


def add_count_balancing_moves(
    lemmas: Sequence[Lemma], proposed: dict[int, int]
) -> list[PlannedMove]:
    """Restore each level's count with deterministic unambiguous fillers."""
    current_counts = Counter(int(lemma.difficulty_level or 0) for lemma in lemmas)
    proposed_counts = Counter(proposed[lemma.id] for lemma in lemmas)
    deficits: list[int] = []
    surpluses: list[int] = []
    for level in sorted(set(current_counts) | set(proposed_counts)):
        difference = proposed_counts[level] - current_counts[level]
        if difference < 0:
            deficits.extend([level] * -difference)
        elif difference > 0:
            surpluses.extend([level] * difference)
    if len(deficits) != len(surpluses):
        raise RuntimeError("Sense-level plan does not conserve lemma count")

    headword_counts = Counter(lemma.lemma_text.casefold() for lemma in lemmas)
    already_changed = {
        lemma.id for lemma in lemmas if proposed[lemma.id] != int(lemma.difficulty_level or 0)
    }
    for surplus_level, deficit_level in zip(surpluses, deficits):
        deficit_themes = Counter(
            _theme(lemma)
            for lemma in lemmas
            if proposed[lemma.id] == deficit_level and lemma.id not in already_changed
        )
        preferred_theme = deficit_themes.most_common(1)[0][0] if deficit_themes else None
        subtype_counts = Counter(
            (lemma.pos_type, lemma.pos_subtype or lemma.pos_type)
            for lemma in lemmas
            if proposed[lemma.id] == surplus_level
        )
        candidates = [
            lemma
            for lemma in lemmas
            if proposed[lemma.id] == surplus_level
            and lemma.id not in already_changed
            and headword_counts[lemma.lemma_text.casefold()] == 1
        ]
        candidates.sort(
            key=lambda lemma: (
                _theme(lemma) != preferred_theme,
                subtype_counts[(lemma.pos_type, lemma.pos_subtype or lemma.pos_type)] <= 5,
                -(lemma.frequency_rank or 0),
                lemma.guid or "",
            )
        )
        if not candidates:
            raise RuntimeError(f"No filler available at surplus level {surplus_level}")
        filler = candidates[0]
        proposed[filler.id] = deficit_level
        already_changed.add(filler.id)

    if Counter(proposed.values()) != current_counts:
        raise RuntimeError("Filler moves did not restore the original level counts")
    moves = [
        PlannedMove(
            lemma_id=lemma.id,
            guid=lemma.guid or "",
            old_level=int(lemma.difficulty_level or 0),
            new_level=proposed[lemma.id],
            reason=(
                "sense prominence"
                if headword_counts[lemma.lemma_text.casefold()] > 1
                else "count-balancing filler"
            ),
        )
        for lemma in lemmas
        if proposed[lemma.id] != int(lemma.difficulty_level or 0)
    ]
    return sorted(moves, key=lambda move: (move.old_level, move.guid))


def build_moves(session: Session) -> list[PlannedMove]:
    """Build the complete count-preserving correction plan."""
    lemmas = _active_lemmas(session)
    return add_count_balancing_moves(lemmas, plan_sense_levels(lemmas))


def _backup_database(database_path: Path) -> Path:
    """Create a WAL-consistent dated SQLite backup before applying changes."""
    backup_path = database_path.with_name(
        f"{database_path.name}.bak-{date.today():%Y%m%d}-sense-spacing"
    )
    if backup_path.exists():
        raise FileExistsError(f"Refusing to replace existing backup: {backup_path}")
    with sqlite3.connect(database_path) as source_connection:
        with sqlite3.connect(backup_path) as backup_connection:
            source_connection.backup(backup_connection)
    return backup_path


def _apply_moves(session: Session, moves: Sequence[PlannedMove]) -> None:
    lemmas_by_id = {
        lemma.id: lemma
        for lemma in session.query(Lemma).filter(Lemma.id.in_([move.lemma_id for move in moves]))
    }
    for move in moves:
        lemma = lemmas_by_id[move.lemma_id]
        if lemma.guid != move.guid or lemma.difficulty_level != move.old_level:
            raise RuntimeError(f"Lemma changed after preview: {move.guid}")
        lemma.difficulty_level = move.new_level
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_update",
            entity_guid=move.guid,
            changes=[FieldChange("difficulty_level", move.old_level, move.new_level)],
            extra={"reason": move.reason},
            lemma_id=move.lemma_id,
        )


def main() -> None:
    """Preview the correction plan, or back up and apply it transactionally."""
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
        moves = build_moves(session)
        for move in moves:
            print(f"{move.guid}: {move.old_level} -> {move.new_level} ({move.reason})")
        print(f"Planned {len(moves)} total moves")
        if not args.apply or not moves:
            print("Dry run only" if not args.apply else "No changes needed")
            return
        backup_path = _backup_database(args.db_path)
        print(f"Created backup {backup_path}")
        _apply_moves(session, moves)
        session.commit()
        print(f"Applied {len(moves)} total moves")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
