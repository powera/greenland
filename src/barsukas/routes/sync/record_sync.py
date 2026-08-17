#!/usr/bin/python3

"""A whole-record sync engine, and the blueprints built from it.

Idioms and names are both *small, single-file* release types: one
``base.jsonl``, no per-language files, no subtype directories, and a canonical
record builder in :mod:`storage.release`. That makes their sync fundamentally
simpler than the lemma one - there is no field-by-field reconciliation to do,
because the record either matches the database or it does not.

So rather than two more near-identical 800-line blueprints, both are described
by a :class:`RecordSyncSpec` and share these four modes:

``additions``
    GUIDs in the release file that the database does not have. Import them.
``removals``
    GUIDs in the database that the release file does not have. Export them
    (the usual direction) or delete them.
``changes``
    GUIDs in both whose records differ. Pick a side, per row.
``export``
    Rewrite the whole release file from the database.

The lemma and sentence syncs stay separate on purpose: their release data is
spread over per-language and grouped files, and their reconciliation is
per-field. Sharing only the file I/O with them (:mod:`release_io`) is the right
amount of sharing; sharing this engine would not be.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.routes.sync.actions import (
    SKIP,
    USE_DB,
    USE_RELEASE,
    SyncOutcome,
    bulk_actions_for,
    is_readonly,
    parse_bulk_request,
    parse_row_actions,
)
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, paginate
from storage.crud.operation_log import log_operation

logger = logging.getLogger(__name__)

# The repository root is five parents up from this file
# (src/barsukas/routes/sync/record_sync.py).
REPOSITORY_ROOT = Path(__file__).parent.parent.parent.parent.parent


@dataclass(frozen=True)
class RecordSyncSpec:
    """Everything the engine needs to sync one whole-record element type."""

    #: URL segment and blueprint name stem, e.g. "idioms".
    slug: str
    #: Blueprint name, e.g. "sync_idiom_release".
    blueprint_name: str
    #: Singular noun for flash messages and headings, e.g. "idiom".
    noun: str
    #: Plural title for the page heading, e.g. "Idioms".
    title: str
    #: Bootstrap icon name shown beside the heading.
    icon: str
    #: Returns the directory holding the type's base.jsonl. A callable rather
    #: than a plain path so the location resolves per request, matching how the
    #: other sync blueprints expose theirs through a ``_get_release_dir()``.
    get_release_dir: Callable[[], Path]

    #: Read the release directory into {guid: record}.
    load_release: Callable[[Path], Dict[str, Dict[str, Any]]]
    #: Write a full set of records back to the release directory.
    write_release: Callable[[Path, Iterable[Dict[str, Any]]], Any]

    #: Return every GUIDed row of this type from the database.
    query_rows: Callable[[Any], List[Any]]
    #: Build the release record for one database row.
    to_record: Callable[[Any], Dict[str, Any]]
    #: Create a row (and children) from a release record.
    import_record: Callable[[Any, Dict[str, Any]], Any]
    #: Overwrite an existing row from a release record.
    apply_record: Callable[[Any, Dict[str, Any], Any], Any]

    #: Short display columns for one release record: (label, value) pairs.
    describe: Callable[[Dict[str, Any]], List[Tuple[str, str]]]
    #: Endpoint name for viewing one row in Barsukas, or None when there is none.
    view_endpoint: Optional[str] = None
    #: Keyword name the view endpoint takes the row id under.
    view_id_arg: str = "id"


@dataclass
class RowDiff:
    """One GUID that exists on both sides with differing records."""

    guid: str
    row_id: int
    db_fields: List[Tuple[str, str]]
    release_fields: List[Tuple[str, str]]


def _db_records(spec: RecordSyncSpec) -> Dict[str, Tuple[Any, Dict[str, Any]]]:
    """Return ``{guid: (row, record)}`` for every GUIDed row in the database."""
    return {row.guid: (row, spec.to_record(row)) for row in spec.query_rows(g.db)}


def _find_additions(spec: RecordSyncSpec) -> List[Dict[str, Any]]:
    """Release records whose GUID is not in the database, sorted by GUID."""
    release_records = spec.load_release(spec.get_release_dir())
    known = set(_db_records(spec))
    return [record for guid, record in sorted(release_records.items()) if guid not in known]


def _find_removals(spec: RecordSyncSpec) -> List[Dict[str, Any]]:
    """Database rows whose GUID is not in the release file, sorted by GUID.

    The row's own id rides along under ``_row_id`` so the templates can offer a
    delete without a second lookup.
    """
    release_guids = set(spec.load_release(spec.get_release_dir()))
    removals: List[Dict[str, Any]] = []
    for guid, (row, record) in sorted(_db_records(spec).items()):
        if guid not in release_guids:
            removals.append({**record, "_row_id": row.id})
    return removals


def _find_changes(spec: RecordSyncSpec) -> List[RowDiff]:
    """GUIDs present on both sides whose records are not equal, sorted by GUID."""
    release_records = spec.load_release(spec.get_release_dir())
    changes: List[RowDiff] = []
    for guid, (row, db_record) in sorted(_db_records(spec).items()):
        release_record = release_records.get(guid)
        if release_record is None or release_record == db_record:
            continue
        changes.append(
            RowDiff(
                guid=guid,
                row_id=row.id,
                db_fields=spec.describe(db_record),
                release_fields=spec.describe(release_record),
            )
        )
    return changes


def _write_release_from_db(spec: RecordSyncSpec, records: Iterable[Dict[str, Any]]) -> None:
    """Replace the release file with ``records``."""
    spec.write_release(spec.get_release_dir(), records)


def build_blueprint(spec: RecordSyncSpec) -> Blueprint:
    """Build the four-mode sync blueprint for one whole-record element type."""
    bp = Blueprint(spec.blueprint_name, __name__, url_prefix=f"/sync/{spec.slug}")

    def endpoint(name: str) -> str:
        return f"{spec.blueprint_name}.{name}"

    def render(template: str, **context: Any) -> ResponseReturnValue:
        return render_template(
            f"sync_record/{template}",
            spec=spec,
            per_page_choices=PER_PAGE_CHOICES,
            release_dir=str(spec.get_release_dir()),
            **context,
        )

    @bp.route("/")
    def index() -> ResponseReturnValue:
        """Per-mode difference counts for this element type."""
        release_records = spec.load_release(spec.get_release_dir())
        db_by_guid = _db_records(spec)
        release_guids = set(release_records)
        db_guids = set(db_by_guid)

        changed = sum(
            1 for guid in release_guids & db_guids if release_records[guid] != db_by_guid[guid][1]
        )
        counts = {
            "release_total": len(release_guids),
            "db_total": len(db_guids),
            "additions": len(release_guids - db_guids),
            "removals": len(db_guids - release_guids),
            "changes": changed,
        }
        return render("index.html", counts=counts)

    @bp.route("/additions")
    def additions() -> ResponseReturnValue:
        """Release records the database does not have."""
        return render("additions.html", page=paginate(_find_additions(spec)))

    @bp.route("/additions/apply", methods=["POST"])
    def apply_additions() -> ResponseReturnValue:
        """Import the selected release records into the database."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return redirect(url_for(endpoint("additions")))

        release_records = spec.load_release(spec.get_release_dir())
        if request.form.get("select_scope") == "all":
            selected_guids = [str(record["guid"]) for record in _find_additions(spec)]
        else:
            selected_guids = request.form.getlist("selected_guids")

        if not selected_guids:
            flash(f"No {spec.noun}s selected for import", "warning")
            return redirect(url_for(endpoint("additions")))

        outcome = SyncOutcome(noun=spec.noun)
        for guid in selected_guids:
            record = release_records.get(guid)
            if record is None:
                outcome.record_error(f"Release record not found for GUID: {guid}")
                continue
            try:
                if spec.import_record(g.db, record) is None:
                    # Already present - the list was stale, not an error.
                    outcome.skipped += 1
                    continue
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{spec.noun}_import",
                    details={"guid": guid},
                )
                outcome.imported += 1
            except Exception as e:
                outcome.record_error(f"Error importing {spec.noun} {guid}: {e}")

        outcome.commit(g.db)
        outcome.flash_summary()
        return redirect(url_for(endpoint("additions")))

    @bp.route("/removals")
    def removals() -> ResponseReturnValue:
        """Database rows the release file does not have."""
        return render("removals.html", page=paginate(_find_removals(spec)))

    @bp.route("/removals/export", methods=["POST"])
    def export_removals() -> ResponseReturnValue:
        """Write the selected database-only rows into the release file."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return redirect(url_for(endpoint("removals")))

        if request.form.get("select_scope") == "all":
            selected_ids = {str(item["_row_id"]) for item in _find_removals(spec)}
        else:
            selected_ids = set(request.form.getlist("selected_ids"))

        if not selected_ids:
            flash(f"No {spec.noun}s selected for export", "warning")
            return redirect(url_for(endpoint("removals")))

        # The release file is rewritten whole, so start from what is already in
        # it and add the selected rows: a partial write must not drop siblings.
        merged = dict(spec.load_release(spec.get_release_dir()))
        outcome = SyncOutcome(noun=spec.noun)
        for row in spec.query_rows(g.db):
            if str(row.id) not in selected_ids:
                continue
            merged[row.guid] = spec.to_record(row)
            outcome.exported += 1

        if outcome.exported:
            try:
                _write_release_from_db(spec, merged.values())
            except Exception as e:  # noqa: BLE001 - surfaced to the user
                logger.error(f"Release file write error: {e}")
                flash(f"Error writing release file: {e}", "error")
                outcome.exported = 0
                outcome.errors += 1
            else:
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{spec.noun}_export",
                    details={"count": outcome.exported},
                )
                g.db.commit()

        outcome.flash_summary()
        return redirect(url_for(endpoint("removals")))

    @bp.route("/removals/delete", methods=["POST"])
    def delete_removals() -> ResponseReturnValue:
        """Delete the selected database-only rows.

        Deliberately offers no "select all": export is the safe bulk action on
        this page, and one-click deletion of every unreleased row is not
        something a sync page should make easy.
        """
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return redirect(url_for(endpoint("removals")))

        selected_ids = set(request.form.getlist("selected_ids"))
        if not selected_ids:
            flash(f"No {spec.noun}s selected for deletion", "warning")
            return redirect(url_for(endpoint("removals")))

        outcome = SyncOutcome(noun=spec.noun)
        for row in spec.query_rows(g.db):
            if str(row.id) not in selected_ids:
                continue
            try:
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{spec.noun}_delete",
                    details={"guid": row.guid},
                )
                g.db.delete(row)
                outcome.deleted += 1
            except Exception as e:
                outcome.record_error(f"Error deleting {spec.noun} {row.guid}: {e}")

        outcome.commit(g.db)
        outcome.flash_summary()
        return redirect(url_for(endpoint("removals")))

    @bp.route("/changes")
    def changes() -> ResponseReturnValue:
        """GUIDs present on both sides whose records differ."""
        return render("changes.html", page=paginate(_find_changes(spec)))

    @bp.route("/changes/apply", methods=["POST"])
    def apply_changes() -> ResponseReturnValue:
        """Reconcile the selected differing records, per row."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return redirect(url_for(endpoint("changes")))

        bulk = parse_bulk_request()
        if bulk is not None:
            all_changes = _find_changes(spec)
            expanded = bulk_actions_for(
                bulk, (diff.row_id for diff in all_changes), total=len(all_changes)
            )
            if expanded is None:
                return redirect(url_for(endpoint("changes")))
            actions = expanded
        else:
            actions = parse_row_actions()

        if not actions:
            flash("No changes selected", "warning")
            return redirect(url_for(endpoint("changes")))

        release_records = spec.load_release(spec.get_release_dir())
        rows_by_id = {str(row.id): row for row in spec.query_rows(g.db)}
        outcome = SyncOutcome(noun=spec.noun)
        # Release-side edits accumulate into one rewrite of the whole file.
        merged = dict(release_records)
        release_dirty = False

        for row_id, action in actions.items():
            if action == SKIP:
                outcome.skipped += 1
                continue
            if action not in (USE_RELEASE, USE_DB):
                continue

            row = rows_by_id.get(row_id)
            if row is None:
                outcome.record_error(f"{spec.noun.title()} not found: {row_id}")
                continue

            try:
                if action == USE_RELEASE:
                    record = release_records.get(row.guid)
                    if record is None:
                        outcome.record_error(f"Release record not found for GUID: {row.guid}")
                        continue
                    spec.apply_record(g.db, record, row)
                    log_operation(
                        session=g.db,
                        source="sync-release",
                        operation_type=f"{spec.noun}_record_sync",
                        details={"guid": row.guid, "direction": "release_to_db"},
                    )
                    outcome.updated_db += 1
                else:  # USE_DB
                    merged[row.guid] = spec.to_record(row)
                    release_dirty = True
                    outcome.updated_release += 1
            except Exception as e:
                outcome.record_error(f"Error syncing {spec.noun} {row.guid}: {e}")

        outcome.commit(g.db)
        if release_dirty:
            try:
                _write_release_from_db(spec, merged.values())
            except Exception as e:  # noqa: BLE001 - surfaced to the user
                logger.error(f"Release file write error: {e}")
                flash(f"Error writing release file: {e}", "error")
                outcome.updated_release = 0
                outcome.errors += 1

        outcome.flash_summary()
        return redirect(url_for(endpoint("changes")))

    @bp.route("/export", methods=["POST"])
    def export_all() -> ResponseReturnValue:
        """Rewrite the release file from every GUIDed row in the database."""
        rows = spec.query_rows(g.db)
        try:
            _write_release_from_db(spec, [spec.to_record(row) for row in rows])
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            logger.error(f"Release file write error: {e}")
            flash(f"Error writing release file: {e}", "error")
            return redirect(url_for(endpoint("index")))

        log_operation(
            session=g.db,
            source="sync-release",
            operation_type=f"{spec.noun}_export_all",
            details={"count": len(rows)},
        )
        g.db.commit()
        flash(f"Exported {len(rows)} {spec.noun}(s) to the release file", "success")
        return redirect(url_for(endpoint("index")))

    return bp
