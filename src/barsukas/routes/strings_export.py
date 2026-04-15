#!/usr/bin/python3

"""Routes for GYVATE STRINGS export functionality."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from agents.gyvate import GyvateAgent
from storage.backend.config import DataSourceConfig

bp = Blueprint("gyvate", __name__, url_prefix="/gyvate")
DEFAULT_SCOPES = ["templates"]
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
    if not selected_scopes:
        flash("Select at least one scope (templates/modules).", "error")
        return redirect(url_for("gyvate.export_page"))

    project_root = request.form.get("project_root", _default_project_root()).strip()
    template_path = request.form.get("template_path", DEFAULT_TEMPLATE_PATH).strip()
    strings_path = request.form.get("strings_path", DEFAULT_STRINGS_PATH).strip()
    write_mode = request.form.get("mode", "dry") == "write"

    selected_languages = request.form.getlist("target_languages")
    language_csv = request.form.get("target_languages_csv", "")
    target_languages = _normalize_languages(selected_languages, language_csv)

    agent = GyvateAgent(config=_get_config())
    result = agent.run_export(
        project_root=project_root,
        template_path=template_path,
        strings_path=strings_path,
        scopes=selected_scopes,
        target_languages=target_languages,
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
