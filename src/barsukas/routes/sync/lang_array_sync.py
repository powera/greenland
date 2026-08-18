#!/usr/bin/python3

"""Sync engine for the per-language form arrays in ``{lang}.jsonl``.

Derivative forms and synonyms are the same sync with two knobs. Both live in a
top-level array on a lemma's per-language release line::

    {"guid": "N02_001", "forms": [...], "synonyms": [...]}

and both map to ``DerivativeForm`` rows, partitioned by whether the
grammatical form is in ``NON_INFLECTION_GRAMMATICAL_FORMS``. The knobs are
:attr:`LangArraySpec.array_key` and :attr:`LangArraySpec.has_base_form` - an
inflection records whether it is the base form, a synonym has no such notion.

Everything else - the per-language hub, the detail view, and the additions,
removals, changes and export-all applies - was duplicated line for line
between the two blueprints before this module existed.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response as WerkzeugResponse

from barsukas.routes.sync import sync_release_helpers as helpers
from barsukas.routes.sync.actions import SKIP, USE_DB, USE_RELEASE, SyncOutcome, is_readonly
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, paginate
from storage.crud.operation_log import log_operation
from storage.models.schema import NON_INFLECTION_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.translation_helpers import LANGUAGE_HIERARCHY, LANGUAGE_NAMES

logger = logging.getLogger(__name__)

REPOSITORY_ROOT = Path(__file__).parent.parent.parent.parent.parent
DEFAULT_RELEASE_DIR = REPOSITORY_ROOT / "data" / "release" / "lemmas"


@dataclass(frozen=True)
class LangArraySpec:
    """What distinguishes one per-language array sync from the other."""

    slug: str
    blueprint_name: str
    #: Singular noun for flash messages and operation-log types.
    noun: str
    title: str
    icon: str
    #: Top-level array key on the release line: "forms" or "synonyms".
    array_key: str
    #: Whether entries carry ``is_base_form``. False for synonyms.
    has_base_form: bool


def _release_arrays(spec: LangArraySpec, lang_code: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load this spec's array for a language, keyed by GUID."""
    return helpers.load_release_array_for_lang(DEFAULT_RELEASE_DIR, lang_code, spec.array_key)


def _db_forms(spec: LangArraySpec, lang_code: str) -> Dict[str, List[DerivativeForm]]:
    """Load this spec's DerivativeForm rows for a language, keyed by GUID.

    The two specs partition the same table: synonyms are the non-inflection
    grammatical forms, derivatives are everything else.
    """
    grammatical_forms = tuple(NON_INFLECTION_GRAMMATICAL_FORMS)
    membership = (
        DerivativeForm.grammatical_form.in_(grammatical_forms)
        if spec.array_key == "synonyms"
        else DerivativeForm.grammatical_form.notin_(grammatical_forms)
    )
    rows = (
        g.db.query(DerivativeForm, Lemma.guid)
        .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
        .filter(DerivativeForm.language_code == lang_code, Lemma.guid.isnot(None), membership)
        .all()
    )
    forms_by_guid: Dict[str, List[DerivativeForm]] = {}
    for form, guid in rows:
        forms_by_guid.setdefault(guid, []).append(form)
    return forms_by_guid


def _keyed(forms: List[Any], from_db: bool) -> Dict[str, Any]:
    """Index release dicts or DB rows by their (grammatical_form, text) key."""
    if from_db:
        return {helpers.form_key(f.grammatical_form, f.derivative_form_text): f for f in forms}
    return {helpers.form_key(f.get("grammatical_form", ""), f.get("text", "")): f for f in forms}


def _form_diffs(
    spec: LangArraySpec, release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> List[Dict[str, Any]]:
    """Per-form differences between the release array and the DB rows."""
    release_by_key = _keyed(release_forms, from_db=False)
    db_by_key = _keyed(db_forms, from_db=True)
    release_keys, db_keys = set(release_by_key), set(db_by_key)
    diffs: List[Dict[str, Any]] = []

    for key in sorted(release_keys - db_keys):
        release_form = release_by_key[key]
        diffs.append(
            {
                "type": "release_only",
                "grammatical_form": release_form.get("grammatical_form", ""),
                "release_text": release_form.get("text", ""),
                "db_text": "",
                "release_ipa": release_form.get("ipa", ""),
                "db_ipa": "",
                "release_phonetic": release_form.get("phonetic", ""),
                "db_phonetic": "",
                "release_is_base": release_form.get("is_base_form", False),
                "db_is_base": False,
            }
        )

    for key in sorted(db_keys - release_keys):
        db_form = db_by_key[key]
        diffs.append(
            {
                "type": "db_only",
                "grammatical_form": db_form.grammatical_form,
                "release_text": "",
                "db_text": db_form.derivative_form_text,
                "release_ipa": "",
                "db_ipa": db_form.ipa_pronunciation or "",
                "release_phonetic": "",
                "db_phonetic": db_form.phonetic_pronunciation or "",
                "release_is_base": False,
                "db_is_base": db_form.is_base_form,
            }
        )

    for key in sorted(release_keys & db_keys):
        release_form, db_form = release_by_key[key], db_by_key[key]
        release_ipa = release_form.get("ipa") or ""
        db_ipa = db_form.ipa_pronunciation or ""
        release_phonetic = release_form.get("phonetic") or ""
        db_phonetic = db_form.phonetic_pronunciation or ""
        release_base = release_form.get("is_base_form", False)
        db_base = db_form.is_base_form

        differs = release_ipa != db_ipa or release_phonetic != db_phonetic
        if spec.has_base_form and release_base != db_base:
            differs = True
        if differs:
            diffs.append(
                {
                    "type": "field_diff",
                    "grammatical_form": release_form.get("grammatical_form", ""),
                    "release_text": release_form.get("text", ""),
                    "db_text": db_form.derivative_form_text,
                    "release_ipa": release_ipa,
                    "db_ipa": db_ipa,
                    "release_phonetic": release_phonetic,
                    "db_phonetic": db_phonetic,
                    "release_is_base": release_base,
                    "db_is_base": db_base,
                }
            )
    return diffs


def _has_differences(
    spec: LangArraySpec, release_forms: List[Dict[str, Any]], db_forms: List[DerivativeForm]
) -> bool:
    """Whether a GUID's array differs at all, for the hub's counts."""
    return bool(_form_diffs(spec, release_forms, db_forms))


def _new_db_form(
    spec: LangArraySpec, lemma_id: int, lang_code: str, data: Dict[str, Any]
) -> DerivativeForm:
    """Build a DerivativeForm row from one release array entry."""
    return DerivativeForm(
        lemma_id=lemma_id,
        language_code=lang_code,
        grammatical_form=data.get("grammatical_form", ""),
        derivative_form_text=data.get("text", ""),
        is_base_form=data.get("is_base_form", False) if spec.has_base_form else False,
        ipa_pronunciation=data.get("ipa") or None,
        phonetic_pronunciation=data.get("phonetic") or None,
        verified=False,
    )


def _write_array(
    spec: LangArraySpec, guid: str, lang_code: str, forms: List[DerivativeForm]
) -> bool:
    """Write a GUID's array to its release file. False when no file resolves.

    Only this spec's array key is rewritten; the other one on the same line is
    preserved by ``write_release_line_partial``.
    """
    file_path = helpers.find_release_file_for_lemma_lang(DEFAULT_RELEASE_DIR, guid, lang_code)
    if file_path is None:
        logger.warning(f"Could not resolve release file for {guid} lang={lang_code}")
        return False
    helpers.write_release_line_partial(
        file_path,
        guid,
        spec.array_key,
        [helpers.db_form_to_dict(form=f, include_base_form=spec.has_base_form) for f in forms],
    )
    return True


def build_blueprint(spec: LangArraySpec) -> Blueprint:
    """Build the per-language array sync blueprint for one spec."""
    bp = Blueprint(spec.blueprint_name, __name__, url_prefix=f"/sync/{spec.slug}")

    def detail_url(lang_code: str) -> WerkzeugResponse:
        return redirect(url_for(f"{spec.blueprint_name}.language_detail", lang_code=lang_code))

    @bp.route("/")
    def index() -> ResponseReturnValue:
        """Per-language difference counts for this array."""
        if not DEFAULT_RELEASE_DIR.exists():
            return render_template(
                "sync_lang_array/index.html",
                spec=spec,
                release_dir=str(DEFAULT_RELEASE_DIR),
                error="Release directory not found",
                lang_counts=None,
            )

        db_languages: Set[str] = {
            row[0]
            for row in g.db.query(DerivativeForm.language_code)
            .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
            .filter(Lemma.guid.isnot(None))
            .distinct()
            .all()
        }
        all_languages = sorted(
            helpers.languages_with_release_files(DEFAULT_RELEASE_DIR) | db_languages,
            key=lambda code: (
                LANGUAGE_HIERARCHY.index(code) if code in LANGUAGE_HIERARCHY else 999
            ),
        )

        lang_counts: List[Dict[str, Any]] = []
        for lang_code in all_languages:
            release_forms = _release_arrays(spec, lang_code)
            db_forms = _db_forms(spec, lang_code)
            release_guids, db_guids = set(release_forms), set(db_forms)
            changes = sum(
                1
                for guid in release_guids & db_guids
                if _has_differences(spec, release_forms[guid], db_forms[guid])
            )
            lang_counts.append(
                {
                    "lang_code": lang_code,
                    "lang_name": LANGUAGE_NAMES.get(lang_code, lang_code),
                    "release_count": len(release_guids),
                    "db_count": len(db_guids),
                    "additions": len(release_guids - db_guids),
                    "removals": len(db_guids - release_guids),
                    "changes": changes,
                    "total_diffs": len(release_guids ^ db_guids) + changes,
                }
            )

        return render_template(
            "sync_lang_array/index.html",
            spec=spec,
            release_dir=str(DEFAULT_RELEASE_DIR),
            lang_counts=lang_counts,
        )

    @bp.route("/<lang_code>")
    def language_detail(lang_code: str) -> ResponseReturnValue:
        """Additions, removals and changes for one language."""
        if not DEFAULT_RELEASE_DIR.exists():
            flash(f"Release directory not found: {DEFAULT_RELEASE_DIR}", "error")
            return redirect(url_for(f"{spec.blueprint_name}.index"))

        release_forms = _release_arrays(spec, lang_code)
        db_forms = _db_forms(spec, lang_code)
        release_guids, db_guids = set(release_forms), set(db_forms)
        guid_info = helpers.lemma_info_by_guids(g.db, release_guids | db_guids)

        additions = [
            {
                **guid_info.get(guid, {}),
                "guid": guid,
                "form_count": len(release_forms[guid]),
                "forms_preview": ", ".join(f.get("text", "") for f in release_forms[guid][:5]),
            }
            for guid in sorted(release_guids - db_guids)
        ]
        removals = [
            {
                **guid_info.get(guid, {}),
                "guid": guid,
                "form_count": len(db_forms[guid]),
                "forms_preview": ", ".join(f.derivative_form_text for f in db_forms[guid][:5]),
            }
            for guid in sorted(db_guids - release_guids)
        ]
        changes: List[Dict[str, Any]] = []
        for guid in sorted(release_guids & db_guids):
            diffs = _form_diffs(spec, release_forms[guid], db_forms[guid])
            if diffs:
                changes.append(
                    {
                        **guid_info.get(guid, {}),
                        "guid": guid,
                        "form_diffs": diffs,
                        "diff_count": len(diffs),
                    }
                )

        return render_template(
            "sync_lang_array/language_detail.html",
            spec=spec,
            lang_code=lang_code,
            lang_name=LANGUAGE_NAMES.get(lang_code, lang_code),
            additions=paginate(additions),
            removals=paginate(removals),
            changes=paginate(changes),
            per_page_choices=PER_PAGE_CHOICES,
            db_count=len(db_guids),
            release_dir=str(DEFAULT_RELEASE_DIR),
        )

    @bp.route("/<lang_code>/additions/apply", methods=["POST"])
    def apply_additions(lang_code: str) -> ResponseReturnValue:
        """Import the selected GUIDs' release arrays into the database."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return detail_url(lang_code)

        release_forms = _release_arrays(spec, lang_code)
        if request.form.get("select_scope") == "all":
            selected_guids = sorted(set(release_forms) - set(_db_forms(spec, lang_code)))
        else:
            selected_guids = request.form.getlist("selected_guids")

        if not selected_guids:
            flash("No lemmas selected for import", "warning")
            return detail_url(lang_code)

        guid_to_lemma_id = helpers.guid_to_lemma_id(g.db)
        outcome = SyncOutcome(noun="lemma")

        for guid in selected_guids:
            forms = release_forms.get(guid)
            lemma_id = guid_to_lemma_id.get(guid)
            if not forms:
                outcome.record_error(f"No release {spec.array_key} for {guid} lang={lang_code}")
                continue
            if not lemma_id:
                outcome.record_error(f"Lemma not found in DB for GUID {guid}")
                continue
            try:
                for form_data in forms:
                    g.db.add(_new_db_form(spec, lemma_id, lang_code, form_data))
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{spec.noun}_import",
                    lemma_id=lemma_id,
                    details={"guid": guid, "language_code": lang_code, "form_count": len(forms)},
                )
                outcome.imported += 1
            except Exception as e:
                outcome.record_error(f"Error importing {guid} lang={lang_code}: {e}")

        outcome.commit(g.db)
        outcome.flash_summary()
        return detail_url(lang_code)

    @bp.route("/<lang_code>/removals/apply", methods=["POST"])
    def apply_removals(lang_code: str) -> ResponseReturnValue:
        """Export or delete GUIDs whose array is in the DB but not in release."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return detail_url(lang_code)

        actions = {
            key[len("action_") :]: value
            for key, value in request.form.items()
            if key.startswith("action_")
        }
        if not actions:
            flash("No actions selected", "warning")
            return detail_url(lang_code)

        db_forms = _db_forms(spec, lang_code)
        outcome = SyncOutcome(noun="lemma")

        for guid, action in actions.items():
            if action == SKIP:
                outcome.skipped += 1
                continue
            forms = db_forms.get(guid)
            if not forms:
                outcome.record_error(f"No DB {spec.array_key} for GUID {guid}")
                continue
            try:
                if action == "export":
                    if not _write_array(spec, guid, lang_code, forms):
                        outcome.record_error(f"Could not resolve release file for {guid}")
                        continue
                    outcome.exported += 1
                elif action == "delete":
                    for form in forms:
                        g.db.delete(form)
                    outcome.deleted += 1
                else:
                    continue
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{spec.noun}_{action}",
                    lemma_id=forms[0].lemma_id,
                    details={"guid": guid, "language_code": lang_code, "form_count": len(forms)},
                )
            except Exception as e:
                outcome.record_error(f"Error on {guid} lang={lang_code}: {e}")

        outcome.commit(g.db)
        if outcome.exported:
            g.db.commit()
        outcome.flash_summary()
        return detail_url(lang_code)

    @bp.route("/<lang_code>/changes/apply", methods=["POST"])
    def apply_changes(lang_code: str) -> ResponseReturnValue:
        """Replace one side's array with the other's, per GUID."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return detail_url(lang_code)

        actions = {
            key[len("action_") :]: value
            for key, value in request.form.items()
            if key.startswith("action_")
        }
        if not actions:
            flash("No changes selected", "warning")
            return detail_url(lang_code)

        release_forms = _release_arrays(spec, lang_code)
        db_forms = _db_forms(spec, lang_code)
        guid_to_lemma_id = helpers.guid_to_lemma_id(g.db)
        outcome = SyncOutcome(noun="lemma")

        for guid, action in actions.items():
            if action == SKIP:
                outcome.skipped += 1
                continue
            lemma_id = guid_to_lemma_id.get(guid)
            if not lemma_id:
                outcome.record_error(f"Lemma not found for GUID: {guid}")
                continue
            try:
                if action == USE_RELEASE:
                    incoming = release_forms.get(guid, [])
                    existing = db_forms.get(guid, [])
                    for db_form in existing:
                        g.db.delete(db_form)
                    for form_data in incoming:
                        g.db.add(_new_db_form(spec, lemma_id, lang_code, form_data))
                    log_operation(
                        session=g.db,
                        source="sync-release",
                        operation_type=f"{spec.noun}_sync_use_release",
                        lemma_id=lemma_id,
                        details={
                            "guid": guid,
                            "language_code": lang_code,
                            "old_count": len(existing),
                            "new_count": len(incoming),
                        },
                    )
                    outcome.updated_db += 1
                elif action == USE_DB:
                    existing = db_forms.get(guid, [])
                    if not _write_array(spec, guid, lang_code, existing):
                        outcome.record_error(f"Could not find release file for GUID: {guid}")
                        continue
                    log_operation(
                        session=g.db,
                        source="sync-release",
                        operation_type=f"{spec.noun}_sync_use_db",
                        lemma_id=lemma_id,
                        details={
                            "guid": guid,
                            "language_code": lang_code,
                            "form_count": len(existing),
                        },
                    )
                    outcome.updated_release += 1
            except Exception as e:
                outcome.record_error(f"Error syncing {guid} lang={lang_code}: {e}")

        outcome.commit(g.db)
        outcome.flash_summary()
        return detail_url(lang_code)

    @bp.route("/<lang_code>/export_all", methods=["POST"])
    def export_all(lang_code: str) -> ResponseReturnValue:
        """Write every DB array for this language into the release files."""
        if is_readonly():
            flash("Database is in read-only mode", "error")
            return detail_url(lang_code)

        if not DEFAULT_RELEASE_DIR.exists():
            flash(f"Release directory not found: {DEFAULT_RELEASE_DIR}", "error")
            return detail_url(lang_code)

        db_forms = _db_forms(spec, lang_code)
        if not db_forms:
            language = LANGUAGE_NAMES.get(lang_code, lang_code)
            flash(f"No {language} {spec.noun} entries in database", "warning")
            return detail_url(lang_code)

        outcome = SyncOutcome(noun="lemma")
        for guid, forms in sorted(db_forms.items()):
            try:
                if _write_array(spec, guid, lang_code, forms):
                    outcome.exported += 1
                else:
                    outcome.record_error(f"Could not resolve release file for {guid}")
            except Exception as e:
                outcome.record_error(f"Error exporting {guid} lang={lang_code}: {e}")

        if outcome.exported:
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type=f"{spec.noun}_export_all",
                details={"language_code": lang_code, "guid_count": outcome.exported},
            )
            g.db.commit()
        outcome.flash_summary()
        return detail_url(lang_code)

    return bp
