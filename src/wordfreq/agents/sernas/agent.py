"""
Šernas - Synonym and Alternative Form Generator Agent

This agent generates synonyms and alternative forms for lemmas across all supported
languages. It distinguishes between:
- Abbreviations: Shortened forms (e.g., "television" → "TV", "Doctor" → "Dr.")
- Expanded forms: Longer/fuller forms (e.g., "thousand" → "one thousand", "TV" → "television")
- Alternate spellings: Spelling variants (e.g., "gray" → "grey", "color" → "colour")
- Synonyms: Different words with similar meanings (e.g., "street" → "road", "mad" → "angry")

"Šernas" means "boar" in Lithuanian - persistent in finding similar things.

Supported languages:
- English (en)
- Lithuanian (lt)
- Chinese (zh)
- Korean (ko)
- French (fr)
- Spanish (es)
- German (de)
- Portuguese (pt)
- Swahili (sw)
- Vietnamese (vi)
"""

import logging
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, DerivativeForm
from wordfreq.storage.crud.derivative_form import add_derivative_form
from wordfreq.storage.crud.word_token import add_word_token
from wordfreq.storage.crud.grammar_fact import add_grammar_fact, get_alternate_forms_facts
from wordfreq.storage.translation_helpers import get_translation, get_supported_languages
from wordfreq.translation.client import LinguisticClient

# Configure logging
logger = logging.getLogger(__name__)


class SernasAgent:
    """Agent for generating synonyms and alternative forms across multiple languages."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Šernas agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def _is_numeral(self, text: str) -> bool:
        """
        Check if a string is primarily a numeral or numeral variant.

        Args:
            text: The text to check

        Returns:
            True if the text is a numeral (e.g., "1000", "42", "1K", "4th"), False otherwise
        """
        if not text:
            return False

        # Strip whitespace
        text = text.strip()

        # Check if it's purely digits
        if text.isdigit():
            return True

        import re

        # Check if it's a number with common separators (1,000 or 1.000)
        if re.match(r'^[\d,.\s]+$', text):
            return True

        # Check for abbreviated numbers with K/M/B suffix (1K, 2.5M, etc.)
        if re.match(r'^\d+[.,]?\d*[KMBkmb]$', text):
            return True

        # Check for ordinal numbers (1st, 2nd, 3rd, 4th, etc.)
        if re.match(r'^\d+(st|nd|rd|th)$', text, re.IGNORECASE):
            return True

        return False

    def check_missing_synonyms(
        self,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Check for lemmas missing synonyms or alternative forms.

        Args:
            language_code: Language to check (e.g., 'en', 'lt'). If None, check all.
            form_type: Type to check (e.g., 'synonym', 'abbreviation', 'expanded_form', 'alternate_spelling').
                      If None, checks all types.

        Returns:
            Dictionary with check results
        """
        logger.info(f"Checking for lemmas missing synonyms/alternative forms...")

        session = self.get_session()
        try:
            # Get all lemmas
            lemmas = session.query(Lemma).all()
            logger.info(f"Found {len(lemmas)} lemmas in database")

            # Determine which language codes to check
            if language_code:
                lang_codes = [language_code]
            else:
                lang_codes = ['en'] + list(get_supported_languages().keys())

            # Determine which form types to check
            if form_type:
                form_types = [form_type]
            else:
                # Check all types (including legacy 'alternative_form')
                form_types = ['synonym', 'abbreviation', 'expanded_form', 'alternate_spelling', 'alternative_form']

            missing_by_language = {}
            for lang in lang_codes:
                missing_by_language[lang] = []

            for lemma in lemmas:
                for lang in lang_codes:
                    # Get the translation for this language
                    if lang == 'en':
                        translation = lemma.lemma_text
                    else:
                        translation = get_translation(session, lemma, lang)

                    # Skip if no translation exists
                    if not translation or not translation.strip():
                        continue

                    # Check if alternate forms facts have been recorded for this lemma/language
                    facts = get_alternate_forms_facts(session, lemma.id, lang)

                    # If no facts recorded, we need to run ŠERNAS
                    if facts is None:
                        missing_by_language[lang].append({
                            'guid': lemma.guid,
                            'english': lemma.lemma_text,
                            'translation': translation,
                            'pos_type': lemma.pos_type,
                            'pos_subtype': lemma.pos_subtype,
                            'difficulty_level': lemma.difficulty_level
                        })
                    # If form_type is specified, check if that specific fact is missing
                    elif form_type:
                        fact_key = f"has_{form_type}s" if not form_type.endswith('s') else f"has_{form_type}"
                        if fact_key not in facts:
                            missing_by_language[lang].append({
                                'guid': lemma.guid,
                                'english': lemma.lemma_text,
                                'translation': translation,
                                'pos_type': lemma.pos_type,
                                'pos_subtype': lemma.pos_subtype,
                                'difficulty_level': lemma.difficulty_level
                            })

            # Calculate statistics
            total_missing = sum(len(items) for items in missing_by_language.values())

            logger.info(f"Found {total_missing} lemmas missing synonyms/alternatives across all languages")

            return {
                'total_missing': total_missing,
                'missing_by_language': missing_by_language,
                'checked_languages': lang_codes,
                'checked_form_types': form_types
            }

        except Exception as e:
            logger.error(f"Error checking missing synonyms: {e}")
            return {
                'error': str(e),
                'total_missing': 0,
                'missing_by_language': {}
            }
        finally:
            session.close()

    def generate_synonyms_for_lemma(
        self,
        lemma_id: int,
        language_code: str,
        model: str = 'gpt-5-mini',
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate synonyms and alternative forms for a specific lemma and language.

        Args:
            lemma_id: ID of the lemma
            language_code: Language code (e.g., 'en', 'lt', 'zh')
            model: LLM model to use
            dry_run: If True, only show what would be generated without saving

        Returns:
            Dictionary with generated forms
        """
        session = self.get_session()
        try:
            # Get the lemma
            lemma = session.query(Lemma).get(lemma_id)
            if not lemma:
                return {'error': f'Lemma ID {lemma_id} not found'}

            # Get the translation for the target language
            if language_code == 'en':
                word = lemma.lemma_text
            else:
                word = get_translation(session, lemma, language_code)

            if not word or not word.strip():
                return {
                    'error': f'No translation found for language {language_code}',
                    'lemma_id': lemma_id,
                    'language_code': language_code
                }

            logger.info(f"Generating synonyms for '{word}' ({language_code})")

            # Initialize LLM client
            client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

            # Generate synonyms using LLM
            result = self._query_synonyms(
                client=client,
                word=word,
                language_code=language_code,
                pos_type=lemma.pos_type,
                definition=lemma.definition_text,
                english_word=lemma.lemma_text
            )

            if not result['success']:
                return {
                    'error': result.get('error', 'Failed to generate synonyms'),
                    'lemma_id': lemma_id,
                    'language_code': language_code
                }

            # Extract results and filter out numerals
            synonyms = [s for s in result.get('synonyms', []) if not self._is_numeral(s)]
            abbreviations = [a for a in result.get('abbreviations', []) if not self._is_numeral(a)]
            expanded_forms = [e for e in result.get('expanded_forms', []) if not self._is_numeral(e)]
            alternate_spellings = [a for a in result.get('alternate_spellings', []) if not self._is_numeral(a)]

            if dry_run:
                return {
                    'dry_run': True,
                    'lemma_id': lemma_id,
                    'language_code': language_code,
                    'word': word,
                    'synonyms': synonyms,
                    'abbreviations': abbreviations,
                    'expanded_forms': expanded_forms,
                    'alternate_spellings': alternate_spellings,
                    'total_count': len(synonyms) + len(abbreviations) + len(expanded_forms) + len(alternate_spellings)
                }

            # Store the forms in the database
            stored_synonyms = 0
            stored_abbreviations = 0
            stored_expanded = 0
            stored_spellings = 0

            for synonym in synonyms:
                try:
                    word_token = add_word_token(session, synonym, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=synonym,
                        language_code=language_code,
                        grammatical_form='synonym',
                        word_token=word_token,
                        verified=False
                    )
                    stored_synonyms += 1
                except Exception as e:
                    logger.warning(f"Failed to store synonym '{synonym}': {e}")

            for abbr in abbreviations:
                try:
                    word_token = add_word_token(session, abbr, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=abbr,
                        language_code=language_code,
                        grammatical_form='abbreviation',
                        word_token=word_token,
                        verified=False
                    )
                    stored_abbreviations += 1
                except Exception as e:
                    logger.warning(f"Failed to store abbreviation '{abbr}': {e}")

            for exp_form in expanded_forms:
                try:
                    word_token = add_word_token(session, exp_form, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=exp_form,
                        language_code=language_code,
                        grammatical_form='expanded_form',
                        word_token=word_token,
                        verified=False
                    )
                    stored_expanded += 1
                except Exception as e:
                    logger.warning(f"Failed to store expanded form '{exp_form}': {e}")

            for alt_spelling in alternate_spellings:
                try:
                    word_token = add_word_token(session, alt_spelling, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=alt_spelling,
                        language_code=language_code,
                        grammatical_form='alternate_spelling',
                        word_token=word_token,
                        verified=False
                    )
                    stored_spellings += 1
                except Exception as e:
                    logger.warning(f"Failed to store alternate spelling '{alt_spelling}': {e}")

            # Record grammar facts to track what ŠERNAS found (or didn't find)
            add_grammar_fact(session, lemma.id, language_code, "has_synonyms",
                           "true" if stored_synonyms > 0 else "false", verified=True)
            add_grammar_fact(session, lemma.id, language_code, "has_abbreviations",
                           "true" if stored_abbreviations > 0 else "false", verified=True)
            add_grammar_fact(session, lemma.id, language_code, "has_expanded_forms",
                           "true" if stored_expanded > 0 else "false", verified=True)
            add_grammar_fact(session, lemma.id, language_code, "has_alternate_spellings",
                           "true" if stored_spellings > 0 else "false", verified=True)

            session.commit()

            logger.info(f"Stored {stored_synonyms} synonyms, {stored_abbreviations} abbreviations, {stored_expanded} expanded forms, and {stored_spellings} alternate spellings")

            return {
                'success': True,
                'lemma_id': lemma_id,
                'language_code': language_code,
                'word': word,
                'synonyms': synonyms,
                'abbreviations': abbreviations,
                'expanded_forms': expanded_forms,
                'alternate_spellings': alternate_spellings,
                'stored_synonyms': stored_synonyms,
                'stored_abbreviations': stored_abbreviations,
                'stored_expanded': stored_expanded,
                'stored_spellings': stored_spellings
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error generating synonyms for lemma {lemma_id}: {e}")
            return {
                'error': str(e),
                'lemma_id': lemma_id,
                'language_code': language_code
            }
        finally:
            session.close()

    def _query_synonyms(
        self,
        client: LinguisticClient,
        word: str,
        language_code: str,
        pos_type: str,
        definition: str,
        english_word: str
    ) -> Dict[str, any]:
        """
        Query LLM for synonyms and alternative forms.

        Args:
            client: LinguisticClient instance
            word: The word to find synonyms for
            language_code: Language code
            pos_type: Part of speech
            definition: English definition
            english_word: Original English lemma (for context)

        Returns:
            Dictionary with synonyms, alternative_forms, and success flag
        """
        # Get language name
        language_names = get_supported_languages()
        if language_code == 'en':
            language_name = 'English'
        else:
            language_name = language_names.get(language_code, language_code)

        # Build the prompt
        prompt = f"""You are a linguistic expert helping to generate synonyms and alternative forms for vocabulary learning software called Trakaido.

**Task:** For the {language_name} word "{word}" (part of speech: {pos_type}), generate:
1. **Abbreviations**: Shortened forms of the word (e.g., "television" → "TV", "Doctor" → "Dr.", "Avenue" → "Ave")
2. **Expanded forms**: Longer/fuller forms of the word (e.g., "thousand" → "one thousand", "TV" → "television", "Dr." → "Doctor")
3. **Alternate spellings**: Spelling variants of the SAME word (e.g., "gray" → "grey", "color" → "colour", "doughnut" → "donut")
4. **Synonyms**: Words that can be used INTERCHANGEABLY in most contexts (e.g., "street" → "road", "mad" → "angry", "start" → "begin")

**Context:**
- English lemma: {english_word}
- Definition: {definition}
- This is for language learning, so focus on common, useful forms that learners might encounter
- Consider whether forms would be appropriate/correct in Trakaido learning context

**IMPORTANT Guidelines:**
- For abbreviations: Only include shortened forms of the same word (initialisms, truncations, contractions)
- For expanded_forms: Only include longer/fuller versions of the same word or phrase
- For alternate_spellings: Only include different spelling variations (regional, historical, informal spellings)
- For synonyms: ONLY include words that can replace the original in MOST contexts
  * Do NOT include hyponyms (specific types): "cheddar" is NOT a synonym of "cheese"
  * Do NOT include hypernyms (categories): "dairy product" is NOT a synonym of "cheese"
  * Do NOT include related words: "fromage" is NOT a synonym of "cheese" (it's the same word in another language)
  * Do NOT include examples or variants of the thing
  * TRUE synonyms are rare - most words will have ZERO synonyms
- **RETURN EMPTY ARRAYS when no valid forms exist** - this is completely normal and expected
- Most words will have ZERO items in most categories - only return items when they genuinely exist
- Do NOT make up forms, add explanations, or include text like "(no common alternate spelling)"
- Do NOT include the original word itself
- Do NOT include pure numerals (e.g., "1000", "42") - only word forms
- Prefer common, useful forms over rare or archaic ones
- Consider the part of speech and usage context
"""

        if language_code == 'zh':
            prompt += "\n- For Chinese, provide Traditional Chinese characters (繁體字) (e.g., 街道, 馬路 for 'street')"
        elif language_code == 'ko':
            prompt += "\n- For Korean, provide words in Hangul (e.g., 거리, 길 for 'street')"

        prompt += """

**Output Format (JSON):**
{
  "abbreviations": ["abbr1", "abbr2"],
  "expanded_forms": ["expanded1", "expanded2"],
  "alternate_spellings": ["spelling1", "spelling2"],
  "synonyms": ["syn1", "syn2", "syn3"],
  "explanation": "Brief note about your choices"
}

Respond ONLY with valid JSON, no other text."""

        try:
            # Query the LLM using generate_chat with JSON schema
            json_schema = {
                "type": "object",
                "properties": {
                    "abbreviations": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "expanded_forms": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "alternate_spellings": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "synonyms": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "explanation": {"type": "string"}
                },
                "required": ["abbreviations", "expanded_forms", "alternate_spellings", "synonyms"]
            }

            response = client.client.generate_chat(
                prompt=prompt,
                model=client.model,
                json_schema=json_schema
            )

            if not response.structured_data:
                return {
                    'success': False,
                    'error': 'Empty response from LLM'
                }

            # Use structured data from response
            result = response.structured_data

            return {
                'success': True,
                'synonyms': result.get('synonyms', []),
                'abbreviations': result.get('abbreviations', []),
                'expanded_forms': result.get('expanded_forms', []),
                'alternate_spellings': result.get('alternate_spellings', []),
                'explanation': result.get('explanation', '')
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response}")
            return {
                'success': False,
                'error': f'Invalid JSON response: {e}'
            }
        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def fix_missing_synonyms(
        self,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: str = 'gpt-5-mini',
        throttle: float = 1.0,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate missing synonyms and alternative forms for lemmas.

        Args:
            language_code: Language to fix (e.g., 'en', 'lt'). If None, defaults to English.
            form_type: Type to generate ('synonym' or 'alternative_form'). If None, generates both.
            limit: Maximum number of lemmas to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        # Default to English if no language specified
        if not language_code:
            language_code = 'en'
            logger.info("No language specified, defaulting to English")

        # Check what's missing
        check_results = self.check_missing_synonyms(
            language_code=language_code,
            form_type=form_type
        )

        if 'error' in check_results:
            return check_results

        lemmas_missing = check_results['missing_by_language'].get(language_code, [])
        total_needs_fix = len(lemmas_missing)

        if total_needs_fix == 0:
            logger.info(f"No lemmas need synonyms/alternatives for {language_code}!")
            return {
                'total_needing_fix': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'dry_run': dry_run
            }

        logger.info(f"Found {total_needs_fix} lemmas needing synonyms/alternatives for {language_code}")

        # Apply limit if specified
        if limit:
            lemmas_to_process = lemmas_missing[:limit]
            logger.info(f"Processing limited to {limit} lemmas")
        else:
            lemmas_to_process = lemmas_missing

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(lemmas_to_process)} lemmas:")
            for lemma_info in lemmas_to_process[:10]:  # Show first 10
                logger.info(f"  - {lemma_info['english']} -> {lemma_info['translation']} (level {lemma_info['difficulty_level']})")
            if len(lemmas_to_process) > 10:
                logger.info(f"  ... and {len(lemmas_to_process) - 10} more")
            return {
                'total_needing_fix': total_needs_fix,
                'would_process': len(lemmas_to_process),
                'dry_run': True,
                'sample': lemmas_to_process[:10]
            }

        # Process each lemma
        successful = 0
        failed = 0
        session = self.get_session()

        try:
            for i, lemma_info in enumerate(lemmas_to_process, 1):
                logger.info(f"\n[{i}/{len(lemmas_to_process)}] Processing: {lemma_info['english']} -> {lemma_info['translation']}")

                # Get lemma object
                lemma = session.query(Lemma).filter(Lemma.guid == lemma_info['guid']).first()
                if not lemma:
                    logger.error(f"Could not find lemma with GUID {lemma_info['guid']}")
                    failed += 1
                    continue

                # Generate synonyms
                result = self.generate_synonyms_for_lemma(
                    lemma_id=lemma.id,
                    language_code=language_code,
                    model=model,
                    dry_run=False
                )

                if result.get('success'):
                    successful += 1
                    logger.info(f"Successfully generated {result.get('stored_synonyms', 0)} synonyms and {result.get('stored_alternatives', 0)} alternatives")
                else:
                    failed += 1
                    logger.error(f"Failed: {result.get('error', 'Unknown error')}")

                # Throttle to avoid overloading the API
                if i < len(lemmas_to_process):
                    time.sleep(throttle)

        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total needing fix: {total_needs_fix}")
        logger.info(f"  Processed: {len(lemmas_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            'total_needing_fix': total_needs_fix,
            'processed': len(lemmas_to_process),
            'successful': successful,
            'failed': failed,
            'dry_run': dry_run,
            'language_code': language_code
        }
