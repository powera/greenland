"""Capacity-aware volumes within explicitly equivalent curriculum topic families."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from reports.curriculum_bands import PlannedMove, apply_moves
from storage.backend import DataSourceConfig
from storage.backup import create_backup
from storage.crud.curriculum_level import list_curriculum_levels, set_curriculum_level
from storage.crud.operation_log import log_entity_operation
from storage.models.schema import Lemma


@dataclass(frozen=True)
class VolumeFamily:
    """Equivalent subject boundaries, rather than different sense categories."""

    name: str
    levels: tuple[int, ...]


VOLUME_FAMILIES = (
    VolumeFamily("Advanced Character, Thought and Feelings", (1300, 1310, 1311)),
    VolumeFamily("Advanced Actions, Change and Movement", (1301, 1320, 1321)),
    VolumeFamily("Figurative Language and Imagery", (1182, 1330)),
)


def volume_name(family: VolumeFamily, position: int) -> str:
    return family.name if position == 0 else f"{family.name} {position + 1}"


def volume_context() -> str:
    """Tell the model that numbered volumes share the same semantic boundary."""
    return (
        "\nNumbered volume families (same subject, not different meanings):\n"
        + "\n".join(
            f"{', '.join(str(level) for level in family.levels)} | {family.name}"
            for family in VOLUME_FAMILIES
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
        metadata = {row.level: row for row in list_curriculum_levels(session)}
        self.families: dict[int, tuple[int, ...]] = {}
        members = {level for family in VOLUME_FAMILIES for level in family.levels}
        self.counts: Counter[int] = Counter(
            {
                level: count
                for level, count in session.query(Lemma.difficulty_level, func.count(Lemma.id))
                .filter(Lemma.difficulty_level.in_(members))
                .group_by(Lemma.difficulty_level)
                if level is not None
            }
        )
        for family in VOLUME_FAMILIES:
            base = metadata.get(family.levels[0])
            if base is None:
                continue
            available = tuple(
                level
                for position, level in enumerate(family.levels)
                if level in metadata
                and metadata[level].name == volume_name(family, position)
                and metadata[level].cefr == base.cefr
                and metadata[level].notes == base.notes
            )
            for member in available:
                self.families[member] = available

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
    session: Session, config: DataSourceConfig, *, dry_run: bool = False
) -> dict[str, Any]:
    """Register the five continuation volumes and minimally rebalance existing senses."""
    if not dry_run:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    metadata = {row.level: row for row in list_curriculum_levels(session)}
    additions: list[dict[str, Any]] = []
    moves: list[PlannedMove] = []
    results: list[dict[str, Any]] = []
    for family in VOLUME_FAMILIES:
        base = metadata.get(family.levels[0])
        if base is None or base.name != family.name:
            raise ValueError(f"Missing or changed family base: {family.levels[0]}")
        for position, level in enumerate(family.levels):
            existing = metadata.get(level)
            name = volume_name(family, position)
            if existing is not None:
                if (
                    existing.name != name
                    or existing.cefr != base.cefr
                    or existing.notes != base.notes
                ):
                    raise ValueError(f"Volume metadata conflict: {level}")
            elif (
                session.query(Lemma.id).filter(Lemma.difficulty_level == level).first() is not None
            ):
                raise ValueError(f"Volume number already occupied: {level}")
            else:
                additions.append(
                    dict(
                        level=level,
                        name=name,
                        cefr=base.cefr,
                        notes=base.notes,
                        prerequisites=base.get_prerequisites(),
                    )
                )
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
        return dict(families=results, new_volumes=additions, moves=[asdict(move) for move in moves])
    if additions or moves:
        print(
            "Minor backup:", create_backup(config, "balance-topic-vols", tier="minor"), flush=True
        )
        for addition in additions:
            set_curriculum_level(session, source="curriculum-review/volume-balancing", **addition)
        apply_moves(session, moves, source="curriculum-review/volume-balancing")
        log_entity_operation(
            session,
            source="curriculum-review/volume-balancing",
            operation_type="curriculum_volumes_balanced",
            fact=dict(families=results, moves=len(moves), new_volumes=len(additions)),
        )
    session.commit()
    return dict(families=results, moved=len(moves), new_volumes=len(additions))
