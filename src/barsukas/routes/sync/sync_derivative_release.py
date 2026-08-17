#!/usr/bin/python3

"""Routes for syncing derivative forms between per-language release files and SQLite database.

Derivative forms are stored in per-language JSONL files alongside the base.jsonl:
    data/release/lemmas/{pos_type}/{pos_subtype}/{lang_code}.jsonl

Each line in a language file contains derivative forms for one lemma:
    {"guid": "N02_001", "forms": [
        {"grammatical_form": "noun/es_singular", "text": "perro", "is_base_form": true,
         "ipa": "/ˈpe.ro/", "phonetic": null},
        {"grammatical_form": "noun/es_plural", "text": "perros", "is_base_form": false}
    ]}
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.routes.sync import sync_release_helpers as helpers
from barsukas.routes.sync.sync_release_helpers import (
    find_release_file_for_lemma_lang,
    load_release_array_for_lang,
    write_release_line_partial,
)
from storage.crud.operation_log import log_operation
from storage.models.schema import NON_INFLECTION_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_derivative_release", __name__, url_prefix="/sync/derivatives")

# Default path to data/release/lemmas (derivative files live alongside base.jsonl)
DEFAULT_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "lemmas"
)


def _get_release_dir() -> Path:
    """Get the path to the data/release/lemmas directory."""
    return DEFAULT_RELEASE_DIR


# =============================================================================
# JSONL format helpers
# =============================================================================


def _forms_match(release_form: Dict[str, Any], db_form: DerivativeForm) -> bool:
    """Check if a release form dict matches a DB DerivativeForm on key fields."""
    return bool(
        release_form.get("grammatical_form") == db_form.grammatical_form
        and release_form.get("text") == db_form.derivative_form_text
    )


# =============================================================================
# Loading release data
# =============================================================================


def _load_release_derivatives_for_lang(
    release_dir: Path, lang_code: str
) -> Dict[str, List[Dict[str, Any]]]:
    """Load inflectional derivative forms for a language from release JSONL files.

    Reads only the top-level ``forms`` array; synonyms live under a separate
    ``synonyms`` key and are handled by ``sync_synonym_release``.

    Returns:
        Dictionary mapping GUID to list of derivative form dicts.
    """
    return load_release_array_for_lang(release_dir, lang_code, "forms")


def _find_release_file_for_lemma_lang(
    release_dir: Path, guid: str, lang_code: str
) -> Optional[Path]:
    """Find the {lang}.jsonl file that contains (or should contain) ``guid``."""
    return find_release_file_for_lemma_lang(release_dir, guid, lang_code)


# =============================================================================
# DB loading helpers
# =============================================================================


def _load_db_derivatives_for_lang(
    db_session: Any, lang_code: str
) -> Dict[str, List[DerivativeForm]]:
    """Load all derivative forms for a language from the DB, keyed by lemma GUID.

    Returns:
        Dictionary mapping GUID to list of DerivativeForm objects.
    """
    forms_by_guid: Dict[str, List[DerivativeForm]] = {}

    # Join DerivativeForm with Lemma to get GUIDs. Synonym-class rows are
    # managed by the parallel /sync/synonyms route, so exclude them here.
    rows = (
        db_session.query(DerivativeForm, Lemma.guid)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(
            DerivativeForm.language_code == lang_code,
            Lemma.guid.isnot(None),
            DerivativeForm.grammatical_form.notin_(tuple(NON_INFLECTION_GRAMMATICAL_FORMS)),
        )
        .all()
    )

    for form, guid in rows:
        if guid not in forms_by_guid:
            forms_by_guid[guid] = []
        forms_by_guid[guid].append(form)

    return forms_by_guid


# =============================================================================
# Index (Hub)
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display derivative form sync hub with per-language counts."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        return render_template(
            "sync_derivative_release/index.html",
            release_dir=str(release_dir),
            error="Release directory not found",
            lang_counts=None,
        )

    # Find languages that have release files
    release_languages = helpers.languages_with_release_files(release_dir)

    # Find languages that have DB derivative forms
    db_lang_rows = (
        g.db.query(DerivativeForm.language_code)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(Lemma.guid.isnot(None))
        .distinct()
        .all()
    )
    db_languages = {row[0] for row in db_lang_rows}

    all_languages = sorted(
        release_languages | db_languages,
        key=lambda lc: (LANGUAGE_HIERARCHY.index(lc) if lc in LANGUAGE_HIERARCHY else 999),
    )

    # For each language, compute summary counts
    lang_counts: List[Dict[str, Any]] = []
    for lang_code in all_languages:
        release_forms = _load_release_derivatives_for_lang(release_dir, lang_code)
        db_forms = _load_db_derivatives_for_lang(g.db, lang_code)

        release_guids = set(release_forms.keys())
        db_guids = set(db_forms.keys())

        additions = len(release_guids - db_guids)
        removals = len(db_guids - release_guids)

        # Count changes among common GUIDs
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
        "sync_derivative_release/index.html",
        release_dir=str(release_dir),
        lang_counts=lang_counts,
    )


def _has_form_differences(
    release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> bool:
    """Check if there are any differences between release and DB forms for a GUID."""
    release_keys = {
        helpers.form_key(f.get("grammatical_form", ""), f.get("text", "")) for f in release_forms
    }
    db_keys = {helpers.form_key(f.grammatical_form, f.derivative_form_text) for f in db_forms}

    if release_keys != db_keys:
        return True

    # Keys match; check pronunciation/is_base_form differences
    release_by_key = {
        helpers.form_key(f.get("grammatical_form", ""), f.get("text", "")): f for f in release_forms
    }
    db_by_key = {helpers.form_key(f.grammatical_form, f.derivative_form_text): f for f in db_forms}

    for key in release_keys:
        rf = release_by_key[key]
        df = db_by_key[key]

        if rf.get("is_base_form", False) != df.is_base_form:
            return True
        if (rf.get("ipa") or "") != (df.ipa_pronunciation or ""):
            return True
        if (rf.get("phonetic") or "") != (df.phonetic_pronunciation or ""):
            return True

    return False


# =============================================================================
# Language detail view (per-language additions, removals, changes)
# =============================================================================


def _compute_form_diffs(
    release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> List[Dict[str, Any]]:
    """Compute detailed per-form differences between release and DB.

    Returns a list of diff dicts, each describing one form difference.
    """
    diffs: List[Dict[str, Any]] = []

    release_by_key = {
        helpers.form_key(f.get("grammatical_form", ""), f.get("text", "")): f for f in release_forms
    }
    db_by_key = {helpers.form_key(f.grammatical_form, f.derivative_form_text): f for f in db_forms}

    release_keys = set(release_by_key.keys())
    db_keys = set(db_by_key.keys())

    # Forms only in release
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
                "release_is_base": rf.get("is_base_form", False),
                "db_is_base": False,
            }
        )

    # Forms only in DB
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
                "release_is_base": False,
                "db_is_base": df.is_base_form,
            }
        )

    # Forms in both - check for field differences
    for key in sorted(release_keys & db_keys):
        rf = release_by_key[key]
        df = db_by_key[key]

        r_ipa = rf.get("ipa") or ""
        d_ipa = df.ipa_pronunciation or ""
        r_phonetic = rf.get("phonetic") or ""
        d_phonetic = df.phonetic_pronunciation or ""
        r_base = rf.get("is_base_form", False)
        d_base = df.is_base_form

        if r_ipa != d_ipa or r_phonetic != d_phonetic or r_base != d_base:
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
                    "release_is_base": r_base,
                    "db_is_base": d_base,
                }
            )

    return diffs


@bp.route("/<lang_code>")
def language_detail(lang_code: str) -> ResponseReturnValue:
    """Show detailed sync status for a single language."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_derivative_release.index"))

    release_forms = _load_release_derivatives_for_lang(release_dir, lang_code)
    db_forms = _load_db_derivatives_for_lang(g.db, lang_code)

    release_guids = set(release_forms.keys())
    db_guids = set(db_forms.keys())

    # Build GUID -> lemma info lookup for display
    all_guids = release_guids | db_guids
    guid_info = helpers.lemma_info_by_guids(g.db, all_guids)

    # Additions: in release but not in DB
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

    # Removals: in DB but not in release
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

    # Changes: in both but different
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
        "sync_derivative_release/language_detail.html",
        lang_code=lang_code,
        lang_name=LANGUAGE_NAMES.get(lang_code, lang_code),
        additions=additions,
        removals=removals,
        changes=changes,
        db_count=len(db_guids),
        release_dir=str(release_dir),
    )


# =============================================================================
# Apply additions (import release -> DB)
# =============================================================================


@bp.route("/<lang_code>/additions/apply", methods=["POST"])
def apply_additions(lang_code: str) -> ResponseReturnValue:
    """Import selected derivative forms from release files into DB."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    selected_guids = request.form.getlist("selected_guids")
    if not selected_guids:
        flash("No lemmas selected for import", "warning")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    release_forms = _load_release_derivatives_for_lang(release_dir, lang_code)

    # Build GUID -> lemma_id lookup
    guid_to_lemma_id = helpers.guid_to_lemma_id(g.db)

    imported_count = 0
    error_count = 0

    for guid in selected_guids:
        forms = release_forms.get(guid)
        if not forms:
            logger.warning(f"No release forms found for GUID {guid} lang={lang_code}")
            error_count += 1
            continue

        lemma_id = guid_to_lemma_id.get(guid)
        if not lemma_id:
            logger.warning(f"Lemma not found in DB for GUID {guid}")
            error_count += 1
            continue

        try:
            for form_data in forms:
                df = DerivativeForm(
                    lemma_id=lemma_id,
                    language_code=lang_code,
                    grammatical_form=form_data.get("grammatical_form", ""),
                    derivative_form_text=form_data.get("text", ""),
                    is_base_form=form_data.get("is_base_form", False),
                    ipa_pronunciation=form_data.get("ipa") or None,
                    phonetic_pronunciation=form_data.get("phonetic") or None,
                    verified=False,
                )
                g.db.add(df)

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="derivative_import",
                lemma_id=lemma_id,
                details={
                    "guid": guid,
                    "language_code": lang_code,
                    "form_count": len(forms),
                },
            )
            imported_count += 1

        except Exception as e:
            logger.error(f"Error importing derivative forms for {guid} lang={lang_code}: {e}")
            error_count += 1

    if imported_count > 0:
        try:
            g.db.commit()
            flash(f"Imported derivative forms for {imported_count} lemma(s)", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))


# =============================================================================
# Apply removals (export DB -> release or delete from DB)
# =============================================================================


@bp.route("/<lang_code>/removals/apply", methods=["POST"])
def apply_removals(lang_code: str) -> ResponseReturnValue:
    """Handle derivative forms in DB but not in release: export to release or delete."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            guid = key[len("action_") :]
            actions[guid] = value

    if not actions:
        flash("No actions selected", "warning")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    db_forms = _load_db_derivatives_for_lang(g.db, lang_code)

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
            # Export DB forms to release file
            try:
                file_path = _find_release_file_for_lemma_lang(release_dir, guid, lang_code)
                if not file_path:
                    logger.warning(f"Could not resolve release file for {guid} lang={lang_code}")
                    error_count += 1
                    continue

                form_dicts = [
                    helpers.db_form_to_dict(include_base_form=True, form=f) for f in forms
                ]
                _append_or_update_release_line(file_path, guid, form_dicts)
                exported_count += 1

                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="derivative_export",
                    lemma_id=forms[0].lemma_id,
                    details={
                        "guid": guid,
                        "language_code": lang_code,
                        "form_count": len(forms),
                    },
                )

            except Exception as e:
                logger.error(f"Error exporting derivatives for {guid} lang={lang_code}: {e}")
                error_count += 1

        elif action == "delete":
            try:
                lemma_id = forms[0].lemma_id
                for form in forms:
                    g.db.delete(form)

                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="derivative_delete",
                    lemma_id=lemma_id,
                    details={
                        "guid": guid,
                        "language_code": lang_code,
                        "form_count": len(forms),
                    },
                )
                deleted_count += 1

            except Exception as e:
                logger.error(f"Error deleting derivatives for {guid} lang={lang_code}: {e}")
                error_count += 1

    if deleted_count > 0 or exported_count > 0:
        try:
            g.db.commit()
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if exported_count > 0:
        flash(
            f"Exported derivative forms for {exported_count} lemma(s) to release files", "success"
        )
    if deleted_count > 0:
        flash(f"Deleted derivative forms for {deleted_count} lemma(s) from database", "success")
    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")
    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))


# =============================================================================
# Apply changes (bidirectional sync of form differences)
# =============================================================================


@bp.route("/<lang_code>/changes/apply", methods=["POST"])
def apply_changes(lang_code: str) -> ResponseReturnValue:
    """Apply selected form changes (use_release or use_db) for a language."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    # Parse form actions: action_{guid} = use_release | use_db | skip
    # Each GUID gets a whole-lemma action (replace all forms for this GUID+lang)
    actions: Dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("action_"):
            guid = key[len("action_") :]
            actions[guid] = value

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    release_dir = _get_release_dir()
    release_forms = _load_release_derivatives_for_lang(release_dir, lang_code)
    db_forms = _load_db_derivatives_for_lang(g.db, lang_code)
    guid_to_lemma_id = helpers.guid_to_lemma_id(g.db)

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
            logger.warning(f"Lemma not found for GUID: {guid}")
            error_count += 1
            continue

        try:
            if action == "use_release":
                # Replace DB forms with release forms
                r_forms = release_forms.get(guid, [])
                d_forms = db_forms.get(guid, [])

                # Delete existing DB forms for this lemma+lang
                for df in d_forms:
                    g.db.delete(df)

                # Add release forms
                for form_data in r_forms:
                    df = DerivativeForm(
                        lemma_id=lemma_id,
                        language_code=lang_code,
                        grammatical_form=form_data.get("grammatical_form", ""),
                        derivative_form_text=form_data.get("text", ""),
                        is_base_form=form_data.get("is_base_form", False),
                        ipa_pronunciation=form_data.get("ipa") or None,
                        phonetic_pronunciation=form_data.get("phonetic") or None,
                        verified=False,
                    )
                    g.db.add(df)

                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type="derivative_sync_use_release",
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
                # Update release file with DB forms
                d_forms = db_forms.get(guid, [])
                form_dicts = [
                    helpers.db_form_to_dict(include_base_form=True, form=f) for f in d_forms
                ]

                file_path = _find_release_file_for_lemma_lang(release_dir, guid, lang_code)
                if file_path:
                    _append_or_update_release_line(file_path, guid, form_dicts)

                    log_operation(
                        session=g.db,
                        source="sync-release",
                        operation_type="derivative_sync_use_db",
                        lemma_id=lemma_id,
                        details={
                            "guid": guid,
                            "language_code": lang_code,
                            "form_count": len(d_forms),
                        },
                    )
                    updated_release_count += 1
                else:
                    logger.warning(f"Could not find release file for GUID: {guid}")
                    error_count += 1

        except Exception as e:
            logger.error(f"Error syncing derivatives for {guid} lang={lang_code}: {e}")
            error_count += 1

    if updated_db_count > 0:
        try:
            g.db.commit()
            flash(
                f"Updated DB derivative forms for {updated_db_count} lemma(s)",
                "success",
            )
        except Exception as e:
            g.db.rollback()
            flash(f"Error committing DB changes: {e}", "error")
            logger.error(f"Commit error: {e}")

    if updated_release_count > 0:
        flash(
            f"Updated release files for {updated_release_count} lemma(s)",
            "success",
        )

    if skipped_count > 0:
        flash(f"Skipped {skipped_count} lemma(s)", "info")

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))


# =============================================================================
# Export all DB -> Release
# =============================================================================


@bp.route("/<lang_code>/export_all", methods=["POST"])
def export_all(lang_code: str) -> ResponseReturnValue:
    """Export all DB derivative forms for a language to release files.

    Writes every GUID that has derivative forms in the DB for this language
    into the appropriate {lang_code}.jsonl files, creating or updating as needed.
    """
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    db_forms = _load_db_derivatives_for_lang(g.db, lang_code)

    if not db_forms:
        flash(
            f"No {LANGUAGE_NAMES.get(lang_code, lang_code)} derivative forms in database", "warning"
        )
        return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))

    exported_count = 0
    error_count = 0

    for guid, forms in sorted(db_forms.items()):
        try:
            file_path = _find_release_file_for_lemma_lang(release_dir, guid, lang_code)
            if not file_path:
                logger.warning(f"Could not resolve release file for {guid} lang={lang_code}")
                error_count += 1
                continue

            form_dicts = [helpers.db_form_to_dict(include_base_form=True, form=f) for f in forms]
            _append_or_update_release_line(file_path, guid, form_dicts)
            exported_count += 1

        except Exception as e:
            logger.error(f"Error exporting derivatives for {guid} lang={lang_code}: {e}")
            error_count += 1

    if exported_count > 0:
        log_operation(
            session=g.db,
            source="sync-release",
            operation_type="derivative_export_all",
            details={
                "language_code": lang_code,
                "guid_count": exported_count,
            },
        )
        try:
            g.db.commit()
        except Exception as e:
            g.db.rollback()
            logger.error(f"Commit error logging export_all: {e}")

        flash(
            f"Exported {lang_code} derivative forms for {exported_count} lemma(s) to release files",
            "success",
        )

    if error_count > 0:
        flash(f"Errors: {error_count}", "warning")

    return redirect(url_for("sync_derivative_release.language_detail", lang_code=lang_code))


# =============================================================================
# Release file write helpers
# =============================================================================


def _append_or_update_release_line(file_path: Path, guid: str, forms: List[Dict[str, Any]]) -> None:
    """Write or update a GUID's ``forms`` array in a release JSONL file.

    Preserves the ``synonyms`` array (if present) on the same line.
    """
    write_release_line_partial(file_path, guid, "forms", forms)
