#!/usr/bin/python3

"""Routes for agent operations (voras, vilkas, etc)."""

from flask import Blueprint, request, redirect, url_for, flash, g, jsonify, render_template

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_supported_languages
from wordfreq.agents.voras.agent import VorasAgent
from config import Config

bp = Blueprint('agents', __name__, url_prefix='/agents')


@bp.route('/check-translations/<int:lemma_id>', methods=['POST'])
def check_translations(lemma_id):
    """Check translations for a lemma using the voras agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get language code from form (optional - if not provided, check all)
    lang_code = request.form.get('lang_code')

    try:
        # Initialize voras agent
        agent = VorasAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Gather translations for this word
        from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS
        translations = {}
        for lc in LANGUAGE_FIELDS.keys():
            translation = agent.get_translation(g.db, lemma, lc)
            if translation and translation.strip():
                translations[lc] = translation

        if not translations:
            flash('No translations found to check', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Use the LLM validator to check all translations at once
        from wordfreq.tools.llm_validators import validate_all_translations_for_word
        validation_results = validate_all_translations_for_word(
            lemma.lemma_text,
            translations,
            lemma.pos_type,
            agent.model
        )

        # Format results for display
        issues = []
        all_good = True
        for lc, result in validation_results.items():
            has_issues = not result['is_correct'] or not result['is_lemma_form']
            if has_issues and result['confidence'] >= 0.7:
                all_good = False
                issues.append({
                    'language_code': lc,
                    'language_name': get_supported_languages()[lc],
                    'current': translations[lc],
                    'suggested': result['suggested_translation'],
                    'is_correct': result['is_correct'],
                    'is_lemma_form': result['is_lemma_form'],
                    'issues': result['issues'],
                    'confidence': result['confidence']
                })

        if all_good:
            flash('All translations look good!', 'success')
        else:
            # Store issues in session or pass as query param
            # For now, we'll flash a summary
            flash(f'Found {len(issues)} translation issues. Check the results below.', 'warning')
            # Redirect to a results page or back to lemma view with issues
            return render_template('agents/translation_check_results.html',
                                 lemma=lemma,
                                 issues=issues,
                                 all_good=all_good)

    except Exception as e:
        flash(f'Error checking translations: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
