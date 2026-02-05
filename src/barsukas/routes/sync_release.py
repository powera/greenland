#!/usr/bin/python3

"""Routes for syncing data between data/release and SQLite database."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from wordfreq.storage.crud.operation_log import log_operation, log_translation_change
from wordfreq.storage.models.schema import Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    compute_sort_key,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_release", __name__, url_prefix="/sync")

# Default path to data/release/lemmas
# __file__ is src/barsukas/routes/sync_release.py
# .parent = routes/, .parent.parent = barsukas/, .parent.parent.parent = src/
# .parent.parent.parent.parent = repo root
DEFAULT_RELEASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "release" / "lemmas"


def _get_release_dir() -> Path:
    """Get the path to the data/release/lemmas directory."""
    return DEFAULT_RELEASE_DIR


def _load_release_lemmas(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all lemmas from data/release JSONL files.

    Returns:
        Dictionary mapping GUID to lemma data from release files.
    """
    release_lemmas: Dict[str, Dict[str, Any]] = {}

    if not release_dir.exists():
        logger.warning(f"Release directory not found: {release_dir}")
        return release_lemmas

    # Load all base.jsonl files
    for base_file in release_dir.rglob("base.jsonl"):
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        guid = data.get("guid")
                        if guid:
                            release_lemmas[guid] = data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {base_file}:{line_num}: {e}")
        except Exception as e:
            logger.error(f"Error reading {base_file}: {e}")

    return release_lemmas


def _get_release_lemma_text(release_data: Dict[str, Any]) -> str:
    """Extract lemma_text from release data."""
    translations = release_data.get("translations", {})
    en_text = translations.get("en")
    if en_text:
        return str(en_text)
    concept_label = release_data.get("concept_label", "")
    return str(concept_label) if concept_label else ""


# =============================================================================
# Hub / Index
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display sync hub with links to all sync modes."""
    release_dir = _get_release_dir()

    # Check if release directory exists
    if not release_dir.exists():
        return render_template(
            "sync_release/index.html",
            release_dir=str(release_dir),
            error="Release directory not found",
            counts=None,
        )

    # Load release lemmas
    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        return render_template(
            "sync_release/index.html",
            release_dir=str(release_dir),
            release_count=0,
            counts=None,
        )

    # Get all DB GUIDs
    db_guids = set(guid for (guid,) in g.db.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    # Calculate counts for each category
    additions = release_guids - db_guids
    removals = db_guids - release_guids
    common_guids = release_guids & db_guids

    # Count difficulty differences (among common GUIDs with matching lemma_text)
    difficulty_diffs = 0
    lemma_text_changes = 0

    # Query common GUIDs in batches
    batch_size = 500
    common_list = list(common_guids)
    for i in range(0, len(common_list), batch_size):
        batch = common_list[i : i + batch_size]
        db_lemmas = g.db.query(Lemma).filter(Lemma.guid.in_(batch)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_text = _get_release_lemma_text(release_data)

            if db_lemma.lemma_text != release_text:
                lemma_text_changes += 1
            elif release_data.get("difficulty_level") != db_lemma.difficulty_level:
                difficulty_diffs += 1

    # Count translation differences (only for matching lemmas)
    translation_diffs = _count_translation_differences(release_lemmas, g.db)

    counts = {
        "release_total": len(release_lemmas),
        "db_total": len(db_guids),
        "additions": len(additions),
        "removals": len(removals),
        "difficulty": difficulty_diffs,
        "changes": lemma_text_changes,
        "translations": translation_diffs,
    }

    return render_template(
        "sync_release/index.html",
        release_dir=str(release_dir),
        counts=counts,
    )


# =============================================================================
# Difficulty Sync
# =============================================================================


def _find_difficulty_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where difficulty_level differs between release and SQLite."""
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return differences

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)

            # Skip if lemma_text differs
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_level = release_data.get("difficulty_level")
            db_level = db_lemma.difficulty_level

            if release_level == db_level:
                continue

            differences.append(
                {
                    "guid": db_lemma.guid,
                    "lemma_id": db_lemma.id,
                    "lemma_text": db_lemma.lemma_text,
                    "definition": db_lemma.definition_text[:80] if db_lemma.definition_text else "",
                    "pos_type": db_lemma.pos_type,
                    "pos_subtype": db_lemma.pos_subtype,
                    "release_level": release_level,
                    "db_level": db_level,
                }
            )

    differences.sort(key=lambda x: x["guid"])
    return differences


@bp.route("/difficulty")
def difficulty() -> ResponseReturnValue:
    """Display difficulty level differences."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    differences = _find_difficulty_differences(release_lemmas, g.db)

    return render_template(
        "sync_release/difficulty.html",
        differences=differences,
        release_dir=str(release_dir),
        release_count=len(release_lemmas),
    )


@bp.route("/difficulty/apply", methods=["POST"])
def apply_difficulty() -> ResponseReturnValue:
    """Apply selected difficulty level changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.difficulty"))

    actions = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            lemma_id = key.replace("action_", "")
            actions[lemma_id] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.difficulty"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for lemma_id_str, action in actions.items():
        if action == "skip" or action == "keep_old":
            skipped_count += 1
            continue

        if action != "use_new":
            continue

        try:
            lemma_id_int = int(lemma_id_str)
            lemma = g.db.query(Lemma).filter(Lemma.id == lemma_id_int).first()

            if not lemma:
                logger.warning(f"Lemma not found: {lemma_id_int}")
                error_count += 1
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {lemma.guid}")
                error_count += 1
                continue

            new_level = release_data.get("difficulty_level")
            old_level = lemma.difficulty_level

            lemma.difficulty_level = new_level
            updated_count += 1

            log_translation_change(
                session=g.db,
                source="sync-release",
                operation_type="difficulty_sync",
                lemma_id=lemma.id,
                field_name="difficulty_level",
                old_value=str(old_level) if old_level is not None else None,
                new_value=str(new_level) if new_level is not None else None,
            )

            logger.info(
                f"Updated difficulty for '{lemma.lemma_text}' ({lemma.guid}): "
                f"{old_level} -> {new_level}"
            )

        except Exception as e:
            logger.error(f"Error updating lemma {lemma_id_str}: {e}")
            error_count += 1

    if updated_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_release.difficulty"))


# =============================================================================
# Additions (GUIDs in release but not in SQLite)
# =============================================================================


def _find_additions(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find GUIDs in release that don't exist in SQLite."""
    additions: List[Dict[str, Any]] = []

    db_guids = set(guid for (guid,) in db_session.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    new_guids = release_guids - db_guids

    for guid in sorted(new_guids):
        release_data = release_lemmas[guid]
        lemma_text = _get_release_lemma_text(release_data)

        additions.append(
            {
                "guid": guid,
                "lemma_text": lemma_text,
                "definition": (release_data.get("concept_definition", "") or "")[:80],
                "pos_type": release_data.get("pos_type", ""),
                "pos_subtype": release_data.get("pos_subtype", ""),
                "difficulty_level": release_data.get("difficulty_level"),
                "translations": release_data.get("translations", {}),
            }
        )

    return additions


@bp.route("/additions")
def additions() -> ResponseReturnValue:
    """Display GUIDs in release that don't exist in SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    additions_list = _find_additions(release_lemmas, g.db)

    return render_template(
        "sync_release/additions.html",
        additions=additions_list,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new lemmas from release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.additions"))

    selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No lemmas selected for import", "warning")
        return redirect(url_for("sync_release.additions"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    imported_count = 0
    error_count = 0

    for guid in selected_guids:
        release_data = release_lemmas.get(guid)
        if not release_data:
            logger.warning(f"Release data not found for GUID: {guid}")
            error_count += 1
            continue

        try:
            lemma_text = _get_release_lemma_text(release_data)

            lemma = Lemma(
                guid=guid,
                lemma_text=lemma_text,
                definition_text=release_data.get("concept_definition", ""),
                pos_type=release_data.get("pos_type", ""),
                pos_subtype=release_data.get("pos_subtype"),
                difficulty_level=release_data.get("difficulty_level"),
            )
            g.db.add(lemma)
            g.db.flush()  # Get the ID

            # Add translations
            translations = release_data.get("translations", {})
            for lang_code, translation_text in translations.items():
                if lang_code == "en":  # English is stored as lemma_text
                    continue
                if not translation_text:
                    continue

                trans = LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    translation=translation_text,
                    sort_key=compute_sort_key(lang_code, translation_text),
                    verified=False,
                )
                g.db.add(trans)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="lemma_import",
                lemma_id=lemma.id,
                details={
                    "lemma_text": lemma_text,
                    "guid": guid,
                    "pos_type": release_data.get("pos_type", ""),
                    "translation_count": len(translations),
                },
            )

            imported_count += 1
            logger.info(f"Imported lemma '{lemma_text}' ({guid})")

        except Exception as e:
            logger.error(f"Error importing GUID {guid}: {e}")
            error_count += 1

    if imported_count > 0:
        try:
            g.db.commit()
            flash(f"Imported {imported_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_release.additions"))


# =============================================================================
# Removals (GUIDs in SQLite but not in release)
# =============================================================================


def _find_removals(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find GUIDs in SQLite that don't exist in release."""
    removals: List[Dict[str, Any]] = []

    db_guids = set(guid for (guid,) in db_session.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    removed_guids = db_guids - release_guids

    # Query DB for these lemmas
    if removed_guids:
        batch_size = 500
        guid_list = list(removed_guids)

        for i in range(0, len(guid_list), batch_size):
            batch = guid_list[i : i + batch_size]
            db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch)).all()

            for lemma in db_lemmas:
                removals.append(
                    {
                        "guid": lemma.guid,
                        "lemma_id": lemma.id,
                        "lemma_text": lemma.lemma_text,
                        "definition": lemma.definition_text[:80] if lemma.definition_text else "",
                        "pos_type": lemma.pos_type,
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                    }
                )

    removals.sort(key=lambda x: x["guid"])
    return removals


@bp.route("/removals")
def removals() -> ResponseReturnValue:
    """Display GUIDs in SQLite that don't exist in release."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    # Note: empty release_lemmas is valid here - we're looking for DB entries not in release

    removals_list = _find_removals(release_lemmas, g.db)

    return render_template(
        "sync_release/removals.html",
        removals=removals_list,
        release_dir=str(release_dir),
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected lemmas that are not in release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.removals"))

    selected_ids = request.form.getlist("selected_ids")

    if not selected_ids:
        flash("No lemmas selected for deletion", "warning")
        return redirect(url_for("sync_release.removals"))

    deleted_count = 0
    error_count = 0

    for lemma_id_str in selected_ids:
        try:
            lemma_id = int(lemma_id_str)
            lemma = g.db.query(Lemma).filter(Lemma.id == lemma_id).first()

            if not lemma:
                logger.warning(f"Lemma not found: {lemma_id}")
                error_count += 1
                continue

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="lemma_delete",
                lemma_id=lemma.id,
                details={
                    "lemma_text": lemma.lemma_text,
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                },
            )

            logger.info(f"Deleting lemma '{lemma.lemma_text}' ({lemma.guid})")
            g.db.delete(lemma)
            deleted_count += 1

        except Exception as e:
            logger.error(f"Error deleting lemma {lemma_id_str}: {e}")
            error_count += 1

    if deleted_count > 0:
        try:
            g.db.commit()
            flash(f"Deleted {deleted_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_release.removals"))


# =============================================================================
# Changes (lemma_text differs between release and SQLite)
# =============================================================================


def _find_lemma_text_changes(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where lemma_text differs between release and SQLite."""
    changes: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return changes

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)

            if db_lemma.lemma_text == release_lemma_text:
                continue

            changes.append(
                {
                    "guid": db_lemma.guid,
                    "lemma_id": db_lemma.id,
                    "db_lemma_text": db_lemma.lemma_text,
                    "release_lemma_text": release_lemma_text,
                    "db_definition": (
                        db_lemma.definition_text[:60] if db_lemma.definition_text else ""
                    ),
                    "release_definition": (release_data.get("concept_definition", "") or "")[:60],
                    "pos_type": db_lemma.pos_type,
                    "pos_subtype": db_lemma.pos_subtype,
                }
            )

    changes.sort(key=lambda x: x["guid"])
    return changes


@bp.route("/changes")
def changes() -> ResponseReturnValue:
    """Display lemmas where lemma_text differs between release and SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    changes_list = _find_lemma_text_changes(release_lemmas, g.db)

    return render_template(
        "sync_release/changes.html",
        changes=changes_list,
        release_dir=str(release_dir),
    )


@bp.route("/changes/apply", methods=["POST"])
def apply_changes() -> ResponseReturnValue:
    """Apply selected lemma_text changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.changes"))

    actions = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            lemma_id = key.replace("action_", "")
            actions[lemma_id] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.changes"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for lemma_id_str, action in actions.items():
        if action == "skip" or action == "keep_old":
            skipped_count += 1
            continue

        if action != "use_new":
            continue

        try:
            lemma_id_int = int(lemma_id_str)
            lemma = g.db.query(Lemma).filter(Lemma.id == lemma_id_int).first()

            if not lemma:
                logger.warning(f"Lemma not found: {lemma_id_int}")
                error_count += 1
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {lemma.guid}")
                error_count += 1
                continue

            old_text = lemma.lemma_text
            new_text = _get_release_lemma_text(release_data)
            new_definition = release_data.get("concept_definition", "")

            lemma.lemma_text = new_text
            if new_definition:
                lemma.definition_text = new_definition

            log_translation_change(
                session=g.db,
                source="sync-release",
                operation_type="lemma_text_sync",
                lemma_id=lemma.id,
                field_name="lemma_text",
                old_value=old_text,
                new_value=new_text,
            )

            updated_count += 1

            logger.info(f"Updated lemma_text for ({lemma.guid}): '{old_text}' -> '{new_text}'")

        except Exception as e:
            logger.error(f"Error updating lemma {lemma_id_str}: {e}")
            error_count += 1

    if updated_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_release.changes"))


# =============================================================================
# Translations (translation differences between release and SQLite)
# =============================================================================


def _find_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where translations differ between release and SQLite.

    Only considers lemmas where GUID exists in both and lemma_text matches.
    Returns differences where either:
    - Release has a translation that DB doesn't have (or is different)
    - DB has a translation that release doesn't have (or is different)
    """
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return differences

    # Languages to check (excluding 'en' which is stored as lemma_text)
    lang_codes_to_check = [lang for lang in LANGUAGE_HIERARCHY if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        # Build lemma_id -> lemma mapping
        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        # Batch fetch all translations for these lemmas
        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)

            # Only check translations for lemmas with matching text
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_lemma.id, {})

            # Find differences for each language
            lang_diffs: List[Dict[str, Any]] = []
            for lang_code in lang_codes_to_check:
                release_val = release_translations.get(lang_code, "")
                db_val = db_trans.get(lang_code, "")

                # Normalize empty values
                release_val = release_val.strip() if release_val else ""
                db_val = db_val.strip() if db_val else ""

                if release_val != db_val:
                    lang_diffs.append(
                        {
                            "lang_code": lang_code,
                            "lang_name": LANGUAGE_NAMES.get(lang_code, lang_code),
                            "release_val": release_val,
                            "db_val": db_val,
                        }
                    )

            if lang_diffs:
                differences.append(
                    {
                        "guid": db_lemma.guid,
                        "lemma_id": db_lemma.id,
                        "lemma_text": db_lemma.lemma_text,
                        "definition": (
                            db_lemma.definition_text[:60] if db_lemma.definition_text else ""
                        ),
                        "pos_type": db_lemma.pos_type,
                        "pos_subtype": db_lemma.pos_subtype,
                        "lang_diffs": lang_diffs,
                        "diff_count": len(lang_diffs),
                    }
                )

    differences.sort(key=lambda x: x["guid"])
    return differences


def _count_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> int:
    """Count lemmas with translation differences (faster than full diff scan)."""
    count = 0
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return count

    # Languages to check (excluding 'en')
    lang_codes_to_check = [lang for lang in LANGUAGE_HIERARCHY if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        # Batch fetch translations
        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_lemma.id, {})

            for lang_code in lang_codes_to_check:
                release_val = (release_translations.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

                if release_val != db_val:
                    count += 1
                    break  # Just need to know this lemma has differences

    return count


@bp.route("/translations")
def translations() -> ResponseReturnValue:
    """Display translation differences between release and SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    differences = _find_translation_differences(release_lemmas, g.db)

    return render_template(
        "sync_release/translations.html",
        differences=differences,
        release_dir=str(release_dir),
        language_names=LANGUAGE_NAMES,
    )


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected translation changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.translations"))

    # Parse form actions
    # Format: action_{lemma_id}_{lang_code} = skip|use_release|use_db
    actions: Dict[str, Dict[str, str]] = {}  # {lemma_id: {lang_code: action}}
    for key, value in request.form.items():
        if key.startswith("action_"):
            # key format: action_{lemma_id}_{lang_code}
            # lang_code may contain hyphens (e.g. zh-tw), so split carefully
            remainder = key[len("action_") :]
            underscore_pos = remainder.find("_")
            if underscore_pos == -1:
                continue
            lemma_id = remainder[:underscore_pos]
            lang_code = remainder[underscore_pos + 1 :]
            if lemma_id not in actions:
                actions[lemma_id] = {}
            actions[lemma_id][lang_code] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.translations"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    # Track release file updates: {filepath: {guid: {lang_code: new_translation}}}
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for lemma_id_str, lang_actions in actions.items():
        try:
            lemma_id_int = int(lemma_id_str)
            lemma = g.db.query(Lemma).filter(Lemma.id == lemma_id_int).first()

            if not lemma:
                logger.warning(f"Lemma not found: {lemma_id_int}")
                error_count += 1
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {lemma.guid}")
                error_count += 1
                continue

            release_translations = release_data.get("translations", {})

            for lang_code, action in lang_actions.items():
                if action == "skip":
                    skipped_count += 1
                    continue

                if action == "use_release":
                    # Copy from release to DB
                    release_val = release_translations.get(lang_code, "")
                    if release_val:
                        trans_obj = (
                            g.db.query(LemmaTranslation)
                            .filter(
                                LemmaTranslation.lemma_id == lemma.id,
                                LemmaTranslation.language_code == lang_code,
                            )
                            .first()
                        )

                        if trans_obj:
                            old_val = trans_obj.translation
                            trans_obj.translation = release_val
                            trans_obj.sort_key = compute_sort_key(lang_code, release_val)
                        else:
                            trans_obj = LemmaTranslation(
                                lemma_id=lemma.id,
                                language_code=lang_code,
                                translation=release_val,
                                sort_key=compute_sort_key(lang_code, release_val),
                                verified=False,
                            )
                            g.db.add(trans_obj)
                            old_val = None

                        log_translation_change(
                            session=g.db,
                            source="sync-release",
                            operation_type="translation_sync",
                            lemma_id=lemma.id,
                            language_code=lang_code,
                            old_translation=old_val,
                            new_translation=release_val,
                        )

                        updated_db_count += 1
                        logger.info(
                            f"Updated DB translation for '{lemma.lemma_text}' "
                            f"({lemma.guid}) {lang_code}: '{old_val}' -> '{release_val}'"
                        )
                    else:
                        skipped_count += 1

                elif action == "use_db":
                    # Mark for release file update (DB value -> release)
                    trans_obj = (
                        g.db.query(LemmaTranslation)
                        .filter(
                            LemmaTranslation.lemma_id == lemma.id,
                            LemmaTranslation.language_code == lang_code,
                        )
                        .first()
                    )

                    db_val = trans_obj.translation if trans_obj else ""
                    if db_val:
                        # Find the release file for this lemma
                        file_path = _find_release_file_for_lemma(release_dir, lemma.guid)
                        if file_path:
                            if file_path not in release_updates:
                                release_updates[file_path] = {}
                            if lemma.guid not in release_updates[file_path]:
                                release_updates[file_path][lemma.guid] = {}
                            release_updates[file_path][lemma.guid][lang_code] = db_val
                            updated_release_count += 1
                            logger.info(
                                f"Queued release update for '{lemma.lemma_text}' "
                                f"({lemma.guid}) {lang_code}: -> '{db_val}'"
                            )
                        else:
                            logger.warning(f"Could not find release file for GUID: {lemma.guid}")
                            error_count += 1
                    else:
                        skipped_count += 1

        except Exception as e:
            logger.error(f"Error processing lemma {lemma_id_str}: {e}")
            error_count += 1

    # Commit DB changes
    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_db_count} translation(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing DB changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    # Apply release file updates
    if release_updates:
        try:
            _apply_release_translation_updates(release_updates)
            flash(f"Updated {updated_release_count} translation(s) in release files", "success")
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
            logger.error(f"Release file update error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} item(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_release.translations"))


def _find_release_file_for_lemma(release_dir: Path, guid: str) -> Optional[Path]:
    """Find the base.jsonl file containing a specific GUID."""
    for base_file in release_dir.rglob("base.jsonl"):
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("guid") == guid:
                            return base_file
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return None


def _apply_release_translation_updates(
    updates: Dict[Path, Dict[str, Dict[str, str]]],
) -> None:
    """Apply translation updates to release JSONL files.

    Args:
        updates: {filepath: {guid: {lang_code: new_translation}}}
    """
    for file_path, guid_updates in updates.items():
        if not file_path.exists():
            logger.warning(f"Release file not found: {file_path}")
            continue

        # Read all lines, update translations, write back
        updated_lines: List[str] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        updated_lines.append(line)
                        continue

                    try:
                        data = json.loads(stripped)
                        guid = data.get("guid")

                        if guid in guid_updates:
                            # Update translations for this lemma
                            if "translations" not in data:
                                data["translations"] = {}
                            for lang_code, new_val in guid_updates[guid].items():
                                data["translations"][lang_code] = new_val
                            # Re-serialize with consistent formatting
                            updated_lines.append(json.dumps(data, ensure_ascii=False) + "\n")
                            logger.info(f"Updated translations for {guid} in {file_path}")
                        else:
                            updated_lines.append(line)
                    except json.JSONDecodeError:
                        updated_lines.append(line)

            # Write back
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)

        except Exception as e:
            logger.error(f"Error updating {file_path}: {e}")
            raise
