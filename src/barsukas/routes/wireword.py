#!/usr/bin/python3

"""Routes for WireWord export functionality."""

import tempfile
from datetime import datetime
from typing import TYPE_CHECKING

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

from agents.ungurys import SUPPORTED_LANGUAGES, UngurysAgent
from wordfreq.storage.backend.config import DataSourceConfig

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

bp = Blueprint("wireword", __name__, url_prefix="/wireword")


def _get_config() -> DataSourceConfig:
    """Get DataSourceConfig from the Flask app's backend_config."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    return app.backend_config


def export_all_languages() -> ResponseReturnValue:
    """Export WireWord files for all supported languages (directory mode only)."""
    try:
        # Create DataSourceConfig
        config = _get_config()

        all_results = {}
        errors = []

        # Export for each supported language
        for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
            try:
                # Handle Chinese: export both Simplified and Traditional
                if lang_code == "zh":
                    # Export Simplified Chinese
                    agent_simplified = UngurysAgent(
                        config=config,
                        language=lang_code,
                        simplified_chinese=True,
                    )
                    success_simp, results_simp = agent_simplified.export_wireword_directory()
                    all_results[f"{lang_name} (Simplified)"] = {
                        "success": success_simp,
                        "results": results_simp,
                    }
                    if not success_simp:
                        errors.append(f"{lang_name} (Simplified)")

                    # Export Traditional Chinese
                    agent_traditional = UngurysAgent(
                        config=config,
                        language=lang_code,
                        simplified_chinese=False,
                    )
                    success_trad, results_trad = agent_traditional.export_wireword_directory()
                    all_results[f"{lang_name} (Traditional)"] = {
                        "success": success_trad,
                        "results": results_trad,
                    }
                    if not success_trad:
                        errors.append(f"{lang_name} (Traditional)")
                else:
                    # Export other languages
                    agent = UngurysAgent(
                        config=config,
                        language=lang_code,
                    )
                    success, results = agent.export_wireword_directory()
                    all_results[lang_name] = {"success": success, "results": results}
                    if not success:
                        errors.append(lang_name)

            except Exception as e:
                errors.append(f"{lang_name}: {str(e)}")
                all_results[lang_name] = {"success": False, "error": str(e)}

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


@bp.route("/")
def export_page() -> ResponseReturnValue:
    """Display the WireWord export page."""
    return render_template("wireword/export.html", languages=SUPPORTED_LANGUAGES)


@bp.route("/export", methods=["POST"])
def export_wireword() -> ResponseReturnValue:
    """Export WireWord files for a specific language."""
    language = request.form.get("language", "").strip()
    export_type = request.form.get("export_type", "directory")
    difficulty_level = request.form.get("difficulty_level", "").strip()
    pos_type = request.form.get("pos_type", "").strip()

    # Handle "All Languages" option
    if language == "all":
        return export_all_languages()

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

        elif export_type == "verbs":
            # Export verbs only
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            success, stats = agent.export_wireword_verbs(
                output_path=tmp_path, difficulty_level=difficulty_filter, include_unverified=True
            )

            if success:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"wireword_verbs_{language}_{timestamp}.json"

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
