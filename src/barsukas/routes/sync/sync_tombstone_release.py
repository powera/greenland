#!/usr/bin/python3

"""Sync GUID tombstones between ``data/release/tombstones`` and SQLite.

A tombstone records that a GUID has been permanently retired.  Until this page
existed the file moved in one direction only and only in bulk: written by a full
``sqlite-to-release`` export, and read back only by a complete bootstrap.  There
was no way to see that the database and the release file disagreed about which
GUIDs are spent, which matters because ``storage.utils.guid`` refuses to reissue
exactly the GUIDs this file names.

A tombstone is the simplest release type there is: one flat file, keyed by GUID,
with no per-language spread and no subtype directories, so it uses the
whole-record engine in :mod:`barsukas.routes.sync.record_sync`.

Deletion is switched off (``allow_delete=False``).  Every other type's removals
page offers export-or-delete, but deleting a tombstone would un-retire its GUID
and free it to be handed to a different word - the one outcome this whole
mechanism exists to prevent.  Export is the only action offered here.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from barsukas.routes.sync.record_sync import (
    REPOSITORY_ROOT,
    RecordSyncSpec,
    build_blueprint,
)
from storage.models.guid_tombstone import GuidTombstone
from storage.release.tombstone import (
    RELEASE_DIRNAME,
    import_release_record,
    read_release_records_by_guid,
    tombstone_to_release_record,
    write_release_records,
)

DEFAULT_TOMBSTONE_RELEASE_DIR = REPOSITORY_ROOT / "data" / "release" / RELEASE_DIRNAME


def _get_release_dir() -> Path:
    """Get the path to the data/release/tombstones directory."""
    return DEFAULT_TOMBSTONE_RELEASE_DIR


def _query_tombstones(db_session: Any) -> List[GuidTombstone]:
    """Every tombstone, in GUID order."""
    return list(db_session.query(GuidTombstone).order_by(GuidTombstone.guid).all())


def _apply_record(db_session: Any, record: Dict[str, Any], row: GuidTombstone) -> GuidTombstone:
    """Overwrite one tombstone from a release record.

    ``create_tombstone`` upserts on the GUID, so importing the record is also how
    an existing row is refreshed; the row argument is unused but kept to match
    the engine's signature.
    """
    return import_release_record(db_session, record)


def _describe(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Columns shown for one tombstone on the difference pages.

    What a reviewer needs is the retired word, what replaced it, and why - the
    provenance fields are shown when present because for the backfilled rows the
    note is the only account of where the record came from.
    """
    was = str(record.get("original_pos_type", ""))
    if record.get("original_pos_subtype"):
        was = f"{was} / {record['original_pos_subtype']}"

    fields: List[Tuple[str, str]] = [
        ("Was", f"{record.get('original_lemma_text', '')} ({was})"),
        ("Reason", str(record.get("reason", "")).replace("_", " ")),
    ]
    if record.get("replacement_guid"):
        fields.append(("Replaced by", str(record["replacement_guid"])))
    if record.get("tombstoned_at"):
        fields.append(("Retired", str(record["tombstoned_at"])))
    if record.get("changed_by"):
        fields.append(("By", str(record["changed_by"])))
    if record.get("notes"):
        fields.append(("Notes", str(record["notes"])))
    return fields


SPEC = RecordSyncSpec(
    slug="tombstones",
    blueprint_name="sync_tombstone_release",
    noun="tombstone",
    title="GUID Tombstones",
    icon="bi-archive",
    get_release_dir=_get_release_dir,
    load_release=read_release_records_by_guid,
    write_release=write_release_records,
    query_rows=_query_tombstones,
    to_record=tombstone_to_release_record,
    import_record=import_release_record,
    apply_record=_apply_record,
    describe=_describe,
    allow_delete=False,
)

bp = build_blueprint(SPEC)
