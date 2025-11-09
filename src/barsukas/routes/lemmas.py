#!/usr/bin/python3

"""Routes for lemma management."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from sqlalchemy import or_, func

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.crud.difficulty_override import get_all_overrides_for_lemma, get_effective_difficulty_level
from wordfreq.storage.translation_helpers import get_all_translations, get_supported_languages
from config import Config

bp = Blueprint('lemmas', __name__, url_prefix='/lemmas')


@bp.route('/')
def list_lemmas():
    """List all lemmas with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    pos_type = request.args.get('pos_type', '').strip()
    difficulty = request.args.get('difficulty', '', type=str).strip()

    # Build query
    query = g.db.query(Lemma)

    # Apply filters
    if search:
        query = query.filter(
            or_(
                Lemma.lemma_text.ilike(f'%{search}%'),
                Lemma.definition_text.ilike(f'%{search}%')
            )
        )

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    if difficulty:
        if difficulty == '-1':
            query = query.filter(Lemma.difficulty_level == -1)
        elif difficulty == 'null':
            query = query.filter(Lemma.difficulty_level.is_(None))
        else:
            query = query.filter(Lemma.difficulty_level == int(difficulty))

    # Order by lemma_text
    query = query.order_by(Lemma.lemma_text)

    # Paginate
    total = query.count()
    lemmas = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Get unique POS types for filter dropdown
    pos_types = g.db.query(Lemma.pos_type).distinct().order_by(Lemma.pos_type).all()
    pos_types = [p[0] for p in pos_types if p[0]]

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template('lemmas/list.html',
                         lemmas=lemmas,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         search=search,
                         pos_type=pos_type,
                         difficulty=difficulty,
                         pos_types=pos_types)


@bp.route('/<int:lemma_id>')
def view_lemma(lemma_id):
    """View a single lemma with all details."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get all translations
    translations = get_all_translations(g.db, lemma)
    language_names = get_supported_languages()

    # Get difficulty overrides
    overrides = get_all_overrides_for_lemma(g.db, lemma_id)

    # Calculate effective levels for each language
    effective_levels = {}
    for lang_code in language_names.keys():
        effective_levels[lang_code] = get_effective_difficulty_level(g.db, lemma, lang_code)

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = _get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    return render_template('lemmas/view.html',
                         lemma=lemma,
                         translations=translations,
                         language_names=language_names,
                         overrides=overrides,
                         effective_levels=effective_levels,
                         difficulty_stats=difficulty_stats)


@bp.route('/<int:lemma_id>/edit', methods=['GET', 'POST'])
def edit_lemma(lemma_id):
    """Edit a lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    if request.method == 'POST':
        # Track changes for logging
        changes = []

        # Update basic fields
        new_lemma_text = request.form.get('lemma_text', '').strip()
        if new_lemma_text != lemma.lemma_text:
            changes.append(('lemma_text', lemma.lemma_text, new_lemma_text))
            lemma.lemma_text = new_lemma_text

        new_definition = request.form.get('definition_text', '').strip()
        if new_definition != lemma.definition_text:
            changes.append(('definition_text', lemma.definition_text, new_definition))
            lemma.definition_text = new_definition

        new_pos_type = request.form.get('pos_type', '').strip()
        if new_pos_type != lemma.pos_type:
            changes.append(('pos_type', lemma.pos_type, new_pos_type))
            lemma.pos_type = new_pos_type

        new_pos_subtype = request.form.get('pos_subtype', '').strip() or None
        if new_pos_subtype != lemma.pos_subtype:
            changes.append(('pos_subtype', lemma.pos_subtype, new_pos_subtype))
            lemma.pos_subtype = new_pos_subtype

        # Handle difficulty level
        difficulty_str = request.form.get('difficulty_level', '').strip()
        new_difficulty = None
        if difficulty_str:
            try:
                new_difficulty = int(difficulty_str)
                # Validate
                if new_difficulty != Config.EXCLUDE_DIFFICULTY_LEVEL and \
                   (new_difficulty < Config.MIN_DIFFICULTY_LEVEL or new_difficulty > Config.MAX_DIFFICULTY_LEVEL):
                    flash(f'Difficulty level must be -1 or between {Config.MIN_DIFFICULTY_LEVEL} and {Config.MAX_DIFFICULTY_LEVEL}', 'error')
                    return render_template('lemmas/edit.html', lemma=lemma)
            except ValueError:
                flash('Invalid difficulty level', 'error')
                return render_template('lemmas/edit.html', lemma=lemma)

        if new_difficulty != lemma.difficulty_level:
            changes.append(('difficulty_level', lemma.difficulty_level, new_difficulty))
            lemma.difficulty_level = new_difficulty

        # Handle verified checkbox
        new_verified = request.form.get('verified') == 'on'
        if new_verified != lemma.verified:
            changes.append(('verified', lemma.verified, new_verified))
            lemma.verified = new_verified

        # Handle confidence
        confidence_str = request.form.get('confidence', '').strip()
        if confidence_str:
            try:
                new_confidence = float(confidence_str)
                if new_confidence != lemma.confidence:
                    changes.append(('confidence', lemma.confidence, new_confidence))
                    lemma.confidence = new_confidence
            except ValueError:
                flash('Invalid confidence value', 'error')
                return render_template('lemmas/edit.html', lemma=lemma)

        # Handle notes and tags
        new_notes = request.form.get('notes', '').strip() or None
        if new_notes != lemma.notes:
            changes.append(('notes', lemma.notes, new_notes))
            lemma.notes = new_notes

        new_tags = request.form.get('tags', '').strip() or None
        if new_tags != lemma.tags:
            changes.append(('tags', lemma.tags, new_tags))
            lemma.tags = new_tags

        # Log all changes
        for field_name, old_value, new_value in changes:
            log_translation_change(
                session=g.db,
                source=Config.OPERATION_LOG_SOURCE,
                operation_type='lemma_update',
                lemma_id=lemma.id,
                field_name=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None
            )

        g.db.commit()
        flash(f'Updated lemma: {lemma.lemma_text}', 'success')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma.id))

    # Get difficulty level distribution for same POS type/subtype
    difficulty_stats = _get_difficulty_stats(g.db, lemma.pos_type, lemma.pos_subtype)

    return render_template('lemmas/edit.html', lemma=lemma, difficulty_stats=difficulty_stats)


def _get_difficulty_stats(session, pos_type, pos_subtype):
    """Get difficulty level distribution for a given POS type/subtype."""
    query = session.query(Lemma.difficulty_level, func.count(Lemma.id)).filter(
        Lemma.pos_type == pos_type,
        Lemma.difficulty_level.isnot(None)
    )

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.group_by(Lemma.difficulty_level).order_by(Lemma.difficulty_level)

    results = query.all()

    # Format as a dictionary
    stats = {}
    for level, count in results:
        stats[level] = count

    return stats
