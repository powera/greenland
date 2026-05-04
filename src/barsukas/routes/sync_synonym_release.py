#!/usr/bin/python3

"""Routes for syncing synonyms between per-language release files and the DB.

Synonyms live alongside inflected forms in the same per-language JSONL file
under a separate top-level array key, so both can be edited independently::

    {"guid": "N02_001",
     "forms":    [{"grammatical_form": "noun/es_singular", "text": "perro", ...}],
     "synonyms": [{"grammatical_form": "synonym",          "text": "can"},
                  {"grammatical_form": "synonym_regional", "text": "chucho"}]}

In the SQL DB, synonyms are stored in the same ``DerivativeForm`` table as
other forms, distinguished by ``grammatical_form`` membership in
``SYNONYM_GRAMMATICAL_FORMS``. We may revisit that grouping later, but for
now treating them as DerivativeForm rows keeps load/lookup paths uniform.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.routes.sync_release_helpers import (
    find_release_file_for_lemma_lang,
    load_release_array_for_lang,
    write_release_line_partial,
)
from storage.crud.operation_log import log_operation
from storage.models.schema import SYNONYM_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_synonym_release", __name__, url_prefix="/sync/synonyms")

DEFAULT_RELEASE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "release" / "lemmas"


def _get_release_dir() -> Path:
    return DEFAULT_RELEASE_DIR


# =============================================================================
# JSONL format helpers
# =============================================================================


def _db_form_to_dict(form: DerivativeForm) -> Dict[str, Any]:
    """Convert a DB synonym DerivativeForm to the release file dict format."""
    d: Dict[str, Any] = {
        "grammatical_form": form.grammatical_form,
        "text": form.derivative_form_text,
    }
    if form.ipa_pronunciation:
        d["ipa"] = form.ipa_pronunciation
    if form.phonetic_pronunciation:
        d["phonetic"] = form.phonetic_pronunciation
    return d


def _form_key(grammatical_form: str, text: str) -> str:
    return f"{grammatical_form}|{text}"


# =============================================================================
# Loading
# =============================================================================


def _load_release_synonyms_for_lang(
    release_dir: Path, lang_code: str
) -> Dict[str, List[Dict[str, Any]]]:
    """Load synonym entries for a language from release JSONL files."""
    return load_release_array_for_lang(release_dir, lang_code, "synonyms")


def _get_languages_with_release_files(release_dir: Path) -> Set[str]:
    """Find which languages have release files in the release directory."""
    languages: Set[str] = set()
    if not release_dir.exists():
        return languages
    for jsonl_file in release_dir.rglob("*.jsonl"):
        stem = jsonl_file.stem
        if stem == "base":
            continue
        if len(stem) in (2, 3) and stem.isalpha():
            languages.add(stem)
    return languages


def _load_db_synonyms_for_lang(db_session: Any, lang_code: str) -> Dict[str, List[DerivativeForm]]:
    """Load synonym DerivativeForm rows for a language, keyed by lemma GUID."""
    forms_by_guid: Dict[str, List[DerivativeForm]] = {}
    rows = (
        db_session.query(DerivativeForm, Lemma.guid)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            DerivativeForm.language_code == lang_code,
            Lemma.guid.isnot(None),
            DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)),
        )
        .all()
    )
    for form, guid in rows:
        forms_by_guid.setdefault(guid, []).append(form)
    return forms_by_guid


# =============================================================================
# Diff helpers
# =============================================================================


def _has_form_differences(
    release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> bool:
    release_keys = {
        _form_key(f.get("grammatical_form", ""), f.get("text", "")) for f in release_forms
    }
    db_keys = {_form_key(f.grammatical_form, f.derivative_form_text) for f in db_forms}

    if release_keys != db_keys:
        return True

    release_by_key = {
        _form_key(f.get("grammatical_form", ""), f.get("text", "")): f for f in release_forms
    }
    db_by_key = {_form_key(f.grammatical_form, f.derivative_form_text): f for f in db_forms}

    for key in release_keys:
        rf = release_by_key[key]
        df = db_by_key[key]
        if (rf.get("ipa") or "") != (df.ipa_pronunciation or ""):
            return True
        if (rf.get("phonetic") or "") != (df.phonetic_pronunciation or ""):
            return True
    return False


def _compute_form_diffs(
    release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> List[Dict[str, Any]]:
    diffs: List[Dict[str, Any]] = []

    release_by_key = {
        _form_key(f.get("grammatical_form", ""), f.get("text", "")): f for f in release_forms
    }
    db_by_key = {_form_key(f.grammatical_form, f.derivative_form_text): f for f in db_forms}

    release_keys = set(release_by_key.keys())
    db_keys = set(db_by_key.keys())

    for key in sorted(release_keys - db_keys):
        rf = release_by_key[key]
        diffs.append(
            {
                "type": "release_only",
                "grammatical_form": rf.get("grammatical_form", ""),
                "release_text": rf.get("text", ""),
                "db_text": "",
                "release_ipa": rf.get("ipa", ""),
                "db_ipa": "",
                "release_phonetic": rf.get("phonetic", ""),
                "db_phonetic": "",
            }
        )

    for key in sorted(db_keys - release_keys):
        df = db_by_key[key]
        diffs.append(
            {
                "type": "db_only",
                "grammatical_form": df.grammatical_form,
                "release_text": "",
                "db_text": df.derivative_form_text,
                "release_ipa": "",
                "db_ipa": df.ipa_pronunciation or "",
                "release_phonetic": "",
                "db_phonetic": df.phonetic_pronunciation or "",
            }
        )

    for key in sorted(release_keys & db_keys):
        rf = release_by_key[key]
        df = db_by_key[key]
        r_ipa = rf.get("ipa") or ""
        d_ipa = df.ipa_pronunciation or ""
        r_phonetic = rf.get("phonetic") or ""
        d_phonetic = df.phonetic_pronunciation or ""
        if r_ipa != d_ipa or r_phonetic != d_phonetic:
            diffs.append(
                {
                    "type": "field_diff",
                    "grammatical_form": rf.get("grammatical_form", ""),
                    "release_text": rf.get("text", ""),
                    "db_text": df.derivative_form_text,
                    "release_ipa": r_ipa,
                    "db_ipa": d_ipa,
                    "release_phonetic": r_phonetic,
                    "db_phonetic": d_phonetic,
                }
            )
    return diffs


def _get_lemma_info_by_guids(db_session: Any, guids: Set[str]) -> Dict[str, Dict[str, Any]]:
    info: Dict[str, Dict[str, Any]] = {}
    if not guids:
        return info
    batch_size = 500
    guid_list = list(guids)
    for i in range(0, len(guid_list), batch_size):
        batch = guid_list[i : i + batch_size]
        lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch)).all()
        for lemma in lemmas:
            info[lemma.guid] = {
                "lemma_id": lemma.id,
                "lemma_text": lemma.lemma_text,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype or "",
            }
    return info


def _build_guid_to_lemma_id(db_session: Any) -> Dict[str, int]:
    return {
        guid: lid
        for lid, guid in db_session.query(Lemma.id, Lemma.guid).filter(Lemma.guid.isnot(None)).all()
    }


# =============================================================================
# Index
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Per-language synonym sync hub."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        return render_template(
            "sync_synonym_release/index.html",
            release_dir=str(release_dir),
            error="Release directory not found",
            lang_counts=None,
        )

    release_languages = _get_languages_with_release_files(release_dir)

    db_lang_rows = (
        g.db.query(DerivativeForm.language_code)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            Lemma.guid.isnot(None),
            DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)),
        )
        .distinct()
        .all()
    )
    db_languages = {row[0] for row in db_lang_rows}

    all_languages = sorted(
        release_languages | db_languages,
        key=lambda lc: (LANGUAGE_HIERARCHY.index(lc) if lc in LANGUAGE_HIERARCHY else 999),
    )

    lang_counts: List[Dict[str, Any]] = []
    for lang_code in all_languages:
        release_forms = _load_release_synonyms_for_lang(release_dir, lang_code)
        db_forms = _load_db_synonyms_for_lang(g.db, lang_code)

        release_guids = set(release_forms.keys())
        db_guids = set(db_forms.keys())

        additions = len(release_guids - db_guids)
        removals = len(db_guids - release_guids)

        common_guids = release_guids & db_guids
        changes = 0
        for guid in common_guids:
            if _has_form_differences(release_forms[guid], db_forms[guid]):
                changes += 1

        total_diffs = additions + removals + changes

        lang_counts.append(
            {
                "lang_code": lang_code,
                "lang_name": LANGUAGE_NAMES.get(lang_code, lang_code),
                "release_count": len(release_guids),
                "db_count": len(db_guids),
                "additions": additions,
                "removals": removals,
                "changes": changes,
                "total_diffs": total_diffs,
            }
        )

    return render_template(
        "sync_synonym_release/index.html",
        release_dir=str(release_dir),
        lang_counts=lang_counts,
    )


# =============================================================================
# Language detail
# =============================================================================


@bp.route("/<lang_code>")
def language_detail(lang_code: str) -> ResponseReturnValue:
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_synonym_release.index"))

    release_forms = _load_release_synonyms_for_lang(release_dir, lang_code)
    db_forms = _load_db_synonyms_for_lang(g.db, lang_code)

    release_guids = set(release_forms.keys())
    db_guids = set(db_forms.keys())

    all_guids = release_guids | db_guids
    guid_info = _get_lemma_info_by_guids(g.db, all_guids)

    additions: List[Dict[str, Any]] = []
    for guid in sorted(release_guids - db_guids):
        info = guid_info.get(guid, {})
        additions.append(
            {
                "guid": guid,
                "lemma_text": info.get("lemma_text", ""),
                "pos_type": info.get("pos_type", ""),
                "pos_subtype": info.get("pos_subtype", ""),
                "form_count": len(release_forms[guid]),
                "forms_preview": ", ".join(f.get("text", "") for f in release_forms[guid][:5]),
            }
        )

    removals: List[Dict[str, Any]] = []
    for guid in sorted(db_guids - release_guids):
        info = guid_info.get(guid, {})
        removals.append(
            {
                "guid": guid,
                "lemma_text": info.get("lemma_text", ""),
                "lemma_id": info.get("lemma_id", 0),
                "pos_type": info.get("pos_type", ""),
                "pos_subtype": info.get("pos_subtype", ""),
                "form_count": len(db_forms[guid]),
                "forms_preview": ", ".join(f.derivative_form_text for f in db_forms[guid][:5]),
            }
        )

    changes: List[Dict[str, Any]] = []
    for guid in sorted(release_guids & db_guids):
        form_diffs = _compute_form_diffs(release_forms[guid], db_forms[guid])
        if form_diffs:
            info = guid_info.get(guid, {})
            changes.append(
                {
                    "guid": guid,
                    "lemma_text": info.get("lemma_text", ""),
                    "lemma_id": info.get("lemma_id", 0),
                    "pos_type": info.get("pos_type", ""),
                    "pos_subtype": info.get("pos_subtype", ""),
                    "form_diffs": form_diffs,
                    "diff_count": len(form_diffs),
                }
            )

    return render_template(
        "sync_synonym_release/language_detail.html",
        lang_code=lang_code,
        lang_name=LANGUAGE_NAMES.get(lang_code, lang_code),
        additions=additions,
        removals=removals,
        changes=changes,
        db_count=len(db_guids),
        release_dir=str(release_dir),
    )


# =============================================================================
# Apply additions
# =============================================================================


@bp.route("/<lang_code>/additions/apply", methods=["POST"])
def apply_additions(lang_code: str) -> ResponseReturnValue:
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    selected_guids = request.form.getlist("selected_guids")
    if not selected_guids:
        flash("No lemmas selected for import", "warning")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    release_forms = _load_release_synonyms_for_lang(release_dir, lang_code)
    guid_to_lemma_id = _build_guid_to_lemma_id(g.db)

    imported_count = 0
    error_count = 0

    for guid in selected_guids:
        forms = release_forms.get(guid)
        if not forms:
            error_count += 1
            continue
        lemma_id = guid_to_lemma_id.get(guid)
        if not lemma_id:
            error_count += 1
            continue
        try:
            for form_data in forms:
                gform = form_data.get("grammatical_form", "")
                if gform not in SYNONYM_GRAMMATICAL_FORMS:
                    logger.warning(
                        f"Skipping non-synonym grammatical_form {gform!r} in synonyms array "
                        f"for {guid} lang={lang_code}"
                    )
                    continue
                df = DerivativeForm(
                    lemma_id=lemma_id,
                    language_code=lang_code,
                    grammatical_form=gform,
                    derivative_form_text=form_data.get("text", ""),
                    is_base_form=False,
                    ipa_pronunciation=form_data.get("ipa") or None,
                    phonetic_pronunciation=form_data.get("phonetic") or None,
                    verified=False,
                )
                g.db.add(df)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="synonym_import",
                lemma_id=lemma_id,
                details={
                    "guid": guid,
                    "language_code": lang_code,
                    "form_count": len(forms),
                },
            )
            imported_count += 1
        except Exception as e:
            logger.error(f"Error importing synonyms for {guid} lang={lang_code}: {e}")
            error_count += 1

    if imported_count > 0:
        try:
            g.db.commit()
            flash(f"Imported synonyms for {imported_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))


# =============================================================================
# Apply removals
# =============================================================================


@bp.route("/<lang_code>/removals/apply", methods=["POST"])
def apply_removals(lang_code: str) -> ResponseReturnValue:
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            guid = key[len("action_") :]
            actions[guid] = value

    if not actions:
        flash("No actions selected", "warning")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    db_forms = _load_db_synonyms_for_lang(g.db, lang_code)

    exported_count = 0
    deleted_count = 0
    skipped_count = 0
    error_count = 0

    for guid, action in actions.items():
        if action == "skip":
            skipped_count += 1
            continue

        forms = db_forms.get(guid)
        if not forms:
            error_count += 1
            continue

        if action == "export":
            try:
                file_path = find_release_file_for_lemma_lang(release_dir, guid, lang_code)
                if not file_path:
                    error_count += 1
                    continue
                form_dicts = [_db_form_to_dict(f) for f in forms]
                write_release_line_partial(file_path, guid, "synonyms", form_dicts)
                exported_count += 1
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="synonym_export",
                    lemma_id=forms[0].lemma_id,
                    details={
                        "guid": guid,
                        "language_code": lang_code,
                        "form_count": len(forms),
                    },
                )
            except Exception as e:
                logger.error(f"Error exporting synonyms for {guid} lang={lang_code}: {e}")
                error_count += 1

        elif action == "delete":
            try:
                lemma_id = forms[0].lemma_id
                for form in forms:
                    g.db.delete(form)
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="synonym_delete",
                    lemma_id=lemma_id,
                    details={
                        "guid": guid,
                        "language_code": lang_code,
                        "form_count": len(forms),
                    },
                )
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting synonyms for {guid} lang={lang_code}: {e}")
                error_count += 1

    if deleted_count > 0 or exported_count > 0:
        try:
            g.db.commit()
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if exported_count > 0:
        flash(f"Exported synonyms for {exported_count} lemma(s) to release files", "success")
    if deleted_count > 0:
        flash(f"Deleted synonyms for {deleted_count} lemma(s) from database", "success")
    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")
    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))


# =============================================================================
# Apply changes
# =============================================================================


@bp.route("/<lang_code>/changes/apply", methods=["POST"])
def apply_changes(lang_code: str) -> ResponseReturnValue:
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            guid = key[len("action_") :]
            actions[guid] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    release_forms = _load_release_synonyms_for_lang(release_dir, lang_code)
    db_forms = _load_db_synonyms_for_lang(g.db, lang_code)
    guid_to_lemma_id = _build_guid_to_lemma_id(g.db)

    updated_db_count = 0
    updated_release_count = 0
    skipped_count = 0
    error_count = 0

    for guid, action in actions.items():
        if action == "skip":
            skipped_count += 1
            continue

        lemma_id = guid_to_lemma_id.get(guid)
        if not lemma_id:
            error_count += 1
            continue

        try:
            if action == "use_release":
                r_forms = release_forms.get(guid, [])
                d_forms = db_forms.get(guid, [])

                for df in d_forms:
                    g.db.delete(df)

                for form_data in r_forms:
                    gform = form_data.get("grammatical_form", "")
                    if gform not in SYNONYM_GRAMMATICAL_FORMS:
                        continue
                    df = DerivativeForm(
                        lemma_id=lemma_id,
                        language_code=lang_code,
                        grammatical_form=gform,
                        derivative_form_text=form_data.get("text", ""),
                        is_base_form=False,
                        ipa_pronunciation=form_data.get("ipa") or None,
                        phonetic_pronunciation=form_data.get("phonetic") or None,
                        verified=False,
                    )
                    g.db.add(df)

                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="synonym_sync_use_release",
                    lemma_id=lemma_id,
                    details={
                        "guid": guid,
                        "language_code": lang_code,
                        "old_count": len(d_forms),
                        "new_count": len(r_forms),
                    },
                )
                updated_db_count += 1

            elif action == "use_db":
                d_forms = db_forms.get(guid, [])
                form_dicts = [_db_form_to_dict(f) for f in d_forms]
                file_path = find_release_file_for_lemma_lang(release_dir, guid, lang_code)
                if file_path:
                    write_release_line_partial(file_path, guid, "synonyms", form_dicts)
                    log_operation(
                        session=g.db,
                        source="sync-release",
                        operation_type="synonym_sync_use_db",
                        lemma_id=lemma_id,
                        details={
                            "guid": guid,
                            "language_code": lang_code,
                            "form_count": len(d_forms),
                        },
                    )
                    updated_release_count += 1
                else:
                    error_count += 1

        except Exception as e:
            logger.error(f"Error syncing synonyms for {guid} lang={lang_code}: {e}")
            error_count += 1

    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(f"Updated DB synonyms for {updated_db_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing DB changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if updated_release_count > 0:
        flash(f"Updated release files for {updated_release_count} lemma(s)", "success")
    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")
    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))


# =============================================================================
# Export all DB -> Release
# =============================================================================


@bp.route("/<lang_code>/export_all", methods=["POST"])
def export_all(lang_code: str) -> ResponseReturnValue:
    """Export every DB synonym for a language to release files."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    db_forms = _load_db_synonyms_for_lang(g.db, lang_code)

    if not db_forms:
        flash(f"No {LANGUAGE_NAMES.get(lang_code, lang_code)} synonyms in database", "warning")
        return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))

    exported_count = 0
    error_count = 0

    for guid, forms in sorted(db_forms.items()):
        try:
            file_path = find_release_file_for_lemma_lang(release_dir, guid, lang_code)
            if not file_path:
                error_count += 1
                continue
            form_dicts = [_db_form_to_dict(f) for f in forms]
            write_release_line_partial(file_path, guid, "synonyms", form_dicts)
            exported_count += 1
        except Exception as e:
            logger.error(f"Error exporting synonyms for {guid} lang={lang_code}: {e}")
            error_count += 1

    if exported_count > 0:
        log_operation(
            session=g.db,
            source="sync-release",
            operation_type="synonym_export_all",
            details={"language_code": lang_code, "guid_count": exported_count},
        )
        try:
            g.db.commit()
        except Exception as e:
            g.db.rollback()
            logger.error(f"Commit error logging export_all: {e}")

        flash(
            f"Exported {lang_code} synonyms for {exported_count} lemma(s) to release files",
            "success",
        )

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_synonym_release.language_detail", lang_code=lang_code))
