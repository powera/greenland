#!/usr/bin/python3

"""Routes for GYVATE STRINGS export functionality."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from agents.gyvate import GyvateAgent
from storage.backend.config import DataSourceConfig

bp = Blueprint("gyvate", __name__, url_prefix="/gyvate")
DEFAULT_SCOPES: list[str] = []
DEFAULT_TARGET_LANGUAGES = ["lt"]
DEFAULT_TEMPLATE_PATH = "src/barsukas/templates"
DEFAULT_STRINGS_PATH = "strings/barsukas"


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[3])


def _get_config() -> DataSourceConfig:
    app = current_app
    return app.backend_config  # type: ignore[no-any-return, attr-defined]


def _normalize_languages(raw_languages: list[str], csv_languages: str) -> list[str]:
    merged = set(raw_languages)
    for csv_value in csv_languages.split(","):
        normalized = csv_value.strip()
        if normalized:
            merged.add(normalized)
    return sorted(merged)


def _normalize_namespace_from_path(relative_path: str) -> str:
    normalized_path = relative_path.strip().replace("\\", "/")
    if normalized_path.endswith("/en.json"):
        normalized_path = normalized_path[: -len("/en.json")]
    elif normalized_path.endswith("en.json"):
        normalized_path = normalized_path[: -len("en.json")]

    namespace = normalized_path.strip("/").replace("/", ".")
    if not namespace:
        raise ValueError(f'Could not infer namespace from path "{relative_path}"')
    return namespace


def _parse_uploaded_catalog_json(raw_bytes: bytes, source_name: str) -> dict[str, str]:
    loaded = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{source_name} must contain a JSON object")
    return {str(key_name): str(value_text) for key_name, value_text in loaded.items()}


def _parse_uploaded_xcstrings(raw_bytes: bytes, source_name: str) -> dict[str, str]:
    loaded = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{source_name} must contain a JSON object")
    strings_payload = loaded.get("strings")
    if not isinstance(strings_payload, dict):
        raise ValueError(f'{source_name} must contain a "strings" object')

    source_language = str(loaded.get("sourceLanguage") or "en")
    extracted_catalog: dict[str, str] = {}
    for translation_key, translation_entry in strings_payload.items():
        if not isinstance(translation_entry, dict):
            continue
        localization_map = translation_entry.get("localizations")
        if not isinstance(localization_map, dict):
            continue
        source_entry = localization_map.get(source_language) or localization_map.get("en")
        if not isinstance(source_entry, dict):
            continue
        string_unit = source_entry.get("stringUnit")
        if not isinstance(string_unit, dict):
            continue
        value_text = string_unit.get("value")
        if not isinstance(value_text, str):
            continue
        extracted_catalog[str(translation_key)] = value_text

    if not extracted_catalog:
        raise ValueError(f"{source_name} did not contain extractable source-language strings")
    return extracted_catalog


def _load_uploaded_english_catalogs() -> dict[str, dict[str, str]]:
    uploaded_catalogs: dict[str, dict[str, str]] = {}

    uploaded_files = [
        entry for entry in request.files.getlist("english_strings_files") if entry.filename
    ]
    for uploaded_file in uploaded_files:
        assert uploaded_file.filename is not None
        namespace = _normalize_namespace_from_path(uploaded_file.filename)
        source_bytes = uploaded_file.read()
        if uploaded_file.filename.endswith(".xcstrings"):
            uploaded_catalogs[namespace] = _parse_uploaded_xcstrings(
                source_bytes, uploaded_file.filename
            )
        else:
            uploaded_catalogs[namespace] = _parse_uploaded_catalog_json(
                source_bytes, uploaded_file.filename
            )

    zip_bundle = request.files.get("english_strings_bundle")
    if not zip_bundle or not zip_bundle.filename:
        return uploaded_catalogs

    zip_data = zip_bundle.read()
    with zipfile.ZipFile(BytesIO(zip_data)) as zip_handle:
        for entry_name in zip_handle.namelist():
            if entry_name.endswith("/"):
                continue
            if not (entry_name.endswith("en.json") or entry_name.endswith(".xcstrings")):
                continue
            namespace = _normalize_namespace_from_path(entry_name.replace(".xcstrings", "/en.json"))
            with zip_handle.open(entry_name) as zip_entry:
                source_bytes = zip_entry.read()
                if entry_name.endswith(".xcstrings"):
                    uploaded_catalogs[namespace] = _parse_uploaded_xcstrings(
                        source_bytes, entry_name
                    )
                else:
                    uploaded_catalogs[namespace] = _parse_uploaded_catalog_json(
                        source_bytes,
                        entry_name,
                    )
    return uploaded_catalogs


@bp.route("/")
def export_page() -> ResponseReturnValue:
    """Display the GYVATE STRINGS export form."""
    return render_template(
        "gyvate/export.html",
        default_project_root=_default_project_root(),
        default_template_path=DEFAULT_TEMPLATE_PATH,
        default_strings_path=DEFAULT_STRINGS_PATH,
        default_scopes=DEFAULT_SCOPES,
        default_target_languages=DEFAULT_TARGET_LANGUAGES,
    )


@bp.route("/export", methods=["POST"])
def export_strings() -> ResponseReturnValue:
    """Run STRINGS extraction/generation via the GYVATE service layer."""
    selected_scopes = request.form.getlist("scopes")
    project_root = request.form.get("project_root", _default_project_root()).strip()
    template_path = request.form.get("template_path", DEFAULT_TEMPLATE_PATH).strip()
    strings_path = request.form.get("strings_path", DEFAULT_STRINGS_PATH).strip()
    write_mode = request.form.get("mode", "dry") == "write"

    selected_languages = request.form.getlist("target_languages")
    language_csv = request.form.get("target_languages_csv", "")
    target_languages = _normalize_languages(selected_languages, language_csv)
    try:
        uploaded_english_catalogs = _load_uploaded_english_catalogs()
    except (ValueError, json.JSONDecodeError, zipfile.BadZipFile) as upload_error:
        flash(f"Invalid uploaded STRINGS input: {upload_error}", "error")
        return redirect(url_for("gyvate.export_page"))

    agent = GyvateAgent(config=_get_config())
    result = agent.run_export(
        project_root=project_root,
        template_path=template_path,
        strings_path=strings_path,
        scopes=selected_scopes,
        target_languages=target_languages,
        uploaded_english_catalogs=uploaded_english_catalogs,
        write_mode=write_mode,
    )

    if not result.success:
        flash(f"GYVATE export failed: {result.error}", "error")
        return redirect(url_for("gyvate.export_page"))

    flash(
        f"GYVATE completed in {result.mode} mode with {result.replacements_total} replacements.",
        "success",
    )
    return render_template("gyvate/results.html", result=result)
