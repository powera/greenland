"""Read and write ``data/release/levels/curriculum_levels.jsonl``.

Level metadata is curated by hand -- a name, a CEFR estimate, prerequisites --
and so has to survive a database rebuild the same way the lemmas do.  One line
per level, in level order:

    {"level": 120, "names": {"en": "Food & Cooking II"}, "cefr": "B1",
     "prerequisites": [100], "extra": {"icon": "🍳"}, "notes": "..."}

Optional fields are omitted rather than written as ``null`` so a hand-edited
file stays readable and re-exporting an unchanged database is byte-stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

from storage.crud.curriculum_level import list_curriculum_levels, set_curriculum_level
from storage.models.curriculum_level import CurriculumLevel
from storage.release.io import iter_release_lines, write_jsonl_atomic

RELEASE_DIRNAME = "levels"
RELEASE_FILENAME = "curriculum_levels.jsonl"


def to_release_record(row: CurriculumLevel) -> Dict[str, Any]:
    """Build the release JSONL record for one level."""
    record: Dict[str, Any] = {"level": row.level, "names": row.get_names()}
    if row.cefr:
        record["cefr"] = row.cefr
    prerequisites = row.get_prerequisites()
    if prerequisites:
        record["prerequisites"] = prerequisites
    extra = row.get_extra()
    if extra:
        record["extra"] = extra
    if row.notes:
        record["notes"] = row.notes
    return record


def read_release_records(release_dir: Path) -> List[Dict[str, Any]]:
    """Read level records from ``release_dir`` (i.e. ``data/release/levels``)."""
    release_file = Path(release_dir) / RELEASE_FILENAME
    if not release_file.exists():
        return []
    return [record for _, record in iter_release_lines(release_file)]


def write_release_records(release_dir: Path, records: Iterable[Dict[str, Any]]) -> Path:
    """Write level records to ``release_dir``, sorted by level."""
    release_file = Path(release_dir) / RELEASE_FILENAME
    ordered = sorted(records, key=lambda record: int(record["level"]))
    write_jsonl_atomic(release_file, ordered, sort_by_guid=False)
    return release_file


def export_to_release(session: Session, release_dir: Path) -> int:
    """Export every level's metadata to the release directory. Returns the count."""
    rows = list_curriculum_levels(session)
    write_release_records(release_dir, [to_release_record(row) for row in rows])
    return len(rows)


def import_release_record(session: Session, record: Dict[str, Any]) -> CurriculumLevel:
    """Create or replace one level from a release record."""
    return set_curriculum_level(
        session,
        level=int(record["level"]),
        names=record.get("names") or {},
        cefr=record.get("cefr"),
        prerequisites=record.get("prerequisites") or (),
        extra=record.get("extra"),
        notes=record.get("notes"),
    )


def import_from_release(session: Session, release_dir: Path) -> int:
    """Import every level record from a release directory. Returns the count.

    Upserts on the level number, so re-running is safe.  No ``source`` is
    passed: re-importing the whole file would otherwise log one entry per level
    per run.  Rows missing from the file are left alone rather than deleted.
    """
    records = [record for record in read_release_records(release_dir) if "level" in record]
    for record in records:
        import_release_record(session, record)
    session.commit()
    return len(records)
