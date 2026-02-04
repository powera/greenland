#!/usr/bin/python3

"""Routes for syncing data between data/release and SQLite database."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from wordfreq.storage.models.schema import Lemma, LemmaTranslation

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

    counts = {
        "release_total": len(release_lemmas),
        "db_total": len(db_guids),
        "additions": len(additions),
        "removals": len(removals),
        "difficulty": difficulty_diffs,
        "changes": lemma_text_changes,
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
                    verified=False,
                )
                g.db.add(trans)

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
