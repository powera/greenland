"""Capacity-aware volumes within equivalent curriculum topic families (series)."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from reports.curriculum_bands import PlannedMove, apply_moves
from storage.backend import DataSourceConfig
from storage.backup import create_backup
from storage.crud.curriculum_level import list_curriculum_levels
from storage.crud.operation_log import log_entity_operation
from storage.models.curriculum_level import CurriculumLevel
from storage.models.schema import Lemma


@dataclass(frozen=True)
class VolumeFamily:
    """A series whose volumes share one subject boundary, so any of them will do."""

    name: str
    series: str
    levels: tuple[int, ...]


def volume_families(session: Session) -> tuple[VolumeFamily, ...]:
    """The series whose volumes are interchangeable for word placement.

    Series and volume come from ``curriculum_levels`` -- the one place they are
    recorded.  Not every series qualifies: its volumes must all share volume
    1's CEFR and its (non-empty) notes, because the notes are the subject
    boundary the placement prompt shows, and two volumes with different
    boundaries are different subjects, not more room for the same one.
    """
    members: dict[str, list[CurriculumLevel]] = defaultdict(list)
    for row in list_curriculum_levels(session):
        if row.series is not None and row.volume is not None:
            members[row.series].append(row)
    families: list[VolumeFamily] = []
    for series, rows in sorted(members.items()):
        ordered = sorted(rows, key=lambda row: int(row.volume or 0))
        base = ordered[0]
        if len(ordered) < 2 or base.volume != 1 or not base.notes:
            continue
        if all(row.cefr == base.cefr and row.notes == base.notes for row in ordered):
            families.append(VolumeFamily(base.name, series, tuple(row.level for row in ordered)))
    return tuple(families)


def volume_context(session: Session) -> str:
    """Tell the model that numbered volumes share the same semantic boundary."""
    families = volume_families(session)
    if not families:
        return ""
    return (
        "\nNumbered volume families (same subject, not different meanings):\n"
        + "\n".join(
            f"{', '.join(str(level) for level in family.levels)} | {family.name}"
            for family in families
        )
        + (
            "\nChoose the correct subject family for this definition. Any offered volume of it "
            "is equivalent; application balances GUIDs using current database counts. "
            "Do not choose another subject merely because this family is large. "
            "The 80–120 target is advisory; no suitable subject still means fit=none.\n"
        )
    )


class VolumeAllocator:
    """Allocate against live counts, also reserving slots for uncommitted planned moves.

    Call under the application's writer lock. Never widen a frozen destination
    menu, move an already-correct family member, or change a semantic family.
    """

    def __init__(self, session: Session) -> None:
        self.families: dict[int, tuple[int, ...]] = {}
        families = volume_families(session)
        members = {level for family in families for level in family.levels}
        self.counts: Counter[int] = Counter(
            {
                level: count
                for level, count in session.query(Lemma.difficulty_level, func.count(Lemma.id))
                .filter(Lemma.difficulty_level.in_(members))
                .group_by(Lemma.difficulty_level)
                if level is not None
            }
        )
        for family in families:
            for member in family.levels:
                self.families[member] = family.levels

    def choose(self, proposed: int, allowed: Sequence[int], current: int | None) -> int:
        permitted = set(allowed)
        candidates = [level for level in self.families.get(proposed, ()) if level in permitted]
        if not candidates:
            return proposed
        if current in candidates:
            return int(current)
        target = min(candidates, key=lambda level: (self.counts[level], level))
        self.counts[target] += 1
        return target


def balance_volumes(
    session: Session,
    config: DataSourceConfig,
    *,
    dry_run: bool = False,
    series: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Minimally rebalance existing senses across the volumes of each family.

    Volumes are no longer created here: add the new level in Barsukas with the
    series, the next volume number and volume 1's CEFR and notes, then run
    this.  ``series`` limits the run to those slugs; each must be a family
    ``volume_families`` recognises.
    """
    if not dry_run:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    families = volume_families(session)
    if series is not None:
        known = {family.series: family for family in families}
        unknown = sorted(set(series) - set(known))
        if unknown:
            raise ValueError(f"Not an interchangeable volume family: {unknown}")
        families = tuple(known[slug] for slug in series)
    moves: list[PlannedMove] = []
    results: list[dict[str, Any]] = []
    for family in families:
        rows = (
            session.query(Lemma)
            .filter(Lemma.difficulty_level.in_(family.levels))
            .order_by(Lemma.guid)
            .all()
        )
        if any(not lemma.guid for lemma in rows):
            raise ValueError("All family members must have GUIDs")
        by_level: dict[int, list[Lemma]] = defaultdict(list)
        for lemma in rows:
            by_level[int(lemma.difficulty_level or 0)].append(lemma)
        quotient, remainder = divmod(len(rows), len(family.levels))
        desired = {
            level: quotient + int(position < remainder)
            for position, level in enumerate(family.levels)
        }
        excess = sorted(
            (lemma for level in family.levels for lemma in by_level[level][desired[level] :]),
            key=lambda lemma: str(lemma.guid),
        )
        cursor = 0
        for target in family.levels:
            deficit = max(0, desired[target] - len(by_level[target]))
            for lemma in excess[cursor : cursor + deficit]:
                moves.append(
                    PlannedMove(
                        lemma.id,
                        str(lemma.guid),
                        lemma.difficulty_level,
                        target,
                        f"Balance equivalent numbered volumes of {family.name}; definition unchanged",
                    )
                )
            cursor += deficit
        results.append(dict(family=family.name, levels=desired))
    if dry_run:
        return dict(families=results, moves=[asdict(move) for move in moves])
    if moves:
        print(
            "Minor backup:", create_backup(config, "balance-topic-vols", tier="minor"), flush=True
        )
        apply_moves(session, moves, source="curriculum-review/volume-balancing")
        log_entity_operation(
            session,
            source="curriculum-review/volume-balancing",
            operation_type="curriculum_volumes_balanced",
            fact=dict(families=results, moves=len(moves)),
        )
    session.commit()
    return dict(families=results, moved=len(moves))
