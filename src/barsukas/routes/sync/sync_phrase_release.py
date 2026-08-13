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

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import selectinload

from storage.crud.operation_log import log_operation, log_translation_change
from storage.crud.phrase import set_phrase_translation
from storage.migrate import _write_jsonl_atomic, phrase_to_release_records
from storage.models.schema import Phrase, PhraseTranslation
from storage.translation_helpers import LANGUAGE_NAMES, RELEASE_LANGUAGES

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

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
    """Load all phrases from data/release/phrases base.jsonl files, keyed by GUID."""
    release_phrases: Dict[str, Dict[str, Any]] = {}
    if not release_dir.exists():
        logger.warning(f"Phrase release directory not found: {release_dir}")
        return release_phrases

    for base_file in release_dir.rglob("base.jsonl"):
        subtype_from_dir = base_file.parent.name
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {base_file}:{line_num}: {e}")
                        continue
                    guid = data.get("guid")
                    if guid:
                        data.setdefault("phrase_subtype", subtype_from_dir)
                        release_phrases[guid] = data
        except Exception as e:
            logger.error(f"Error reading {base_file}: {e}")

    return release_phrases


def _find_release_file_for_phrase(release_dir: Path, guid: str) -> Optional[Path]:
    """Find the base.jsonl file containing a specific phrase GUID."""
    for base_file in release_dir.rglob("base.jsonl"):
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        if json.loads(line).get("guid") == guid:
                            return base_file
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return None


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
        additions=additions_list,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new phrases from release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.additions"))

    selected_guids = request.form.getlist("selected_guids")
    if not selected_guids:
        flash("No phrases selected for import", "warning")
        return redirect(url_for("sync_phrase_release.additions"))

    release_phrases = _load_release_phrases(_get_phrase_release_dir())
    imported = 0
    errors = 0
    for guid in selected_guids:
        release_data = release_phrases.get(guid)
        if not release_data:
            errors += 1
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
            imported += 1
        except Exception as e:
            logger.error(f"Error importing phrase {guid}: {e}")
            errors += 1

    if imported:
        try:
            g.db.commit()
            flash(f"Imported {imported} phrase(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
    if errors:
        flash(f"Errors: {errors}", "warning")
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
        removals=removals_list,
        release_dir=str(release_dir),
    )


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected phrases that are not in release."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.removals"))

    selected_ids = request.form.getlist("selected_ids")
    if not selected_ids:
        flash("No phrases selected for deletion", "warning")
        return redirect(url_for("sync_phrase_release.removals"))

    deleted = 0
    errors = 0
    for phrase_id_str in selected_ids:
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                errors += 1
                continue
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="phrase_delete",
                details={"guid": phrase.guid, "phrase_id": phrase.id},
            )
            g.db.delete(phrase)
            deleted += 1
        except Exception as e:
            logger.error(f"Error deleting phrase {phrase_id_str}: {e}")
            errors += 1

    if deleted:
        try:
            g.db.commit()
            flash(f"Deleted {deleted} phrase(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
    if errors:
        flash(f"Errors: {errors}", "warning")
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
        "sync_phrase_release/level.html", differences=differences, release_dir=str(release_dir)
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
        "sync_phrase_release/changes.html", changes=changes_list, release_dir=str(release_dir)
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
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for(redirect_endpoint))

    actions = {
        key[len("action_") :]: value
        for key, value in request.form.items()
        if key.startswith("action_")
    }
    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for(redirect_endpoint))

    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)
    attr = "difficulty_level" if field == "difficulty_level" else "label"

    updated_db = 0
    skipped = 0
    errors = 0
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for phrase_id_str, action in actions.items():
        if action == "skip":
            skipped += 1
            continue
        if action not in ("use_release", "use_db"):
            continue
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                errors += 1
                continue
            release_data = release_phrases.get(phrase.guid)
            if not release_data:
                errors += 1
                continue

            if action == "use_release":
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
                updated_db += 1
            else:  # use_db
                file_path = _find_release_file_for_phrase(release_dir, phrase.guid)
                if file_path:
                    release_updates.setdefault(file_path, {})[phrase.guid] = {
                        field: getattr(phrase, attr)
                    }
                else:
                    errors += 1
        except Exception as e:
            logger.error(f"Error updating phrase {phrase_id_str}: {e}")
            errors += 1

    if updated_db:
        try:
            g.db.commit()
            flash(f"Updated {updated_db} phrase(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
    if release_updates:
        try:
            _apply_release_field_updates(release_updates)
            flash("Updated release files", "success")
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
    if skipped:
        flash(f"Skipped {skipped}", "info")
    if errors:
        flash(f"Errors: {errors}", "warning")
    return redirect(url_for(redirect_endpoint))


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
        differences=differences,
        release_dir=str(release_dir),
    )


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected per-language translation changes."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_phrase_release.translations"))

    # action_{phrase_id}_{lang_code} = skip|use_release|use_db
    actions: Dict[str, Dict[str, str]] = {}
    for key, value in request.form.items():
        if not key.startswith("action_"):
            continue
        remainder = key[len("action_") :]
        underscore = remainder.find("_")
        if underscore == -1:
            continue
        actions.setdefault(remainder[:underscore], {})[remainder[underscore + 1 :]] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_phrase_release.translations"))

    release_dir = _get_phrase_release_dir()
    release_phrases = _load_release_phrases(release_dir)

    updated_db = 0
    skipped = 0
    errors = 0
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for phrase_id_str, lang_actions in actions.items():
        try:
            phrase = g.db.query(Phrase).filter(Phrase.id == int(phrase_id_str)).first()
            if not phrase:
                errors += 1
                continue
            release_data = release_phrases.get(phrase.guid)
            if not release_data:
                errors += 1
                continue
            release_translations = release_data.get("translations", {})

            for lang_code, action in lang_actions.items():
                if action == "use_release":
                    release_val = release_translations.get(lang_code, "")
                    if release_val:
                        set_phrase_translation(g.db, phrase, lang_code, release_val)
                        updated_db += 1
                    else:
                        skipped += 1
                elif action == "use_db":
                    existing = (
                        g.db.query(PhraseTranslation)
                        .filter(
                            PhraseTranslation.phrase_id == phrase.id,
                            PhraseTranslation.language_code == lang_code,
                        )
                        .first()
                    )
                    db_val = existing.translation if existing else ""
                    if db_val:
                        file_path = _find_release_file_for_phrase(release_dir, phrase.guid)
                        if file_path:
                            release_updates.setdefault(file_path, {}).setdefault(phrase.guid, {})[
                                lang_code
                            ] = db_val
                        else:
                            errors += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
        except Exception as e:
            logger.error(f"Error processing phrase {phrase_id_str}: {e}")
            errors += 1

    if updated_db:
        try:
            g.db.commit()
            flash(f"Updated {updated_db} translation(s) in database", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing DB changes: {e}", "error")
    if release_updates:
        try:
            _apply_release_translation_updates(release_updates)
            flash("Updated translations in release files", "success")
        except Exception as e:
            flash(f"Error updating release files: {e}", "error")
    if skipped:
        flash(f"Skipped {skipped} item(s)", "info")
    if errors:
        flash(f"Errors: {errors}", "warning")
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
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
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

    # Group the new/updated records by subtype, merged with existing base.jsonl.
    by_subtype: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    touched_subtypes = set()
    for phrase in db_phrases:
        base_record, _ = phrase_to_release_records(phrase)
        by_subtype[phrase.phrase_subtype][phrase.guid] = base_record
        touched_subtypes.add(phrase.phrase_subtype)

    # Pre-load existing records for touched subtypes so we don't drop siblings.
    for subtype in touched_subtypes:
        base_file = release_dir / subtype / "base.jsonl"
        if not base_file.exists():
            continue
        with open(base_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                guid = data.get("guid")
                if guid and guid not in by_subtype[subtype]:
                    by_subtype[subtype][guid] = data

    written = 0
    for subtype, guid_to_record in by_subtype.items():
        category_dir = release_dir / subtype
        category_dir.mkdir(parents=True, exist_ok=True)
        records = sorted(guid_to_record.values(), key=lambda r: r["guid"])
        _write_jsonl_atomic(category_dir / "base.jsonl", records)
        written += sum(1 for p in db_phrases if p.phrase_subtype == subtype)

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


def _apply_release_field_updates(updates: Dict[Path, Dict[str, Dict[str, Any]]]) -> None:
    """Apply top-level field updates (concept_label / difficulty_level) to JSONL."""
    for file_path, guid_updates in updates.items():
        if not file_path.exists():
            continue
        out: List[str] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    out.append(line)
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    out.append(line)
                    continue
                guid = data.get("guid")
                if guid in guid_updates:
                    data.update(guid_updates[guid])
                    out.append(json.dumps(data, ensure_ascii=False) + "\n")
                else:
                    out.append(line)
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(out)


def _apply_release_translation_updates(updates: Dict[Path, Dict[str, Dict[str, str]]]) -> None:
    """Apply per-language translation updates to release JSONL files."""
    for file_path, guid_updates in updates.items():
        if not file_path.exists():
            continue
        out: List[str] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    out.append(line)
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    out.append(line)
                    continue
                guid = data.get("guid")
                if guid in guid_updates:
                    data.setdefault("translations", {})
                    for lang_code, new_val in guid_updates[guid].items():
                        data["translations"][lang_code] = new_val
                    out.append(json.dumps(data, ensure_ascii=False) + "\n")
                else:
                    out.append(line)
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(out)
