#!/usr/bin/python3

"""Routes for syncing sentence data between data/release/sentences and SQLite database."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, cast

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import selectinload

from barsukas.routes.sync import release_io
from barsukas.routes.sync.actions import (
    SKIP,
    USE_DB,
    USE_RELEASE,
    SyncOutcome,
    bulk_actions_for,
    is_readonly,
    parse_bulk_request,
    parse_language_actions,
    parse_row_actions,
)
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, paginate
from storage.crud.operation_log import log_operation, log_translation_change
from storage.migrate import _resolve_primary_lemma_category, _sentence_to_release_record
from storage.models.schema import (
    ConversationSentence,
    Lemma,
    Sentence,
    SentenceWordHint,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    RELEASE_LANGUAGES,
)

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
        db_session.query(Sentence.id, Sentence.guid)
        .filter(Sentence.guid.isnot(None))
        .filter(Sentence.rejected.is_(False))
        .all()
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
        word_hints = release_data.get("word_hints", [])
        sentence_words = release_data.get("words", [])

        # Check for missing lemma GUIDs
        missing_lemma_guids: Set[str] = set()
        for release_word in [*word_hints, *sentence_words]:
            lemma_guid = release_word.get("lemma_guid")
            if lemma_guid and lemma_guid not in all_lemma_guids:
                missing_lemma_guids.add(lemma_guid)

        item: Dict[str, Any] = {
            "guid": guid,
            "english_text": english_text[:120] if english_text else "",
            "full_english_text": english_text,
            "pattern_type": release_data.get("pattern_type", ""),
            "tense": release_data.get("tense", ""),
            "minimum_level": release_data.get("minimum_level"),
            "translations": release_data.get("translations", {}),
            "word_hints": word_hints,
        }

        if missing_lemma_guids:
            item["missing_lemma_guids"] = sorted(missing_lemma_guids)
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
        page=paginate(importable),
        per_page_choices=PER_PAGE_CHOICES,
        blocked=blocked,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new sentences from release."""
    if is_readonly():
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
            # Validate all referenced lemma GUIDs exist. Skipping an unresolved
            # decomposition word would silently corrupt the JSONL round trip.
            word_hints = release_data.get("word_hints", [])
            sentence_words = release_data.get("words", [])
            missing_guids = sorted(
                {
                    release_word["lemma_guid"]
                    for release_word in [*word_hints, *sentence_words]
                    if release_word.get("lemma_guid")
                    and release_word["lemma_guid"] not in lemma_guid_to_id
                }
            )
            if missing_guids:
                flash(
                    f"Skipped {guid}: missing lemma GUIDs: {', '.join(missing_guids)}",
                    "warning",
                )
                error_count += 1
                continue

            sentence = Sentence(
                guid=guid,
                sentence_collection=release_data.get("collection") or None,
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

            # Add word hints
            for pw in word_hints:
                lemma_guid = pw.get("lemma_guid")
                lemma_id = lemma_guid_to_id.get(lemma_guid) if lemma_guid else None
                if lemma_id is None:
                    continue

                word_hint = SentenceWordHint(
                    sentence_id=sentence.id,
                    lemma_id=lemma_id,
                    position=pw.get("position", 0),
                    slot_name=pw.get("slot_name", "unknown"),
                    english_text=pw.get("english_text", ""),
                )
                g.db.add(word_hint)

            # Add the full per-language decomposition, including Universal
            # Dependencies fields. The release serializer already writes these
            # fields; importing them here completes the Barsukas sync round trip.
            for word_data in sentence_words:
                lemma_guid = word_data.get("lemma_guid")
                lemma_id = lemma_guid_to_id.get(lemma_guid) if lemma_guid else None
                sentence_word = SentenceWord(
                    sentence_id=sentence.id,
                    lemma_id=lemma_id,
                    language_code=word_data.get("language_code", ""),
                    position=word_data.get("position", 0),
                    part_of_speech=word_data.get("word_role", ""),
                    english_text=word_data.get("english_text"),
                    target_language_text=word_data.get("target_language_text"),
                    grammatical_form=word_data.get("grammatical_form"),
                    grammatical_case=word_data.get("grammatical_case"),
                    declined_form=word_data.get("declined_form"),
                    ud_relation=word_data.get("ud_relation"),
                    ud_head_position=word_data.get("ud_head_position"),
                )
                g.db.add(sentence_word)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="sentence_import",
                details={
                    "guid": guid,
                    "english_text": _get_release_sentence_english(release_data)[:80],
                    "translation_count": len(translations),
                    "word_hint_count": len(word_hints),
                    "word_count": len(sentence_words),
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
        page=paginate(removals_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected sentences that are not in release."""
    if is_readonly():
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
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/level/apply", methods=["POST"])
def apply_level() -> ResponseReturnValue:
    """Apply selected minimum_level changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.level"))

    actions: Dict[str, str] = {}
    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        differences = _find_level_differences(release_sentences, g.db)
        expanded = bulk_actions_for(
            bulk, (diff["sentence_id"] for diff in differences), total=len(differences)
        )
        if expanded is None:
            return redirect(url_for("sync_sentence_release.level"))
        actions = expanded
    else:
        actions = parse_row_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.level"))

    outcome = SyncOutcome(noun="sentence")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for sentence_id_str, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        if action not in (USE_RELEASE, USE_DB):
            continue

        try:
            sentence = g.db.query(Sentence).filter(Sentence.id == int(sentence_id_str)).first()
            if not sentence:
                outcome.record_error(f"Sentence not found: {sentence_id_str}")
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {sentence.guid}")
                continue

            if action == USE_RELEASE:
                new_level = release_data.get("minimum_level")
                old_level = sentence.minimum_level
                sentence.minimum_level = new_level
                outcome.updated_db += 1

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="sentence_level_sync",
                    field_name="minimum_level",
                    old_value=str(old_level) if old_level is not None else None,
                    new_value=str(new_level) if new_level is not None else None,
                )
            else:  # USE_DB
                file_path = release_io.file_for_guid(guid_files, sentence.guid)
                if file_path is None:
                    outcome.record_error(
                        f"Could not find release file for sentence GUID: {sentence.guid}"
                    )
                    continue
                release_updates.setdefault(file_path, {})[sentence.guid] = {
                    "minimum_level": sentence.minimum_level,
                }
                outcome.updated_release += 1

        except Exception as e:
            outcome.record_error(f"Error updating sentence {sentence_id_str}: {e}")

    outcome.commit(g.db)
    outcome.write_release(lambda: release_io.apply_field_updates(release_updates))
    outcome.flash_summary()
    return redirect(url_for("sync_sentence_release.level"))
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
        page=paginate(changes_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/changes/apply", methods=["POST"])
def apply_changes() -> ResponseReturnValue:
    """Apply selected English text changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.changes"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        changes_list = _find_english_text_changes(release_sentences, g.db)
        expanded = bulk_actions_for(
            bulk, (item["sentence_id"] for item in changes_list), total=len(changes_list)
        )
        if expanded is None:
            return redirect(url_for("sync_sentence_release.changes"))
        actions = expanded
    else:
        actions = parse_row_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.changes"))

    outcome = SyncOutcome(noun="sentence")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for sentence_id_str, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        if action not in (USE_RELEASE, USE_DB):
            continue

        try:
            sentence = g.db.query(Sentence).filter(Sentence.id == int(sentence_id_str)).first()
            if not sentence:
                outcome.record_error(f"Sentence not found: {sentence_id_str}")
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {sentence.guid}")
                continue

            if action == USE_RELEASE:
                new_english = _get_release_sentence_english(release_data)
                old_english = _get_db_sentence_english(g.db, sentence)

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
                    g.db.add(
                        SentenceTranslation(
                            sentence_id=sentence.id,
                            language_code="en",
                            translation_text=new_english,
                            verified=False,
                        )
                    )

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="sentence_text_sync",
                    language_code="en",
                    old_translation=old_english,
                    new_translation=new_english,
                )
                outcome.updated_db += 1
            else:  # USE_DB
                db_english = _get_db_sentence_english(g.db, sentence)
                if not db_english:
                    outcome.skipped += 1
                    continue
                file_path = release_io.file_for_guid(guid_files, sentence.guid)
                if file_path is None:
                    outcome.record_error(
                        f"Could not find release file for sentence GUID: {sentence.guid}"
                    )
                    continue
                release_updates.setdefault(file_path, {})[sentence.guid] = {
                    "translations.en": db_english,
                }
                outcome.updated_release += 1

        except Exception as e:
            outcome.record_error(f"Error updating sentence {sentence_id_str}: {e}")

    outcome.commit(g.db)
    outcome.write_release(lambda: release_io.apply_field_updates(release_updates))
    outcome.flash_summary()
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
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
        language_names=LANGUAGE_NAMES,
    )


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected sentence translation changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.translations"))

    release_dir = _get_sentence_release_dir()
    release_sentences = _load_release_sentences(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        differences = _find_sentence_translation_differences(release_sentences, g.db)
        if bulk_actions_for(bulk, (), total=len(differences)) is None:
            return redirect(url_for("sync_sentence_release.translations"))
        actions = {
            str(diff["sentence_id"]): {
                str(lang_diff["lang_code"]): bulk.action for lang_diff in diff["lang_diffs"]
            }
            for diff in differences
        }
    else:
        actions = parse_language_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_sentence_release.translations"))

    outcome = SyncOutcome(noun="translation")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for sentence_id_str, lang_actions in actions.items():
        try:
            sentence = g.db.query(Sentence).filter(Sentence.id == int(sentence_id_str)).first()
            if not sentence:
                outcome.record_error(f"Sentence not found: {sentence_id_str}")
                continue

            release_data = release_sentences.get(sentence.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {sentence.guid}")
                continue

            release_translations = release_data.get("translations", {})

            for lang_code, action in lang_actions.items():
                if action == SKIP:
                    outcome.skipped += 1
                    continue

                trans_obj = (
                    g.db.query(SentenceTranslation)
                    .filter(
                        SentenceTranslation.sentence_id == sentence.id,
                        SentenceTranslation.language_code == lang_code,
                    )
                    .first()
                )

                if action == USE_RELEASE:
                    release_val = release_translations.get(lang_code, "")
                    if not release_val:
                        outcome.skipped += 1
                        continue
                    if trans_obj:
                        old_val = trans_obj.translation_text
                        trans_obj.translation_text = release_val
                    else:
                        g.db.add(
                            SentenceTranslation(
                                sentence_id=sentence.id,
                                language_code=lang_code,
                                translation_text=release_val,
                                verified=False,
                            )
                        )
                        old_val = None

                    log_translation_change(
                        session=g.db,
                        source="sync-release",
                        operation_type="sentence_translation_sync",
                        language_code=lang_code,
                        old_translation=old_val,
                        new_translation=release_val,
                    )
                    outcome.updated_db += 1

                elif action == USE_DB:
                    db_val = trans_obj.translation_text if trans_obj else ""
                    if not db_val:
                        outcome.skipped += 1
                        continue
                    file_path = release_io.file_for_guid(guid_files, sentence.guid)
                    if file_path is None:
                        outcome.record_error(
                            f"Could not find release file for sentence GUID: {sentence.guid}"
                        )
                        continue
                    release_updates.setdefault(file_path, {}).setdefault(sentence.guid, {})[
                        lang_code
                    ] = db_val
                    outcome.updated_release += 1

        except Exception as e:
            outcome.record_error(f"Error processing sentence {sentence_id_str}: {e}")

    outcome.commit(g.db)
    outcome.write_release(lambda: release_io.apply_translation_updates(release_updates))
    outcome.flash_summary()
    return redirect(url_for("sync_sentence_release.translations"))


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


def _export_file_for_sentence(release_dir: Path, sentence: Any) -> Path:
    """The base.jsonl a sentence belongs in, by collection and primary lemma."""
    collection = sentence.sentence_collection or "general"
    pos_type, pos_subtype = _resolve_primary_lemma_category(sentence)
    dir_name = _TYPE_TO_DIR.get(pos_type, pos_type)
    return release_dir / collection / dir_name / pos_subtype / "base.jsonl"


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
        db_sentences = (
            db_session.query(Sentence)
            .filter(Sentence.guid.in_(batch))
            .filter(Sentence.rejected.is_(False))
            .all()
        )

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

    for field_name in ("collection", "pattern_type", "tense", "minimum_level", "notes"):
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

    word_hints = release_data.get("word_hints", [])
    if isinstance(word_hints, list) and word_hints:
        normalized_words: List[Dict[str, Any]] = []
        sorted_words = sorted(word_hints, key=lambda p: p.get("position", 0))
        for word_hint in sorted_words:
            normalized_words.append(
                {
                    "position": word_hint.get("position", 0),
                    "slot_name": word_hint.get("slot_name"),
                    "lemma_guid": word_hint.get("lemma_guid"),
                    "english_text": word_hint.get("english_text"),
                }
            )
        normalized["word_hints"] = normalized_words

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
                    "ud_relation": word_data.get("ud_relation"),
                    "ud_head_position": word_data.get("ud_head_position"),
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
    db_rows = (
        db_session.query(Sentence.id, Sentence.guid)
        .filter(Sentence.guid.isnot(None))
        .filter(Sentence.rejected.is_(False))
        .all()
    )
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
            .filter(Sentence.rejected.is_(False))
            .options(
                selectinload(Sentence.translations),
                selectinload(Sentence.word_hints).selectinload(SentenceWordHint.lemma),
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
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_sentence_release.export"))

    selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No sentences selected for export", "warning")
        return redirect(url_for("sync_sentence_release.export"))

    release_dir = _get_sentence_release_dir()

    # Get conversation sentence IDs to exclude
    conversation_ids = _get_conversation_sentence_ids(g.db)

    # Query selected sentences with eager-loaded relationships
    db_sentences = (
        g.db.query(Sentence)
        .filter(Sentence.guid.in_(selected_guids))
        .filter(Sentence.rejected.is_(False))
        .options(
            selectinload(Sentence.translations),
            selectinload(Sentence.word_hints).selectinload(SentenceWordHint.lemma),
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

    # upsert_records merges by GUID, so records already in a file survive and
    # only the files actually being written to are touched.
    records_by_file: Dict[Path, List[Dict[str, Any]]] = defaultdict(list)
    for sentence in db_sentences:
        target = _export_file_for_sentence(release_dir, sentence)
        records_by_file[target].append(_sentence_to_release_record(sentence))

    exported_count = sum(
        release_io.upsert_records(release_file, records)
        for release_file, records in records_by_file.items()
    )

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
    if is_readonly():
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
        .filter(Sentence.rejected.is_(False))
        .options(
            selectinload(Sentence.translations),
            selectinload(Sentence.word_hints).selectinload(SentenceWordHint.lemma),
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

    # Group by target file so each base.jsonl is rewritten once, not once per
    # sentence. upsert_records merges by GUID, so siblings survive.
    guid_files = release_io.build_guid_file_index(release_dir)
    records_by_file: Dict[Path, List[Dict[str, Any]]] = defaultdict(list)
    for guid in selected_guids:
        sentence = db_by_guid.get(guid)
        if not sentence:
            continue
        release_file = release_io.file_for_guid(guid_files, guid)
        if release_file is None:
            release_file = _export_file_for_sentence(release_dir, sentence)
        records_by_file[release_file].append(_sentence_to_release_record(sentence))

    updated_count = sum(
        release_io.upsert_records(release_file, records)
        for release_file, records in records_by_file.items()
    )

    log_operation(
        session=g.db,
        source="sync-release",
        operation_type="sentence_sync_back",
        details={"updated_count": updated_count, "selected_guids": selected_guids},
    )
    g.db.commit()

    flash(f"Synced {updated_count} sentence(s) from SQLite to release files", "success")
    return redirect(url_for("sync_sentence_release.export"))
