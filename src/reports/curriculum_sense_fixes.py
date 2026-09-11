"""Preview or apply deterministic curriculum sense-order corrections.

The pass orders senses of the same English headword by stored prominence.
Cross-cohort moves reserve a small same-subtype group at their destination;
the remaining subtype runs are then repacked around those fixed groups.
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
from reports.curriculum_relevel import (
    COUNTRY_COHORT_LEVEL,
    COUNTRY_LEVEL_CAPACITIES,
    MAX_LEVEL_SIZE,
    MIN_LEVEL_SIZE,
    PROMINENCE_ORDER,
    TARGET_LEVEL_SIZE,
    US_STATE_COHORT_LEVEL,
    _family_reserved_level,
    _is_us_state,
)
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.schema import Lemma
from wordfreq.tools.country_word_priorities import CONTINENT_NAMES, COUNTRY_NAMES

SOURCE = "curriculum/blind-sense-spacing"
SPACING = 18
MIN_SUBTYPE_GROUP_SIZE = 5


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
                constants.GENERAL_DIFFICULTY_LEVEL_MAX,
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


def _subtype_key(lemma: Lemma) -> tuple[str, str]:
    return (lemma.pos_type, lemma.pos_subtype or lemma.pos_type)


def _level_bounds(level: int) -> tuple[int, int, int]:
    if level <= 5 or level in {COUNTRY_COHORT_LEVEL, US_STATE_COHORT_LEVEL}:
        return (0, constants.GENERAL_DIFFICULTY_LEVEL_MAX, 0)
    return COUNTRY_LEVEL_CAPACITIES.get(
        level,
        (MIN_LEVEL_SIZE, MAX_LEVEL_SIZE, TARGET_LEVEL_SIZE),
    )


def _repair_level_sizes(
    lemmas: Sequence[Lemma], proposed: dict[int, int], fixed_ids: set[int]
) -> None:
    """Move coherent pieces only where a sense splice breaks level bounds."""
    by_id = {lemma.id: lemma for lemma in lemmas}
    for _attempt in range(len(lemmas)):
        level_counts = Counter(proposed.values())
        deficit_levels = [
            level
            for level, count in sorted(level_counts.items())
            if count < _level_bounds(level)[0]
        ]
        surplus_levels = [
            level
            for level, count in sorted(level_counts.items())
            if count > _level_bounds(level)[1]
        ]
        if not deficit_levels and not surplus_levels:
            return

        target_level = deficit_levels[0] if deficit_levels else surplus_levels[0]
        target_count = level_counts[target_level]
        target_minimum, _target_maximum, target_goal = _level_bounds(target_level)
        needed = max(1, (target_minimum or target_goal) - target_count)
        target_subtypes = Counter(
            _subtype_key(by_id[lemma_id])
            for lemma_id, assigned_level in proposed.items()
            if assigned_level == target_level
        )
        donor_levels = sorted(
            (
                level
                for level, count in level_counts.items()
                if level != target_level and count > _level_bounds(level)[0]
            ),
            key=lambda level: (
                level not in surplus_levels,
                abs(level - target_level),
                level,
            ),
        )
        moved = False
        for donor_level in donor_levels:
            donor_minimum, _donor_maximum, _donor_goal = _level_bounds(donor_level)
            movable = [
                by_id[lemma_id]
                for lemma_id, assigned_level in proposed.items()
                if assigned_level == donor_level and lemma_id not in fixed_ids
            ]
            by_subtype: dict[tuple[str, str], list[Lemma]] = defaultdict(list)
            for lemma in movable:
                by_subtype[_subtype_key(lemma)].append(lemma)
            subtype_options = sorted(
                by_subtype,
                key=lambda subtype_key: (
                    target_subtypes[subtype_key] == 0,
                    abs(len(by_subtype[subtype_key]) - needed),
                    subtype_key,
                ),
            )
            for subtype_key in subtype_options:
                candidates = sorted(
                    by_subtype[subtype_key],
                    key=lambda lemma: (lemma.frequency_rank or 10**9, lemma.guid or ""),
                )
                existing_target_count = target_subtypes[subtype_key]
                minimum_move = 1 if existing_target_count >= MIN_SUBTYPE_GROUP_SIZE else 5
                maximum_move = level_counts[donor_level] - donor_minimum
                move_count = min(len(candidates), maximum_move, max(needed, minimum_move))
                remaining_subtype_count = len(candidates) - move_count
                if move_count < minimum_move or 0 < remaining_subtype_count < 5:
                    continue
                for companion in candidates[:move_count]:
                    proposed[companion.id] = target_level
                    fixed_ids.add(companion.id)
                moved = True
                break
            if moved:
                break
        if not moved:
            raise RuntimeError(f"Could not repair curriculum sizes around level {target_level}")
    raise RuntimeError("Curriculum size repair did not converge")


def rebalance_around_sense_moves(
    lemmas: Sequence[Lemma], proposed: dict[int, int]
) -> list[PlannedMove]:
    """Reserve coherent moved groups, then repack all remaining subtype runs."""
    headword_counts = Counter(lemma.lemma_text.casefold() for lemma in lemmas)
    fixed_ids: set[int] = set()
    polysemy_ids = {
        lemma.id for lemma in lemmas if headword_counts[lemma.lemma_text.casefold()] > 1
    }

    for lemma in lemmas:
        family_level = _family_reserved_level(lemma)
        if family_level is not None:
            proposed[lemma.id] = family_level
            fixed_ids.add(lemma.id)
        elif _is_us_state(lemma):
            proposed[lemma.id] = US_STATE_COHORT_LEVEL
            fixed_ids.add(lemma.id)
        elif lemma.pos_subtype == "region" and lemma.lemma_text in (
            COUNTRY_NAMES | CONTINENT_NAMES
        ):
            proposed[lemma.id] = COUNTRY_COHORT_LEVEL
            fixed_ids.add(lemma.id)
        elif int(lemma.difficulty_level or 0) <= 5 and lemma.id not in polysemy_ids:
            fixed_ids.add(lemma.id)
    fixed_ids.update(polysemy_ids)

    # A cross-cohort sense move carries enough same-subtype vocabulary with it
    # to avoid creating an isolated verb, noun subtype, or other singleton.
    moved_polysemy = [
        lemma
        for lemma in lemmas
        if lemma.id in polysemy_ids and proposed[lemma.id] != int(lemma.difficulty_level or 0)
    ]
    required_groups = sorted(
        {(proposed[lemma.id], _subtype_key(lemma)) for lemma in moved_polysemy}
    )
    for target_level, subtype_key in required_groups:
        fixed_group = [
            lemma
            for lemma in lemmas
            if lemma.id in fixed_ids
            and proposed[lemma.id] == target_level
            and _subtype_key(lemma) == subtype_key
        ]
        needed = max(0, MIN_SUBTYPE_GROUP_SIZE - len(fixed_group))
        candidates = [
            lemma
            for lemma in lemmas
            if lemma.id not in fixed_ids and _subtype_key(lemma) == subtype_key
        ]
        candidates.sort(
            key=lambda lemma: (
                int(lemma.difficulty_level or 0) != target_level,
                abs(int(lemma.difficulty_level or 0) - target_level),
                lemma.frequency_rank is None,
                lemma.frequency_rank or 0,
                lemma.guid or "",
            )
        )
        if len(candidates) < needed:
            # Some small subtypes are spliced across more destinations than
            # their inventory can support. Keep the reviewed sense move and
            # leave that thin group visible in the report for manual review.
            continue
        for companion in candidates[:needed]:
            proposed[companion.id] = target_level
            fixed_ids.add(companion.id)

    _repair_level_sizes(lemmas, proposed, fixed_ids)

    moves = [
        PlannedMove(
            lemma_id=lemma.id,
            guid=lemma.guid or "",
            old_level=int(lemma.difficulty_level or 0),
            new_level=proposed[lemma.id],
            reason=("sense prominence" if lemma.id in polysemy_ids else "cohort rebalance"),
        )
        for lemma in lemmas
        if proposed[lemma.id] != int(lemma.difficulty_level or 0)
    ]
    return sorted(moves, key=lambda move: (move.old_level, move.guid))


def build_moves(session: Session) -> list[PlannedMove]:
    """Build the complete subtype-aware correction plan."""
    lemmas = _active_lemmas(session)
    return rebalance_around_sense_moves(lemmas, plan_sense_levels(lemmas))


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
