#!/usr/bin/python3

"""Sync idioms between ``data/release/idioms`` and SQLite.

An idiom is a whole-record element: one ``base.jsonl``, no per-language files,
and a canonical record builder in :mod:`storage.release.idiom`. All the route
logic therefore comes from :mod:`barsukas.routes.sync.record_sync`; this module
only says what an idiom is.

Until now idioms could only move between the database and the release file
through ``storage.migrate`` on the command line, and only in the
create-if-absent direction - there was no way to reconcile an idiom that had
changed on either side.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import selectinload

from barsukas.routes.sync.record_sync import (
    REPOSITORY_ROOT,
    RecordSyncSpec,
    build_blueprint,
)
from storage.models.idiom import Idiom
from storage.release.idiom import (
    apply_release_record,
    idiom_to_release_record,
    import_release_record,
    read_release_records_by_guid,
    write_release_records,
)

DEFAULT_IDIOM_RELEASE_DIR = REPOSITORY_ROOT / "data" / "release" / "idioms"


def _get_release_dir() -> Path:
    """Get the path to the data/release/idioms directory."""
    return DEFAULT_IDIOM_RELEASE_DIR


def _query_idioms(db_session: Any) -> List[Idiom]:
    """Every GUIDed idiom, with equivalents eager-loaded for record building."""
    return list(
        db_session.query(Idiom)
        .filter(Idiom.guid.isnot(None))
        .options(selectinload(Idiom.equivalents))
        .order_by(Idiom.guid)
        .all()
    )


def _describe(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Columns shown for one idiom on the difference pages.

    Equivalents are summarized as ``lang: expression`` lines rather than a full
    table: what a reviewer needs to see is which languages moved and to what,
    not every optional gloss.
    """
    source = record.get("source") or {}
    fields: List[Tuple[str, str]] = [
        ("Expression", f"{source.get('expression', '')} ({source.get('language', '')})"),
        ("Meaning", str(record.get("meaning", ""))),
    ]
    equivalents = record.get("equivalents") or {}
    if equivalents:
        fields.append(
            (
                "Equivalents",
                "; ".join(
                    f"{language_code}: "
                    + ", ".join(entry.get("expression", "") for entry in entries)
                    for language_code, entries in equivalents.items()
                ),
            )
        )
    for label, key in (("Register", "register"), ("Region", "region"), ("Usage", "usageNote")):
        if record.get(key):
            fields.append((label, str(record[key])))
    if record.get("difficulty_level") is not None:
        fields.append(("Level", str(record["difficulty_level"])))
    return fields


SPEC = RecordSyncSpec(
    slug="idioms",
    blueprint_name="sync_idiom_release",
    noun="idiom",
    title="Idioms",
    icon="bi-chat-square-quote",
    get_release_dir=_get_release_dir,
    load_release=read_release_records_by_guid,
    write_release=write_release_records,
    query_rows=_query_idioms,
    to_record=idiom_to_release_record,
    import_record=import_release_record,
    apply_record=apply_release_record,
    describe=_describe,
    view_endpoint="idioms.view_idiom",
    view_id_arg="idiom_id",
)

bp = build_blueprint(SPEC)
