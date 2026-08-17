#!/usr/bin/python3

"""Routes for syncing phrase data between data/release/phrases and SQLite.

This mirrors ``sync_sentence_release`` but for the simpler phrase model:
phrases have a concept label (English), a definition, a difficulty level, and
per-language translations — no word hints, sentence words, audio, or
conversation exclusion. The two syncs are deliberately kept as parallel modules
(as lemma/sentence sync already are) rather than a shared engine.

Field mapping (release JSONL <-> Phrase):
  concept_label       <-> Phrase.label       (the "changes" / English-text mode)
  difficulty_level    <-> Phrase.difficulty_level  (the "level" mode)
  translations[lang]  <-> PhraseTranslation   (the "translations" mode, non-en)
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
from storage.crud.phrase import set_phrase_translation
from storage.migrate import phrase_to_release_records
from storage.models.schema import Phrase, PhraseTranslation
from storage.translation_helpers import LANGUAGE_NAMES, RELEASE_LANGUAGES

logger = logging.getLogger(__name__)

bp = Blueprint("sync_phrase_release", __name__, url_prefix="/sync/phrases")

# __file__ is src/barsukas/routes/sync/sync_phrase_release.py; five parents up is
# the repo root.
DEFAULT_PHRASE_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "phrases"
)

# Languages compared/synced by the translations mode (English is handled by the
# concept-label "changes" mode instead).
_TRANSLATION_LANGS: List[str] = [lang for lang in RELEASE_LANGUAGES if lang != "en"]


def _get_phrase_release_dir() -> Path:
    """Get the path to the data/release/phrases directory."""
    return DEFAULT_PHRASE_RELEASE_DIR


def _load_release_phrases(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all phrases from data/release/phrases base.jsonl files, keyed by GUID.

    A phrase's subtype is its directory name rather than a stored field, so it
    is filled in from the path.
    """
    return release_io.load_release_records(release_dir, subtype_key="phrase_subtype")


def _release_english(release_data: Dict[str, Any]) -> str:
    """The canonical English text of a release phrase (its concept_label)."""
    return str(release_data.get("concept_label") or "")


def _db_translations(db_session: Any, phrase_ids: List[int]) -> Dict[int, Dict[str, str]]:
    """Return {phrase_id: {lang_code: translation}} for the given phrases."""
    result: Dict[int, Dict[str, str]] = {pid: {} for pid in phrase_ids}
    if not phrase_ids:
        return result
    rows = (
        db_session.query(PhraseTranslation)
        .filter(PhraseTranslation.phrase_id.in_(phrase_ids))
        .all()
    )
    for row in rows:
        if row.translation:
            result[row.phrase_id][row.language_code] = row.translation
    return result


# =============================================================================
# Index
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the phrase sync hub with per-mode difference counts."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)

    db_phrases = g.db.query(Phrase).filter(Phrase.guid.isnot(None)).all()
    db_by_guid = {p.guid: p for p in db_phrases}
    db_guids = set(db_by_guid.keys())
    release_guids = set(release_phrases.keys())

    common = release_guids & db_guids
    db_trans = _db_translations(g.db, [db_by_guid[guid].id for guid in common])

    level_diffs = 0
    text_changes = 0
    translation_diffs = 0
    for guid in common:
        phrase = db_by_guid[guid]
        release_data = release_phrases[guid]
        if phrase.label != _release_english(release_data):
            text_changes += 1
            continue
        if release_data.get("difficulty_level") != phrase.difficulty_level:
            level_diffs += 1
        if _has_translation_diff(release_data, db_trans.get(phrase.id, {})):
            translation_diffs += 1

    counts = {
        "release_total": len(release_phrases),
        "db_total": len(db_guids),
        "additions": len(release_guids - db_guids),
        "removals": len(db_guids - release_guids),
        "export": len(db_guids - release_guids),
        "level": level_diffs,
        "changes": text_changes,
        "translations": translation_diffs,
    }
    return render_template(
        "sync_phrase_release/index.html", release_dir=str(release_dir), counts=counts
    )


def _has_translation_diff(release_data: Dict[str, Any], db_trans: Dict[str, str]) -> bool:
    """True if any non-English translation differs between release and DB."""
    release_translations = release_data.get("translations", {})
    for lang in _TRANSLATION_LANGS:
        if (release_translations.get(lang, "") or "").strip() != (
            db_trans.get(lang, "") or ""
        ).strip():
            return True
    return False


# =============================================================================
# Additions
# =============================================================================


@bp.route("/additions")
def additions() -> ResponseReturnValue:
    """Phrase GUIDs in release but not in SQLite."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)

    db_guids = {guid for (guid,) in g.db.query(Phrase.guid).filter(Phrase.guid.isnot(None)).all()}
    additions_list = [
        {
            "guid": guid,
            "phrase_subtype": data.get("phrase_subtype", ""),
            "english_text": _release_english(data),
            "difficulty_level": data.get("difficulty_level"),
            "translations": data.get("translations", {}),
        }
        for guid, data in sorted(release_phrases.items())
        if guid not in db_guids
    ]
    return render_template(
        "sync_phrase_release/additions.html",
        page=paginate(additions_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new phrases from release."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.additions"))

    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)

    if request.form.get("select_scope") == "all":
        db_guids = {guid for (guid,) in g.db.query(Phrase.guid).filter(Phrase.guid.isnot(None))}
        selected_guids = [guid for guid in sorted(release_phrases) if guid not in db_guids]
    else:
        selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No phrases selected for import", "warning")
        return redirect(url_for("sync_phrase_release.additions"))

    outcome = SyncOutcome(noun="phrase")
    for guid in selected_guids:
        release_data = release_phrases.get(guid)
        if not release_data:
            outcome.record_error(f"Release data not found for GUID: {guid}")
            continue
        try:
            phrase = Phrase(
                guid=guid,
                phrase_subtype=release_data.get("phrase_subtype") or "greetings",
                label=_release_english(release_data),
                definition=release_data.get("concept_definition"),
                difficulty_level=release_data.get("difficulty_level"),
            )
            g.db.add(phrase)
            g.db.flush()
            for lang_code, text in (release_data.get("translations") or {}).items():
                if not text:
                    continue
                meta = (release_data.get("translation_metadata") or {}).get(lang_code, {})
                set_phrase_translation(
                    g.db,
                    phrase,
                    lang_code,
                    text,
                    translation_status=meta.get("translation_status"),
                    translation_status_note=meta.get("translation_status_note"),
                )
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="phrase_import",
                details={"guid": guid, "english_text": _release_english(release_data)[:80]},
            )
            outcome.imported += 1
        except Exception as e:
            outcome.record_error(f"Error importing phrase {guid}: {e}")

    outcome.commit(g.db)
    outcome.flash_summary()
    return redirect(url_for("sync_phrase_release.additions"))


# =============================================================================
# Removals
# =============================================================================


@bp.route("/removals")
def removals() -> ResponseReturnValue:
    """Phrase GUIDs in SQLite but not in release."""
    release_dir = _get_phrase_release_dir()
    release_guids = set(_load_release_phrases(release_dir).keys())

    removals_list = [
        {
            "guid": p.guid,
            "phrase_id": p.id,
            "phrase_subtype": p.phrase_subtype,
            "english_text": p.label,
            "difficulty_level": p.difficulty_level,
        }
        for p in g.db.query(Phrase).filter(Phrase.guid.isnot(None)).order_by(Phrase.guid).all()
        if p.guid not in release_guids
    ]
    return render_template(
        "sync_phrase_release/removals.html",
        page=paginate(removals_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected phrases that are not in release."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.removals"))

    selected_ids = request.form.getlist("selected_ids")
    if not selected_ids:
        flash("No phrases selected for deletion", "warning")
        return redirect(url_for("sync_phrase_release.removals"))

    outcome = SyncOutcome(noun="phrase")
    for phrase_id_str in selected_ids:
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                outcome.record_error(f"Phrase not found: {phrase_id_str}")
                continue
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="phrase_delete",
                details={"guid": phrase.guid, "phrase_id": phrase.id},
            )
            g.db.delete(phrase)
            outcome.deleted += 1
        except Exception as e:
            outcome.record_error(f"Error deleting phrase {phrase_id_str}: {e}")

    outcome.commit(g.db)
    outcome.flash_summary()
    return redirect(url_for("sync_phrase_release.removals"))


# =============================================================================
# Level (difficulty_level differs)
# =============================================================================


def _common_phrases(
    release_phrases: Dict[str, Dict[str, Any]],
) -> List[Tuple[Phrase, Dict[str, Any]]]:
    """Return (Phrase, release_data) pairs for GUIDs present in both."""
    release_guids = list(release_phrases.keys())
    if not release_guids:
        return []
    db_phrases = g.db.query(Phrase).filter(Phrase.guid.in_(release_guids)).all()
    return [(p, release_phrases[p.guid]) for p in db_phrases if p.guid in release_phrases]


@bp.route("/level")
def level() -> ResponseReturnValue:
    """Difficulty-level differences (where English text matches)."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    differences = []
    for phrase, release_data in _common_phrases(release_phrases):
        if phrase.label != _release_english(release_data):
            continue
        if release_data.get("difficulty_level") == phrase.difficulty_level:
            continue
        differences.append(
            {
                "guid": phrase.guid,
                "phrase_id": phrase.id,
                "english_text": phrase.label,
                "phrase_subtype": phrase.phrase_subtype,
                "db_level": phrase.difficulty_level,
                "release_level": release_data.get("difficulty_level"),
            }
        )
    differences.sort(key=lambda x: str(x["guid"]))
    return render_template(
        "sync_phrase_release/level.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/level/apply", methods=["POST"])
def apply_level() -> ResponseReturnValue:
    """Apply selected difficulty-level changes."""
    return _apply_field_actions(
        field="difficulty_level", redirect_endpoint="sync_phrase_release.level"
    )


# =============================================================================
# Changes (concept_label / English text differs)
# =============================================================================


@bp.route("/changes")
def changes() -> ResponseReturnValue:
    """English concept-label differences."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    changes_list = []
    for phrase, release_data in _common_phrases(release_phrases):
        release_english = _release_english(release_data)
        if phrase.label == release_english:
            continue
        changes_list.append(
            {
                "guid": phrase.guid,
                "phrase_id": phrase.id,
                "phrase_subtype": phrase.phrase_subtype,
                "db_english": phrase.label,
                "release_english": release_english,
            }
        )
    changes_list.sort(key=lambda x: str(x["guid"]))
    return render_template(
        "sync_phrase_release/changes.html",
        page=paginate(changes_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/changes/apply", methods=["POST"])
def apply_changes() -> ResponseReturnValue:
    """Apply selected English concept-label changes."""
    return _apply_field_actions(
        field="concept_label", redirect_endpoint="sync_phrase_release.changes"
    )


def _apply_field_actions(field: str, redirect_endpoint: str) -> ResponseReturnValue:
    """Shared handler for the level and changes modes (single-field per phrase).

    ``field`` is ``difficulty_level`` or ``concept_label``; it selects which
    Phrase attribute and which release JSONL key to sync.
    """
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for(redirect_endpoint))

    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    attr = "difficulty_level" if field == "difficulty_level" else "label"

    bulk = parse_bulk_request()
    if bulk is not None:
        differing = _differing_phrase_ids(release_phrases, field, attr)
        expanded = bulk_actions_for(bulk, differing, total=len(differing))
        if expanded is None:
            return redirect(url_for(redirect_endpoint))
        actions = expanded
    else:
        actions = parse_row_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for(redirect_endpoint))

    outcome = SyncOutcome(noun="phrase")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for phrase_id_str, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        if action not in (USE_RELEASE, USE_DB):
            continue
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                outcome.record_error(f"Phrase not found: {phrase_id_str}")
                continue
            release_data = release_phrases.get(phrase.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {phrase.guid}")
                continue

            if action == USE_RELEASE:
                old_value = getattr(phrase, attr)
                new_value = release_data.get(field)
                setattr(phrase, attr, new_value)
                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"phrase_{field}_sync",
                    field_name=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
                outcome.updated_db += 1
            else:  # USE_DB
                file_path = release_io.file_for_guid(guid_files, phrase.guid)
                if file_path is None:
                    outcome.record_error(f"Could not find release file for GUID: {phrase.guid}")
                    continue
                release_updates.setdefault(file_path, {})[phrase.guid] = {
                    field: getattr(phrase, attr)
                }
                outcome.updated_release += 1
        except Exception as e:
            outcome.record_error(f"Error updating phrase {phrase_id_str}: {e}")

    outcome.commit(g.db)
    outcome.write_release(lambda: release_io.apply_field_updates(release_updates))
    outcome.flash_summary()
    return redirect(url_for(redirect_endpoint))


def _differing_phrase_ids(
    release_phrases: Dict[str, Dict[str, Any]], field: str, attr: str
) -> List[int]:
    """Phrase ids whose ``field`` differs from the release record."""
    return [
        phrase.id
        for phrase, release_data in _common_phrases(release_phrases)
        if getattr(phrase, attr) != release_data.get(field)
        and (field == "concept_label" or phrase.label == _release_english(release_data))
    ]


# =============================================================================
# Translations
# =============================================================================


@bp.route("/translations")
def translations() -> ResponseReturnValue:
    """Per-language translation differences (where English text matches)."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    common = _common_phrases(release_phrases)
    db_trans = _db_translations(g.db, [p.id for p, _ in common])

    differences = []
    for phrase, release_data in common:
        if phrase.label != _release_english(release_data):
            continue
        release_translations = release_data.get("translations", {})
        this_db = db_trans.get(phrase.id, {})
        lang_diffs = []
        for lang in _TRANSLATION_LANGS:
            release_val = (release_translations.get(lang, "") or "").strip()
            db_val = (this_db.get(lang, "") or "").strip()
            if release_val != db_val:
                lang_diffs.append(
                    {
                        "lang_code": lang,
                        "lang_name": LANGUAGE_NAMES.get(lang, lang),
                        "release_val": release_val,
                        "db_val": db_val,
                    }
                )
        if lang_diffs:
            differences.append(
                {
                    "guid": phrase.guid,
                    "phrase_id": phrase.id,
                    "english_text": phrase.label,
                    "lang_diffs": lang_diffs,
                    "diff_count": len(lang_diffs),
                }
            )
    differences.sort(key=lambda x: str(x["guid"]))
    return render_template(
        "sync_phrase_release/translations.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected per-language translation changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.translations"))

    actions = parse_language_actions()
    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_phrase_release.translations"))

    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)

    outcome = SyncOutcome(noun="translation")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for phrase_id_str, lang_actions in actions.items():
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                outcome.record_error(f"Phrase not found: {phrase_id_str}")
                continue
            release_data = release_phrases.get(phrase.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {phrase.guid}")
                continue
            release_translations = release_data.get("translations", {})

            for lang_code, action in lang_actions.items():
                if action == USE_RELEASE:
                    release_val = release_translations.get(lang_code, "")
                    if release_val:
                        set_phrase_translation(g.db, phrase, lang_code, release_val)
                        outcome.updated_db += 1
                    else:
                        outcome.skipped += 1
                elif action == USE_DB:
                    existing = (
                        g.db.query(PhraseTranslation)
                        .filter(
                            PhraseTranslation.phrase_id == phrase.id,
                            PhraseTranslation.language_code == lang_code,
                        )
                        .first()
                    )
                    db_val = existing.translation if existing else ""
                    if not db_val:
                        outcome.skipped += 1
                        continue
                    file_path = release_io.file_for_guid(guid_files, phrase.guid)
                    if file_path is None:
                        outcome.record_error(f"Could not find release file for GUID: {phrase.guid}")
                        continue
                    release_updates.setdefault(file_path, {}).setdefault(phrase.guid, {})[
                        lang_code
                    ] = db_val
                    outcome.updated_release += 1
                else:
                    outcome.skipped += 1
        except Exception as e:
            outcome.record_error(f"Error processing phrase {phrase_id_str}: {e}")

    outcome.commit(g.db)
    outcome.write_release(lambda: release_io.apply_translation_updates(release_updates))
    outcome.flash_summary()
    return redirect(url_for("sync_phrase_release.translations"))


# =============================================================================
# Export (DB phrases not in release) + sync-back
# =============================================================================


@bp.route("/export")
def export() -> ResponseReturnValue:
    """DB phrases not yet in release, plus phrases whose release record differs."""
    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    release_guids = set(release_phrases.keys())

    db_phrases = (
        g.db.query(Phrase)
        .filter(Phrase.guid.isnot(None))
        .options(selectinload(Phrase.translations))
        .order_by(Phrase.guid)
        .all()
    )

    exportable = []
    sync_back_candidates = []
    for phrase in db_phrases:
        if phrase.guid not in release_guids:
            exportable.append(
                {
                    "guid": phrase.guid,
                    "phrase_subtype": phrase.phrase_subtype,
                    "english_text": phrase.label,
                    "difficulty_level": phrase.difficulty_level,
                }
            )
        else:
            base_record, _ = phrase_to_release_records(phrase)
            if base_record != _normalize_release_phrase(release_phrases[phrase.guid]):
                sync_back_candidates.append(
                    {
                        "guid": phrase.guid,
                        "phrase_subtype": phrase.phrase_subtype,
                        "english_text": phrase.label,
                        "difficulty_level": phrase.difficulty_level,
                    }
                )

    return render_template(
        "sync_phrase_release/export.html",
        exportable=exportable,
        sync_back_candidates=sync_back_candidates,
        release_dir=str(release_dir),
    )


def _normalize_release_phrase(release_data: Dict[str, Any]) -> Dict[str, Any]:
    """Project a release record onto the base-record fields for comparison."""
    normalized: Dict[str, Any] = {
        "guid": release_data.get("guid"),
        "phrase_subtype": release_data.get("phrase_subtype"),
        "concept_label": release_data.get("concept_label"),
        "concept_definition": release_data.get("concept_definition"),
    }
    release_lang_set = set(RELEASE_LANGUAGES)
    translations = {
        lang: text
        for lang, text in (release_data.get("translations") or {}).items()
        if lang in release_lang_set and text and str(text).strip()
    }
    if translations:
        normalized["translations"] = translations
    metadata = release_data.get("translation_metadata")
    if metadata:
        normalized["translation_metadata"] = metadata
    if release_data.get("difficulty_level") is not None:
        normalized["difficulty_level"] = release_data["difficulty_level"]
    return normalized


@bp.route("/export/apply", methods=["POST"])
def apply_export() -> ResponseReturnValue:
    """Export selected DB phrases to release JSONL files (new records)."""
    return _write_phrases_to_release(sync_back=False)


@bp.route("/export/sync-back", methods=["POST"])
def apply_export_sync_back() -> ResponseReturnValue:
    """Overwrite existing release phrase records with canonical SQLite records."""
    return _write_phrases_to_release(sync_back=True)


def _write_phrases_to_release(sync_back: bool) -> ResponseReturnValue:
    """Write selected DB phrases into their subtype base.jsonl, merging by GUID."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.export"))

    selected_guids = request.form.getlist("selected_guids")
    if not selected_guids:
        flash("No phrases selected", "warning")
        return redirect(url_for("sync_phrase_release.export"))

    release_dir = _get_phrase_release_dir()
    db_phrases = (
        g.db.query(Phrase)
        .filter(Phrase.guid.in_(selected_guids))
        .options(selectinload(Phrase.translations))
        .all()
    )

    # upsert_records merges by GUID, so siblings already in the file survive.
    by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for phrase in db_phrases:
        base_record, _ = phrase_to_release_records(phrase)
        by_subtype[phrase.phrase_subtype].append(base_record)

    written = 0
    for subtype, records in by_subtype.items():
        written += release_io.upsert_records(release_dir / subtype / "base.jsonl", records)

    log_operation(
        session=g.db,
        source="sync-release",
        operation_type="phrase_sync_back" if sync_back else "phrase_export",
        details={"count": written, "selected_guids": selected_guids},
    )
    g.db.commit()

    verb = "Synced back" if sync_back else "Exported"
    flash(f"{verb} {written} phrase(s) to release files", "success")
    return redirect(url_for("sync_phrase_release.export"))


# =============================================================================
# Release-file writers
# =============================================================================
