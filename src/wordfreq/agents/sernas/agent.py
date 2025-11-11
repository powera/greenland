"""
Šernas - Synonym and Alternative Form Generator Agent

This agent generates synonyms and alternative forms for lemmas across all supported
languages. It distinguishes between:
- Alternative forms: Shortened versions, spelling variants (e.g., "one thousand" → "thousand", "gray" → "grey")
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
            form_type: Type to check ('synonym' or 'alternative_form'). If None, check both.

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
                form_types = ['synonym', 'alternative_form']

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

                    # Check for existing synonyms/alternatives
                    existing_forms = session.query(DerivativeForm).filter(
                        DerivativeForm.lemma_id == lemma.id,
                        DerivativeForm.language_code == lang,
                        DerivativeForm.grammatical_form.in_(form_types)
                    ).all()

                    if not existing_forms:
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
            alternative_forms = [a for a in result.get('alternative_forms', []) if not self._is_numeral(a)]

            if dry_run:
                return {
                    'dry_run': True,
                    'lemma_id': lemma_id,
                    'language_code': language_code,
                    'word': word,
                    'synonyms': synonyms,
                    'alternative_forms': alternative_forms,
                    'total_count': len(synonyms) + len(alternative_forms)
                }

            # Store the forms in the database
            stored_synonyms = 0
            stored_alternatives = 0

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

            for alt_form in alternative_forms:
                try:
                    word_token = add_word_token(session, alt_form, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=alt_form,
                        language_code=language_code,
                        grammatical_form='alternative_form',
                        word_token=word_token,
                        verified=False
                    )
                    stored_alternatives += 1
                except Exception as e:
                    logger.warning(f"Failed to store alternative form '{alt_form}': {e}")

            session.commit()

            logger.info(f"Stored {stored_synonyms} synonyms and {stored_alternatives} alternative forms")

            return {
                'success': True,
                'lemma_id': lemma_id,
                'language_code': language_code,
                'word': word,
                'synonyms': synonyms,
                'alternative_forms': alternative_forms,
                'stored_synonyms': stored_synonyms,
                'stored_alternatives': stored_alternatives
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
1. **Alternative forms**: Shortened versions, abbreviations, or spelling variants of the SAME word (e.g., "one thousand" → "thousand", "gray" → "grey", "TV" for "television")
2. **Synonyms**: Different words with similar or related meanings that would be appropriate for language learners (e.g., "street" → "road", "mad" → "angry")

**Context:**
- English lemma: {english_word}
- Definition: {definition}
- This is for language learning, so focus on common, useful synonyms that learners might encounter
- Consider whether synonyms would be appropriate/correct in Trakaido learning context

**Guidelines:**
- For alternative_forms: Only include forms that are essentially the same word (shortened, abbreviated, or variant spellings)
- For synonyms: Include words with similar meanings, but be mindful of context appropriateness
- Return 0-5 items for each category (not all words have synonyms or alternative forms)
- Do NOT include the original word itself
- Do NOT include pure numerals (e.g., "1000", "42") - only word forms
- Prefer common, useful words over rare or archaic ones
- Consider the part of speech and usage context
"""

        if language_code == 'zh':
            prompt += "\n- For Chinese, provide Traditional Chinese characters (繁體字) (e.g., 街道, 馬路 for 'street')"
        elif language_code == 'ko':
            prompt += "\n- For Korean, provide words in Hangul (e.g., 거리, 길 for 'street')"

        prompt += """

**Output Format (JSON):**
{
  "alternative_forms": ["form1", "form2"],
  "synonyms": ["syn1", "syn2", "syn3"],
  "explanation": "Brief note about your choices"
}

Respond ONLY with valid JSON, no other text."""

        try:
            # Query the LLM using generate_chat with JSON schema
            json_schema = {
                "type": "object",
                "properties": {
                    "alternative_forms": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "synonyms": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "explanation": {"type": "string"}
                },
                "required": ["alternative_forms", "synonyms"]
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
                'alternative_forms': result.get('alternative_forms', []),
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
