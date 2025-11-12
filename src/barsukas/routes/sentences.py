#!/usr/bin/python3

"""Routes for sentence management."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from sqlalchemy import or_, func, case

from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord, Lemma
from wordfreq.storage.translation_helpers import get_supported_languages
from config import Config

bp = Blueprint('sentences', __name__, url_prefix='/sentences')


@bp.route('/')
def list_sentences():
    """List all sentences with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    pattern_type = request.args.get('pattern_type', '').strip()
    minimum_level = request.args.get('minimum_level', '', type=str).strip()

    # Build query
    query = g.db.query(Sentence)

    # Apply filters
    if search:
        # Search in sentence translations (any language)
        translation_subquery = g.db.query(SentenceTranslation.sentence_id).filter(
            SentenceTranslation.translation_text.ilike(f'%{search}%')
        )
        query = query.filter(Sentence.id.in_(translation_subquery))

    if pattern_type:
        query = query.filter(Sentence.pattern_type == pattern_type)

    if minimum_level:
        if minimum_level == 'null':
            query = query.filter(Sentence.minimum_level.is_(None))
        else:
            query = query.filter(Sentence.minimum_level == int(minimum_level))

    # Order by minimum level (NULL at end), then by ID
    level_order = case(
        (Sentence.minimum_level.is_(None), 99),  # NULL levels last
        else_=Sentence.minimum_level
    )
    query = query.order_by(level_order, Sentence.id)

    # Paginate
    total = query.count()
    sentences = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Get unique pattern types for filter dropdown
    pattern_types = g.db.query(Sentence.pattern_type).distinct().order_by(Sentence.pattern_type).all()
    pattern_types = [p[0] for p in pattern_types if p[0]]

    # For each sentence, get a preview of the English translation (if available)
    sentence_previews = {}
    for sentence in sentences:
        # Get English translation for preview
        en_translation = g.db.query(SentenceTranslation).filter(
            SentenceTranslation.sentence_id == sentence.id,
            SentenceTranslation.language_code == 'en'
        ).first()
        if en_translation:
            sentence_previews[sentence.id] = en_translation.translation_text
        else:
            # Fall back to any translation
            any_translation = g.db.query(SentenceTranslation).filter(
                SentenceTranslation.sentence_id == sentence.id
            ).first()
            sentence_previews[sentence.id] = any_translation.translation_text if any_translation else '(No translation)'

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template('sentences/list.html',
                         sentences=sentences,
                         sentence_previews=sentence_previews,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         search=search,
                         pattern_type=pattern_type,
                         minimum_level=minimum_level,
                         pattern_types=pattern_types)


@bp.route('/<int:sentence_id>')
def view_sentence(sentence_id):
    """View a single sentence with all translations."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash('Sentence not found', 'error')
        return redirect(url_for('sentences.list_sentences'))

    # Get all translations
    translations_query = g.db.query(SentenceTranslation).filter(
        SentenceTranslation.sentence_id == sentence_id
    ).order_by(SentenceTranslation.language_code).all()

    # Convert to dict keyed by language code
    translations = {t.language_code: t.translation_text for t in translations_query}
    language_names = get_supported_languages()

    # Get words used in the sentence (with lemma information)
    sentence_words = g.db.query(SentenceWord).filter(
        SentenceWord.sentence_id == sentence_id
    ).order_by(
        SentenceWord.language_code,
        SentenceWord.position
    ).all()

    # Group by language
    words_by_language = {}
    for sw in sentence_words:
        if sw.language_code not in words_by_language:
            words_by_language[sw.language_code] = []

        # Get lemma details if available
        lemma = None
        if sw.lemma_id:
            lemma = g.db.query(Lemma).get(sw.lemma_id)

        words_by_language[sw.language_code].append({
            'position': sw.position,
            'role': sw.word_role,
            'english_text': sw.english_text,
            'target_text': sw.target_language_text,
            'lemma': lemma,
            'lemma_id': sw.lemma_id
        })

    return render_template('sentences/view.html',
                         sentence=sentence,
                         translations=translations,
                         language_names=language_names,
                         words_by_language=words_by_language)
