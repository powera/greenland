#!/usr/bin/python3

"""Routes for lemma management."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from sqlalchemy import or_, func, case

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.storage.crud.difficulty_override import get_all_overrides_for_lemma, get_effective_difficulty_level
from wordfreq.storage.translation_helpers import get_all_translations, get_supported_languages
from config import Config

bp = Blueprint('lemmas', __name__, url_prefix='/lemmas')


@bp.route('/add', methods=['GET', 'POST'])
def add_lemma():
    """Add a new lemma."""
    from flask import current_app

    if request.method == 'POST':
        if current_app.config.get('READONLY', False):
            flash('Cannot add lemma: running in read-only mode', 'error')
            return redirect(url_for('lemmas.list_lemmas'))

        # Get form data
        lemma_text = request.form.get('lemma_text', '').strip()
        definition_text = request.form.get('definition_text', '').strip()
        pos_type = request.form.get('pos_type', '').strip()
        pos_subtype = request.form.get('pos_subtype', '').strip() or None

        # Validate required fields
        if not lemma_text:
            flash('Lemma text is required', 'error')
            return render_template('lemmas/add.html')

        if not definition_text:
            flash('Definition is required', 'error')
            return render_template('lemmas/add.html')

        if not pos_type:
            flash('POS type is required', 'error')
            return render_template('lemmas/add.html')

        if not pos_subtype:
            flash('POS subtype is required for GUID generation', 'error')
            return render_template('lemmas/add.html')

        # Check if lemma already exists
        existing = g.db.query(Lemma).filter(
            Lemma.lemma_text == lemma_text,
            Lemma.pos_type == pos_type
        ).first()

        if existing:
            flash(f'Lemma "{lemma_text}" with POS type "{pos_type}" already exists', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=existing.id))

        # Generate GUID based on pos_subtype
        from wordfreq.storage.utils.guid import generate_guid
        try:
            guid = generate_guid(g.db, pos_subtype)
        except ValueError as e:
            flash(f'Invalid POS subtype for GUID generation: {e}', 'error')
            return render_template('lemmas/add.html')

        # Create new lemma
        new_lemma = Lemma(
            lemma_text=lemma_text,
            definition_text=definition_text,
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            guid=guid,
            confidence=0.0,
            verified=False
        )

        g.db.add(new_lemma)
        g.db.flush()  # Get the ID

        # Log the creation
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type='lemma_create',
            lemma_id=new_lemma.id,
            field_name='created',
            old_value=None,
            new_value=f'{lemma_text} ({pos_type})'
        )

        g.db.commit()
        flash(f'Created new lemma: {lemma_text}', 'success')
        return redirect(url_for('lemmas.view_lemma', lemma_id=new_lemma.id))

    return render_template('lemmas/add.html')


@bp.route('/')
def list_lemmas():
    """List all lemmas with pagination and filtering."""
    from wordfreq.storage.models.schema import LemmaTranslation

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    pos_type = request.args.get('pos_type', '').strip()
    difficulty = request.args.get('difficulty', '', type=str).strip()

    # Build query
    query = g.db.query(Lemma)

    # Apply filters
    if search:
        # Search in lemma text, definition, disambiguation, and ALL translations
        search_conditions = [
            Lemma.lemma_text.ilike(f'%{search}%'),
            Lemma.definition_text.ilike(f'%{search}%'),
            Lemma.disambiguation.ilike(f'%{search}%'),
            # Search in legacy translation columns
            Lemma.chinese_translation.ilike(f'%{search}%'),
            Lemma.french_translation.ilike(f'%{search}%'),
            Lemma.korean_translation.ilike(f'%{search}%'),
            Lemma.swahili_translation.ilike(f'%{search}%'),
            Lemma.lithuanian_translation.ilike(f'%{search}%'),
            Lemma.vietnamese_translation.ilike(f'%{search}%'),
        ]

        # Also search in LemmaTranslation table
        # Join with LemmaTranslation and search those translations too
        translation_subquery = g.db.query(LemmaTranslation.lemma_id).filter(
            LemmaTranslation.translation.ilike(f'%{search}%')
        )

        search_conditions.append(Lemma.id.in_(translation_subquery))

        query = query.filter(or_(*search_conditions))

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    if difficulty:
        if difficulty == '-1':
            query = query.filter(Lemma.difficulty_level == -1)
        elif difficulty == 'null':
            query = query.filter(Lemma.difficulty_level.is_(None))
        else:
            query = query.filter(Lemma.difficulty_level == int(difficulty))

    # Order by relevance: exact matches first, then starts-with, then contains
    # Use CASE expressions to create a relevance score
    if search:
        search_lower = search.lower()
        relevance = case(
            (func.lower(Lemma.lemma_text) == search_lower, 1),  # Exact match in lemma
            (func.lower(Lemma.lemma_text).startswith(search_lower), 2),  # Starts with in lemma
            (func.lower(Lemma.lemma_text).contains(search_lower), 3),  # Contains in lemma
            (func.lower(Lemma.definition_text).contains(search_lower), 4),  # Contains in definition
            (func.lower(Lemma.disambiguation).contains(search_lower), 5),  # Contains in disambiguation
            # Translation matches
            (func.lower(Lemma.lithuanian_translation).contains(search_lower), 6),
            (func.lower(Lemma.chinese_translation).contains(search_lower), 6),
            (func.lower(Lemma.french_translation).contains(search_lower), 6),
            (func.lower(Lemma.korean_translation).contains(search_lower), 6),
            (func.lower(Lemma.swahili_translation).contains(search_lower), 6),
            (func.lower(Lemma.vietnamese_translation).contains(search_lower), 6),
            else_=7
        )
        query = query.order_by(relevance, Lemma.lemma_text)
    else:
        # No search, just order alphabetically
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
    from wordfreq.storage.models.schema import DerivativeForm, SentenceWord

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

    # Get derivative forms grouped by language
    derivative_forms = g.db.query(DerivativeForm).filter(
        DerivativeForm.lemma_id == lemma_id
    ).order_by(
        DerivativeForm.language_code,
        DerivativeForm.is_base_form.desc(),
        DerivativeForm.grammatical_form
    ).all()

    # Group forms by language and type
    forms_by_language = {}
    synonyms_by_language = {}
    alternative_forms_by_language = {}

    for form in derivative_forms:
        lang_code = form.language_code

        # Separate synonyms and alternative forms
        if form.grammatical_form == 'synonym':
            if lang_code not in synonyms_by_language:
                synonyms_by_language[lang_code] = []
            synonyms_by_language[lang_code].append(form)
        elif form.grammatical_form == 'alternative_form':
            if lang_code not in alternative_forms_by_language:
                alternative_forms_by_language[lang_code] = []
            alternative_forms_by_language[lang_code].append(form)
        else:
            # Regular grammatical forms (conjugations, declensions, etc.)
            if lang_code not in forms_by_language:
                forms_by_language[lang_code] = []
            forms_by_language[lang_code].append(form)

    # Get all languages that have synonyms or alternatives
    all_synonym_languages = sorted(set(list(synonyms_by_language.keys()) + list(alternative_forms_by_language.keys())))

    # Get count of sentences using this lemma (for nouns)
    sentence_count = 0
    if lemma.pos_type == 'noun':
        sentence_count = g.db.query(SentenceWord).filter(
            SentenceWord.lemma_id == lemma_id
        ).count()

    return render_template('lemmas/view.html',
                         lemma=lemma,
                         translations=translations,
                         language_names=language_names,
                         overrides=overrides,
                         effective_levels=effective_levels,
                         difficulty_stats=difficulty_stats,
                         forms_by_language=forms_by_language,
                         synonyms_by_language=synonyms_by_language,
                         alternative_forms_by_language=alternative_forms_by_language,
                         all_synonym_languages=all_synonym_languages,
                         sentence_count=sentence_count)


@bp.route('/<int:lemma_id>/edit', methods=['GET', 'POST'])
def edit_lemma(lemma_id):
    """Edit a lemma."""
    from flask import current_app

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    if request.method == 'POST':
        if current_app.config.get('READONLY', False):
            flash('Cannot update: running in read-only mode', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
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

        new_guid = request.form.get('guid', '').strip() or None
        if new_guid != lemma.guid:
            changes.append(('guid', lemma.guid, new_guid))
            lemma.guid = new_guid

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

        # Handle disambiguation
        new_disambiguation = request.form.get('disambiguation', '').strip() or None
        if new_disambiguation != lemma.disambiguation:
            changes.append(('disambiguation', lemma.disambiguation, new_disambiguation))
            lemma.disambiguation = new_disambiguation

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
