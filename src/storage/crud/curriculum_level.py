#!/usr/bin/python3

"""CRUD operations for curriculum level metadata and its name translations.

Writes validate what the client cannot repair -- a known CEFR value, known
language codes, ``extra`` keys that do not collide with the manifest fields --
and nothing more.  Prerequisites are stored as given (coerced to integers,
sorted and de-duplicated): a stale or odd prerequisite is a curation question,
not a reason to refuse the save.
"""

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional

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
    CurriculumLevel,
    CurriculumLevelTranslation,
)
from storage.translation_helpers import LANGUAGE_NAMES

#: Keys the manifest entry builds from columns; ``extra`` may not shadow them.
RESERVED_MANIFEST_KEYS: frozenset[str] = frozenset({"level", "name", "cefr", "prerequisites"})


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


def normalize_prerequisites(prerequisites: Iterable[Any]) -> List[int]:
    """Coerce prerequisites to a sorted, de-duplicated list of integers."""
    return sorted({int(prerequisite) for prerequisite in prerequisites})


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
) -> CurriculumLevel:
    """Create or replace the metadata for one level.

    The row's own fields are replaced whole rather than patched: every field
    passed here is the new value, so a caller editing one field reads the row
    first.  That keeps the release importer and the Barsukas form on one path.

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
    clean_prerequisites = normalize_prerequisites(prerequisites)
    clean_extra = normalize_extra(extra)
    new_values: Dict[str, Optional[str]] = {
        "name": clean_name,
        "cefr": normalize_cefr(cefr),
        "prerequisites": _dump(clean_prerequisites) if clean_prerequisites else None,
        "extra": _dump(clean_extra) if clean_extra else None,
        "notes": notes.strip() if notes and notes.strip() else None,
    }
    for language_code in translations or {}:
        _check_translation_language(language_code)

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


def to_manifest_entry(row: CurriculumLevel) -> Dict[str, Any]:
    """The client-facing record for one level, as ``config.levels`` ships it.

    ``name`` carries every language, English first.  Optional fields are
    omitted rather than null, and ``extra`` keys follow the fixed ones.
    """
    entry: Dict[str, Any] = {"level": row.level, "name": row.get_names()}
    if row.cefr:
        entry["cefr"] = row.cefr
    prerequisites = row.get_prerequisites()
    if prerequisites:
        entry["prerequisites"] = prerequisites
    entry.update(row.get_extra())
    return entry
