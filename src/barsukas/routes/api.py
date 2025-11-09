#!/usr/bin/python3

"""API routes for AJAX requests."""

from flask import Blueprint, jsonify, request, g
from sqlalchemy import or_, func

from wordfreq.storage.models.schema import Lemma

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/check_lemma_exists')
def check_lemma_exists():
    """Check if a lemma exists or find similar lemmas."""
    search = request.args.get('search', '').strip()
    pos_type = request.args.get('pos_type', '').strip()

    if not search:
        return jsonify({
            'exact_match': None,
            'similar_matches': []
        })

    # Check for exact match
    exact_query = g.db.query(Lemma).filter(
        func.lower(Lemma.lemma_text) == search.lower()
    )
    if pos_type:
        exact_query = exact_query.filter(Lemma.pos_type == pos_type)

    exact_match = exact_query.first()

    # Find similar matches (case-insensitive LIKE search)
    similar_query = g.db.query(Lemma).filter(
        Lemma.lemma_text.ilike(f'%{search}%')
    )

    # If exact match found, exclude it from similar matches
    if exact_match:
        similar_query = similar_query.filter(Lemma.id != exact_match.id)

    similar_matches = similar_query.limit(5).all()

    return jsonify({
        'exact_match': {
            'id': exact_match.id,
            'lemma_text': exact_match.lemma_text,
            'pos_type': exact_match.pos_type,
            'definition_text': exact_match.definition_text
        } if exact_match else None,
        'similar_matches': [
            {
                'id': lemma.id,
                'lemma_text': lemma.lemma_text,
                'pos_type': lemma.pos_type,
                'definition_text': lemma.definition_text
            }
            for lemma in similar_matches
        ]
    })
