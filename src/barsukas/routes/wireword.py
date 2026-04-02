#!/usr/bin/python3

"""Routes for WireWord export functionality."""

import tempfile
from datetime import datetime
from typing import TYPE_CHECKING, Any

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

from agents.ungurys import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    UngurysAgent,
)
from storage.backend.config import DataSourceConfig

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

bp = Blueprint("wireword", __name__, url_prefix="/wireword")
ALL_SOURCE_LANGUAGE_OPTION = "all"


def _get_config() -> DataSourceConfig:
    """Get DataSourceConfig from the Flask app's backend_config."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    return app.backend_config


def export_all_languages(
    include_unreviewed_audio: bool = False,
    apply_level_overrides: bool = False,
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
                result_label = (
                    f"{lang_name} from {source_display}"
                    if source_language != "en"
                    else f"{lang_name} from English"
                )
                try:
                    # Handle Chinese: export both Simplified and Traditional
                    if lang_code == "zh":
                        # Export Simplified Chinese
                        agent_simplified = UngurysAgent(
                            config=config,
                            language=lang_code,
                            simplified_chinese=True,
                            include_unreviewed_audio=include_unreviewed_audio,
                            source_language=source_language,
                        )
                        if apply_level_overrides:
                            agent_simplified.apply_level_overrides()
                        success_simp, results_simp = agent_simplified.export_wireword_directory()
                        simplified_label = f"{result_label} (Simplified)"
                        all_results[simplified_label] = {
                            "success": success_simp,
                            "results": results_simp,
                        }
                        if not success_simp:
                            errors.append(simplified_label)

                        # Export Traditional Chinese
                        agent_traditional = UngurysAgent(
                            config=config,
                            language=lang_code,
                            simplified_chinese=False,
                            include_unreviewed_audio=include_unreviewed_audio,
                            source_language=source_language,
                        )
                        if apply_level_overrides:
                            agent_traditional.apply_level_overrides()
                        success_trad, results_trad = agent_traditional.export_wireword_directory()
                        traditional_label = f"{result_label} (Traditional)"
                        all_results[traditional_label] = {
                            "success": success_trad,
                            "results": results_trad,
                        }
                        if not success_trad:
                            errors.append(traditional_label)
                    else:
                        # Export other languages
                        agent = UngurysAgent(
                            config=config,
                            language=lang_code,
                            include_unreviewed_audio=include_unreviewed_audio,
                            source_language=source_language,
                        )
                        if apply_level_overrides:
                            agent.apply_level_overrides()
                        success, results = agent.export_wireword_directory()
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
            source_languages=selected_source_languages,
        )

    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        flash("Invalid language selected", "error")
        return redirect(url_for("wireword.export_page"))

    # Handle Chinese variant
    simplified_chinese = True
    if language == "zh":
        chinese_variant = request.form.get("chinese_variant", "simplified")
        if chinese_variant == "traditional":
            simplified_chinese = False
            language = "zh-Hant"

    # Parse optional filters
    difficulty_filter = (
        int(difficulty_level) if difficulty_level and difficulty_level != "all" else None
    )
    pos_filter = pos_type if pos_type and pos_type != "all" else None

    try:
        # Create DataSourceConfig
        config = _get_config()

        # Initialize agent
        agent = UngurysAgent(
            config=config,
            language=language if language != "zh-Hant" else "zh",
            simplified_chinese=simplified_chinese,
            include_unreviewed_audio=include_unreviewed_audio,
            source_language=source_language,
        )

        # Apply level overrides if requested
        override_results = None
        if apply_level_overrides:
            override_results = agent.apply_level_overrides()
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
                source_label = SUPPORTED_SOURCE_LANGUAGES.get(
                    selected_source_language, selected_source_language
                )
                variant_agent = UngurysAgent(
                    config=config,
                    language=language if language != "zh-Hant" else "zh",
                    simplified_chinese=simplified_chinese,
                    include_unreviewed_audio=include_unreviewed_audio,
                    source_language=selected_source_language,
                )
                if apply_level_overrides:
                    variant_agent.apply_level_overrides()
                success, results = variant_agent.export_wireword_directory()
                variant_results[source_label] = {
                    "success": success,
                    "results": results,
                    "output_dir": variant_agent.get_language_output_dir(),
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
            success, results = agent.export_wireword_directory()

            if success:
                files_created = results.get("files_created", [])
                levels_exported = results.get("levels_exported", [])
                subtypes_exported = results.get("subtypes_exported", [])
                sentences_exported = results.get("sentences_exported", 0)

                flash(
                    f'Successfully exported WireWord files for {SUPPORTED_LANGUAGES.get(language if language != "zh-Hant" else "zh", language)}!',
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
                    language_name=SUPPORTED_LANGUAGES.get(
                        language if language != "zh-Hant" else "zh", language
                    ),
                    export_type="directory",
                    files_created=files_created,
                    levels_exported=levels_exported,
                    subtypes_exported=subtypes_exported,
                    output_dir=agent.get_language_output_dir(),
                )
            else:
                flash("Export failed. Check the logs for details.", "error")
                return redirect(url_for("wireword.export_page"))

        elif export_type == "single":
            # Export to a single file - create temp file for download
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            success, stats = agent.export_wireword_single(
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
