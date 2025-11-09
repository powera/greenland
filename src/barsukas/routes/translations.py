#!/usr/bin/python3

"""Routes for translation management."""

from flask import Blueprint, request, redirect, url_for, flash, g, jsonify

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import set_translation, get_translation, get_supported_languages
from wordfreq.storage.crud.operation_log import log_translation_change
from config import Config

bp = Blueprint('translations', __name__, url_prefix='/translations')


@bp.route('/<int:lemma_id>/<lang_code>', methods=['POST'])
def update_translation(lemma_id, lang_code):
    """Update a translation for a lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Validate language code
    if lang_code not in get_supported_languages():
        flash('Invalid language code', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    # Get new translation value
    new_translation = request.form.get('translation', '').strip()

    if not new_translation:
        flash('Translation cannot be empty', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    # Check for slash warning (will be shown in UI, but we allow it)
    has_slash = '/' in new_translation

    try:
        # Update translation using helper
        old_translation, new_translation = set_translation(g.db, lemma, lang_code, new_translation)

        # Log the change
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type='translation',
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=old_translation,
            new_translation=new_translation
        )

        g.db.commit()

        # Flash message with warning if needed
        message = f'Updated {get_supported_languages()[lang_code]} translation'
        if has_slash:
            message += ' (note: contains "/")'
            flash(message, 'warning')
        else:
            flash(message, 'success')

    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/<int:lemma_id>/<lang_code>/check', methods=['GET'])
def check_translation(lemma_id, lang_code):
    """Check if a translation has a slash (for AJAX validation)."""
    translation = request.args.get('translation', '')
    has_slash = '/' in translation
    return jsonify({'has_slash': has_slash})
