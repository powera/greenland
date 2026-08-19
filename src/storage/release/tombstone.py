"""Read and write ``data/release/tombstones/guid_tombstones.jsonl``.

A tombstone is the record that a GUID has been permanently retired.  It is
release data for the same reason the GUIDs themselves are: ``data/release``
leaves a gap where a word was removed and never renumbers, and once the lemma
row is gone this file is the only remaining evidence that the number was ever
spent.  ``storage.utils.guid`` reads the table these records load into, so
losing the file would let allocation walk back onto published numbers.

The record is deliberately thin.  Everything in it either identifies the
retired GUID, says what it used to be, or points at what replaced it:

    {"guid": "A05_001", "original_lemma_text": "kind",
     "original_pos_type": "adjective", "original_pos_subtype": "quality",
     "replacement_guid": "A16_001", "reason": "release_history_gap",
     "notes": "...", "changed_by": "...", "tombstoned_at": "2026-06-15T00:00:00"}

``lemma_id`` is **not** part of the record even though the column exists.  It is
a local SQLite primary key: it differs after every bootstrap, and on the
synonym-merge path it names a row that is deleted moments later.  The GUID is
the portable identifier and ``replacement_guid`` carries the only link worth
shipping.

Optional fields are omitted rather than written as ``null`` so a hand-edited
file stays readable and re-exporting an unchanged database is byte-stable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from storage.crud.guid_tombstone import create_tombstone
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_TYPE_CHANGE,
    TOMBSTONE_REASONS,
    GuidTombstone,
)

RELEASE_DIRNAME = "tombstones"
RELEASE_FILENAME = "guid_tombstones.jsonl"

# Optional string fields, in the order they appear in the record.
_OPTIONAL_FIELDS = ("original_pos_subtype", "replacement_guid", "notes", "changed_by")


def _isoformat(value: Any) -> Optional[str]:
    """Render a timestamp as ISO-8601, tolerating a string already in that form."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def tombstone_to_release_record(tombstone: GuidTombstone) -> Dict[str, Any]:
    """Build the release JSONL record for one tombstone."""
    record: Dict[str, Any] = {
        "guid": tombstone.guid,
        "original_lemma_text": tombstone.original_lemma_text,
        "original_pos_type": tombstone.original_pos_type,
        "reason": tombstone.reason,
    }
    for field in _OPTIONAL_FIELDS:
        value = getattr(tombstone, field, None)
        if value:
            record[field] = value

    tombstoned_at = _isoformat(tombstone.tombstoned_at)
    if tombstoned_at:
        record["tombstoned_at"] = tombstoned_at
    return record


def read_release_records(release_dir: Path) -> List[Dict[str, Any]]:
    """Read tombstone records from a release directory, in file order.

    ``release_dir`` is the directory holding the file, i.e.
    ``data/release/tombstones``.
    """
    release_file = Path(release_dir) / RELEASE_FILENAME
    if not release_file.exists():
        return []

    records: List[Dict[str, Any]] = []
    with release_file.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def read_release_records_by_guid(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read tombstone records keyed by GUID, dropping any record without one."""
    return {
        str(record["guid"]): record
        for record in read_release_records(release_dir)
        if record.get("guid")
    }


def write_release_records(release_dir: Path, records: Iterable[Dict[str, Any]]) -> Path:
    """Write tombstone records to a release directory, sorted by GUID."""
    target_dir = Path(release_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    release_file = target_dir / RELEASE_FILENAME

    ordered = sorted(records, key=lambda record: str(record.get("guid") or ""))
    with release_file.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return release_file


def export_tombstones_to_release(session: Session, release_dir: Path) -> int:
    """Export every tombstone to the release directory. Returns the count."""
    tombstones = session.query(GuidTombstone).order_by(GuidTombstone.guid).all()
    write_release_records(
        release_dir, [tombstone_to_release_record(tombstone) for tombstone in tombstones]
    )
    return len(tombstones)


def import_release_record(session: Session, record: Dict[str, Any]) -> GuidTombstone:
    """Create or refresh one tombstone from a release record.

    An unrecognised ``reason`` is not fatal here the way it is for a caller
    minting a new tombstone: the file may predate a rename, and dropping the row
    would un-retire the GUID, which is far worse than an unfamiliar label.  It
    falls back to the default reason instead.
    """
    reason = str(record.get("reason") or TOMBSTONE_REASON_TYPE_CHANGE)
    if reason not in TOMBSTONE_REASONS:
        reason = TOMBSTONE_REASON_TYPE_CHANGE

    return create_tombstone(
        session=session,
        guid=str(record["guid"]),
        original_lemma_text=str(record.get("original_lemma_text") or ""),
        original_pos_type=str(record.get("original_pos_type") or ""),
        original_pos_subtype=record.get("original_pos_subtype"),
        replacement_guid=record.get("replacement_guid"),
        lemma_id=None,
        reason=reason,
        notes=record.get("notes"),
        changed_by=record.get("changed_by"),
    )


def import_tombstones_from_release(session: Session, release_dir: Path) -> int:
    """Import every tombstone record from a release directory. Returns the count.

    ``create_tombstone`` upserts on the GUID, so re-running this is safe and
    refreshes rows whose details changed rather than duplicating them.
    """
    records = read_release_records(release_dir)
    for record in records:
        if record.get("guid"):
            import_release_record(session, record)
    session.commit()
    return len(records)
