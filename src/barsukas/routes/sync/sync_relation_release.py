#!/usr/bin/python3

"""Routes for syncing lemma relation group data between data/release/lemma_relations and SQLite."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import joinedload

from barsukas.routes.sync import release_io
from barsukas.routes.sync.actions import is_readonly
from storage.crud.operation_log import log_operation
from storage.models.lemma_relation import LemmaRelationGroup, LemmaRelationMember
from storage.migrate import _write_jsonl_atomic as migrate_write_jsonl_atomic
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)

bp = Blueprint("sync_relation_release", __name__, url_prefix="/sync/relations")

# Default path to data/release/lemma_relations
# __file__ is src/barsukas/routes/sync/sync_relation_release.py
# .parent = sync/, .parent.parent = routes/, .parent.parent.parent = barsukas/,
# .parent.parent.parent.parent = src/, .parent.parent.parent.parent.parent = repo root
DEFAULT_RELATION_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "lemma_relations"
)


def _get_relation_release_dir() -> Path:
    """Get the path to the data/release/lemma_relations directory."""
    return DEFAULT_RELATION_RELEASE_DIR


def _load_release_relations(
    release_dir: Path,
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Load all relation groups from data/release/lemma_relations JSONL files.

    Returns:
        Dictionary mapping (relation_type, concept_label) to release data.
        Each value has keys: concept, members, _subtype, _relation_type.
    """
    release_groups: Dict[Tuple[str, str], Dict[str, Any]] = {}

    if not release_dir.exists():
        return release_groups

    for jsonl_file in sorted(release_dir.rglob("*.jsonl")):
        # relation_type is the directory above the subtype directory
        # e.g. derivational/shape.jsonl -> relation_type="derivational"
        relation_type = jsonl_file.parent.name
        subtype = jsonl_file.stem  # e.g. "shape"

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        concept = data.get("concept", "")
                        if concept:
                            key = (relation_type, concept)
                            release_groups[key] = {
                                "concept": concept,
                                "members": data.get("members", []),
                                "_subtype": subtype,
                                "_relation_type": relation_type,
                            }
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {jsonl_file}:{line_num}: {e}")
        except Exception as e:
            logger.error(f"Error reading {jsonl_file}: {e}")

    return release_groups


def _get_db_groups(
    db_session: Any,
) -> Dict[Tuple[str, str], LemmaRelationGroup]:
    """Load all DB relation groups with their members.

    Returns:
        Dictionary mapping (relation_type, concept_label) to group ORM object.
    """
    groups = (
        db_session.query(LemmaRelationGroup)
        .options(joinedload(LemmaRelationGroup.members).joinedload(LemmaRelationMember.lemma))
        .all()
    )
    return {(g.relation_type, g.concept_label): g for g in groups}


def _get_member_guids(group: LemmaRelationGroup) -> List[str]:
    """Get sorted list of lemma GUIDs for a group's members."""
    guids: List[str] = []
    for member in group.members:
        lemma = member.lemma
        if lemma and lemma.guid:
            guids.append(lemma.guid)
    return sorted(guids)


def _resolve_subtype(lemmas: List[Lemma]) -> str:
    """Resolve the subtype for a group based on its member lemmas.

    Priority: verb's pos_subtype > noun's pos_subtype > "other".
    """
    for lemma in lemmas:
        if lemma.pos_type == "verb" and lemma.pos_subtype:
            return lemma.pos_subtype
    for lemma in lemmas:
        if lemma.pos_type == "noun" and lemma.pos_subtype:
            return lemma.pos_subtype
    return "other"


def _group_to_release_record(group: LemmaRelationGroup) -> Dict[str, Any]:
    """Convert a DB group to a release JSONL record."""
    return {
        "concept": group.concept_label,
        "members": _get_member_guids(group),
    }


def _write_jsonl_atomic(file_path: Path, records: List[Dict[str, Any]]) -> None:
    """Write JSONL file atomically, creating the parent directory."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    migrate_write_jsonl_atomic(file_path, records)


# =============================================================================
# Index (Hub)
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display relation sync hub with counts for all sync modes."""
    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)
    db_groups = _get_db_groups(g.db)

    release_keys = set(release_groups.keys())
    db_keys = set(db_groups.keys())

    additions_count = len(release_keys - db_keys)
    removals_count = len(db_keys - release_keys)

    # Count member differences in common groups
    common_keys = release_keys & db_keys
    differences_count = 0
    for key in common_keys:
        release_members = sorted(release_groups[key].get("members", []))
        db_members = _get_member_guids(db_groups[key])
        if release_members != db_members:
            differences_count += 1

    counts = {
        "release_total": len(release_groups),
        "db_total": len(db_groups),
        "additions": additions_count,
        "removals": removals_count,
        "differences": differences_count,
    }

    return render_template(
        "sync_relation_release/index.html",
        release_dir=str(release_dir),
        counts=counts,
    )


# =============================================================================
# Additions (groups in release but not in DB)
# =============================================================================


@bp.route("/additions")
def additions() -> ResponseReturnValue:
    """Display relation groups in release that don't exist in DB."""
    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)

    if not release_groups:
        flash("No relation groups found in release directory", "warning")
        return redirect(url_for("sync_relation_release.index"))

    db_groups = _get_db_groups(g.db)
    db_keys = set(db_groups.keys())

    # Pre-load all lemma GUIDs for validation
    all_lemma_guids: Set[str] = set(
        guid for (guid,) in g.db.query(Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    )

    importable: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    for key in sorted(release_groups.keys()):
        if key in db_keys:
            continue

        data = release_groups[key]
        member_guids = data.get("members", [])

        missing_guids = [guid for guid in member_guids if guid not in all_lemma_guids]

        item: Dict[str, Any] = {
            "relation_type": key[0],
            "concept": key[1],
            "members": member_guids,
            "subtype": data.get("_subtype", ""),
        }

        if missing_guids:
            item["missing_guids"] = missing_guids
            blocked.append(item)
        else:
            importable.append(item)

    return render_template(
        "sync_relation_release/additions.html",
        additions=importable,
        blocked=blocked,
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected relation groups from release into DB."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_relation_release.additions"))

    selected_keys = request.form.getlist("selected_keys")
    if not selected_keys:
        flash("No groups selected for import", "warning")
        return redirect(url_for("sync_relation_release.additions"))

    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)

    # Build lemma GUID -> ID lookup
    lemma_guid_to_id: Dict[str, int] = {}
    for lemma_id, lemma_guid in (
        g.db.query(Lemma.id, Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    ):
        lemma_guid_to_id[lemma_guid] = lemma_id

    imported_count = 0
    error_count = 0

    for key_str in selected_keys:
        # key_str is "relation_type|concept"
        parts = key_str.split("|", 1)
        if len(parts) != 2:
            error_count += 1
            continue

        relation_type, concept = parts
        release_data = release_groups.get((relation_type, concept))
        if not release_data:
            logger.warning(f"Release data not found for ({relation_type}, {concept})")
            error_count += 1
            continue

        member_guids = release_data.get("members", [])
        missing = [guid for guid in member_guids if guid not in lemma_guid_to_id]
        if missing:
            flash(f"Skipped {concept}: missing lemma GUIDs: {', '.join(missing)}", "warning")
            error_count += 1
            continue

        try:
            group = LemmaRelationGroup(
                relation_type=relation_type,
                concept_label=concept,
            )
            g.db.add(group)
            g.db.flush()

            for guid in member_guids:
                lemma_id = lemma_guid_to_id[guid]
                member = LemmaRelationMember(
                    group_id=group.id,
                    lemma_id=lemma_id,
                )
                g.db.add(member)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="relation_import",
                details={
                    "relation_type": relation_type,
                    "concept": concept,
                    "member_count": len(member_guids),
                    "member_guids": member_guids,
                },
            )

            imported_count += 1
            logger.info(f"Imported relation group ({relation_type}, {concept})")

        except Exception as e:
            logger.error(f"Error importing group ({relation_type}, {concept}): {e}")
            error_count += 1

    if imported_count > 0:
        try:
            g.db.commit()
            flash(f"Imported {imported_count} relation group(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_relation_release.additions"))


# =============================================================================
# Removals (groups in DB but not in release)
# =============================================================================


@bp.route("/removals")
def removals() -> ResponseReturnValue:
    """Display relation groups in DB that don't exist in release."""
    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)
    db_groups = _get_db_groups(g.db)

    release_keys = set(release_groups.keys())
    removals_list: List[Dict[str, Any]] = []

    for key in sorted(db_groups.keys()):
        if key in release_keys:
            continue

        group = db_groups[key]
        member_details: List[Dict[str, str]] = []
        for member in group.members:
            lemma = member.lemma
            if lemma:
                member_details.append(
                    {
                        "guid": lemma.guid or "",
                        "word": lemma.word,
                        "pos_type": lemma.pos_type,
                    }
                )

        removals_list.append(
            {
                "group_id": group.id,
                "relation_type": group.relation_type,
                "concept": group.concept_label,
                "members": member_details,
            }
        )

    return render_template(
        "sync_relation_release/removals.html",
        removals=removals_list,
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected relation groups from DB."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_relation_release.removals"))

    selected_ids = request.form.getlist("selected_ids")
    if not selected_ids:
        flash("No groups selected for deletion", "warning")
        return redirect(url_for("sync_relation_release.removals"))

    deleted_count = 0
    error_count = 0

    for group_id_str in selected_ids:
        try:
            group_id = int(group_id_str)
            group = g.db.query(LemmaRelationGroup).filter(LemmaRelationGroup.id == group_id).first()
            if not group:
                logger.warning(f"Relation group not found: {group_id}")
                error_count += 1
                continue

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="relation_delete",
                details={
                    "relation_type": group.relation_type,
                    "concept": group.concept_label,
                    "group_id": group.id,
                },
            )

            logger.info(f"Deleting relation group ({group.relation_type}, {group.concept_label})")
            g.db.delete(group)
            deleted_count += 1

        except Exception as e:
            logger.error(f"Error deleting group {group_id_str}: {e}")
            error_count += 1

    if deleted_count > 0:
        try:
            g.db.commit()
            flash(f"Deleted {deleted_count} relation group(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_relation_release.removals"))


# =============================================================================
# Differences (same concept but different members)
# =============================================================================


@bp.route("/differences")
def differences() -> ResponseReturnValue:
    """Display groups where member sets differ between release and DB."""
    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)
    db_groups = _get_db_groups(g.db)

    release_keys = set(release_groups.keys())
    db_keys = set(db_groups.keys())
    common_keys = release_keys & db_keys

    diffs: List[Dict[str, Any]] = []

    for key in sorted(common_keys):
        release_members = sorted(release_groups[key].get("members", []))
        db_group = db_groups[key]
        db_members = _get_member_guids(db_group)

        if release_members == db_members:
            continue

        # Build richer DB member info
        db_member_details: List[Dict[str, str]] = []
        for member in db_group.members:
            lemma = member.lemma
            if lemma:
                db_member_details.append(
                    {
                        "guid": lemma.guid or "",
                        "word": lemma.word,
                        "pos_type": lemma.pos_type,
                    }
                )
        db_member_details.sort(key=lambda m: m["guid"])

        diffs.append(
            {
                "group_id": db_group.id,
                "relation_type": key[0],
                "concept": key[1],
                "release_members": release_members,
                "db_members": db_member_details,
                "only_in_release": sorted(set(release_members) - set(db_members)),
                "only_in_db": sorted(set(db_members) - {m["guid"] for m in db_member_details}),
            }
        )

    return render_template(
        "sync_relation_release/differences.html",
        differences=diffs,
    )


@bp.route("/differences/apply", methods=["POST"])
def apply_differences() -> ResponseReturnValue:
    """Apply member difference resolutions (use_release or use_db per group)."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_relation_release.differences"))

    release_dir = _get_relation_release_dir()
    release_groups = _load_release_relations(release_dir)

    # Build lemma GUID -> ID lookup
    lemma_guid_to_id: Dict[str, int] = {}
    for lemma_id, lemma_guid in (
        g.db.query(Lemma.id, Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    ):
        lemma_guid_to_id[lemma_guid] = lemma_id

    actions: Dict[str, str] = {}
    for form_key, value in request.form.items():
        if form_key.startswith("action_"):
            group_id = form_key.replace("action_", "")
            actions[group_id] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_relation_release.differences"))

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    # Track release file updates for use_db actions
    # {(relation_type, subtype): {concept: [member_guids]}}
    release_updates: Dict[Tuple[str, str], Dict[str, List[str]]] = {}

    for group_id_str, action in actions.items():
        if action == "skip":
            skipped_count += 1
            continue

        if action not in ("use_release", "use_db"):
            continue

        try:
            group_id_int = int(group_id_str)
            group = (
                g.db.query(LemmaRelationGroup)
                .options(
                    joinedload(LemmaRelationGroup.members).joinedload(LemmaRelationMember.lemma)
                )
                .filter(LemmaRelationGroup.id == group_id_int)
                .first()
            )
            if not group:
                logger.warning(f"Relation group not found: {group_id_int}")
                error_count += 1
                continue

            group_key: Tuple[str, str] = (group.relation_type, group.concept_label)
            release_data = release_groups.get(group_key)

            if action == "use_release":
                if not release_data:
                    logger.warning(f"Release data not found for {group_key}")
                    error_count += 1
                    continue

                new_member_guids = release_data.get("members", [])
                missing = [guid for guid in new_member_guids if guid not in lemma_guid_to_id]
                if missing:
                    flash(
                        f"Skipped {group.concept_label}: missing lemma GUIDs: {', '.join(missing)}",
                        "warning",
                    )
                    error_count += 1
                    continue

                # Remove existing members
                for member in list(group.members):
                    g.db.delete(member)
                g.db.flush()

                # Add new members from release
                for guid in new_member_guids:
                    lemma_id = lemma_guid_to_id[guid]
                    member = LemmaRelationMember(
                        group_id=group.id,
                        lemma_id=lemma_id,
                    )
                    g.db.add(member)

                updated_db_count += 1
                logger.info(f"Updated DB members for group {group_key}")

            elif action == "use_db":
                # Update release file with DB members
                db_member_guids = _get_member_guids(group)
                if release_data:
                    subtype = release_data.get("_subtype", "other")
                    relation_type = release_data.get("_relation_type", group.relation_type)
                else:
                    # Resolve subtype from DB members
                    member_lemmas = [m.lemma for m in group.members if m.lemma]
                    subtype = _resolve_subtype(member_lemmas)
                    relation_type = group.relation_type

                file_key = (relation_type, subtype)
                if file_key not in release_updates:
                    release_updates[file_key] = {}
                release_updates[file_key][group.concept_label] = db_member_guids
                updated_release_count += 1
                logger.info(f"Queued release update for group {group_key}")

        except Exception as e:
            logger.error(f"Error processing group {group_id_str}: {e}")
            error_count += 1

    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_db_count} group(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if release_updates:
        try:
            _apply_release_member_updates(release_dir, release_updates)
            flash(
                f"Updated {updated_release_count} group(s) in release files",
                "success",
            )
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
            logger.error(f"Release file update error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} group(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_relation_release.differences"))


def _apply_release_member_updates(
    release_dir: Path,
    updates: Dict[Tuple[str, str], Dict[str, List[str]]],
) -> None:
    """Apply member updates to relation release JSONL files.

    Relation groups are identified by ``concept`` rather than by a GUID, which
    is what ``key_field`` selects.

    Args:
        release_dir: Path to data/release/lemma_relations
        updates: {(relation_type, subtype): {concept: [member_guids]}}
    """
    release_io.apply_field_updates(
        {
            release_dir
            / relation_type
            / f"{subtype}.jsonl": {
                concept: {"members": members} for concept, members in concept_updates.items()
            }
            for (relation_type, subtype), concept_updates in updates.items()
        },
        key_field="concept",
    )


# =============================================================================
# Export to JSONL
# =============================================================================


@bp.route("/export", methods=["POST"])
def export_to_jsonl() -> ResponseReturnValue:
    """Export all DB relation groups to JSONL release files."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_relation_release.index"))

    release_dir = _get_relation_release_dir()
    db_groups = _get_db_groups(g.db)

    if not db_groups:
        flash("No relation groups found in database", "warning")
        return redirect(url_for("sync_relation_release.index"))

    # Group records by (relation_type, subtype) for file output
    records_by_file: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for key, group in db_groups.items():
        record = _group_to_release_record(group)
        member_lemmas = [m.lemma for m in group.members if m.lemma]
        subtype = _resolve_subtype(member_lemmas)
        file_key = (group.relation_type, subtype)
        records_by_file[file_key].append(record)

    total_exported = 0
    for (relation_type, subtype), records in records_by_file.items():
        records.sort(key=lambda r: r["concept"])
        file_path = release_dir / relation_type / f"{subtype}.jsonl"
        _write_jsonl_atomic(file_path, records)
        total_exported += len(records)

    log_operation(
        session=g.db,
        source="sync-release",
        operation_type="relation_export",
        details={
            "total_groups": total_exported,
            "files": len(records_by_file),
        },
    )
    g.db.commit()

    flash(
        f"Exported {total_exported} relation groups across {len(records_by_file)} file(s)",
        "success",
    )
    return redirect(url_for("sync_relation_release.index"))
