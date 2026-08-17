#!/usr/bin/python3

"""Sync names between ``data/release/names`` and SQLite.

Names ("George", "Fresh Mart") are release data because their per-language
renderings are: Lithuanian ``Džordžas``, Chinese ``乔治``, Japanese ``ジョージ``.
Those have to be identical in every text that casts the character, which makes
them content to be reviewed and shipped rather than scratch state.

Like idioms, a name is a whole-record element - one ``base.jsonl``, a canonical
record builder in :mod:`storage.release.name` - so the routes come from
:mod:`barsukas.routes.sync.record_sync` and this module only says what a name
is.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import selectinload

from barsukas.routes.sync.record_sync import (
    REPOSITORY_ROOT,
    RecordSyncSpec,
    build_blueprint,
)
from storage.models.name_entity import NAME_KIND_LABELS, Name
from storage.release.name import (
    apply_release_record,
    import_release_record,
    name_to_release_record,
    read_release_records_by_guid,
    write_release_records,
)

DEFAULT_NAME_RELEASE_DIR = REPOSITORY_ROOT / "data" / "release" / "names"


def _get_release_dir() -> Path:
    """Get the path to the data/release/names directory."""
    return DEFAULT_NAME_RELEASE_DIR


def _query_names(db_session: Any) -> List[Name]:
    """Every GUIDed name, with renderings eager-loaded for record building."""
    return list(
        db_session.query(Name)
        .filter(Name.guid.isnot(None))
        .options(selectinload(Name.translations))
        .order_by(Name.guid)
        .all()
    )


def _describe(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Columns shown for one name on the difference pages.

    Renderings are the point of the record, so they are listed in full as
    ``lang: rendering``; the per-language extras (IPA, sort key) are summarized
    as a count, since a reviewer comparing two sides needs to see *that* they
    differ, and the name's own page is where the detail lives.
    """
    fields: List[Tuple[str, str]] = [
        ("Name", str(record.get("name_text", ""))),
        ("Kind", NAME_KIND_LABELS.get(str(record.get("kind", "")), str(record.get("kind", "")))),
    ]
    if record.get("disambiguation"):
        fields.append(("Role", str(record["disambiguation"])))
    if record.get("gender"):
        fields.append(("Gender", str(record["gender"])))

    translations = record.get("translations") or {}
    if translations:
        fields.append(
            (
                "Renderings",
                "; ".join(
                    f"{language_code}: {rendering}"
                    for language_code, rendering in translations.items()
                ),
            )
        )
    metadata = record.get("translation_metadata") or {}
    if metadata:
        fields.append(("Pronunciation data", f"{len(metadata)} language(s)"))
    if record.get("notes"):
        fields.append(("Notes", str(record["notes"])))
    return fields


SPEC = RecordSyncSpec(
    slug="names",
    blueprint_name="sync_name_release",
    noun="name",
    title="Names",
    icon="bi-person-badge",
    get_release_dir=_get_release_dir,
    load_release=read_release_records_by_guid,
    write_release=write_release_records,
    query_rows=_query_names,
    to_record=name_to_release_record,
    import_record=import_release_record,
    apply_record=apply_release_record,
    describe=_describe,
    view_endpoint="names.detail",
    view_id_arg="name_id",
)

bp = build_blueprint(SPEC)
