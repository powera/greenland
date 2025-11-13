#!/usr/bin/python3

"""Routes for WireWord export functionality."""

from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file
import os
import tempfile
from datetime import datetime

from agents.ungurys import UngurysAgent, SUPPORTED_LANGUAGES
from config import Config

bp = Blueprint('wireword', __name__, url_prefix='/wireword')


@bp.route('/')
def export_page():
    """Display the WireWord export page."""
    return render_template('wireword/export.html',
                         languages=SUPPORTED_LANGUAGES)


@bp.route('/export', methods=['POST'])
def export_wireword():
    """Export WireWord files for a specific language."""
    language = request.form.get('language', '').strip()
    export_type = request.form.get('export_type', 'directory')
    difficulty_level = request.form.get('difficulty_level', '').strip()
    pos_type = request.form.get('pos_type', '').strip()

    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        flash('Invalid language selected', 'error')
        return redirect(url_for('wireword.export_page'))

    # Handle Chinese variant
    simplified_chinese = True
    if language == 'zh':
        chinese_variant = request.form.get('chinese_variant', 'simplified')
        if chinese_variant == 'traditional':
            simplified_chinese = False
            language = 'zh-Hant'

    # Parse optional filters
    difficulty_filter = int(difficulty_level) if difficulty_level and difficulty_level != 'all' else None
    pos_filter = pos_type if pos_type and pos_type != 'all' else None

    try:
        # Initialize agent
        agent = UngurysAgent(
            db_path=Config.DB_PATH,
            debug=Config.DEBUG,
            language=language if language != 'zh-Hant' else 'zh',
            simplified_chinese=simplified_chinese
        )

        if export_type == 'directory':
            # Export to directory structure
            success, results = agent.export_wireword_directory()

            if success:
                files_created = results.get('files_created', [])
                levels_exported = results.get('levels_exported', [])
                subtypes_exported = results.get('subtypes_exported', [])

                flash(f'Successfully exported WireWord files for {SUPPORTED_LANGUAGES.get(language if language != "zh-Hant" else "zh", language)}!', 'success')
                flash(f'Created {len(files_created)} files for {len(levels_exported)} difficulty levels', 'info')

                return render_template('wireword/results.html',
                                     success=True,
                                     language=language,
                                     language_name=SUPPORTED_LANGUAGES.get(language if language != 'zh-Hant' else 'zh', language),
                                     export_type='directory',
                                     files_created=files_created,
                                     levels_exported=levels_exported,
                                     subtypes_exported=subtypes_exported,
                                     output_dir=agent.get_language_output_dir())
            else:
                flash('Export failed. Check the logs for details.', 'error')
                return redirect(url_for('wireword.export_page'))

        elif export_type == 'single':
            # Export to a single file - create temp file for download
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                tmp_path = tmp_file.name

            success, stats = agent.export_wireword_single(
                output_path=tmp_path,
                difficulty_level=difficulty_filter,
                pos_type=pos_filter,
                include_unverified=True
            )

            if success:
                # Prepare download filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'wireword_{language}_{timestamp}.json'

                return send_file(
                    tmp_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/json'
                )
            else:
                flash('Export failed. Check the logs for details.', 'error')
                return redirect(url_for('wireword.export_page'))

        elif export_type == 'verbs':
            # Export verbs only
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                tmp_path = tmp_file.name

            success, stats = agent.export_wireword_verbs(
                output_path=tmp_path,
                difficulty_level=difficulty_filter,
                include_unverified=True
            )

            if success:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'wireword_verbs_{language}_{timestamp}.json'

                return send_file(
                    tmp_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/json'
                )
            else:
                flash('Export failed. Check the logs for details.', 'error')
                return redirect(url_for('wireword.export_page'))

    except Exception as e:
        flash(f'Error during export: {str(e)}', 'error')
        return redirect(url_for('wireword.export_page'))
