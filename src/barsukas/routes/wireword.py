#!/usr/bin/python3

"""Routes for WireWord export functionality."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import constants
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue

from exports.wireword.service import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    WirewordExportService,
)
from langtools.dialect_overrides import normalize_language_code
from storage.backend.config import DataSourceConfig

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

bp = Blueprint("wireword", __name__, url_prefix="/wireword")
ALL_SOURCE_LANGUAGE_OPTION = "all"


def _get_config() -> DataSourceConfig:
    """Get DataSourceConfig from the Flask app's backend_config."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    return app.backend_config


def _cdn_credentials_available() -> bool:
    """Return True if DigitalOcean Spaces credentials are configured.

    Reports no credentials under GREENLAND_TEST_MODE, so the UI offers the
    non-CDN path rather than a button that would raise on click.
    """
    from clients.keys import test_mode_enabled

    if test_mode_enabled():
        return False
    if os.getenv("DO_SPACES_KEY") and os.getenv("DO_SPACES_SECRET"):
        return True
    key_file = Path(constants.KEY_DIR) / "digitalocean.key"
    return key_file.exists()


def _flash_cdn_upload_status(results: dict[str, Any]) -> None:
    """Flash CDN upload status when export includes CDN metadata."""
    cdn_result: Any = results.get("cdn_upload")
    if not isinstance(cdn_result, dict):
        return

    uploaded_count = cdn_result.get("files_uploaded")
    if not isinstance(uploaded_count, int):
        uploaded_count = 0

    if cdn_result.get("success"):
        flash(f"CDN upload successful: {uploaded_count} files uploaded.", "success")
    else:
        flash(
            "CDN upload failed or partially failed. Check server logs for per-file errors.",
            "warning",
        )


def export_all_languages(
    include_unreviewed_audio: bool = False,
    apply_level_overrides: bool = False,
    cdn_upload: bool = False,
    source_languages: list[str] | None = None,
) -> ResponseReturnValue:
    """Export WireWord files for all supported languages (directory mode only)."""
    try:
        # Create DataSourceConfig
        config = _get_config()
        selected_source_languages = source_languages or ["en"]

        all_results: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        for source_language in selected_source_languages:
            source_display = SUPPORTED_SOURCE_LANGUAGES.get(source_language, source_language)

            # Export for each supported language
            for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
                if source_language == lang_code:
                    # Skip same source/target combos (e.g. es from es).
                    continue
                result_label = (
                    f"{lang_name} from {source_display}"
                    if source_language != "en"
                    else f"{lang_name} from English"
                )
                try:
                    # Every supported language is exported the same way; zh-tw
                    # is one of them, not a second pass over zh.
                    exporter = WirewordExportService(
                        config=config,
                        language=lang_code,
                        include_unreviewed_audio=include_unreviewed_audio,
                        source_language=source_language,
                    )
                    if apply_level_overrides:
                        exporter.apply_level_overrides()
                    success, results = exporter.export_wireword_directory(cdn_upload=cdn_upload)
                    all_results[result_label] = {"success": success, "results": results}
                    if not success:
                        errors.append(result_label)

                except Exception as e:
                    errors.append(f"{result_label}: {str(e)}")
                    all_results[result_label] = {"success": False, "error": str(e)}

        # Show results
        if errors:
            flash(
                f"Export completed with errors for: {', '.join(errors)}",
                "warning",
            )
        else:
            flash("Successfully exported WireWord files for all languages!", "success")

        # Count successes
        successes = sum(1 for r in all_results.values() if r.get("success", False))
        total = len(all_results)
        flash(f"Exported {successes}/{total} language variants", "info")

        return render_template(
            "wireword/results_all.html",
            all_results=all_results,
            errors=errors,
        )

    except Exception as e:
        flash(f"Error during export: {str(e)}", "error")
        return redirect(url_for("wireword.export_page"))


# Supported source languages for WireWord export
SUPPORTED_SOURCE_LANGUAGES = {
    ALL_SOURCE_LANGUAGE_OPTION: "All source languages",
    "en": "English",
    **{
        language_code: SUPPORTED_LANGUAGES.get(language_code, language_code)
        for language_code in SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES
    },
}


LITHUANIAN_DEFAULT_TARGET = "lt"
LITHUANIAN_DEFAULT_SOURCE_LANGUAGES: tuple[str, ...] = (
    "en",
    *SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
)


@bp.route("/default-export", methods=["POST"])
def default_export() -> ResponseReturnValue:
    """Run the canonical Lithuanian export across all supported source languages.

    Generates Lithuanian wordlists from English plus every supported non-English
    source language, applies level overrides, includes unreviewed audio, and
    uploads to S3 if credentials are available.
    """
    if LITHUANIAN_DEFAULT_TARGET not in SUPPORTED_LANGUAGES:
        flash("Lithuanian is not configured as a supported target language.", "error")
        return redirect(url_for("wireword.export_page"))

    upload_to_cdn_requested = True
    cdn_upload = _cdn_credentials_available()
    if upload_to_cdn_requested and not cdn_upload:
        flash(
            "DigitalOcean Spaces credentials not found; exporting locally without CDN upload.",
            "warning",
        )

    config = _get_config()
    variant_results: dict[str, dict[str, Any]] = {}
    variant_errors: list[str] = []

    for source_language in LITHUANIAN_DEFAULT_SOURCE_LANGUAGES:
        if source_language == LITHUANIAN_DEFAULT_TARGET:
            continue
        source_label = SUPPORTED_SOURCE_LANGUAGES.get(source_language, source_language)
        try:
            exporter = WirewordExportService(
                config=config,
                language=LITHUANIAN_DEFAULT_TARGET,
                include_unreviewed_audio=True,
                source_language=source_language,
            )
            exporter.apply_level_overrides()
            success, results = exporter.export_wireword_directory(cdn_upload=cdn_upload)
            variant_results[source_label] = {
                "success": success,
                "results": results,
                "output_dir": exporter.get_language_output_dir(),
            }
            if not success:
                variant_errors.append(source_label)
        except Exception as e:
            variant_errors.append(f"{source_label}: {str(e)}")
            variant_results[source_label] = {"success": False, "error": str(e)}

    if variant_errors:
        flash(
            f"Default export completed with errors for: {', '.join(variant_errors)}",
            "warning",
        )
    else:
        flash(
            "Default Lithuanian export completed for all source languages.",
            "success",
        )

    successes = sum(1 for r in variant_results.values() if r.get("success", False))
    flash(f"Exported {successes}/{len(variant_results)} source-language variants", "info")

    return render_template(
        "wireword/results_all.html",
        all_results=variant_results,
        errors=variant_errors,
    )


@bp.route("/")
def export_page() -> ResponseReturnValue:
    """Display the WireWord export page."""
    return render_template(
        "wireword/export.html",
        languages=SUPPORTED_LANGUAGES,
        source_languages=SUPPORTED_SOURCE_LANGUAGES,
    )


@bp.route("/export", methods=["POST"])
def export_wireword() -> ResponseReturnValue:
    """Export WireWord files for a specific language."""
    language = request.form.get("language", "").strip()
    export_type = request.form.get("export_type", "directory")
    difficulty_level = request.form.get("difficulty_level", "").strip()
    pos_type = request.form.get("pos_type", "").strip()
    include_unreviewed_audio = request.form.get("include_unreviewed_audio") == "on"
    apply_level_overrides = request.form.get("apply_level_overrides") == "on"
    source_language = request.form.get("source_language", "en").strip()
    all_source_languages = source_language == ALL_SOURCE_LANGUAGE_OPTION
    selected_source_languages = (
        ["en", *SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES]
        if all_source_languages
        else [source_language]
    )
    upload_to_cdn_requested = request.form.get("upload_to_cdn", "on") == "on"
    cdn_upload = upload_to_cdn_requested and _cdn_credentials_available()

    if upload_to_cdn_requested and not cdn_upload:
        flash(
            "DigitalOcean Spaces credentials not found; exporting locally without CDN upload.",
            "warning",
        )

    if export_type == "single" and all_source_languages:
        flash(
            'Single file export does not support "All source languages". Use Default export.',
            "error",
        )
        return redirect(url_for("wireword.export_page"))

    # Handle "All Languages" option
    if language == "all":
        return export_all_languages(
            include_unreviewed_audio=include_unreviewed_audio,
            apply_level_overrides=apply_level_overrides,
            cdn_upload=cdn_upload,
            source_languages=selected_source_languages,
        )

    # Validate language.  zh-tw is an ordinary entry in SUPPORTED_LANGUAGES, so
    # the Traditional Chinese export is just another language choice here.
    language = normalize_language_code(language)
    if language not in SUPPORTED_LANGUAGES:
        flash("Invalid language selected", "error")
        return redirect(url_for("wireword.export_page"))

    # Parse optional filters
    difficulty_filter = (
        int(difficulty_level) if difficulty_level and difficulty_level != "all" else None
    )
    pos_filter = pos_type if pos_type and pos_type != "all" else None

    try:
        # Create DataSourceConfig
        config = _get_config()

        # Initialize exporter
        exporter = WirewordExportService(
            config=config,
            language=language,
            include_unreviewed_audio=include_unreviewed_audio,
            source_language=source_language,
        )

        # Apply level overrides if requested
        override_results = None
        if apply_level_overrides:
            override_results = exporter.apply_level_overrides()
            country_applied = override_results.get("country_overrides", {}).get("applied", False)
            family_applied = override_results.get("family_relation_overrides", {}).get(
                "applied", False
            )
            if country_applied or family_applied:
                flash("Applied difficulty level overrides before export", "info")

        if export_type == "directory" and all_source_languages:
            variant_results: dict[str, dict[str, Any]] = {}
            variant_errors: list[str] = []
            for selected_source_language in selected_source_languages:
                if selected_source_language == language:
                    # Skip same source/target combos.
                    continue
                source_label = SUPPORTED_SOURCE_LANGUAGES.get(
                    selected_source_language, selected_source_language
                )
                variant_exporter = WirewordExportService(
                    config=config,
                    language=language,
                    include_unreviewed_audio=include_unreviewed_audio,
                    source_language=selected_source_language,
                )
                if apply_level_overrides:
                    variant_exporter.apply_level_overrides()
                success, results = variant_exporter.export_wireword_directory(cdn_upload=cdn_upload)
                variant_results[source_label] = {
                    "success": success,
                    "results": results,
                    "output_dir": variant_exporter.get_language_output_dir(),
                }
                if not success:
                    variant_errors.append(source_label)

            if variant_errors:
                flash(
                    f'Export completed with errors for source language(s): {", ".join(variant_errors)}',
                    "warning",
                )
            else:
                flash("Successfully exported WireWord files for all source languages!", "success")

            return render_template(
                "wireword/results_all.html",
                all_results=variant_results,
                errors=variant_errors,
            )

        if export_type == "directory":
            # Export to directory structure (includes sentences automatically via UNGURYS)
            success, results = exporter.export_wireword_directory(cdn_upload=cdn_upload)
            _flash_cdn_upload_status(results)

            if success:
                files_created = results.get("files_created", [])
                levels_exported = results.get("levels_exported", [])
                subtypes_exported = results.get("subtypes_exported", [])
                sentences_exported = results.get("sentences_exported", 0)

                flash(
                    f"Successfully exported WireWord files for "
                    f"{SUPPORTED_LANGUAGES.get(language, language)}!",
                    "success",
                )
                flash(
                    f"Created {len(files_created)} word files for {len(levels_exported)} difficulty levels",
                    "info",
                )
                if sentences_exported > 0:
                    flash(
                        f"Exported {sentences_exported} sentences to wireword_sentences.json",
                        "info",
                    )

                return render_template(
                    "wireword/results.html",
                    success=True,
                    language=language,
                    language_name=SUPPORTED_LANGUAGES.get(language, language),
                    export_type="directory",
                    files_created=files_created,
                    levels_exported=levels_exported,
                    subtypes_exported=subtypes_exported,
                    output_dir=exporter.get_language_output_dir(),
                    cdn_upload=results.get("cdn_upload"),
                )
            else:
                flash("Export failed. Check the logs for details.", "error")
                return redirect(url_for("wireword.export_page"))

        elif export_type == "single":
            # Export to a single file - create temp file for download
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            success, stats = exporter.export_wireword_single(
                output_path=tmp_path,
                difficulty_level=difficulty_filter,
                pos_type=pos_filter,
                include_unverified=True,
            )

            if success:
                # Prepare download filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"wireword_{language}_{timestamp}.json"

                return send_file(
                    tmp_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype="application/json",
                )
            else:
                flash("Export failed. Check the logs for details.", "error")
                return redirect(url_for("wireword.export_page"))

        else:
            flash(f"Invalid export type: {export_type}", "error")
            return redirect(url_for("wireword.export_page"))

    except Exception as e:
        flash(f"Error during export: {str(e)}", "error")
        return redirect(url_for("wireword.export_page"))
