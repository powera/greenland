#!/usr/bin/python3

"""Routes for agent operations (voras, vilkas, etc)."""

from flask import Blueprint, request, redirect, url_for, flash, g, jsonify, render_template

from wordfreq.storage.models.schema import Lemma, DerivativeForm
from wordfreq.storage.translation_helpers import get_supported_languages
from wordfreq.agents.voras.agent import VorasAgent
from wordfreq.agents.papuga import PapugaAgent
from wordfreq.agents.vilkas.agent import VilkasAgent
from wordfreq.agents.lokys import LokysAgent
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


@bp.route('/check-pronunciations/<int:lemma_id>', methods=['POST'])
def check_pronunciations(lemma_id):
    """Check pronunciations for a lemma's derivative forms using the PAPUGA agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    try:
        # Get all derivative forms for this lemma that have pronunciations
        forms_with_pronunciations = g.db.query(DerivativeForm).filter(
            DerivativeForm.lemma_id == lemma_id,
            ((DerivativeForm.ipa_pronunciation.isnot(None)) |
             (DerivativeForm.phonetic_pronunciation.isnot(None)))
        ).all()

        if not forms_with_pronunciations:
            flash('No pronunciations found to check', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Initialize PAPUGA agent
        agent = PapugaAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Check pronunciations (using dry_run=False to actually validate)
        from wordfreq.tools.llm_validators import validate_pronunciation
        from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord

        issues = []
        for form in forms_with_pronunciations:
            # Get example sentence for context - find sentences that use the lemma
            example_translation = g.db.query(SentenceTranslation).join(Sentence).join(SentenceWord).filter(
                SentenceWord.lemma_id == lemma_id,
                SentenceTranslation.language_code == 'en'  # Get English version for context
            ).first()
            example_text = example_translation.translation_text if example_translation else None

            result = validate_pronunciation(
                word=form.derivative_form_text,
                ipa_pronunciation=form.ipa_pronunciation,
                phonetic_pronunciation=form.phonetic_pronunciation,
                pos_type=lemma.pos_type,
                example_sentence=example_text,
                definition=lemma.definition_text,
                model='gpt-5-mini'
            )

            if result['needs_update'] and result['confidence'] >= 0.7:
                issues.append({
                    'form_id': form.id,
                    'form_text': form.derivative_form_text,
                    'grammatical_form': form.grammatical_form,
                    'current_ipa': form.ipa_pronunciation,
                    'current_phonetic': form.phonetic_pronunciation,
                    'suggested_ipa': result['suggested_ipa'],
                    'suggested_phonetic': result['suggested_phonetic'],
                    'issues': result['issues'],
                    'confidence': result['confidence']
                })

        if not issues:
            flash('All pronunciations look good!', 'success')
        else:
            flash(f'Found {len(issues)} pronunciation issues', 'warning')
            return render_template('agents/pronunciation_check_results.html',
                                 lemma=lemma,
                                 issues=issues)

    except Exception as e:
        flash(f'Error checking pronunciations: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/generate-pronunciations/<int:lemma_id>', methods=['POST'])
def generate_pronunciations(lemma_id):
    """Generate missing pronunciations for a lemma's derivative forms using the PAPUGA agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get language code from form (default to English)
    lang_code = request.form.get('lang_code', 'en')

    try:
        # Get derivative forms without pronunciations for this lemma
        forms_missing_pronunciations = g.db.query(DerivativeForm).filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == lang_code,
            DerivativeForm.ipa_pronunciation.is_(None),
            DerivativeForm.phonetic_pronunciation.is_(None)
        ).all()

        if not forms_missing_pronunciations:
            flash(f'No missing pronunciations for {lang_code} forms', 'success')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Initialize PAPUGA agent
        agent = PapugaAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Generate pronunciations
        from wordfreq.tools.llm_validators import generate_pronunciation
        from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord

        generated_count = 0
        for form in forms_missing_pronunciations:
            # Get example sentence for context - find sentences that use the lemma
            example_translation = g.db.query(SentenceTranslation).join(Sentence).join(SentenceWord).filter(
                SentenceWord.lemma_id == lemma_id,
                SentenceTranslation.language_code == 'en'  # Get English version for context
            ).first()
            example_text = example_translation.translation_text if example_translation else None

            result = generate_pronunciation(
                word=form.derivative_form_text,
                pos_type=lemma.pos_type,
                definition=lemma.definition_text,
                example_sentence=example_text,
                model='gpt-5-mini'
            )

            # Update the form with generated pronunciations
            if result.get('ipa_pronunciation'):
                form.ipa_pronunciation = result['ipa_pronunciation']
            if result.get('phonetic_pronunciation'):
                form.phonetic_pronunciation = result['phonetic_pronunciation']

            # Count as generated if we got at least one pronunciation
            if result.get('ipa_pronunciation') or result.get('phonetic_pronunciation'):
                generated_count += 1

        if generated_count > 0:
            g.db.commit()
            flash(f'Successfully generated pronunciations for {generated_count} form(s)!', 'success')
        else:
            flash('Could not generate any pronunciations', 'warning')

    except Exception as e:
        g.db.rollback()
        flash(f'Error generating pronunciations: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/generate-forms/<int:lemma_id>', methods=['POST'])
def generate_forms(lemma_id):
    """Generate missing grammatical forms for a lemma using the VILKAS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get language code and pos_type from form
    lang_code = request.form.get('lang_code', 'lt')
    pos_type = request.form.get('pos_type', lemma.pos_type)

    try:
        # Initialize VILKAS agent
        agent = VilkasAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Check if the language/pos_type combination is supported
        # Only languages/POS combinations with individual lemma processing support
        # Note: German, French, Spanish, Portuguese nouns use the new base system
        # and only support batch processing (not available in web interface yet)
        SUPPORTED_LANGUAGES = {
            'lt': ['noun', 'verb', 'adjective'],
            'fr': ['verb'],
            'de': ['verb'],
            'es': ['verb'],
            'pt': ['verb'],
            'en': ['verb']
        }

        if lang_code not in SUPPORTED_LANGUAGES:
            flash(f'Language {lang_code} is not yet supported for form generation', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        if pos_type not in SUPPORTED_LANGUAGES[lang_code]:
            flash(f'POS type {pos_type} is not supported for {lang_code}', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Check if translation exists for this language
        from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS
        translation = None
        if lang_code in LANGUAGE_FIELDS:
            field_name, _, uses_table = LANGUAGE_FIELDS[lang_code]
            if uses_table:
                from wordfreq.storage.models.schema import LemmaTranslation
                trans_obj = g.db.query(LemmaTranslation).filter(
                    LemmaTranslation.lemma_id == lemma_id,
                    LemmaTranslation.language_code == lang_code
                ).first()
                translation = trans_obj.translation if trans_obj else None
            else:
                translation = getattr(lemma, field_name, None)

        if not translation or not translation.strip():
            flash(f'No {lang_code} translation found for this lemma. Add a translation first.', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # For now, we'll use the language-specific generators directly
        # This is a simplified version - a more complete implementation would call
        # the agent's fix_missing_forms for individual lemmas
        from wordfreq.translation.client import LinguisticClient

        client = LinguisticClient(
            model='gpt-5-mini',
            db_path=Config.DB_PATH,
            debug=Config.DEBUG
        )

        # Route to appropriate generator based on language and POS type
        handler_key = f"{lang_code}_{pos_type}"

        # Import the appropriate generator
        if handler_key == 'lt_noun':
            from wordfreq.translation.generate_lithuanian_noun_forms import process_lemma_declensions
            success = process_lemma_declensions(g.db, lemma, client, source='llm')
        elif handler_key == 'lt_verb':
            from wordfreq.translation.generate_lithuanian_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        elif handler_key == 'lt_adjective':
            from wordfreq.translation.generate_lithuanian_adjective_forms import process_lemma_adjective_forms
            success = process_lemma_adjective_forms(g.db, lemma, client)
        elif handler_key == 'fr_verb':
            from wordfreq.translation.generate_french_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        elif handler_key == 'de_verb':
            from wordfreq.translation.generate_german_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        elif handler_key == 'es_verb':
            from wordfreq.translation.generate_spanish_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        elif handler_key == 'pt_verb':
            from wordfreq.translation.generate_portuguese_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        elif handler_key == 'en_verb':
            from wordfreq.translation.generate_english_verb_forms import process_lemma_conjugations
            success = process_lemma_conjugations(g.db, lemma, client)
        else:
            flash(f'Handler not implemented for {lang_code} {pos_type}', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        if success:
            flash(f'Successfully generated {lang_code} {pos_type} forms!', 'success')
        else:
            flash(f'Could not generate {lang_code} {pos_type} forms', 'warning')

    except Exception as e:
        flash(f'Error generating forms: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/generate-synonyms/<int:lemma_id>', methods=['POST'])
def generate_synonyms(lemma_id):
    """Generate synonyms and alternative forms for a lemma using the ŠERNAS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get language code from form
    lang_code = request.form.get('lang_code', 'en')

    try:
        # Initialize ŠERNAS agent
        from wordfreq.agents.sernas.agent import SernasAgent
        agent = SernasAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Check if translation exists for this language (skip for English since that's the lemma itself)
        if lang_code != 'en':
            from wordfreq.storage.translation_helpers import get_translation
            translation = get_translation(g.db, lemma, lang_code)

            if not translation or not translation.strip():
                flash(f'No {lang_code} translation found for this lemma. Add a translation first.', 'warning')
                return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Generate synonyms for this lemma and language
        result = agent.generate_synonyms_for_lemma(
            lemma_id=lemma_id,
            language_code=lang_code,
            model='gpt-5-mini',
            dry_run=False
        )

        if 'error' in result:
            flash(f'Error: {result["error"]}', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Show results
        synonyms_count = result.get('stored_synonyms', 0)
        # Sum all alternative form types (new specific types + legacy)
        alternatives_count = (
            result.get('stored_abbreviations', 0) +
            result.get('stored_expanded', 0) +
            result.get('stored_spellings', 0) +
            result.get('stored_alternatives', 0)  # Legacy field for backward compatibility
        )
        total_count = synonyms_count + alternatives_count

        if total_count > 0:
            flash(f'Successfully generated {synonyms_count} synonym(s) and {alternatives_count} alternative form(s)!', 'success')
        else:
            flash('No synonyms or alternative forms were generated. This word may not have common synonyms.', 'info')

    except Exception as e:
        flash(f'Error generating synonyms: {str(e)}', 'error')
        import traceback
        if Config.DEBUG:
            flash(f'Debug: {traceback.format_exc()}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/check-definition/<int:lemma_id>', methods=['POST'])
def check_definition(lemma_id):
    """Check/improve the definition of a lemma using the LOKYS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    try:
        # Initialize LOKYS agent
        agent = LokysAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Validate definition
        from wordfreq.tools.llm_validators import validate_definition

        result = validate_definition(
            word=lemma.lemma_text,
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            model='gpt-5-mini'
        )

        if result['is_valid'] and result['confidence'] >= 0.7:
            flash('Definition looks good!', 'success')
        else:
            # Show issues and suggested improvement
            return render_template('agents/definition_check_results.html',
                                 lemma=lemma,
                                 result=result)

    except Exception as e:
        flash(f'Error checking definition: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/apply-definition/<int:lemma_id>', methods=['POST'])
def apply_definition(lemma_id):
    """Apply a suggested definition improvement."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    new_definition = request.form.get('new_definition')
    if not new_definition:
        flash('No new definition provided', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    try:
        old_definition = lemma.definition_text
        lemma.definition_text = new_definition
        g.db.commit()

        # Log the change
        from wordfreq.storage.crud.operation_log import log_operation
        log_operation(
            g.db,
            source='barsukas-web-interface',
            operation_type='definition_update',
            fact={
                'lemma_id': lemma_id,
                'lemma_text': lemma.lemma_text,
                'old_definition': old_definition,
                'new_definition': new_definition
            },
            lemma_id=lemma_id
        )

        flash('Definition updated successfully!', 'success')
    except Exception as e:
        g.db.rollback()
        flash(f'Error updating definition: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/check-disambiguation/<int:lemma_id>', methods=['POST'])
def check_disambiguation(lemma_id):
    """Check if a lemma needs disambiguation (parentheticals) using the LOKYS agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    try:
        # Initialize LOKYS agent
        agent = LokysAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Check for lemmas with the same lemma_text
        duplicates = g.db.query(Lemma).filter(
            Lemma.lemma_text == lemma.lemma_text,
            Lemma.guid.isnot(None)
        ).all()

        if len(duplicates) <= 1:
            flash(f'No other lemmas found with lemma_text "{lemma.lemma_text}" - disambiguation not needed', 'info')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Check if translations differ
        from wordfreq.storage.translation_helpers import get_supported_languages, get_translation

        supported_languages = get_supported_languages()
        translations_by_guid = {}

        for dup in duplicates:
            translations = {}
            for lang_code in supported_languages.keys():
                try:
                    translation = get_translation(g.db, dup, lang_code)
                    if translation:
                        translations[lang_code] = translation
                except ValueError:
                    continue
            translations_by_guid[dup.guid] = translations

        # Check if any translations differ
        translations_differ = False
        if len(translations_by_guid) > 1:
            guids = list(translations_by_guid.keys())
            for i in range(len(guids)):
                for j in range(i + 1, len(guids)):
                    trans_i = translations_by_guid[guids[i]]
                    trans_j = translations_by_guid[guids[j]]

                    # Check if any shared language has different translations
                    for lang in set(trans_i.keys()) & set(trans_j.keys()):
                        if trans_i[lang] != trans_j[lang]:
                            translations_differ = True
                            break
                    if translations_differ:
                        break

        if not translations_differ:
            flash(f'Found {len(duplicates)} lemmas with "{lemma.lemma_text}", but translations are the same - may be duplicates', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Check if this lemma has parentheticals
        has_parenthetical = '(' in lemma.lemma_text and ')' in lemma.lemma_text

        if has_parenthetical:
            flash(f'This lemma already has disambiguation: "{lemma.lemma_text}"', 'success')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Get LLM suggestions for disambiguation
        from wordfreq.tools.llm_validators import suggest_disambiguation

        definitions_data = []
        for dup in duplicates:
            item = {
                'guid': dup.guid,
                'definition': dup.definition_text or 'No definition',
                'translations': {}
            }
            for lang_code in supported_languages.keys():
                try:
                    trans = get_translation(g.db, dup, lang_code)
                    if trans:
                        item['translations'][lang_code] = trans
                except ValueError:
                    continue
            definitions_data.append(item)

        llm_result = suggest_disambiguation(
            word=lemma.lemma_text,
            definitions=definitions_data,
            model='gpt-5-mini'
        )

        if llm_result['success'] and llm_result['suggestions']:
            # Render a results page with suggestions
            return render_template('agents/disambiguation_suggestions.html',
                                 lemma=lemma,
                                 duplicates=duplicates,
                                 suggestions=llm_result['suggestions'],
                                 lemma_text=lemma.lemma_text)
        else:
            flash(f'⚠️ This lemma needs disambiguation! Found {len(duplicates)} different meanings for "{lemma.lemma_text}" with different translations', 'warning')
            flash(f'Consider adding parentheticals like: "{lemma.lemma_text} (animal)", "{lemma.lemma_text} (computer)", etc.', 'info')

    except Exception as e:
        flash(f'Error checking disambiguation: {str(e)}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/apply-disambiguation/<int:lemma_id>', methods=['POST'])
def apply_disambiguation(lemma_id):
    """Apply an AI-suggested disambiguation to a lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    new_lemma_text = request.form.get('new_lemma_text')
    return_to_suggestions = request.form.get('return_to_suggestions') == 'true'
    original_lemma_id = request.form.get('original_lemma_id', type=int)

    if not new_lemma_text:
        flash('No disambiguation provided', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

    try:
        old_lemma_text = lemma.lemma_text
        lemma.lemma_text = new_lemma_text
        g.db.commit()

        # Log the change
        from wordfreq.storage.crud.operation_log import log_translation_change
        log_translation_change(
            g.db,
            source='barsukas-web-interface',
            operation_type='lemma_text_update',
            lemma_id=lemma_id,
            old_lemma_text=old_lemma_text,
            new_lemma_text=new_lemma_text,
            guid=lemma.guid,
            change_source='ai_disambiguation_suggestion'
        )

        flash(f'✓ Updated GUID {lemma.guid}: "{old_lemma_text}" → "{new_lemma_text}"', 'success')
    except Exception as e:
        g.db.rollback()
        flash(f'Error applying disambiguation: {str(e)}', 'error')

    # Stay on suggestions page if requested, otherwise go to the updated lemma
    if return_to_suggestions and original_lemma_id:
        # Re-run the check to show updated suggestions page
        return redirect(url_for('agents.check_disambiguation', lemma_id=original_lemma_id))

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/generate-sentences/<int:lemma_id>', methods=['POST'])
def generate_sentences(lemma_id):
    """Generate example sentences for a lemma using the Žvirblis agent."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    # Get parameters from form
    num_sentences = int(request.form.get('num_sentences', 3))
    # Get languages from checkboxes (multiple values with same name)
    languages = request.form.getlist('languages')
    # Always include English as the source language
    if 'en' not in languages:
        languages = ['en'] + languages
    # Remove empty strings
    languages = [lang.strip() for lang in languages if lang.strip()]

    try:
        # Import Žvirblis agent
        from wordfreq.agents.zvirblis import ZvirblisAgent
        from wordfreq.storage.models.schema import Sentence

        # Initialize agent
        agent = ZvirblisAgent(db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Generate sentences
        result = agent.generate_sentences_for_noun(
            lemma=lemma,
            target_languages=languages,
            num_sentences=num_sentences,
            difficulty_context=lemma.difficulty_level
        )

        if not result.get('success'):
            flash(f'Failed to generate sentences: {result.get("error", "Unknown error")}', 'error')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        # Store the generated sentences
        sentences_data = result.get('sentences', [])
        if not sentences_data:
            flash('No sentences were generated', 'warning')
            return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))

        store_result = agent.store_sentences(
            sentences_data=sentences_data,
            source_lemma=lemma,
            session=g.db
        )

        if store_result['stored'] > 0:
            flash(f'Successfully generated and stored {store_result["stored"]} sentence(s)!', 'success')

            # Get the newly created sentences using the IDs returned from store_sentences
            sentence_ids = store_result.get('sentence_ids', [])
            if sentence_ids:
                sentences = g.db.query(Sentence).filter(
                    Sentence.id.in_(sentence_ids)
                ).all()
            else:
                sentences = []

            # Show the results
            return render_template('agents/sentence_generation_results.html',
                                 lemma=lemma,
                                 sentences=sentences,
                                 generated_count=store_result['stored'])
        else:
            flash('Failed to store generated sentences', 'error')
            if store_result.get('errors'):
                for error in store_result['errors'][:3]:  # Show first 3 errors
                    flash(f'Error: {error}', 'error')

    except Exception as e:
        flash(f'Error generating sentences: {str(e)}', 'error')
        import traceback
        if Config.DEBUG:
            flash(f'Debug: {traceback.format_exc()}', 'error')

    return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))


@bp.route('/view-sentences/<int:lemma_id>')
def view_sentences(lemma_id):
    """View all sentences that use a specific lemma."""
    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash('Lemma not found', 'error')
        return redirect(url_for('lemmas.list_lemmas'))

    try:
        # Query sentences that use this lemma
        from wordfreq.storage.models.schema import Sentence, SentenceWord
        from sqlalchemy.orm import joinedload

        sentences = g.db.query(Sentence).join(SentenceWord).filter(
            SentenceWord.lemma_id == lemma_id
        ).options(
            joinedload(Sentence.translations),
            joinedload(Sentence.words)
        ).order_by(Sentence.id.desc()).all()

        return render_template('agents/view_sentences.html',
                             lemma=lemma,
                             sentences=sentences)

    except Exception as e:
        flash(f'Error viewing sentences: {str(e)}', 'error')
        return redirect(url_for('lemmas.view_lemma', lemma_id=lemma_id))
