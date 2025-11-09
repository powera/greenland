#!/usr/bin/python3

"""Routes for difficulty override management."""

from flask import Blueprint, request, redirect, url_for, flash, g

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.difficulty_override import (
    add_difficulty_override,
    delete_difficulty_override,
    get_difficulty_override
)
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.translation_helpers import get_supported_languages
from config import Config

bp = Blueprint('overrides', __name__, url_prefix='/overrides')


@bp.route('/<int:lemma_id>/add', methods=['POST'])
def add_override(lemma_id):
    """Add or update a difficulty override."""
    from flask import current_app
    if current_app.config.get('READONLY', False):
        flash('Cannot add override: running in read-only mode', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get form data
    lang_code = request.form.get('language_code', '').strip()
    difficulty_str = request.form.get('difficulty_level', '').strip()
    notes = request.form.get('notes', '').strip() or None

    # Validate language code
    if lang_code not in get_supported_languages():
        flash('Invalid language code', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    # Validate difficulty level
    try:
        difficulty_level = int(difficulty_str)
        if difficulty_level != Config.EXCLUDE_DIFFICULTY_LEVEL and \
           (difficulty_level < Config.MIN_DIFFICULTY_LEVEL or difficulty_level > Config.MAX_DIFFICULTY_LEVEL):
            flash(f'Difficulty level must be -1 or between {Config.MIN_DIFFICULTY_LEVEL} and {Config.MAX_DIFFICULTY_LEVEL}', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
    except ValueError:
        flash('Invalid difficulty level', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    # Check if override already exists
    old_override = get_difficulty_override(g.db, lemma_id, lang_code)
    old_level = old_override.difficulty_level if old_override else None

    # Add/update override
    override = add_difficulty_override(
        session=g.db,
        lemma_id=lemma_id,
        language_code=lang_code,
        difficulty_level=difficulty_level,
        notes=notes
    )

    # Log the change
    log_translation_change(
        session=g.db,
        source=Config.OPERATION_LOG_SOURCE,
        operation_type='difficulty_override_add',
        lemma_id=lemma_id,
        language_code=lang_code,
        old_translation=str(old_level) if old_level is not None else None,
        new_translation=str(difficulty_level),
        notes=notes
    )

    g.db.commit()

    action = 'Updated' if old_override else 'Added'
    lang_name = get_supported_languages()[lang_code]
    flash(f'{action} difficulty override for {lang_name}: Level {difficulty_level}', 'success')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/<int:lemma_id>/<lang_code>/delete', methods=['POST'])
def delete_override(lemma_id, lang_code):
    """Delete a difficulty override."""
    from flask import current_app
    if current_app.config.get('READONLY', False):
        flash('Cannot delete override: running in read-only mode', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get old override for logging
    old_override = get_difficulty_override(g.db, lemma_id, lang_code)
    if not old_override:
        flash('Override not found', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    old_level = old_override.difficulty_level

    # Delete override
    success = delete_difficulty_override(g.db, lemma_id, lang_code)

    if success:
        # Log the deletion
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type='difficulty_override_delete',
            lemma_id=lemma_id,
            language_code=lang_code,
            old_translation=str(old_level),
            new_translation=None
        )

        g.db.commit()

        lang_name = get_supported_languages()[lang_code]
        flash(f'Deleted difficulty override for {lang_name}', 'success')
    else:
        flash('Failed to delete override', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
