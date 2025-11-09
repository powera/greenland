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


@bp.route('/add-missing-translations/<int:lemma_id>', methods=['POST'])
def add_missing_translations(lemma_id):
    """Add missing translations for a lemma using the voras agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    try:
        # Initialize voras agent
        agent = VorasAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Find missing translations
        from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS
        missing_languages = []
        for lc in LANGUAGE_FIELDS.keys():
            translation = agent.get_translation(g.db, lemma, lc)
            if not translation or not translation.strip():
                missing_languages.append(lc)

        if not missing_languages:
            flash('No missing translations found - all languages already have translations!', 'success')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Use voras agent to fix missing translations for this single lemma
        # We need at least one non-English translation to use as context
        # Find any existing translation to use as the "reference" translation
        reference_translation = None
        reference_lang_code = None

        # Prefer Lithuanian, but use any available translation as fallback
        for lc in ['lt', 'zh', 'ko', 'fr', 'es', 'de', 'pt', 'sw', 'vi']:
            if lc not in missing_languages:
                translation = agent.get_translation(g.db, lemma, lc)
                if translation and translation.strip():
                    reference_translation = translation
                    reference_lang_code = lc
                    break

        if not reference_translation:
            flash('Cannot generate translations: at least one existing translation is required for context', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        from wordfreq.translation.client import LinguisticClient
        client = LinguisticClient(
            model=agent.model,
            db_path=Config.DB_PATH,
            debug=Config.DEBUG
        )

        # Map language codes to language names for query_translations
        lang_code_to_name = {
            'zh': 'chinese',
            'ko': 'korean',
            'fr': 'french',
            'es': 'spanish',
            'de': 'german',
            'pt': 'portuguese',
            'sw': 'swahili',
            'vi': 'vietnamese',
            'lt': 'lithuanian'
        }
        missing_lang_names = [
            lang_code_to_name[lang_code]
            for lang_code in missing_languages
            if lang_code in lang_code_to_name
        ]

        if not missing_lang_names:
            flash('No valid languages to generate', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Query LLM for missing translations - ONE CALL
        # Use the reference translation tuple for context
        # The LLM uses this as a second language hint for accuracy
        translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(reference_lang_code, reference_translation),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=missing_lang_names
        )

        if not success or not translations:
            flash('Failed to generate translations', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Map language codes to LLM response field names
        translation_field_map = {
            'zh': 'chinese_translation',
            'ko': 'korean_translation',
            'fr': 'french_translation',
            'es': 'spanish_translation',
            'de': 'german_translation',
            'pt': 'portuguese_translation',
            'sw': 'swahili_translation',
            'vi': 'vietnamese_translation',
            'lt': 'lithuanian_translation'
        }

        added_count = 0
        for lang_code in missing_languages:
            llm_field = translation_field_map.get(lang_code)
            translation = translations.get(llm_field, '').strip()

            if translation:
                # Update the translation using agent's method which includes logging
                agent.set_translation(g.db, lemma, lang_code, translation)
                added_count += 1

        if added_count > 0:
            flash(f'Successfully added {added_count} missing translation(s)!', 'success')
        else:
            flash('Could not generate any missing translations', 'warning')

    except Exception as e:
        flash(f'Error adding missing translations: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
