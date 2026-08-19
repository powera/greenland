#!/usr/bin/python3

"""Sync spelling variants between per-language release files and SQLite.

Variants live in the ``variants`` array of a lemma's per-language file, beside
``forms`` and ``synonyms``, but unlike either of those they are *nested*: each
variant is a paradigm of its own, identified by ``(kind, key)``::

    {"guid": "A02_008", "variants": [
        {"kind": "spelling", "key": "grey", "forms": [
            {"grammatical_form": "adjective/en_positive", "text": "grey", ...},
            {"grammatical_form": "adjective/en_comparative", "text": "greyer", ...}]}]}

That nesting is why this is not a third :class:`LangArraySpec`: the engine in
``lang_array_sync`` keys a diff on ``(grammatical_form, text)`` over a flat list
of ``DerivativeForm`` rows, while a variant needs ``(kind, key,
grammatical_form)`` over ``VariantForm``, a different table.  Everything either
sync would share anyway - the file I/O, the form parsing, the counters, the
paging, the templates - is shared.

Before this page a variant could only reach ``data/release`` through a
whole-tree ``sqlite-to-release`` export, which is why exactly one exists there.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response as WerkzeugResponse

from barsukas.routes.sync import sync_release_helpers as helpers
from barsukas.routes.sync.actions import SKIP, USE_DB, USE_RELEASE, SyncOutcome, is_readonly
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, paginate
from storage.crud.operation_log import log_operation
from storage.models.schema import Lemma
from storage.models.variant_form import VariantForm
from storage.release.variant import records_to_paradigms, variants_by_language
from storage.translation_helpers import LANGUAGE_HIERARCHY, LANGUAGE_NAMES

logger = logging.getLogger(__name__)

REPOSITORY_ROOT = Path(__file__).parent.parent.parent.parent.parent
DEFAULT_RELEASE_DIR = REPOSITORY_ROOT / "data" / "release" / "lemmas"

#: Top-level key on the per-language release line.
ARRAY_KEY = "variants"

#: (variant_kind, variant_key, grammatical_form) - the table's unique key minus
#: the lemma and language, which are fixed for any one comparison.
FormKey = Tuple[str, str, str]


@dataclass(frozen=True)
class VariantSyncSpec:
    """Display metadata, matching what the shared templates read off a spec."""

    slug: str = "variants"
    blueprint_name: str = "sync_variant_release"
    noun: str = "variant"
    title: str = "Spelling Variants"
    icon: str = "bi-fonts"
    array_key: str = ARRAY_KEY
    #: Variants do carry a base form, scoped to the variant itself.
    has_base_form: bool = True


SPEC = VariantSyncSpec()


def _release_variants(lang_code: str) -> Dict[str, Dict[FormKey, Dict[str, Any]]]:
    """Load the release ``variants`` array per GUID, flattened to form keys."""
    raw = helpers.load_release_array_for_lang(DEFAULT_RELEASE_DIR, lang_code, ARRAY_KEY)
    out: Dict[str, Dict[FormKey, Dict[str, Any]]] = {}
    for guid, entries in raw.items():
        flattened: Dict[FormKey, Dict[str, Any]] = {}
        for (kind, key), forms in records_to_paradigms(entries).items():
            for form in forms:
                flattened[(kind, key, str(form["grammatical_form"]))] = form
        if flattened:
            out[guid] = flattened
    return out


def _db_variants(lang_code: str) -> Dict[str, List[VariantForm]]:
    """Load this language's VariantForm rows, keyed by lemma GUID."""
    rows = (
        g.db.query(VariantForm, Lemma.guid)
        .join(Lemma, VariantForm.lemma_id == Lemma.id)
        .filter(VariantForm.language_code == lang_code, Lemma.guid.isnot(None))
        .all()
    )
    by_guid: Dict[str, List[VariantForm]] = {}
    for row, guid in rows:
        by_guid.setdefault(guid, []).append(row)
    return by_guid


def _db_keyed(rows: List[VariantForm]) -> Dict[FormKey, VariantForm]:
    return {(row.variant_kind, row.variant_key, row.grammatical_form): row for row in rows}


def _label(form_key: FormKey) -> str:
    """How one form is named in the diff table: the variant, then its slot."""
    kind, key, grammatical_form = form_key
    return f"{key} ({kind}) · {grammatical_form}"


def _form_diffs(
    release_forms: Dict[FormKey, Dict[str, Any]], db_rows: List[VariantForm]
) -> List[Dict[str, Any]]:
    """Per-form differences between the release array and the DB rows."""
    db_forms = _db_keyed(db_rows)
    release_keys, db_keys = set(release_forms), set(db_forms)
    diffs: List[Dict[str, Any]] = []

    for form_key in sorted(release_keys - db_keys):
        release_form = release_forms[form_key]
        diffs.append(
            {
                "type": "release_only",
                "variant": _label(form_key),
                "grammatical_form": form_key[2],
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

    for form_key in sorted(db_keys - release_keys):
        row = db_forms[form_key]
        diffs.append(
            {
                "type": "db_only",
                "variant": _label(form_key),
                "grammatical_form": form_key[2],
                "release_text": "",
                "db_text": row.variant_form_text,
                "release_ipa": "",
                "db_ipa": row.ipa_pronunciation or "",
                "release_phonetic": "",
                "db_phonetic": row.phonetic_pronunciation or "",
                "release_is_base": False,
                "db_is_base": row.is_base_form,
            }
        )

    for form_key in sorted(release_keys & db_keys):
        release_form, row = release_forms[form_key], db_forms[form_key]
        release_text = str(release_form.get("text") or "")
        release_ipa = str(release_form.get("ipa") or "")
        release_phonetic = str(release_form.get("phonetic") or "")
        release_base = bool(release_form.get("is_base_form", False))
        db_ipa = row.ipa_pronunciation or ""
        db_phonetic = row.phonetic_pronunciation or ""

        if (
            release_text == row.variant_form_text
            and release_ipa == db_ipa
            and release_phonetic == db_phonetic
            and release_base == row.is_base_form
        ):
            continue

        diffs.append(
            {
                "type": "field_diff",
                "variant": _label(form_key),
                "grammatical_form": form_key[2],
                "release_text": release_text,
                "db_text": row.variant_form_text,
                "release_ipa": release_ipa,
                "db_ipa": db_ipa,
                "release_phonetic": release_phonetic,
                "db_phonetic": db_phonetic,
                "release_is_base": release_base,
                "db_is_base": row.is_base_form,
            }
        )
    return diffs


def _new_db_row(
    lemma_id: int, lang_code: str, form_key: FormKey, data: Dict[str, Any]
) -> VariantForm:
    """Build a VariantForm row from one flattened release entry."""
    kind, key, grammatical_form = form_key
    return VariantForm(
        lemma_id=lemma_id,
        language_code=lang_code,
        variant_kind=kind,
        variant_key=key,
        grammatical_form=grammatical_form,
        variant_form_text=str(data.get("text", "")),
        is_base_form=bool(data.get("is_base_form", False)),
        ipa_pronunciation=data.get("ipa") or None,
        phonetic_pronunciation=data.get("phonetic") or None,
        verified=False,
    )


def _write_variants(guid: str, lang_code: str, rows: List[VariantForm]) -> bool:
    """Write a GUID's variants array to its release file.

    Only the ``variants`` key is rewritten; ``forms`` and ``synonyms`` on the
    same line are preserved by ``write_release_line_partial``. Returns False
    when no release file resolves for the GUID.
    """
    file_path = helpers.find_release_file_for_lemma_lang(DEFAULT_RELEASE_DIR, guid, lang_code)
    if file_path is None:
        logger.warning(f"Could not resolve release file for {guid} lang={lang_code}")
        return False

    # variants_by_language groups and orders exactly as the exporter does, so a
    # row written here matches what a full re-export would produce.
    grouped = variants_by_language(rows)
    helpers.write_release_line_partial(file_path, guid, ARRAY_KEY, grouped.get(lang_code, []))
    return True


bp = Blueprint(SPEC.blueprint_name, __name__, url_prefix=f"/sync/{SPEC.slug}")


def _detail_url(lang_code: str) -> WerkzeugResponse:
    return redirect(url_for(f"{SPEC.blueprint_name}.language_detail", lang_code=lang_code))


def _row_actions() -> Dict[str, str]:
    return {
        key[len("action_") :]: value
        for key, value in request.form.items()
        if key.startswith("action_")
    }


@bp.route("/")
def index() -> ResponseReturnValue:
    """Per-language difference counts for the variants array."""
    if not DEFAULT_RELEASE_DIR.exists():
        return render_template(
            "sync_lang_array/index.html",
            spec=SPEC,
            release_dir=str(DEFAULT_RELEASE_DIR),
            error="Release directory not found",
            lang_counts=None,
        )

    db_languages: Set[str] = {
        row[0]
        for row in g.db.query(VariantForm.language_code)
        .join(Lemma, VariantForm.lemma_id == Lemma.id)
        .filter(Lemma.guid.isnot(None))
        .distinct()
        .all()
    }
    all_languages = sorted(
        helpers.languages_with_release_files(DEFAULT_RELEASE_DIR) | db_languages,
        key=lambda code: (LANGUAGE_HIERARCHY.index(code) if code in LANGUAGE_HIERARCHY else 999),
    )

    lang_counts: List[Dict[str, Any]] = []
    for lang_code in all_languages:
        release_forms = _release_variants(lang_code)
        db_rows = _db_variants(lang_code)
        release_guids, db_guids = set(release_forms), set(db_rows)
        changes = sum(
            1
            for guid in release_guids & db_guids
            if _form_diffs(release_forms[guid], db_rows[guid])
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
        spec=SPEC,
        release_dir=str(DEFAULT_RELEASE_DIR),
        lang_counts=lang_counts,
    )


@bp.route("/<lang_code>")
def language_detail(lang_code: str) -> ResponseReturnValue:
    """Additions, removals and changes for one language."""
    if not DEFAULT_RELEASE_DIR.exists():
        flash(f"Release directory not found: {DEFAULT_RELEASE_DIR}", "error")
        return redirect(url_for(f"{SPEC.blueprint_name}.index"))

    release_forms = _release_variants(lang_code)
    db_rows = _db_variants(lang_code)
    release_guids, db_guids = set(release_forms), set(db_rows)
    guid_info = helpers.lemma_info_by_guids(g.db, release_guids | db_guids)

    additions = [
        {
            **guid_info.get(guid, {}),
            "guid": guid,
            "form_count": len(release_forms[guid]),
            "forms_preview": ", ".join(sorted({key for _, key, _ in release_forms[guid]})[:5]),
        }
        for guid in sorted(release_guids - db_guids)
    ]
    removals = [
        {
            **guid_info.get(guid, {}),
            "guid": guid,
            "form_count": len(db_rows[guid]),
            "forms_preview": ", ".join(sorted({row.variant_key for row in db_rows[guid]})[:5]),
        }
        for guid in sorted(db_guids - release_guids)
    ]
    changes: List[Dict[str, Any]] = []
    for guid in sorted(release_guids & db_guids):
        diffs = _form_diffs(release_forms[guid], db_rows[guid])
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
        spec=SPEC,
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
    """Import the selected GUIDs' release variants into the database."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return _detail_url(lang_code)

    release_forms = _release_variants(lang_code)
    if request.form.get("select_scope") == "all":
        selected_guids = sorted(set(release_forms) - set(_db_variants(lang_code)))
    else:
        selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No lemmas selected for import", "warning")
        return _detail_url(lang_code)

    guid_to_lemma_id = helpers.guid_to_lemma_id(g.db)
    outcome = SyncOutcome(noun="lemma")

    for guid in selected_guids:
        forms = release_forms.get(guid)
        lemma_id = guid_to_lemma_id.get(guid)
        if not forms:
            outcome.record_error(f"No release variants for {guid} lang={lang_code}")
            continue
        if not lemma_id:
            outcome.record_error(f"Lemma not found in DB for GUID {guid}")
            continue
        try:
            for form_key, data in forms.items():
                g.db.add(_new_db_row(lemma_id, lang_code, form_key, data))
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type=f"{SPEC.noun}_import",
                lemma_id=lemma_id,
                details={"guid": guid, "language_code": lang_code, "form_count": len(forms)},
            )
            outcome.imported += 1
        except Exception as e:
            outcome.record_error(f"Error importing {guid} lang={lang_code}: {e}")

    outcome.commit(g.db)
    outcome.flash_summary()
    return _detail_url(lang_code)


@bp.route("/<lang_code>/removals/apply", methods=["POST"])
def apply_removals(lang_code: str) -> ResponseReturnValue:
    """Export or delete GUIDs whose variants are in the DB but not in release."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return _detail_url(lang_code)

    actions = _row_actions()
    if not actions:
        flash("No actions selected", "warning")
        return _detail_url(lang_code)

    db_rows = _db_variants(lang_code)
    outcome = SyncOutcome(noun="lemma")

    for guid, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        rows = db_rows.get(guid)
        if not rows:
            outcome.record_error(f"No DB variants for GUID {guid}")
            continue
        try:
            if action == "export":
                if not _write_variants(guid, lang_code, rows):
                    outcome.record_error(f"Could not resolve release file for {guid}")
                    continue
                outcome.exported += 1
            elif action == "delete":
                for row in rows:
                    g.db.delete(row)
                outcome.deleted += 1
            else:
                continue
            log_operation(
                session=g.db,
                source="sync-release",
                operation_type=f"{SPEC.noun}_{action}",
                lemma_id=rows[0].lemma_id,
                details={"guid": guid, "language_code": lang_code, "form_count": len(rows)},
            )
        except Exception as e:
            outcome.record_error(f"Error on {guid} lang={lang_code}: {e}")

    outcome.commit(g.db)
    if outcome.exported:
        g.db.commit()
    outcome.flash_summary()
    return _detail_url(lang_code)


@bp.route("/<lang_code>/changes/apply", methods=["POST"])
def apply_changes(lang_code: str) -> ResponseReturnValue:
    """Replace one side's variants with the other's, per GUID."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return _detail_url(lang_code)

    actions = _row_actions()
    if not actions:
        flash("No changes selected", "warning")
        return _detail_url(lang_code)

    release_forms = _release_variants(lang_code)
    db_rows = _db_variants(lang_code)
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
                incoming = release_forms.get(guid, {})
                existing = db_rows.get(guid, [])
                for row in existing:
                    g.db.delete(row)
                g.db.flush()
                for form_key, data in incoming.items():
                    g.db.add(_new_db_row(lemma_id, lang_code, form_key, data))
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{SPEC.noun}_sync_use_release",
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
                existing = db_rows.get(guid, [])
                if not _write_variants(guid, lang_code, existing):
                    outcome.record_error(f"Could not find release file for GUID: {guid}")
                    continue
                log_operation(
                    session=g.db,
                    source="sync-release",
                    operation_type=f"{SPEC.noun}_sync_use_db",
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
    return _detail_url(lang_code)


@bp.route("/<lang_code>/export_all", methods=["POST"])
def export_all(lang_code: str) -> ResponseReturnValue:
    """Write every DB variant for this language into the release files."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return _detail_url(lang_code)

    if not DEFAULT_RELEASE_DIR.exists():
        flash(f"Release directory not found: {DEFAULT_RELEASE_DIR}", "error")
        return _detail_url(lang_code)

    db_rows = _db_variants(lang_code)
    if not db_rows:
        language = LANGUAGE_NAMES.get(lang_code, lang_code)
        flash(f"No {language} {SPEC.noun} entries in database", "warning")
        return _detail_url(lang_code)

    outcome = SyncOutcome(noun="lemma")
    for guid, rows in sorted(db_rows.items()):
        try:
            if _write_variants(guid, lang_code, rows):
                outcome.exported += 1
            else:
                outcome.record_error(f"Could not resolve release file for {guid}")
        except Exception as e:
            outcome.record_error(f"Error exporting {guid} lang={lang_code}: {e}")

    if outcome.exported:
        log_operation(
            session=g.db,
            source="sync-release",
            operation_type=f"{SPEC.noun}_export_all",
            details={"language_code": lang_code, "guid_count": outcome.exported},
        )
        g.db.commit()
    outcome.flash_summary()
    return _detail_url(lang_code)
