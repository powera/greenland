#!/usr/bin/python3

"""Routes for syncing sentence data between data/release/sentences and SQLite database."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import selectinload

from storage.crud.operation_log import log_operation, log_translation_change
from storage.migrate import (
    _resolve_primary_lemma_category,
    _sentence_to_release_record,
    _write_jsonl_atomic,
)
from storage.models.schema import (
    ConversationSentence,
    Lemma,
    Sentence,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    RELEASE_LANGUAGES,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_sentence_release", __name__, url_prefix="/sync/sentences")

# Default path to data/release/sentences
# __file__ is src/barsukas/routes/sync/sync_sentence_release.py
# .parent = sync/, .parent.parent = routes/, .parent.parent.parent = barsukas/,
# .parent.parent.parent.parent = src/, .parent.parent.parent.parent.parent = repo root
DEFAULT_SENTENCE_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "sentences"
)


def _get_sentence_release_dir() -> Path:
    """Get the path to the data/release/sentences directory."""
    return DEFAULT_SENTENCE_RELEASE_DIR


def _load_release_sentences(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all sentences from data/release/sentences JSONL files.

    Returns:
        Dictionary mapping GUID to sentence data from release files.
    """
    release_sentences: Dict[str, Dict[str, Any]] = {}

    if not release_dir.exists():
        logger.warning(f"Sentence release directory not found: {release_dir}")
        return release_sentences

    # Load all base.jsonl files under the sentences directory
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
                            release_sentences[guid] = data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {base_file}:{line_num}: {e}")
        except Exception as e:
            logger.error(f"Error reading {base_file}: {e}")

    return release_sentences


def _get_release_sentence_english(release_data: Dict[str, Any]) -> str:
    """Extract English text from release sentence data."""
    translations = release_data.get("translations", {})
    en_text = translations.get("en", "")
    return str(en_text) if en_text else ""


def _get_conversation_sentence_ids(db_session: Any) -> Set[int]:
    """Get all sentence IDs that belong to conversations."""
    return set(
        row[0] for row in db_session.query(ConversationSentence.sentence_id).distinct().all()
    )


def _find_release_file_for_sentence(release_dir: Path, guid: str) -> Optional[Path]:
    """Find the base.jsonl file containing a specific sentence GUID."""
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


def _get_db_sentence_english(db_session: Any, sentence: Any) -> str:
    """Get the English translation text for a sentence from the database."""
    trans = (
        db_session.query(SentenceTranslation)
        .filter(
            SentenceTranslation.sentence_id == sentence.id,
            SentenceTranslation.language_code == "en",
        )
        .first()
    )
    return cast(str, trans.translation_text) if trans else ""


# =============================================================================
# Index (Hub)
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display sentence sync hub with links to all sync modes."""
    release_dir = _get_sentence_release_dir()

    release_sentences = _load_release_sentences(release_dir)

    # Get all DB sentence GUIDs (excluding conversations)
    conversation_ids = _get_conversation_sentence_ids(g.db)
    all_db_rows = g.db.query(Sentence.id, Sentence.guid).filter(Sentence.guid.isnot(None)).all()
    db_guids = set(guid for sid, guid in all_db_rows if guid and sid not in conversation_ids)

    release_guids = set(release_sentences.keys())

    additions = release_guids - db_guids
    removals = db_guids - release_guids
    common_guids = release_guids & db_guids

    # Count level and text differences among common GUIDs
    level_diffs = 0
    text_changes = 0

    batch_size = 500
    common_list = list(common_guids)
    for i in range(0, len(common_list), batch_size):
        batch = common_list[i : i + batch_size]
        db_sentences = g.db.query(Sentence).filter(Sentence.guid.in_(batch)).all()

        for db_sentence in db_sentences:
            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            db_english = _get_db_sentence_english(g.db, db_sentence)
            release_english = _get_release_sentence_english(release_data)

            if db_english != release_english:
                text_changes += 1
            elif release_data.get("minimum_level") != db_sentence.minimum_level:
                level_diffs += 1

    # Count translation differences
    translation_diffs = _count_sentence_translation_differences(release_sentences, g.db)

    counts = {
        "release_total": len(release_sentences),
        "db_total": len(db_guids),
        "additions": len(additions),
        "removals": len(removals),
        "export": len(removals),
        "level": level_diffs,
        "changes": text_changes,
        "translations": translation_diffs,
    }

    return render_template(
        "sync_sentence_release/index.html",
        release_dir=str(release_dir),
        counts=counts,
    )


# =============================================================================
# Additions (GUIDs in release but not in SQLite)
# =============================================================================


def _find_sentence_additions(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Find sentence GUIDs in release that don't exist in SQLite.

    Returns:
        Tuple of (importable additions, blocked additions with missing lemmas)
    """
    conversation_ids = _get_conversation_sentence_ids(db_session)
    all_db_rows = (
        db_session.query(Sentence.id, Sentence.guid).filter(Sentence.guid.isnot(None)).all()
    )
    db_guids = set(guid for sid, guid in all_db_rows if guid and sid not in conversation_ids)

    release_guids = set(release_sentences.keys())
    new_guids = release_guids - db_guids

    # Pre-load all lemma GUIDs for validation
    all_lemma_guids = set(
        guid for (guid,) in db_session.query(Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    )

    importable: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    for guid in sorted(new_guids):
        release_data = release_sentences[guid]
        english_text = _get_release_sentence_english(release_data)
        pattern_words = release_data.get("pattern_words", [])

        # Check for missing lemma GUIDs
        missing_lemma_guids = []
        for pw in pattern_words:
            lemma_guid = pw.get("lemma_guid")
            if lemma_guid and lemma_guid not in all_lemma_guids:
                missing_lemma_guids.append(lemma_guid)

        item: Dict[str, Any] = {
            "guid": guid,
            "english_text": english_text[:120] if english_text else "",
            "full_english_text": english_text,
            "pattern_type": release_data.get("pattern_type", ""),
            "tense": release_data.get("tense", ""),
            "minimum_level": release_data.get("minimum_level"),
            "translations": release_data.get("translations", {}),
            "pattern_words": pattern_words,
        }

        if missing_lemma_guids:
            item["missing_lemma_guids"] = missing_lemma_guids
            blocked.append(item)
        else:
            importable.append(item)

    return importable, blocked


@bp.route("/additions")
def additions() -> ResponseReturnValue:
    """Display sentence GUIDs in release that don't exist in SQLite."""
    release_dir = _get_sentence_release_dir()

    if not release_dir.exists():
        flash(f"Sentence release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_sentence_release.index"))

    release_sentences = _load_release_sentences(release_dir)
    if not release_sentences:
        flash("No sentences found in release directory", "warning")
        return redirect(url_for("sync_sentence_release.index"))

    importable, blocked = _find_sentence_additions(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/additions.html",
        additions=importable,
        blocked=blocked,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new sentences from release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.additions"))

    selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No sentences selected for import", "warning")
        return redirect(url_for("sync_sentence_release.additions"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    # Build lemma GUID -> ID lookup
    lemma_guid_to_id: Dict[str, int] = {}
    for lemma_id, lemma_guid in (
        g.db.query(Lemma.id, Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    ):
        lemma_guid_to_id[lemma_guid] = lemma_id

    imported_count = 0
    error_count = 0

    for guid in selected_guids:
        release_data = release_sentences.get(guid)
        if not release_data:
            logger.warning(f"Release data not found for sentence GUID: {guid}")
            error_count += 1
            continue

        try:
            # Validate all pattern word lemma GUIDs exist
            pattern_words = release_data.get("pattern_words", [])
            missing_guids = [
                pw.get("lemma_guid")
                for pw in pattern_words
                if pw.get("lemma_guid") and pw["lemma_guid"] not in lemma_guid_to_id
            ]
            if missing_guids:
                flash(
                    f"Skipped {guid}: missing lemma GUIDs: {', '.join(missing_guids)}",
                    "warning",
                )
                error_count += 1
                continue

            sentence = Sentence(
                guid=guid,
                pattern_type=release_data.get("pattern_type"),
                tense=release_data.get("tense"),
                minimum_level=release_data.get("minimum_level"),
                notes=release_data.get("notes"),
            )
            g.db.add(sentence)
            g.db.flush()  # Get the ID

            # Add translations
            translations = release_data.get("translations", {})
            for lang_code, translation_text in translations.items():
                if not translation_text:
                    continue
                trans = SentenceTranslation(
                    sentence_id=sentence.id,
                    language_code=lang_code,
                    translation_text=translation_text,
                    verified=False,
                )
                g.db.add(trans)

            # Add pattern words
            for pw in pattern_words:
                lemma_guid = pw.get("lemma_guid")
                lemma_id = lemma_guid_to_id.get(lemma_guid) if lemma_guid else None
                if lemma_id is None:
                    continue

                pattern_word = SentencePatternWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma_id,
                    position=pw.get("position", 0),
                    slot_name=pw.get("slot_name", "unknown"),
                    english_text=pw.get("english_text", ""),
                )
                g.db.add(pattern_word)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="sentence_import",
                details={
                    "guid": guid,
                    "english_text": _get_release_sentence_english(release_data)[:80],
                    "translation_count": len(translations),
                    "pattern_word_count": len(pattern_words),
                },
            )

            imported_count += 1
            logger.info(f"Imported sentence {guid}")

        except Exception as e:
            logger.error(f"Error importing sentence {guid}: {e}")
            error_count += 1

    if imported_count > 0:
        try:
            g.db.commit()
            flash(f"Imported {imported_count} sentence(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_sentence_release.additions"))


# =============================================================================
# Removals (GUIDs in SQLite but not in release)
# =============================================================================


def _find_sentence_removals(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find sentence GUIDs in SQLite that don't exist in release."""
    removals: List[Dict[str, Any]] = []

    conversation_ids = _get_conversation_sentence_ids(db_session)
    all_db_rows = (
        db_session.query(Sentence.id, Sentence.guid).filter(Sentence.guid.isnot(None)).all()
    )
    db_guids_with_ids = {
        guid: sid for sid, guid in all_db_rows if guid and sid not in conversation_ids
    }

    release_guids = set(release_sentences.keys())
    removed_guids = set(db_guids_with_ids.keys()) - release_guids

    if removed_guids:
        batch_size = 500
        guid_list = list(removed_guids)

        for i in range(0, len(guid_list), batch_size):
            batch = guid_list[i : i + batch_size]
            db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch)).all()

            for sentence in db_sentences:
                english_text = _get_db_sentence_english(db_session, sentence)
                removals.append(
                    {
                        "guid": sentence.guid,
                        "sentence_id": sentence.id,
                        "english_text": english_text[:120] if english_text else "",
                        "pattern_type": sentence.pattern_type or "",
                        "minimum_level": sentence.minimum_level,
                    }
                )

    removals.sort(key=lambda x: x["guid"])
    return removals


@bp.route("/removals")
def removals() -> ResponseReturnValue:
    """Display sentence GUIDs in SQLite that don't exist in release."""
    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    removals_list = _find_sentence_removals(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/removals.html",
        removals=removals_list,
        release_dir=str(release_dir),
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected sentences that are not in release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.removals"))

    selected_ids = request.form.getlist("selected_ids")

    if not selected_ids:
        flash("No sentences selected for deletion", "warning")
        return redirect(url_for("sync_sentence_release.removals"))

    deleted_count = 0
    error_count = 0

    for sentence_id_str in selected_ids:
        try:
            sentence_id = int(sentence_id_str)
            sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id).first()

            if not sentence:
                logger.warning(f"Sentence not found: {sentence_id}")
                error_count += 1
                continue

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="sentence_delete",
                details={
                    "guid": sentence.guid,
                    "sentence_id": sentence.id,
                },
            )

            logger.info(f"Deleting sentence {sentence.guid}")
            g.db.delete(sentence)
            deleted_count += 1

        except Exception as e:
            logger.error(f"Error deleting sentence {sentence_id_str}: {e}")
            error_count += 1

    if deleted_count > 0:
        try:
            g.db.commit()
            flash(f"Deleted {deleted_count} sentence(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_sentence_release.removals"))


# =============================================================================
# Level Changes (minimum_level differs)
# =============================================================================


def _find_level_differences(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find sentences where minimum_level differs between release and SQLite."""
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_sentences.keys())

    if not release_guids:
        return differences

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch_guids)).all()

        for db_sentence in db_sentences:
            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            db_english = _get_db_sentence_english(db_session, db_sentence)
            release_english = _get_release_sentence_english(release_data)

            # Skip if English text differs (handled by changes sync)
            if db_english != release_english:
                continue

            release_level = release_data.get("minimum_level")
            db_level = db_sentence.minimum_level

            if release_level == db_level:
                continue

            differences.append(
                {
                    "guid": db_sentence.guid,
                    "sentence_id": db_sentence.id,
                    "english_text": db_english[:120] if db_english else "",
                    "pattern_type": db_sentence.pattern_type or "",
                    "release_level": release_level,
                    "db_level": db_level,
                }
            )

    differences.sort(key=lambda x: x["guid"])
    return differences


@bp.route("/level")
def level() -> ResponseReturnValue:
    """Display minimum_level differences."""
    release_dir = _get_sentence_release_dir()

    if not release_dir.exists():
        flash(f"Sentence release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_sentence_release.index"))

    release_sentences = _load_release_sentences(release_dir)
    if not release_sentences:
        flash("No sentences found in release directory", "warning")
        return redirect(url_for("sync_sentence_release.index"))

    differences = _find_level_differences(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/level.html",
        differences=differences,
        release_dir=str(release_dir),
    )


@bp.route("/level/apply", methods=["POST"])
def apply_level() -> ResponseReturnValue:
    """Apply selected minimum_level changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.level"))

    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            sentence_id = key.replace("action_", "")
            actions[sentence_id] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.level"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    # Track release file updates: {filepath: {guid: {field: value}}}
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for sentence_id_str, action in actions.items():
        if action == "skip":
            skipped_count += 1
            continue

        if action not in ("use_release", "use_db"):
            continue

        try:
            sentence_id_int = int(sentence_id_str)
            sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id_int).first()

            if not sentence:
                logger.warning(f"Sentence not found: {sentence_id_int}")
                error_count += 1
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {sentence.guid}")
                error_count += 1
                continue

            if action == "use_release":
                new_level = release_data.get("minimum_level")
                old_level = sentence.minimum_level

                sentence.minimum_level = new_level
                updated_db_count += 1

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="sentence_level_sync",
                    field_name="minimum_level",
                    old_value=str(old_level) if old_level is not None else None,
                    new_value=str(new_level) if new_level is not None else None,
                )

                logger.info(
                    f"Updated minimum_level for sentence {sentence.guid}: "
                    f"{old_level} -> {new_level}"
                )

            elif action == "use_db":
                db_level = sentence.minimum_level
                file_path = _find_release_file_for_sentence(release_dir, sentence.guid)
                if file_path:
                    if file_path not in release_updates:
                        release_updates[file_path] = {}
                    release_updates[file_path][sentence.guid] = {
                        "minimum_level": db_level,
                    }
                    updated_release_count += 1
                    logger.info(
                        f"Queued release update for sentence {sentence.guid} "
                        f"minimum_level: -> {db_level}"
                    )
                else:
                    logger.warning(
                        f"Could not find release file for sentence GUID: {sentence.guid}"
                    )
                    error_count += 1

        except Exception as e:
            logger.error(f"Error updating sentence {sentence_id_str}: {e}")
            error_count += 1

    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_db_count} sentence(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if release_updates:
        try:
            _apply_release_sentence_field_updates(release_updates)
            flash(
                f"Updated {updated_release_count} sentence(s) in release files",
                "success",
            )
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
            logger.error(f"Release file update error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} sentence(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_sentence_release.level"))


# =============================================================================
# Changes (English text differs between release and SQLite)
# =============================================================================


def _find_english_text_changes(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find sentences where English text differs between release and SQLite."""
    changes: List[Dict[str, Any]] = []
    release_guids = set(release_sentences.keys())

    if not release_guids:
        return changes

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch_guids)).all()

        for db_sentence in db_sentences:
            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            db_english = _get_db_sentence_english(db_session, db_sentence)
            release_english = _get_release_sentence_english(release_data)

            if db_english == release_english:
                continue

            changes.append(
                {
                    "guid": db_sentence.guid,
                    "sentence_id": db_sentence.id,
                    "db_english": db_english,
                    "release_english": release_english,
                    "pattern_type": db_sentence.pattern_type or "",
                }
            )

    changes.sort(key=lambda x: x["guid"])
    return changes


@bp.route("/changes")
def changes() -> ResponseReturnValue:
    """Display sentences where English text differs between release and SQLite."""
    release_dir = _get_sentence_release_dir()

    if not release_dir.exists():
        flash(f"Sentence release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_sentence_release.index"))

    release_sentences = _load_release_sentences(release_dir)
    if not release_sentences:
        flash("No sentences found in release directory", "warning")
        return redirect(url_for("sync_sentence_release.index"))

    changes_list = _find_english_text_changes(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/changes.html",
        changes=changes_list,
        release_dir=str(release_dir),
    )


@bp.route("/changes/apply", methods=["POST"])
def apply_changes() -> ResponseReturnValue:
    """Apply selected English text changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.changes"))

    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            sentence_id = key.replace("action_", "")
            actions[sentence_id] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.changes"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    # Track release file updates: {filepath: {guid: {field: value}}}
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for sentence_id_str, action in actions.items():
        if action == "skip":
            skipped_count += 1
            continue

        if action not in ("use_release", "use_db"):
            continue

        try:
            sentence_id_int = int(sentence_id_str)
            sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id_int).first()

            if not sentence:
                logger.warning(f"Sentence not found: {sentence_id_int}")
                error_count += 1
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {sentence.guid}")
                error_count += 1
                continue

            if action == "use_release":
                new_english = _get_release_sentence_english(release_data)
                old_english = _get_db_sentence_english(g.db, sentence)

                # Update or create the English translation
                trans_obj = (
                    g.db.query(SentenceTranslation)
                    .filter(
                        SentenceTranslation.sentence_id == sentence.id,
                        SentenceTranslation.language_code == "en",
                    )
                    .first()
                )

                if trans_obj:
                    trans_obj.translation_text = new_english
                else:
                    trans_obj = SentenceTranslation(
                        sentence_id=sentence.id,
                        language_code="en",
                        translation_text=new_english,
                        verified=False,
                    )
                    g.db.add(trans_obj)

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="sentence_text_sync",
                    language_code="en",
                    old_translation=old_english,
                    new_translation=new_english,
                )

                updated_db_count += 1
                logger.info(
                    f"Updated English text for sentence {sentence.guid}: "
                    f"'{old_english[:40]}' -> '{new_english[:40]}'"
                )

            elif action == "use_db":
                db_english = _get_db_sentence_english(g.db, sentence)
                if db_english:
                    file_path = _find_release_file_for_sentence(release_dir, sentence.guid)
                    if file_path:
                        if file_path not in release_updates:
                            release_updates[file_path] = {}
                        release_updates[file_path][sentence.guid] = {
                            "translations.en": db_english,
                        }
                        updated_release_count += 1
                        logger.info(
                            f"Queued release update for sentence {sentence.guid} "
                            f"English text: -> '{db_english[:40]}'"
                        )
                    else:
                        logger.warning(
                            f"Could not find release file for sentence GUID: " f"{sentence.guid}"
                        )
                        error_count += 1
                else:
                    skipped_count += 1

        except Exception as e:
            logger.error(f"Error updating sentence {sentence_id_str}: {e}")
            error_count += 1

    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(f"Updated {updated_db_count} sentence(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if release_updates:
        try:
            _apply_release_sentence_field_updates(release_updates)
            flash(
                f"Updated {updated_release_count} sentence(s) in release files",
                "success",
            )
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
            logger.error(f"Release file update error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} sentence(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_sentence_release.changes"))


# =============================================================================
# Translations (translation differences between release and SQLite)
# =============================================================================


def _find_sentence_translation_differences(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find sentences where translations differ between release and SQLite.

    Only considers sentences where GUID exists in both and English text matches.
    """
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_sentences.keys())

    if not release_guids:
        return differences

    # All languages except English (which is handled by changes sync)
    lang_codes_to_check = [lang for lang in LANGUAGE_HIERARCHY if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch_guids)).all()

        # Build sentence_id -> sentence mapping
        sentence_by_id = {s.id: s for s in db_sentences}
        sentence_ids = list(sentence_by_id.keys())

        # Batch fetch all translations
        db_translations: Dict[int, Dict[str, str]] = {sid: {} for sid in sentence_ids}
        if sentence_ids:
            trans_rows = (
                db_session.query(SentenceTranslation)
                .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation_text:
                    db_translations[tr.sentence_id][tr.language_code] = tr.translation_text

        for db_sentence in db_sentences:
            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            # Only check translations where English text matches
            db_english = db_translations.get(db_sentence.id, {}).get("en", "")
            release_english = _get_release_sentence_english(release_data)
            if db_english != release_english:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_sentence.id, {})

            lang_diffs: List[Dict[str, Any]] = []
            for lang_code in lang_codes_to_check:
                release_val = (release_translations.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

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
                        "guid": db_sentence.guid,
                        "sentence_id": db_sentence.id,
                        "english_text": db_english[:120] if db_english else "",
                        "pattern_type": db_sentence.pattern_type or "",
                        "lang_diffs": lang_diffs,
                        "diff_count": len(lang_diffs),
                    }
                )

    differences.sort(key=lambda x: x["guid"])
    return differences


def _count_sentence_translation_differences(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> int:
    """Count sentences with translation differences (faster than full diff scan)."""
    count = 0
    release_guids = set(release_sentences.keys())

    if not release_guids:
        return count

    lang_codes_to_check = [lang for lang in LANGUAGE_HIERARCHY if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch_guids)).all()

        sentence_ids = [s.id for s in db_sentences]

        db_translations: Dict[int, Dict[str, str]] = {sid: {} for sid in sentence_ids}
        if sentence_ids:
            trans_rows = (
                db_session.query(SentenceTranslation)
                .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation_text:
                    db_translations[tr.sentence_id][tr.language_code] = tr.translation_text

        for db_sentence in db_sentences:
            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            db_english = db_translations.get(db_sentence.id, {}).get("en", "")
            release_english = _get_release_sentence_english(release_data)
            if db_english != release_english:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_sentence.id, {})

            for lang_code in lang_codes_to_check:
                release_val = (release_translations.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

                if release_val != db_val:
                    count += 1
                    break

    return count


@bp.route("/translations")
def translations() -> ResponseReturnValue:
    """Display sentence translation differences between release and SQLite."""
    release_dir = _get_sentence_release_dir()

    if not release_dir.exists():
        flash(f"Sentence release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_sentence_release.index"))

    release_sentences = _load_release_sentences(release_dir)
    if not release_sentences:
        flash("No sentences found in release directory", "warning")
        return redirect(url_for("sync_sentence_release.index"))

    differences = _find_sentence_translation_differences(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/translations.html",
        differences=differences,
        release_dir=str(release_dir),
        language_names=LANGUAGE_NAMES,
    )


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected sentence translation changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.translations"))

    # Parse form actions: action_{sentence_id}_{lang_code} = skip|use_release|use_db
    actions: Dict[str, Dict[str, str]] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            remainder = key[len("action_") :]
            underscore_pos = remainder.find("_")
            if underscore_pos == -1:
                continue
            sentence_id = remainder[:underscore_pos]
            lang_code = remainder[underscore_pos + 1 :]
            if sentence_id not in actions:
                actions[sentence_id] = {}
            actions[sentence_id][lang_code] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.translations"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    # Track release file updates: {filepath: {guid: {lang_code: new_translation}}}
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for sentence_id_str, lang_actions in actions.items():
        try:
            sentence_id_int = int(sentence_id_str)
            sentence = g.db.query(Sentence).filter(Sentence.id == sentence_id_int).first()

            if not sentence:
                logger.warning(f"Sentence not found: {sentence_id_int}")
                error_count += 1
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                logger.warning(f"Release data not found for GUID: {sentence.guid}")
                error_count += 1
                continue

            release_translations = release_data.get("translations", {})

            for lang_code, action in lang_actions.items():
                if action == "skip":
                    skipped_count += 1
                    continue

                if action == "use_release":
                    release_val = release_translations.get(lang_code, "")
                    if release_val:
                        trans_obj = (
                            g.db.query(SentenceTranslation)
                            .filter(
                                SentenceTranslation.sentence_id == sentence.id,
                                SentenceTranslation.language_code == lang_code,
                            )
                            .first()
                        )

                        if trans_obj:
                            old_val = trans_obj.translation_text
                            trans_obj.translation_text = release_val
                        else:
                            trans_obj = SentenceTranslation(
                                sentence_id=sentence.id,
                                language_code=lang_code,
                                translation_text=release_val,
                                verified=False,
                            )
                            g.db.add(trans_obj)
                            old_val = None

                        log_translation_change(
                            session=g.db,
                            source="sync-release",
                            operation_type="sentence_translation_sync",
                            language_code=lang_code,
                            old_translation=old_val,
                            new_translation=release_val,
                        )

                        updated_db_count += 1
                        logger.info(
                            f"Updated DB translation for sentence {sentence.guid} "
                            f"{lang_code}: '{old_val}' -> '{release_val}'"
                        )
                    else:
                        skipped_count += 1

                elif action == "use_db":
                    trans_obj = (
                        g.db.query(SentenceTranslation)
                        .filter(
                            SentenceTranslation.sentence_id == sentence.id,
                            SentenceTranslation.language_code == lang_code,
                        )
                        .first()
                    )

                    db_val = trans_obj.translation_text if trans_obj else ""
                    if db_val:
                        file_path = _find_release_file_for_sentence(release_dir, sentence.guid)
                        if file_path:
                            if file_path not in release_updates:
                                release_updates[file_path] = {}
                            if sentence.guid not in release_updates[file_path]:
                                release_updates[file_path][sentence.guid] = {}
                            release_updates[file_path][sentence.guid][lang_code] = db_val
                            updated_release_count += 1
                            logger.info(
                                f"Queued release update for sentence {sentence.guid} "
                                f"{lang_code}: -> '{db_val}'"
                            )
                        else:
                            logger.warning(
                                f"Could not find release file for sentence GUID: "
                                f"{sentence.guid}"
                            )
                            error_count += 1
                    else:
                        skipped_count += 1

        except Exception as e:
            logger.error(f"Error processing sentence {sentence_id_str}: {e}")
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
            _apply_release_sentence_translation_updates(release_updates)
            flash(
                f"Updated {updated_release_count} translation(s) in release files",
                "success",
            )
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
            logger.error(f"Release file update error: {e}")

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} item(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_sentence_release.translations"))


def _apply_release_sentence_translation_updates(
    updates: Dict[Path, Dict[str, Dict[str, str]]],
) -> None:
    """Apply translation updates to sentence release JSONL files.

    Args:
        updates: {filepath: {guid: {lang_code: new_translation}}}
    """
    for file_path, guid_updates in updates.items():
        if not file_path.exists():
            logger.warning(f"Release file not found: {file_path}")
            continue

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
                            if "translations" not in data:
                                data["translations"] = {}
                            for lang_code, new_val in guid_updates[guid].items():
                                data["translations"][lang_code] = new_val
                            updated_lines.append(json.dumps(data, ensure_ascii=False) + "\n")
                            logger.info(f"Updated translations for {guid} in {file_path}")
                        else:
                            updated_lines.append(line)
                    except json.JSONDecodeError:
                        updated_lines.append(line)

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)

        except Exception as e:
            logger.error(f"Error updating {file_path}: {e}")
            raise


def _apply_release_sentence_field_updates(
    updates: Dict[Path, Dict[str, Dict[str, Any]]],
) -> None:
    """Apply field updates to sentence release JSONL files.

    Supports top-level fields (e.g. minimum_level) and dotted paths
    for nested fields (e.g. translations.en).

    Args:
        updates: {filepath: {guid: {field_or_dotted_path: new_value}}}
    """
    for file_path, guid_updates in updates.items():
        if not file_path.exists():
            logger.warning(f"Release file not found: {file_path}")
            continue

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
                            for field_path, new_val in guid_updates[guid].items():
                                if "." in field_path:
                                    parts = field_path.split(".", 1)
                                    parent_key, child_key = parts[0], parts[1]
                                    if parent_key not in data:
                                        data[parent_key] = {}
                                    data[parent_key][child_key] = new_val
                                else:
                                    data[field_path] = new_val
                            updated_lines.append(json.dumps(data, ensure_ascii=False) + "\n")
                            logger.info(f"Updated fields for {guid} in {file_path}")
                        else:
                            updated_lines.append(line)
                    except json.JSONDecodeError:
                        updated_lines.append(line)

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)

        except Exception as e:
            logger.error(f"Error updating {file_path}: {e}")
            raise


# =============================================================================
# Export (DB sentences not yet in release JSONL)
# =============================================================================

# Map POS types to directory names (pluralized)
_TYPE_TO_DIR: Dict[str, str] = {
    "noun": "nouns",
    "verb": "verbs",
    "adjective": "adjectives",
    "adverb": "adverbs",
    "pronoun": "pronouns",
    "preposition": "prepositions",
    "conjunction": "conjunctions",
    "interjection": "interjections",
    "numeral": "numerals",
    "particle": "particles",
}


def _find_exportable_sentences(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find DB sentences with GUIDs not present in release files.

    Returns:
        List of dicts with sentence info for display/export.
    """
    conversation_ids = _get_conversation_sentence_ids(db_session)
    all_db_rows = (
        db_session.query(Sentence.id, Sentence.guid).filter(Sentence.guid.isnot(None)).all()
    )
    db_guids = set(guid for sid, guid in all_db_rows if guid and sid not in conversation_ids)

    release_guids = set(release_sentences.keys())
    export_guids = db_guids - release_guids

    if not export_guids:
        return []

    exportable: List[Dict[str, Any]] = []
    batch_size = 500
    guid_list = list(export_guids)

    for i in range(0, len(guid_list), batch_size):
        batch = guid_list[i : i + batch_size]
        db_sentences = db_session.query(Sentence).filter(Sentence.guid.in_(batch)).all()

        for db_sentence in db_sentences:
            english_text = _get_db_sentence_english(db_session, db_sentence)
            exportable.append(
                {
                    "guid": db_sentence.guid,
                    "sentence_id": db_sentence.id,
                    "english_text": english_text[:120] if english_text else "",
                    "pattern_type": db_sentence.pattern_type or "",
                    "minimum_level": db_sentence.minimum_level,
                }
            )

    exportable.sort(key=lambda x: x["guid"])
    return exportable


def _normalize_release_sentence_for_compare(release_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize release JSONL sentence data for comparison with DB export records."""
    normalized: Dict[str, Any] = {"guid": release_data.get("guid")}

    for field_name in ("pattern_type", "tense", "minimum_level", "notes"):
        if field_name in release_data:
            normalized[field_name] = release_data[field_name]

    release_lang_set = set(RELEASE_LANGUAGES)
    release_translations = release_data.get("translations", {})
    translations: Dict[str, str] = {}
    for lang_code, translation_text in release_translations.items():
        if lang_code not in release_lang_set:
            continue
        if translation_text and str(translation_text).strip():
            translations[lang_code] = str(translation_text)
    if translations:
        normalized["translations"] = translations

    pattern_words = release_data.get("pattern_words", [])
    if isinstance(pattern_words, list) and pattern_words:
        normalized_words: List[Dict[str, Any]] = []
        sorted_words = sorted(pattern_words, key=lambda p: p.get("position", 0))
        for pattern_word in sorted_words:
            normalized_words.append(
                {
                    "position": pattern_word.get("position", 0),
                    "slot_name": pattern_word.get("slot_name"),
                    "lemma_guid": pattern_word.get("lemma_guid"),
                    "english_text": pattern_word.get("english_text"),
                }
            )
        normalized["pattern_words"] = normalized_words

    words = release_data.get("words", [])
    if isinstance(words, list) and words:
        normalized_words_data: List[Dict[str, Any]] = []
        sorted_sentence_words = sorted(
            words, key=lambda item: (item.get("language_code", ""), item.get("position", 0))
        )
        for word_data in sorted_sentence_words:
            normalized_words_data.append(
                {
                    "language_code": word_data.get("language_code"),
                    "position": word_data.get("position", 0),
                    "word_role": word_data.get("word_role"),
                    "lemma_guid": word_data.get("lemma_guid"),
                    "english_text": word_data.get("english_text"),
                    "target_language_text": word_data.get("target_language_text"),
                    "grammatical_form": word_data.get("grammatical_form"),
                    "grammatical_case": word_data.get("grammatical_case"),
                    "declined_form": word_data.get("declined_form"),
                }
            )
        normalized["words"] = normalized_words_data

    audio = release_data.get("audio", [])
    if isinstance(audio, list) and audio:
        normalized_audio_data: List[Dict[str, Any]] = []
        sorted_audio = sorted(
            audio, key=lambda item: (item.get("language_code", ""), item.get("voice_name", ""))
        )
        for audio_data in sorted_audio:
            normalized_audio_data.append(
                {
                    "language_code": audio_data.get("language_code"),
                    "voice_name": audio_data.get("voice_name"),
                    "filename": audio_data.get("filename"),
                    "status": audio_data.get("status"),
                    "expected_text": audio_data.get("expected_text"),
                    "manifest_md5": audio_data.get("manifest_md5"),
                    "s3_prod_url": audio_data.get("s3_prod_url"),
                    "s3_staging_url": audio_data.get("s3_staging_url"),
                    "staging_agent": audio_data.get("staging_agent"),
                }
            )
        normalized["audio"] = normalized_audio_data

    return normalized


def _find_sync_back_candidates(
    release_sentences: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find sentences that exist in both DB and release, but differ from DB canonical record."""
    conversation_ids = _get_conversation_sentence_ids(db_session)
    db_rows = db_session.query(Sentence.id, Sentence.guid).filter(Sentence.guid.isnot(None)).all()
    db_guid_to_id = {guid: sentence_id for sentence_id, guid in db_rows if guid}
    common_guids = sorted(set(release_sentences.keys()) & set(db_guid_to_id.keys()))
    if not common_guids:
        return []

    candidates: List[Dict[str, Any]] = []
    batch_size = 500
    for index in range(0, len(common_guids), batch_size):
        batch = common_guids[index : index + batch_size]
        db_sentences = (
            db_session.query(Sentence)
            .filter(Sentence.guid.in_(batch))
            .options(
                selectinload(Sentence.translations),
                selectinload(Sentence.pattern_words).selectinload(SentencePatternWord.lemma),
                selectinload(Sentence.words).selectinload(SentenceWord.lemma),
                selectinload(Sentence.audio_reviews),
            )
            .all()
        )

        for db_sentence in db_sentences:
            if db_sentence.id in conversation_ids:
                continue

            release_data = release_sentences.get(db_sentence.guid)
            if not release_data:
                continue

            db_record = _sentence_to_release_record(db_sentence)
            normalized_release = _normalize_release_sentence_for_compare(release_data)
            if db_record == normalized_release:
                continue

            candidates.append(
                {
                    "guid": db_sentence.guid,
                    "sentence_id": db_sentence.id,
                    "english_text": _get_db_sentence_english(db_session, db_sentence)[:120],
                    "pattern_type": db_sentence.pattern_type or "",
                    "minimum_level": db_sentence.minimum_level,
                }
            )

    candidates.sort(key=lambda x: x["guid"])
    return candidates


@bp.route("/export")
def export() -> ResponseReturnValue:
    """Display DB sentences that are not yet in release JSONL files."""
    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    exportable = _find_exportable_sentences(release_sentences, g.db)
    sync_back_candidates = _find_sync_back_candidates(release_sentences, g.db)

    return render_template(
        "sync_sentence_release/export.html",
        exportable=exportable,
        sync_back_candidates=sync_back_candidates,
        release_dir=str(release_dir),
    )


@bp.route("/export/apply", methods=["POST"])
def apply_export() -> ResponseReturnValue:
    """Export selected DB sentences to release JSONL files."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.export"))

    selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No sentences selected for export", "warning")
        return redirect(url_for("sync_sentence_release.export"))

    release_dir = _get_sentence_release_dir()

    # Load existing release data so we can merge
    release_sentences = _load_release_sentences(release_dir)

    # Get conversation sentence IDs to exclude
    conversation_ids = _get_conversation_sentence_ids(g.db)

    # Query selected sentences with eager-loaded relationships
    db_sentences = (
        g.db.query(Sentence)
        .filter(Sentence.guid.in_(selected_guids))
        .options(
            selectinload(Sentence.translations),
            selectinload(Sentence.pattern_words).selectinload(SentencePatternWord.lemma),
            selectinload(Sentence.words).selectinload(SentenceWord.lemma),
            selectinload(Sentence.audio_reviews),
        )
        .all()
    )

    # Filter out conversation sentences
    db_sentences = [s for s in db_sentences if s.id not in conversation_ids]

    if not db_sentences:
        flash("No valid sentences found for export", "warning")
        return redirect(url_for("sync_sentence_release.export"))

    # Group new sentences by category, merging with existing release data
    # {(pos_type, pos_subtype): {guid: record}}
    category_records: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = defaultdict(dict)

    # Pre-load existing release records grouped by category
    for base_file in release_dir.rglob("base.jsonl"):
        # Determine category from path: release_dir/pos_dir/subtype/base.jsonl
        rel_path = base_file.relative_to(release_dir)
        parts = rel_path.parts  # e.g. ("verbs", "motion", "base.jsonl")
        if len(parts) < 3:
            continue
        pos_dir = parts[0]
        subtype = parts[1]
        # Reverse-map directory name to pos_type
        pos_type = pos_dir
        for pt, dn in _TYPE_TO_DIR.items():
            if dn == pos_dir:
                pos_type = pt
                break
        category_key = (pos_type, subtype)
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        guid = data.get("guid")
                        if guid:
                            category_records[category_key][guid] = data
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    # Add new sentences to their categories
    exported_count = 0
    for sentence in db_sentences:
        record = _sentence_to_release_record(sentence)
        category = _resolve_primary_lemma_category(sentence)
        category_records[category][sentence.guid] = record
        exported_count += 1

    # Write out all affected categories
    for (pos_type, pos_subtype), guid_to_record in category_records.items():
        # Only write categories that contain newly exported sentences
        has_new = any(
            s.guid in guid_to_record
            for s in db_sentences
            if _resolve_primary_lemma_category(s) == (pos_type, pos_subtype)
        )
        if not has_new:
            continue

        dir_name = _TYPE_TO_DIR.get(pos_type, pos_type)
        category_dir = release_dir / dir_name / pos_subtype
        category_dir.mkdir(parents=True, exist_ok=True)

        records = sorted(guid_to_record.values(), key=lambda r: r["guid"])
        _write_jsonl_atomic(category_dir / "base.jsonl", records)

    log_operation(
        session=g.db,
        source="sync-release",
        operation_type="sentence_export",
        details={
            "exported_count": exported_count,
            "selected_guids": selected_guids,
        },
    )
    g.db.commit()

    flash(f"Exported {exported_count} sentence(s) to release files", "success")
    return redirect(url_for("sync_sentence_release.export"))


@bp.route("/export/sync-back", methods=["POST"])
def apply_export_sync_back() -> ResponseReturnValue:
    """Overwrite existing release sentence records with canonical SQLite records."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.export"))

    selected_guids = request.form.getlist("selected_guids")
    if not selected_guids:
        flash("No sentences selected for sync-back", "warning")
        return redirect(url_for("sync_sentence_release.export"))

    release_dir = _get_sentence_release_dir()
    conversation_ids = _get_conversation_sentence_ids(g.db)
    db_sentences = (
        g.db.query(Sentence)
        .filter(Sentence.guid.in_(selected_guids))
        .options(
            selectinload(Sentence.translations),
            selectinload(Sentence.pattern_words).selectinload(SentencePatternWord.lemma),
            selectinload(Sentence.words).selectinload(SentenceWord.lemma),
            selectinload(Sentence.audio_reviews),
        )
        .all()
    )
    db_by_guid = {
        sentence.guid: sentence for sentence in db_sentences if sentence.id not in conversation_ids
    }

    if not db_by_guid:
        flash("No valid sentences found for sync-back", "warning")
        return redirect(url_for("sync_sentence_release.export"))

    updated_count = 0
    for guid in selected_guids:
        sentence = db_by_guid.get(guid)
        if not sentence:
            continue

        new_record = _sentence_to_release_record(sentence)
        release_file = _find_release_file_for_sentence(release_dir, guid)

        # If no existing file is found (unexpected for sync-back), append via export category.
        if not release_file:
            category = _resolve_primary_lemma_category(sentence)
            dir_name = _TYPE_TO_DIR.get(category[0], category[0])
            category_dir = release_dir / dir_name / category[1]
            category_dir.mkdir(parents=True, exist_ok=True)
            release_file = category_dir / "base.jsonl"

        existing_records: List[Dict[str, Any]] = []
        replaced = False
        if release_file.exists():
            with open(release_file, "r", encoding="utf-8") as source_file:
                for line in source_file:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    existing_guid = data.get("guid")
                    if existing_guid == guid:
                        existing_records.append(new_record)
                        replaced = True
                    else:
                        existing_records.append(data)
        if not replaced:
            existing_records.append(new_record)

        existing_records.sort(key=lambda record: record.get("guid", ""))
        _write_jsonl_atomic(release_file, existing_records)
        updated_count += 1

    log_operation(
        session=g.db,
        source="sync-release",
        operation_type="sentence_sync_back",
        details={"updated_count": updated_count, "selected_guids": selected_guids},
    )
    g.db.commit()

    flash(f"Synced {updated_count} sentence(s) from SQLite to release files", "success")
    return redirect(url_for("sync_sentence_release.export"))
