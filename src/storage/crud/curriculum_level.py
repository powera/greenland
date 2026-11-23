#!/usr/bin/python3

"""CRUD operations for curriculum level metadata and its name translations.

Writes validate what the client cannot repair -- a known CEFR value, known
language codes, known theme and content-flag slugs, ``extra`` keys that do not
collide with the manifest fields, a series volume used once.

Prerequisites are hard (Trakaido locks a unit until they are completed), so a
save is refused when one names the level itself, a level below
``constants.MIN_PREREQUISITE_LEVEL``, or would close a cycle -- counting the
prerequisite each series volume implies on the one before it.  A prerequisite
naming a level with no metadata row is still accepted, so a release file can
be imported in any order; ``validate_curriculum_levels`` reports those, and
gaps in a series, for the whole table.
"""

import enum
import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from sqlalchemy.orm import Session

import constants
from storage.crud.operation_log import (
    CURRICULUM_LEVEL_CREATE,
    CURRICULUM_LEVEL_DELETE,
    CURRICULUM_LEVEL_TRANSLATION_UPDATE,
    CURRICULUM_LEVEL_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.models.curriculum_level import (
    CEFR_LEVELS,
    CONTENT_FLAGS,
    LEVEL_THEMES,
    CurriculumLevel,
    CurriculumLevelTranslation,
)
from storage.translation_helpers import LANGUAGE_NAMES

#: Keys the manifest entry builds from columns (or the export computes);
#: ``extra`` may not shadow them.
RESERVED_MANIFEST_KEYS: frozenset[str] = frozenset(
    {
        "level",
        "name",
        "cefr",
        "prerequisites",
        "series",
        "volume",
        "themes",
        "content_flags",
        "freq_rank",
    }
)

#: The ``extra`` keys that ship to Trakaido.  Everything else in ``extra`` is
#: bookkeeping for curators and stays in the database and the release.
CLIENT_EXTRA_KEYS: frozenset[str] = frozenset({"icon"})

_SERIES_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class _Keep(enum.Enum):
    """Sentinel type for "leave this field as stored"."""

    KEEP = "keep"


#: Pass for a field of ``set_curriculum_level`` to leave its stored value.
KEEP = _Keep.KEEP


def is_curriculum_level(level: int) -> bool:
    """Whether ``level`` is a real level number (not the -1 exclusion sentinel)."""
    return constants.MIN_DIFFICULTY_LEVEL <= level <= constants.MAX_DIFFICULTY_LEVEL


def _dump(value: Any) -> str:
    """Serialize a JSON column deterministically, so re-saves compare equal."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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


def normalize_prerequisites(prerequisites: Iterable[Any], level: Optional[int] = None) -> List[int]:
    """Coerce prerequisites to a sorted, de-duplicated list of integers.

    Raises:
        ValueError: If one names ``level`` itself, the staging sentinel, or a
            level outside the curriculum or below ``MIN_PREREQUISITE_LEVEL``.
    """
    cleaned = sorted({int(prerequisite) for prerequisite in prerequisites})
    for prerequisite in cleaned:
        if prerequisite == level:
            raise ValueError(f"Level {level} cannot be its own prerequisite")
        if prerequisite == constants.STAGING_DIFFICULTY_LEVEL or not is_curriculum_level(
            prerequisite
        ):
            raise ValueError(f"Prerequisite {prerequisite} is not a curriculum level")
        if prerequisite < constants.MIN_PREREQUISITE_LEVEL:
            raise ValueError(
                f"Prerequisite {prerequisite} is below {constants.MIN_PREREQUISITE_LEVEL}; "
                "learners have always completed it by the time extra levels are offered"
            )
    return cleaned


def normalize_series(
    series: Optional[str], volume: Optional[Any]
) -> Tuple[Optional[str], Optional[int]]:
    """Validate a (series slug, volume) pair; a blank series means standalone.

    Raises:
        ValueError: On a malformed slug, a volume without a series (or the
            reverse), or a volume below 1.
    """
    slug = (series or "").strip()
    has_volume = volume is not None and str(volume).strip() != ""
    if not slug:
        if has_volume:
            raise ValueError("A volume needs a series")
        return None, None
    if not _SERIES_SLUG.match(slug):
        raise ValueError(f"Series {slug!r} must be a lower-case slug such as 'plants-and-growth'")
    if not has_volume:
        raise ValueError(f"Series {slug!r} needs a volume number")
    number = int(str(volume).strip())
    if number < 1:
        raise ValueError("Volume numbers start at 1")
    return slug, number


def _normalize_slugs(values: Iterable[str], allowed: Sequence[str], what: str) -> List[str]:
    """De-duplicate ``values`` keeping their order, rejecting unknown slugs."""
    cleaned: List[str] = []
    for value in values:
        slug = value.strip()
        if not slug:
            continue
        if slug not in allowed:
            raise ValueError(f"Unknown {what} {slug!r}; expected one of {list(allowed)}")
        if slug not in cleaned:
            cleaned.append(slug)
    return cleaned


def normalize_themes(themes: Iterable[str]) -> List[str]:
    """Validate theme slugs, keeping the given (relevance) order."""
    return _normalize_slugs(themes, LEVEL_THEMES, "theme")


def normalize_content_flags(flags: Iterable[str]) -> List[str]:
    """Validate content-flag slugs, returned sorted."""
    return sorted(_normalize_slugs(flags, CONTENT_FLAGS, "content flag"))


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


def _check_translation_language(language_code: str) -> None:
    """Raise unless ``language_code`` names a known non-English language."""
    if language_code == "en":
        raise ValueError("The English name is the level's name, not a translation")
    if language_code not in LANGUAGE_NAMES:
        raise ValueError(f"Unknown language code {language_code!r}")


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


# --- The prerequisite graph ------------------------------------------------
#
# Worked on plain (level -> stored prerequisites, series, volume) tuples rather
# than rows, so a save can check the graph *with* its new values before
# writing them.

LevelLinks = Tuple[List[int], Optional[str], Optional[int]]


def _links(row: CurriculumLevel) -> LevelLinks:
    return row.get_prerequisites(), row.series, row.volume


def implied_prerequisites(links: Mapping[int, LevelLinks]) -> Dict[int, int]:
    """Level -> the previous volume of its series, for every volume after the first.

    "Previous" is the highest volume number below this one, so a gap in the
    numbering does not break the chain.  A previous volume below
    ``MIN_PREREQUISITE_LEVEL`` (a series that starts in the core) is left out,
    for the same reason such a level cannot be a stored prerequisite.
    """
    members: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    for level, (_, series, volume) in links.items():
        if series is not None and volume is not None:
            members[series].append((volume, level))
    implied: Dict[int, int] = {}
    for volumes in members.values():
        ordered = sorted(volumes)
        for (_, previous), (_, level) in zip(ordered, ordered[1:]):
            if previous >= constants.MIN_PREREQUISITE_LEVEL:
                implied[level] = previous
    return implied


def effective_prerequisites(links: Mapping[int, LevelLinks]) -> Dict[int, List[int]]:
    """Level -> stored plus implied prerequisites, sorted.  Levels with none are omitted."""
    implied = implied_prerequisites(links)
    effective: Dict[int, List[int]] = {}
    for level, (stored, _, _) in links.items():
        combined = set(stored)
        if level in implied:
            combined.add(implied[level])
        if combined:
            effective[level] = sorted(combined)
    return effective


def find_cycle(graph: Mapping[int, Sequence[int]], start: int) -> Optional[List[int]]:
    """A prerequisite path from ``start`` back to itself, or None.

    Returned as ``[start, ..., start]`` so it can be shown to a curator.
    """
    stack: List[Tuple[int, List[int]]] = [(start, [start])]
    seen: Set[int] = set()
    while stack:
        node, path = stack.pop()
        for prerequisite in graph.get(node, ()):
            if prerequisite == start:
                return path + [start]
            if prerequisite not in seen:
                seen.add(prerequisite)
                stack.append((prerequisite, path + [prerequisite]))
    return None


def _all_links(session: Session) -> Dict[int, LevelLinks]:
    return {row.level: _links(row) for row in list_curriculum_levels(session)}


def _check_links(session: Session, level: int, links: LevelLinks) -> None:
    """Raise if saving ``links`` for ``level`` reuses a volume or closes a cycle."""
    current = _all_links(session)
    _, series, volume = links
    if series is not None:
        for other, (_, other_series, other_volume) in current.items():
            if other != level and other_series == series and other_volume == volume:
                raise ValueError(f"Level {other} is already volume {volume} of series {series!r}")
    current[level] = links
    cycle = find_cycle(effective_prerequisites(current), level)
    if cycle is not None:
        raise ValueError(
            "Prerequisites would form a cycle: " + " -> ".join(str(node) for node in cycle)
        )


def validate_curriculum_levels(session: Session) -> List[str]:
    """Whole-table problems a single save cannot see, as readable messages.

    Reports prerequisite cycles, prerequisites naming a level with no metadata
    row, and series whose volumes are not numbered 1..n.  An empty list means
    the table is consistent.
    """
    links = _all_links(session)
    problems: List[str] = []
    graph = effective_prerequisites(links)
    reported: Set[int] = set()
    for level in sorted(graph):
        if level in reported:
            continue
        cycle = find_cycle(graph, level)
        if cycle is not None:
            reported.update(cycle)
            problems.append("Prerequisite cycle: " + " -> ".join(str(node) for node in cycle))
    for level, (stored, _, _) in sorted(links.items()):
        for prerequisite in stored:
            if prerequisite not in links:
                problems.append(f"Level {level} requires {prerequisite}, which has no metadata row")
    members: Dict[str, List[int]] = defaultdict(list)
    for level, (_, series, volume) in links.items():
        if series is not None and volume is not None:
            members[series].append(volume)
    for series, volumes in sorted(members.items()):
        if sorted(volumes) != list(range(1, len(volumes) + 1)):
            problems.append(
                f"Series {series!r} has volumes {sorted(volumes)}; expected 1..{len(volumes)}"
            )
    return problems


def set_level_translation(
    session: Session,
    level: int,
    language_code: str,
    name: Optional[str],
    source: Optional[str] = None,
) -> Optional[CurriculumLevelTranslation]:
    """Set, replace or (with a blank ``name``) remove one translated name.

    Flushes but does not commit.

    Returns:
        The translation row, or None when it was removed or never existed.

    Raises:
        ValueError: If the level has no row, or the language is unknown or English.
    """
    _check_translation_language(language_code)
    row = get_curriculum_level(session, level)
    if row is None:
        raise ValueError(f"Level {level} has no metadata row to translate")

    cleaned = (name or "").strip()
    existing = next(
        (
            translation
            for translation in row.translations
            if translation.language_code == language_code
        ),
        None,
    )
    old_name = existing.name if existing else None
    if cleaned == (old_name or ""):
        return existing

    result: Optional[CurriculumLevelTranslation]
    if existing is None:
        result = CurriculumLevelTranslation(level=level, language_code=language_code, name=cleaned)
        row.translations.append(result)
    elif not cleaned:
        row.translations.remove(existing)
        result = None
    else:
        existing.name = cleaned
        result = existing
    session.flush()

    log_field_changes(
        session,
        source=source,
        operation_type=CURRICULUM_LEVEL_TRANSLATION_UPDATE,
        entity_guid=None,
        changes=[FieldChange("name", old_name, cleaned or None)],
        extra={"level": level, "language_code": language_code},
    )
    return result


def set_curriculum_level(
    session: Session,
    level: int,
    name: str,
    cefr: Optional[str] = None,
    prerequisites: Iterable[Any] = (),
    extra: Optional[Mapping[str, Any]] = None,
    notes: Optional[str] = None,
    translations: Optional[Mapping[str, Optional[str]]] = None,
    source: Optional[str] = None,
    series: Union[Optional[str], _Keep] = KEEP,
    volume: Union[Optional[int], _Keep] = KEEP,
    themes: Union[Iterable[str], _Keep] = KEEP,
    content_flags: Union[Iterable[str], _Keep] = KEEP,
) -> CurriculumLevel:
    """Create or replace the metadata for one level.

    The row's own fields are replaced whole rather than patched: every field
    passed here is the new value, so a caller editing one field reads the row
    first.  That keeps the release importer and the Barsukas form on one path.

    ``series``, ``volume``, ``themes`` and ``content_flags`` are the exception:
    they default to ``KEEP``, which leaves the stored value (or none, for a new
    row), so callers that rename a level or set its CEFR need not know about
    them.  The release importer and the Barsukas form pass them explicitly.

    ``translations`` is the exception.  None leaves them untouched; a mapping
    sets each language it names, and a blank value removes that language.
    Languages it does not name are left alone.

    Flushes but does not commit, matching the other CRUD modules.

    Raises:
        ValueError: On a blank name, a level outside the curriculum, or any
            invalid field.
    """
    if not is_curriculum_level(level):
        raise ValueError(f"{level} is not a curriculum level")
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("A level needs an English name")
    clean_prerequisites = normalize_prerequisites(prerequisites, level)
    clean_extra = normalize_extra(extra)
    existing = get_curriculum_level(session, level)
    clean_series, clean_volume = normalize_series(
        (existing.series if existing else None) if isinstance(series, _Keep) else series,
        (existing.volume if existing else None) if isinstance(volume, _Keep) else volume,
    )
    clean_themes = (
        (existing.get_themes() if existing else [])
        if isinstance(themes, _Keep)
        else normalize_themes(themes)
    )
    clean_flags = (
        (existing.get_content_flags() if existing else [])
        if isinstance(content_flags, _Keep)
        else normalize_content_flags(content_flags)
    )
    new_values: Dict[str, Any] = {
        "name": clean_name,
        "cefr": normalize_cefr(cefr),
        "prerequisites": _dump(clean_prerequisites) if clean_prerequisites else None,
        "series": clean_series,
        "volume": clean_volume,
        "themes": _dump(clean_themes) if clean_themes else None,
        "content_flags": _dump(clean_flags) if clean_flags else None,
        "extra": _dump(clean_extra) if clean_extra else None,
        "notes": notes.strip() if notes and notes.strip() else None,
    }
    for language_code in translations or {}:
        _check_translation_language(language_code)
    _check_links(session, level, (clean_prerequisites, clean_series, clean_volume))
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
    else:
        row = existing
        changes = [
            FieldChange(field, getattr(row, field), value) for field, value in new_values.items()
        ]
        for field, value in new_values.items():
            setattr(row, field, value)
        session.flush()
        log_field_changes(
            session,
            source=source,
            operation_type=CURRICULUM_LEVEL_UPDATE,
            entity_guid=None,
            changes=changes,
            extra={"level": level},
        )

    for language_code, translated in (translations or {}).items():
        set_level_translation(session, level, language_code, translated, source=source)
    return row


def delete_curriculum_level(session: Session, level: int, source: Optional[str] = None) -> bool:
    """Delete the metadata (and translations) for ``level``.

    Returns False when there was none.  Other levels naming it as a
    prerequisite keep doing so; the manifest drops a prerequisite on a level it
    does not ship.
    """
    row = get_curriculum_level(session, level)
    if row is None:
        return False
    names = row.get_names()
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


def patch_curriculum_level(
    session: Session, level: int, source: Optional[str] = None, **changes: Any
) -> CurriculumLevel:
    """Change some fields of an existing level, keeping the rest.

    ``changes`` takes the keyword arguments of ``set_curriculum_level`` other
    than ``level`` and ``source``.

    Raises:
        ValueError: If the level has no row, or a change is invalid.
    """
    row = get_curriculum_level(session, level)
    if row is None:
        raise ValueError(f"Level {level} has no metadata row")
    current: Dict[str, Any] = {
        "name": row.name,
        "cefr": row.cefr,
        "prerequisites": row.get_prerequisites(),
        "extra": row.get_extra(),
        "notes": row.notes,
    }
    current.update(changes)
    return set_curriculum_level(session, level, source=source, **current)


def to_manifest_entry(
    row: CurriculumLevel, prerequisites: Optional[Sequence[int]] = None
) -> Dict[str, Any]:
    """The client-facing record for one level, as ``config.levels`` ships it.

    ``name`` carries every language, English first.  Optional fields are
    omitted rather than null, and the whitelisted ``extra`` keys follow the
    fixed ones.  ``prerequisites`` overrides the stored list; pass the
    effective one (``manifest_entries`` does) so series volumes chain.
    """
    entry: Dict[str, Any] = {"level": row.level, "name": row.get_names()}
    if row.cefr:
        entry["cefr"] = row.cefr
    shipped = list(prerequisites) if prerequisites is not None else row.get_prerequisites()
    if shipped:
        entry["prerequisites"] = shipped
    if row.series is not None and row.volume is not None:
        entry["series"] = row.series
        entry["volume"] = row.volume
    themes = row.get_themes()
    if themes:
        entry["themes"] = themes
    flags = row.get_content_flags()
    if flags:
        entry["content_flags"] = flags
    entry.update({key: value for key, value in row.get_extra().items() if key in CLIENT_EXTRA_KEYS})
    return entry


def manifest_entries(rows: Sequence[CurriculumLevel]) -> List[Dict[str, Any]]:
    """Manifest entries for ``rows``, with each series volume requiring the one before."""
    effective = effective_prerequisites({row.level: _links(row) for row in rows})
    return [to_manifest_entry(row, effective.get(row.level, [])) for row in rows]
