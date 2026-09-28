#!/usr/bin/python3

"""CRUD operations for curriculum level metadata.

Every write goes through :func:`set_curriculum_level`, which validates the
whole row before touching the database: names keyed by known language codes
with ``en`` present, a CEFR value from :data:`CEFR_LEVELS`, prerequisites that
are real curriculum levels and do not form a cycle, and ``extra`` keys that do
not collide with the manifest fields.  The manifest is read by a client that
cannot repair any of these, so bad data is refused here rather than exported.
"""

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from sqlalchemy.orm import Session

import constants
from storage.crud.operation_log import (
    CURRICULUM_LEVEL_CREATE,
    CURRICULUM_LEVEL_DELETE,
    CURRICULUM_LEVEL_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.models.curriculum_level import CEFR_LEVELS, CurriculumLevel
from storage.translation_helpers import LANGUAGE_NAMES

#: Keys the manifest entry builds from columns; ``extra`` may not shadow them.
RESERVED_MANIFEST_KEYS: frozenset[str] = frozenset({"level", "name", "cefr", "prerequisites"})


def is_curriculum_level(level: int) -> bool:
    """Whether ``level`` is a real level number (not the -1 exclusion sentinel)."""
    return constants.MIN_DIFFICULTY_LEVEL <= level <= constants.MAX_DIFFICULTY_LEVEL


def _dump(value: Any) -> str:
    """Serialize a JSON column deterministically, so re-saves compare equal."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_names(names: Mapping[str, str]) -> Dict[str, str]:
    """Validate and clean a ``names`` mapping.

    Raises:
        ValueError: On an unknown language code, a blank name, or no ``en``.
    """
    cleaned: Dict[str, str] = {}
    for lang_code, raw_name in names.items():
        if lang_code not in LANGUAGE_NAMES:
            raise ValueError(f"Unknown language code {lang_code!r} in level names")
        stripped = str(raw_name or "").strip()
        if stripped:
            cleaned[lang_code] = stripped
    if "en" not in cleaned:
        raise ValueError("Level names must include an English ('en') name")
    return cleaned


def normalize_cefr(cefr: Optional[str]) -> Optional[str]:
    """Validate a CEFR value, upper-casing it; blank means unset.

    Raises:
        ValueError: If the value is not one of CEFR_LEVELS.
    """
    if cefr is None or not cefr.strip():
        return None
    candidate = cefr.strip().upper()
    if candidate not in CEFR_LEVELS:
        raise ValueError(f"Unknown CEFR level {cefr!r}; expected one of {list(CEFR_LEVELS)}")
    return candidate


def normalize_prerequisites(level: int, prerequisites: Iterable[int]) -> List[int]:
    """Validate prerequisites for ``level``, returning them sorted and de-duplicated.

    Raises:
        ValueError: On a self-reference or a number outside the curriculum.
    """
    cleaned: Set[int] = set()
    for raw in prerequisites:
        prerequisite = int(raw)
        if prerequisite == level:
            raise ValueError(f"Level {level} cannot be its own prerequisite")
        if not is_curriculum_level(prerequisite):
            raise ValueError(f"Prerequisite {prerequisite} is not a curriculum level")
        cleaned.add(prerequisite)
    return sorted(cleaned)


def normalize_extra(extra: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Validate the free-form ``extra`` object.

    Raises:
        ValueError: If a key would shadow a manifest field, or a value is not
            JSON-serializable.
    """
    if not extra:
        return {}
    shadowed = sorted(RESERVED_MANIFEST_KEYS.intersection(extra))
    if shadowed:
        raise ValueError(f"extra may not set reserved manifest keys: {shadowed}")
    cleaned = dict(extra)
    try:
        json.dumps(cleaned)
    except (TypeError, ValueError) as error:
        raise ValueError(f"extra is not JSON-serializable: {error}") from error
    return cleaned


def find_prerequisite_cycle(graph: Mapping[int, Iterable[int]], start: int) -> Optional[List[int]]:
    """Return a prerequisite path from ``start`` back to itself, if one exists."""
    stack: List[tuple[int, List[int]]] = [(start, [start])]
    seen: Set[int] = set()
    while stack:
        node, path = stack.pop()
        for prerequisite in graph.get(node, ()):
            if prerequisite == start:
                return [*path, start]
            if prerequisite not in seen:
                seen.add(prerequisite)
                stack.append((prerequisite, [*path, prerequisite]))
    return None


def get_curriculum_level(session: Session, level: int) -> Optional[CurriculumLevel]:
    """The metadata row for ``level``, or None."""
    row: Optional[CurriculumLevel] = session.get(CurriculumLevel, level)
    return row


def list_curriculum_levels(session: Session) -> List[CurriculumLevel]:
    """Every metadata row, in level order."""
    rows: List[CurriculumLevel] = (
        session.query(CurriculumLevel).order_by(CurriculumLevel.level).all()
    )
    return rows


def set_curriculum_level(
    session: Session,
    level: int,
    names: Mapping[str, str],
    cefr: Optional[str] = None,
    prerequisites: Iterable[int] = (),
    extra: Optional[Mapping[str, Any]] = None,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> CurriculumLevel:
    """Create or replace the metadata for one level.

    The row is replaced whole rather than patched: every field passed here is
    the new value, so a caller editing one field reads the row first.  That
    keeps the release importer and a Barsukas form on one code path.

    Flushes but does not commit, matching the other CRUD modules.

    Args:
        session: Database session.
        level: Curriculum level number.
        names: UI language code -> display name; must include ``en``.
        cefr: One of CEFR_LEVELS, or None/blank for unset.
        prerequisites: Level numbers that must be completed first.
        extra: Free-form fields merged into the manifest entry.
        notes: Editorial notes (not exported to the client).
        source: Who made the change, for the operation log; None skips logging.

    Returns:
        The created or updated row.

    Raises:
        ValueError: On any invalid field, or a prerequisite cycle.
    """
    if not is_curriculum_level(level):
        raise ValueError(f"{level} is not a curriculum level")
    clean_names = normalize_names(names)
    clean_cefr = normalize_cefr(cefr)
    clean_prerequisites = normalize_prerequisites(level, prerequisites)
    clean_extra = normalize_extra(extra)
    clean_notes = notes.strip() if notes and notes.strip() else None

    graph: Dict[int, List[int]] = {
        row.level: row.get_prerequisites() for row in list_curriculum_levels(session)
    }
    graph[level] = clean_prerequisites
    cycle = find_prerequisite_cycle(graph, level)
    if cycle:
        raise ValueError(
            "Prerequisites would form a cycle: " + " -> ".join(str(step) for step in cycle)
        )

    new_values: Dict[str, Optional[str]] = {
        "names": _dump(clean_names),
        "cefr": clean_cefr,
        "prerequisites": _dump(clean_prerequisites) if clean_prerequisites else None,
        "extra": _dump(clean_extra) if clean_extra else None,
        "notes": clean_notes,
    }

    existing = get_curriculum_level(session, level)
    if existing is None:
        row = CurriculumLevel(level=level, **new_values)
        session.add(row)
        session.flush()
        if source:
            log_entity_operation(
                session,
                source=source,
                operation_type=CURRICULUM_LEVEL_CREATE,
                fact={"level": level, **new_values},
            )
        return row

    changes = [
        FieldChange(field, getattr(existing, field), value) for field, value in new_values.items()
    ]
    for field, value in new_values.items():
        setattr(existing, field, value)
    session.flush()
    log_field_changes(
        session,
        source=source,
        operation_type=CURRICULUM_LEVEL_UPDATE,
        entity_guid=None,
        changes=changes,
        extra={"level": level},
    )
    return existing


def delete_curriculum_level(session: Session, level: int, source: Optional[str] = None) -> bool:
    """Delete the metadata for ``level``. Returns False when there was none.

    Refuses while another level lists this one as a prerequisite: removing it
    would leave that level waiting on a level the client has never heard of.

    Raises:
        ValueError: If another level depends on ``level``.
    """
    row = get_curriculum_level(session, level)
    if row is None:
        return False
    dependents = [
        other.level
        for other in list_curriculum_levels(session)
        if level in other.get_prerequisites()
    ]
    if dependents:
        raise ValueError(f"Level {level} is a prerequisite of {dependents}")
    names = row.names
    session.delete(row)
    session.flush()
    if source:
        log_entity_operation(
            session,
            source=source,
            operation_type=CURRICULUM_LEVEL_DELETE,
            fact={"level": level, "names": names},
        )
    return True


def to_manifest_entry(row: CurriculumLevel) -> Dict[str, Any]:
    """The client-facing record for one level, as ``config.levels`` ships it.

    Optional fields are omitted rather than null, and ``extra`` keys follow the
    fixed ones.
    """
    entry: Dict[str, Any] = {"level": row.level, "name": row.get_names()}
    if row.cefr:
        entry["cefr"] = row.cefr
    prerequisites = row.get_prerequisites()
    if prerequisites:
        entry["prerequisites"] = prerequisites
    entry.update(row.get_extra())
    return entry
