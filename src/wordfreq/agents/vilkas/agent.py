"""
Vilkas - Lithuanian Word Forms Checker Agent

This agent runs autonomously to check for the presence of Lithuanian word forms
in the database. It identifies lemmas that should have derivative forms but don't,
and reports on data quality issues.

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, DerivativeForm
from wordfreq.translation.client import LinguisticClient

# Configure logging
logger = logging.getLogger(__name__)


class VilkasAgent:
    """Agent for checking Lithuanian word forms in the database."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Vilkas agent.

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

    def check_missing_lithuanian_base_forms(self) -> Dict[str, any]:
        """
        Check for lemmas with Lithuanian translations but no Lithuanian derivative forms.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking for lemmas missing Lithuanian base forms...")

        session = self.get_session()
        try:
            # Find lemmas with Lithuanian translations
            lemmas_with_lt = session.query(Lemma).filter(
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).all()

            logger.info(f"Found {len(lemmas_with_lt)} lemmas with Lithuanian translations")

            # Check which ones are missing Lithuanian derivative forms
            missing_forms = []

            for lemma in lemmas_with_lt:
                # Check for Lithuanian derivative forms
                lt_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == 'lt'
                ).all()

                if not lt_forms:
                    missing_forms.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'lithuanian_translation': lemma.lithuanian_translation,
                        'pos_type': lemma.pos_type,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level
                    })

            logger.info(f"Found {len(missing_forms)} lemmas missing Lithuanian derivative forms")

            return {
                'total_with_translation': len(lemmas_with_lt),
                'missing_forms': missing_forms,
                'missing_count': len(missing_forms),
                'coverage_percentage': ((len(lemmas_with_lt) - len(missing_forms)) / len(lemmas_with_lt) * 100) if lemmas_with_lt else 0
            }

        except Exception as e:
            logger.error(f"Error checking missing Lithuanian base forms: {e}")
            return {
                'error': str(e),
                'total_with_translation': 0,
                'missing_forms': [],
                'missing_count': 0,
                'coverage_percentage': 0
            }
        finally:
            session.close()

    def check_noun_declension_coverage(self) -> Dict[str, any]:
        """
        Check for Lithuanian nouns that have base forms but missing declensions.

        For Lithuanian nouns, we expect various declension forms (cases/numbers).
        This checks which nouns only have the base (nominative singular) form.

        Returns:
            Dictionary with check results
        """
        logger.info("Checking Lithuanian noun declension coverage...")

        session = self.get_session()
        try:
            # Find lemmas that are nouns with Lithuanian translations
            noun_lemmas = session.query(Lemma).filter(
                Lemma.pos_type == 'noun',
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).all()

            logger.info(f"Found {len(noun_lemmas)} noun lemmas with Lithuanian translations")

            # Check declension coverage
            needs_declensions = []
            has_declensions = []

            for lemma in noun_lemmas:
                # Count Lithuanian derivative forms for this noun
                lt_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == 'lt'
                ).all()

                # If we only have 1 form (the base form), it needs declensions
                if len(lt_forms) <= 1:
                    needs_declensions.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'lithuanian': lemma.lithuanian_translation,
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level,
                        'current_form_count': len(lt_forms)
                    })
                else:
                    has_declensions.append({
                        'guid': lemma.guid,
                        'form_count': len(lt_forms)
                    })

            logger.info(f"Nouns with declensions: {len(has_declensions)}")
            logger.info(f"Nouns needing declensions: {len(needs_declensions)}")

            return {
                'total_nouns': len(noun_lemmas),
                'with_declensions': len(has_declensions),
                'needs_declensions': len(needs_declensions),
                'nouns_needing_declensions': needs_declensions,
                'declension_coverage_percentage': (len(has_declensions) / len(noun_lemmas) * 100) if noun_lemmas else 0
            }

        except Exception as e:
            logger.error(f"Error checking noun declension coverage: {e}")
            return {
                'error': str(e),
                'total_nouns': 0,
                'with_declensions': 0,
                'needs_declensions': 0,
                'nouns_needing_declensions': [],
                'declension_coverage_percentage': 0
            }
        finally:
            session.close()

    def check_verb_conjugation_coverage(self, language_code: str = 'lt') -> Dict[str, any]:
        """
        Check for verbs that have base forms but missing conjugations.

        Args:
            language_code: Language code to check ('lt' for Lithuanian, 'fr' for French)

        Returns:
            Dictionary with check results
        """
        language_names = {'lt': 'Lithuanian', 'fr': 'French'}
        language_name = language_names.get(language_code, language_code.upper())

        logger.info(f"Checking {language_name} verb conjugation coverage...")

        session = self.get_session()
        try:
            # Get the appropriate translation field name
            translation_field_map = {
                'lt': 'lithuanian_translation',
                'fr': 'french_translation'
            }
            translation_field = translation_field_map.get(language_code)

            if not translation_field:
                raise ValueError(f"Unsupported language code: {language_code}")

            # Find lemmas that are verbs with translations in the target language
            verb_lemmas = session.query(Lemma).filter(
                Lemma.pos_type == 'verb',
                getattr(Lemma, translation_field).isnot(None),
                getattr(Lemma, translation_field) != ''
            ).all()

            logger.info(f"Found {len(verb_lemmas)} verb lemmas with {language_name} translations")

            # Check conjugation coverage
            needs_conjugations = []
            has_conjugations = []

            for lemma in verb_lemmas:
                # Count derivative forms for this verb in the target language
                forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == language_code
                ).all()

                # If we only have 1 form (the infinitive), it needs conjugations
                if len(forms) <= 1:
                    needs_conjugations.append({
                        'guid': lemma.guid,
                        'english': lemma.lemma_text,
                        'translation': getattr(lemma, translation_field),
                        'pos_subtype': lemma.pos_subtype,
                        'difficulty_level': lemma.difficulty_level,
                        'current_form_count': len(forms)
                    })
                else:
                    has_conjugations.append({
                        'guid': lemma.guid,
                        'form_count': len(forms)
                    })

            logger.info(f"Verbs with conjugations: {len(has_conjugations)}")
            logger.info(f"Verbs needing conjugations: {len(needs_conjugations)}")

            return {
                'language_code': language_code,
                'language_name': language_name,
                'total_verbs': len(verb_lemmas),
                'with_conjugations': len(has_conjugations),
                'needs_conjugations': len(needs_conjugations),
                'verbs_needing_conjugations': needs_conjugations,
                'conjugation_coverage_percentage': (len(has_conjugations) / len(verb_lemmas) * 100) if verb_lemmas else 0
            }

        except Exception as e:
            logger.error(f"Error checking verb conjugation coverage: {e}")
            return {
                'error': str(e),
                'language_code': language_code,
                'language_name': language_name,
                'total_verbs': 0,
                'with_conjugations': 0,
                'needs_conjugations': 0,
                'verbs_needing_conjugations': [],
                'conjugation_coverage_percentage': 0
            }
        finally:
            session.close()

    def fix_missing_forms(
        self,
        language_code: str = 'lt',
        pos_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: str = 'gpt-5-mini',
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = 'llm'
    ) -> Dict[str, any]:
        """
        Generate and store missing word forms for a specific language.

        Currently supports:
        - Lithuanian (lt): noun declensions, verb conjugations
        - French (fr): verb conjugations

        Future support planned for:
        - English (en): noun plurals, verb conjugations, etc.
        - Other languages as needed

        Args:
            language_code: Language code ('lt' for Lithuanian, 'fr' for French)
            pos_type: Part of speech to fix (e.g., 'noun', 'verb'). If None, fixes all supported POS types.
            limit: Maximum number of lemmas to process
            model: LLM model to use for generation
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki' (for Lithuanian only)

        Returns:
            Dictionary with fix results
        """
        if language_code not in ['lt', 'fr']:
            logger.error(f"Language '{language_code}' is not yet supported for form generation")
            return {
                'error': f"Language '{language_code}' not supported",
                'supported_languages': ['lt', 'fr']
            }

        # Handle Lithuanian
        if language_code == 'lt':
            # For Lithuanian, currently only nouns are fully implemented
            if pos_type and pos_type != 'noun':
                logger.warning(f"POS type '{pos_type}' is not fully implemented for Lithuanian. Only nouns are supported.")
                if not dry_run:
                    return {
                        'error': f"POS type '{pos_type}' not fully implemented for Lithuanian",
                        'supported_pos_types': ['noun']
                    }

            # Default to nouns if no POS type specified
            if not pos_type:
                pos_type = 'noun'
                logger.info("No POS type specified, defaulting to 'noun'")

            return self._fix_lithuanian_noun_declensions(
                limit=limit,
                model=model,
                throttle=throttle,
                dry_run=dry_run,
                source=source
            )

        # Handle French
        elif language_code == 'fr':
            # For French, currently only verbs are implemented
            if pos_type and pos_type != 'verb':
                logger.warning(f"POS type '{pos_type}' is not fully implemented for French. Only verbs are supported.")
                if not dry_run:
                    return {
                        'error': f"POS type '{pos_type}' not fully implemented for French",
                        'supported_pos_types': ['verb']
                    }

            # Default to verbs if no POS type specified
            if not pos_type:
                pos_type = 'verb'
                logger.info("No POS type specified, defaulting to 'verb'")

            return self._fix_french_verb_conjugations(
                limit=limit,
                model=model,
                throttle=throttle,
                dry_run=dry_run
            )

    def _fix_lithuanian_noun_declensions(
        self,
        limit: Optional[int] = None,
        model: str = 'gpt-5-mini',
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = 'llm'
    ) -> Dict[str, any]:
        """
        Generate missing Lithuanian noun declensions.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_lithuanian_noun_forms.

        Args:
            limit: Maximum number of lemmas to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki'

        Returns:
            Dictionary with fix results
        """
        from wordfreq.translation.generate_lithuanian_noun_forms import (
            process_lemma_declensions,
            get_lithuanian_noun_lemmas
        )

        logger.info("Finding Lithuanian nouns needing declensions...")

        # Get noun declension coverage check results
        check_results = self.check_noun_declension_coverage()

        if 'error' in check_results:
            return check_results

        nouns_needing_declensions = check_results['nouns_needing_declensions']
        total_needs_fix = len(nouns_needing_declensions)

        if total_needs_fix == 0:
            logger.info("No Lithuanian nouns need declensions!")
            return {
                'total_needing_fix': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'dry_run': dry_run
            }

        logger.info(f"Found {total_needs_fix} Lithuanian nouns needing declensions")

        # Apply limit if specified
        if limit:
            nouns_to_process = nouns_needing_declensions[:limit]
            logger.info(f"Processing limited to {limit} nouns")
        else:
            nouns_to_process = nouns_needing_declensions

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(nouns_to_process)} nouns:")
            for noun in nouns_to_process[:10]:  # Show first 10
                logger.info(f"  - {noun['english']} -> {noun['lithuanian']} (level {noun['difficulty_level']})")
            if len(nouns_to_process) > 10:
                logger.info(f"  ... and {len(nouns_to_process) - 10} more")
            return {
                'total_needing_fix': total_needs_fix,
                'would_process': len(nouns_to_process),
                'dry_run': True,
                'sample': nouns_to_process[:10]
            }

        # Initialize client for LLM-based generation
        client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

        # Process each noun
        successful = 0
        failed = 0

        # Get lemma objects for processing
        session = self.get_session()
        try:
            for i, noun_info in enumerate(nouns_to_process, 1):
                logger.info(f"\n[{i}/{len(nouns_to_process)}] Processing: {noun_info['english']} -> {noun_info['lithuanian']}")

                # Get the full lemma object
                lemma = session.query(Lemma).filter(Lemma.guid == noun_info['guid']).first()

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {noun_info['guid']}")
                    failed += 1
                    continue

                # Use the process_lemma_declensions function from generate_lithuanian_noun_forms
                success = process_lemma_declensions(
                    client=client,
                    lemma_id=lemma.id,
                    db_path=self.db_path,
                    source=source
                )

                if success:
                    successful += 1
                    logger.info(f"Successfully generated declensions for '{noun_info['english']}'")
                else:
                    failed += 1
                    logger.error(f"Failed to generate declensions for '{noun_info['english']}'")

                # Throttle to avoid overloading the API
                if i < len(nouns_to_process):  # Don't sleep after the last one
                    time.sleep(throttle)

        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total needing fix: {total_needs_fix}")
        logger.info(f"  Processed: {len(nouns_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            'total_needing_fix': total_needs_fix,
            'processed': len(nouns_to_process),
            'successful': successful,
            'failed': failed,
            'dry_run': dry_run
        }

    def _fix_french_verb_conjugations(
        self,
        limit: Optional[int] = None,
        model: str = 'gpt-5-mini',
        throttle: float = 1.0,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Generate missing French verb conjugations.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_french_verb_forms.

        Args:
            limit: Maximum number of lemmas to process
            model: LLM model to use
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        from wordfreq.translation.generate_french_verb_forms import (
            process_lemma_conjugations,
            get_french_verb_lemmas
        )

        logger.info("Finding French verbs needing conjugations...")

        # Get verb conjugation coverage check results
        check_results = self.check_verb_conjugation_coverage(language_code='fr')

        if 'error' in check_results:
            return check_results

        verbs_needing_conjugations = check_results['verbs_needing_conjugations']
        total_needs_fix = len(verbs_needing_conjugations)

        if total_needs_fix == 0:
            logger.info("No French verbs need conjugations!")
            return {
                'total_needing_fix': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'dry_run': dry_run
            }

        logger.info(f"Found {total_needs_fix} French verbs needing conjugations")

        # Apply limit if specified
        if limit:
            verbs_to_process = verbs_needing_conjugations[:limit]
            logger.info(f"Processing limited to {limit} verbs")
        else:
            verbs_to_process = verbs_needing_conjugations

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(verbs_to_process)} verbs:")
            for verb in verbs_to_process[:10]:  # Show first 10
                logger.info(f"  - {verb['english']} -> {verb['translation']} (level {verb['difficulty_level']})")
            if len(verbs_to_process) > 10:
                logger.info(f"  ... and {len(verbs_to_process) - 10} more")
            return {
                'total_needing_fix': total_needs_fix,
                'would_process': len(verbs_to_process),
                'dry_run': True,
                'sample': verbs_to_process[:10]
            }

        # Initialize client for LLM-based generation
        client = LinguisticClient(model=model, db_path=self.db_path, debug=self.debug)

        # Process each verb
        successful = 0
        failed = 0

        # Get lemma objects for processing
        session = self.get_session()
        try:
            for i, verb_info in enumerate(verbs_to_process, 1):
                logger.info(f"\n[{i}/{len(verbs_to_process)}] Processing: {verb_info['english']} -> {verb_info['translation']}")

                # Get the full lemma object
                lemma = session.query(Lemma).filter(Lemma.guid == verb_info['guid']).first()

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {verb_info['guid']}")
                    failed += 1
                    continue

                # Use the process_lemma_conjugations function from generate_french_verb_forms
                success = process_lemma_conjugations(
                    client=client,
                    lemma_id=lemma.id,
                    db_path=self.db_path
                )

                if success:
                    successful += 1
                    logger.info(f"Successfully generated conjugations for '{verb_info['english']}'")
                else:
                    failed += 1
                    logger.error(f"Failed to generate conjugations for '{verb_info['english']}'")

                # Throttle to avoid overloading the API
                if i < len(verbs_to_process):  # Don't sleep after the last one
                    time.sleep(throttle)

        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total needing fix: {total_needs_fix}")
        logger.info(f"  Processed: {len(verbs_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            'total_needing_fix': total_needs_fix,
            'processed': len(verbs_to_process),
            'successful': successful,
            'failed': failed,
            'dry_run': dry_run
        }

    def run_full_check(self, output_file: Optional[str] = None) -> Dict[str, any]:
        """
        Run all checks and generate a comprehensive report.

        Args:
            output_file: Optional path to write JSON report

        Returns:
            Dictionary with all check results
        """
        logger.info("Starting full Lithuanian word forms check...")
        start_time = datetime.now()

        results = {
            'timestamp': start_time.isoformat(),
            'database_path': self.db_path,
            'checks': {
                'missing_base_forms': self.check_missing_lithuanian_base_forms(),
                'noun_declensions': self.check_noun_declension_coverage(),
                'verb_conjugations': self.check_verb_conjugation_coverage()
            }
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results['duration_seconds'] = duration

        # Print summary
        logger.info("=" * 80)
        logger.info("VILKAS AGENT REPORT - Lithuanian Word Forms Check")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Missing base forms
        base_check = results['checks']['missing_base_forms']
        logger.info(f"MISSING LITHUANIAN BASE FORMS:")
        logger.info(f"  Total lemmas with Lithuanian translation: {base_check['total_with_translation']}")
        logger.info(f"  Missing derivative forms: {base_check['missing_count']}")
        logger.info(f"  Coverage: {base_check['coverage_percentage']:.1f}%")
        logger.info("")

        # Noun declensions
        noun_check = results['checks']['noun_declensions']
        logger.info(f"LITHUANIAN NOUN DECLENSIONS:")
        logger.info(f"  Total nouns: {noun_check['total_nouns']}")
        logger.info(f"  With declensions: {noun_check['with_declensions']}")
        logger.info(f"  Needing declensions: {noun_check['needs_declensions']}")
        logger.info(f"  Coverage: {noun_check['declension_coverage_percentage']:.1f}%")
        logger.info("")

        # Verb conjugations
        verb_check = results['checks']['verb_conjugations']
        logger.info(f"LITHUANIAN VERB CONJUGATIONS:")
        logger.info(f"  Total verbs: {verb_check['total_verbs']}")
        logger.info(f"  With conjugations: {verb_check['with_conjugations']}")
        logger.info(f"  Needing conjugations: {verb_check['needs_conjugations']}")
        logger.info(f"  Coverage: {verb_check['conjugation_coverage_percentage']:.1f}%")
        logger.info("=" * 80)

        # Write to output file if requested
        if output_file:
            import json
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results
