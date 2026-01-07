"""
Vilkas - Multi-language Word Forms Checker Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/generate-forms/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent runs autonomously to check for the presence of word forms
across multiple languages in the database. It identifies lemmas that should
have derivative forms but don't, and reports on data quality issues.

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.

Supported languages and forms:
- Lithuanian (lt): noun declensions (7 cases), verb conjugations, adjective forms, adverb forms
- French (fr): noun forms (singular/plural), verb conjugations
- German (de): noun declensions (4 cases), verb conjugations
- Spanish (es): noun forms (singular/plural), verb conjugations
- Portuguese (pt): noun forms (singular/plural), verb conjugations
- English (en): noun forms (singular/plural), verb conjugations, adjective forms, adverb forms
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import constants
from agents.common.lemma_selection import find_lemma_by_guid
from clients.barsukas_cache import BarsukasCacheClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import DerivativeForm, Lemma
from wordfreq.storage.translation_helpers import get_language_name, get_translation
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.generate_forms_tasks import get_task_key, process_lemma_for_task

# Configure logging
logger = logging.getLogger(__name__)


class VilkasAgent:
    """Agent for checking word forms across multiple languages in the database."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Vilkas agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        # Keep db_path for backward compatibility with LinguisticClient
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        # Lazy initialization
        self.cache_client = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_cache_client(self):
        """Get or create cache client for BARSUKAS queries."""
        if self.cache_client is None and self.config.barsukas_url:
            self.cache_client = BarsukasCacheClient(
                base_url=self.config.barsukas_url,
                cache_only=self.config.cache_only,
                debug=self.debug,
            )
        return self.cache_client

    def check_missing_lithuanian_base_forms(self) -> Dict[str, any]:
        """
        Check for lemmas with Lithuanian translations but no Lithuanian derivative forms.

        Returns:
            Dictionary with check results
        """
        # Delegate to translation helpers
        from wordfreq.translation.check_lithuanian import (
            check_missing_lithuanian_base_forms as _check,
        )

        return _check(self)

    def check_noun_declension_coverage(self) -> Dict[str, any]:
        """
        Check for Lithuanian nouns that have base forms but missing declensions.

        For Lithuanian nouns, we expect various declension forms (cases/numbers).
        This checks which nouns only have the base (nominative singular) form.

        Returns:
            Dictionary with check results
        """
        # Delegate to translation helpers
        from wordfreq.translation.check_lithuanian import check_noun_declension_coverage as _check

        return _check(self)

    def generate_forms_for_lemma(
        self,
        lemma_guid: str,
        language_code: str,
        pos_type: str,
        client: Optional[LinguisticClient] = None,
    ) -> bool:
        """Generate forms for a single lemma by GUID using configured tasks."""

        session = self.get_session()
        try:
            lemma = find_lemma_by_guid(session, lemma_guid, error_on_missing=False)
            if not lemma:
                logger.error(f"Lemma with GUID {lemma_guid} not found")
                return False

            if lemma.pos_type != pos_type:
                logger.warning(
                    "Requested POS type %s differs from lemma POS %s for GUID %s",
                    pos_type,
                    lemma.pos_type,
                    lemma_guid,
                )

            try:
                task_key = get_task_key(language_code, pos_type)
            except KeyError:
                logger.error(
                    "No form generation task registered for %s %s", language_code, pos_type
                )
                return False

            client = client or LinguisticClient(config=self.config)
            return process_lemma_for_task(task_key, lemma.id, self.config, client)
        finally:
            session.close()

    def check_verb_conjugation_coverage(self, language_code: str = "lt") -> Dict[str, any]:
        """
        Check for verbs that have base forms but missing conjugations.

        Args:
            language_code: Language code to check ('lt' for Lithuanian, 'fr' for French)

        Returns:
            Dictionary with check results
        """
        language_name = get_language_name(language_code)

        logger.info(f"Checking {language_name} verb conjugation coverage...")

        session = self.get_session()
        try:
            # Find verbs with translation in the target language
            from agents.common.lemma_selection import LemmaQueryBuilder

            query_builder = LemmaQueryBuilder(session).filter_custom(
                lambda q: q.filter(Lemma.pos_type == "verb")
            )

            # Add language filter if not English
            if language_code != "en":
                query_builder = query_builder.has_translation_in(language_code)

            verb_lemmas = query_builder.build().all()

            logger.info(f"Found {len(verb_lemmas)} verb lemmas with {language_name} translations")

            # Check conjugation coverage
            needs_conjugations = []
            has_conjugations = []

            for lemma in verb_lemmas:
                # Count derivative forms for this verb in the target language
                forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.lemma_id == lemma.id,
                        DerivativeForm.language_code == language_code,
                    )
                    .all()
                )

                # If we only have 1 form (the infinitive), it needs conjugations
                if len(forms) <= 1:
                    translation = get_translation(session, lemma, language_code)
                    needs_conjugations.append(
                        {
                            "guid": lemma.guid,
                            "english": lemma.lemma_text,
                            "translation": translation,
                            "pos_subtype": lemma.pos_subtype,
                            "difficulty_level": lemma.difficulty_level,
                            "current_form_count": len(forms),
                        }
                    )
                else:
                    has_conjugations.append({"guid": lemma.guid, "form_count": len(forms)})

            logger.info(f"Verbs with conjugations: {len(has_conjugations)}")
            logger.info(f"Verbs needing conjugations: {len(needs_conjugations)}")

            return {
                "language_code": language_code,
                "language_name": language_name,
                "total_verbs": len(verb_lemmas),
                "with_conjugations": len(has_conjugations),
                "needs_conjugations": len(needs_conjugations),
                "verbs_needing_conjugations": needs_conjugations,
                "conjugation_coverage_percentage": (
                    (len(has_conjugations) / len(verb_lemmas) * 100) if verb_lemmas else 0
                ),
            }

        except Exception as e:
            logger.error(f"Error checking verb conjugation coverage: {e}")
            return {
                "error": str(e),
                "language_code": language_code,
                "language_name": language_name,
                "total_verbs": 0,
                "with_conjugations": 0,
                "needs_conjugations": 0,
                "verbs_needing_conjugations": [],
                "conjugation_coverage_percentage": 0,
            }
        finally:
            session.close()

    def fix_missing_forms(
        self,
        lemmas: Optional[List[Lemma]] = None,
        language_code: str = "lt",
        pos_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = "llm",
    ) -> Dict[str, any]:
        """
        Generate and store missing word forms for a specific language.

        Supported languages and forms:
        - Lithuanian (lt): noun declensions (7 cases), verb conjugations, adjective forms, adverb forms
        - French (fr): noun forms (singular/plural), verb conjugations
        - German (de): noun declensions (4 cases), verb conjugations
        - Spanish (es): noun forms (singular/plural), verb conjugations
        - Portuguese (pt): noun forms (singular/plural), verb conjugations
        - English (en): noun forms (singular/plural), verb conjugations, adjective forms, adverb forms

        Args:
            lemmas: List of Lemma objects to process. If None, processes all curated lemmas.
            language_code: Language code (e.g., 'lt', 'fr', 'de', 'es', 'pt', 'en')
            pos_type: Part of speech to fix (e.g., 'noun', 'verb', 'adjective'). If None, uses language-specific default.
            limit: Maximum number of lemmas to process
            model: LLM model to use for generation (if None, uses config.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki' (for Lithuanian nouns only)

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to config model
        effective_model = model if model is not None else self.config.model
        # Define supported languages and their supported POS types
        SUPPORTED_LANGUAGES = {
            "lt": ["noun", "verb", "adjective", "adverb"],
            "fr": ["noun", "verb"],
            "de": ["noun", "verb"],
            "es": ["noun", "verb"],
            "pt": ["noun", "verb"],
            "en": ["noun", "verb", "adjective", "adverb"],
        }

        if language_code not in SUPPORTED_LANGUAGES:
            logger.error(f"Language '{language_code}' is not yet supported for form generation")
            return {
                "error": f"Language '{language_code}' not supported",
                "supported_languages": list(SUPPORTED_LANGUAGES.keys()),
            }

        # Validate POS type for the language
        if pos_type and pos_type not in SUPPORTED_LANGUAGES[language_code]:
            logger.error(f"POS type '{pos_type}' is not supported for {language_code}")
            return {
                "error": f"POS type '{pos_type}' not supported for {language_code}",
                "supported_pos_types": SUPPORTED_LANGUAGES[language_code],
            }

        # Default POS type if not specified (language-specific defaults)
        if not pos_type:
            # Use first supported POS type as default
            pos_type = SUPPORTED_LANGUAGES[language_code][0]
            logger.info(f"No POS type specified, defaulting to '{pos_type}' for {language_code}")

        # Route to appropriate handler based on language and POS type
        handler_key = f"{language_code}_{pos_type}"

        # Map language/POS combinations to their process functions and metadata
        # Format: (process_module, process_func_name, uses_generic_handler, language_display_name)
        handler_map = {
            "lt_noun": (get_task_key("lt", "noun"), "Lithuanian", False),
            "lt_verb": (get_task_key("lt", "verb"), "Lithuanian", True),
            "lt_adjective": (get_task_key("lt", "adjective"), "Lithuanian", True),
            "lt_adverb": (get_task_key("lt", "adverb"), "Lithuanian", True),
            "fr_noun": (get_task_key("fr", "noun"), "French", True),
            "fr_verb": (get_task_key("fr", "verb"), "French", True),
            "de_noun": (get_task_key("de", "noun"), "German", True),
            "de_verb": (get_task_key("de", "verb"), "German", True),
            "es_noun": (get_task_key("es", "noun"), "Spanish", True),
            "es_verb": (get_task_key("es", "verb"), "Spanish", True),
            "pt_noun": (get_task_key("pt", "noun"), "Portuguese", True),
            "pt_verb": (get_task_key("pt", "verb"), "Portuguese", True),
            "en_noun": (get_task_key("en", "noun"), "English", True),
            "en_verb": (get_task_key("en", "verb"), "English", True),
            "en_adjective": (get_task_key("en", "adjective"), "English", True),
            "en_adverb": (get_task_key("en", "adverb"), "English", True),
        }

        if handler_key not in handler_map:
            logger.error(f"No handler found for {language_code} {pos_type}")
            return {
                "error": f"Handler not implemented for {language_code} {pos_type}",
                "supported_combinations": list(handler_map.keys()),
            }

        # Get the process function and metadata
        task_key, language_name, use_generic = handler_map[handler_key]

        # Call the appropriate handler
        if handler_key == "lt_noun":
            return self._fix_lithuanian_noun_declensions(
                lemmas=lemmas,
                limit=limit,
                model=effective_model,
                throttle=throttle,
                dry_run=dry_run,
                source=source,
            )
        elif handler_key == "fr_verb":
            return self._fix_french_verb_conjugations(
                lemmas=lemmas,
                limit=limit,
                model=effective_model,
                throttle=throttle,
                dry_run=dry_run,
            )
        elif use_generic:
            return self._fix_generic_forms(
                lemmas=lemmas,
                language_code=language_code,
                language_name=language_name,
                pos_type=pos_type,
                task_key=task_key,
                limit=limit,
                model=effective_model,
                throttle=throttle,
                dry_run=dry_run,
            )
        else:
            logger.error(f"Unexpected handler configuration for {handler_key}")
            return {"error": f"Handler configuration error for {handler_key}"}

    def _fix_lithuanian_noun_declensions(
        self,
        lemmas: Optional[List[Lemma]] = None,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = "llm",
    ) -> Dict[str, any]:
        """
        Generate missing Lithuanian noun declensions.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_lithuanian_noun_forms.

        Args:
            lemmas: List of Lemma objects to process. If None, processes all curated lemmas.
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses config.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki'

        Returns:
            Dictionary with fix results
        """
        # Delegate to translation helper module
        from wordfreq.translation.fix_lithuanian_noun_declensions import (
            fix_lithuanian_noun_declensions,
        )

        return fix_lithuanian_noun_declensions(
            agent=self,
            lemmas=lemmas,
            limit=limit,
            model=model,
            throttle=throttle,
            dry_run=dry_run,
            source=source,
        )

    def _fix_french_verb_conjugations(
        self,
        lemmas: Optional[List[Lemma]] = None,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Generate missing French verb conjugations.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_french_verb_forms.

        Args:
            lemmas: List of Lemma objects to process. If None, processes all curated lemmas.
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses config.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        # Delegate to translation helper module
        from wordfreq.translation.fix_french_verb_conjugations import fix_french_verb_conjugations

        return fix_french_verb_conjugations(
            agent=self,
            lemmas=lemmas,
            limit=limit,
            model=model,
            throttle=throttle,
            dry_run=dry_run,
        )

    def _fix_generic_forms(
        self,
        lemmas: Optional[List[Lemma]] = None,
        language_code: str = "lt",
        language_name: str = "Lithuanian",
        pos_type: str = "verb",
        task_key: str = "",
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Generic handler for generating missing word forms across languages.

        Args:
            lemmas: List of Lemma objects to process. If None, uses check methods to find lemmas needing forms.
            language_code: Language code (e.g., 'fr', 'de')
            language_name: Human-readable language name
            pos_type: Part of speech type
            task_key: Registered form-generation task key
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses config.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to config model
        effective_model = model if model is not None else self.config.model
        logger.info(f"Finding {language_name} {pos_type}s needing forms...")

        # If lemmas are provided, use them directly
        if lemmas:
            # Filter to just the specified pos_type
            filtered_lemmas = [l for l in lemmas if l.pos_type == pos_type]

            items_needing_forms = []
            for lemma in filtered_lemmas:
                translation = (
                    get_translation(self.get_session(), lemma, language_code)
                    if language_code != "en"
                    else lemma.lemma_text
                )
                items_needing_forms.append(
                    {
                        "guid": lemma.guid,
                        "english": lemma.lemma_text,
                        "translation": translation or f"({language_code})",
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                        "current_form_count": 0,
                    }
                )
            total_needs_fix = len(items_needing_forms)
        else:
            # Get form coverage check results
            check_results = (
                self.check_verb_conjugation_coverage(language_code=language_code)
                if pos_type == "verb"
                else self.check_noun_declension_coverage()
            )

            if "error" in check_results:
                return check_results

            items_key = (
                "verbs_needing_conjugations" if pos_type == "verb" else "nouns_needing_declensions"
            )
            items_needing_forms = check_results.get(items_key, [])
            total_needs_fix = len(items_needing_forms)

        if total_needs_fix == 0:
            logger.info(f"No {language_name} {pos_type}s need forms!")
            return {
                "total_needing_fix": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
            }

        logger.info(f"Found {total_needs_fix} {language_name} {pos_type}s needing forms")

        # Apply limit if specified
        if limit:
            items_to_process = items_needing_forms[:limit]
            logger.info(f"Processing limited to {limit} {pos_type}s")
        else:
            items_to_process = items_needing_forms

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(items_to_process)} {pos_type}s:")
            for item in items_to_process[:10]:  # Show first 10
                logger.info(
                    f"  - {item['english']} -> {item.get('translation', item.get('lithuanian', 'N/A'))} (level {item['difficulty_level']})"
                )
            if len(items_to_process) > 10:
                logger.info(f"  ... and {len(items_to_process) - 10} more")
            return {
                "total_needing_fix": total_needs_fix,
                "would_process": len(items_to_process),
                "dry_run": True,
                "sample": items_to_process[:10],
            }

        # Initialize client
        client = LinguisticClient(config=self.config)

        # Process each item
        successful = 0
        failed = 0

        session = self.get_session()
        try:
            for i, item_info in enumerate(items_to_process, 1):
                logger.info(
                    f"\n[{i}/{len(items_to_process)}] Processing: {item_info['english']} -> {item_info.get('translation', item_info.get('lithuanian', 'N/A'))}"
                )

                # Get the full lemma object
                lemma = find_lemma_by_guid(session, item_info["guid"], error_on_missing=False)

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {item_info['guid']}")
                    failed += 1
                    continue

                # Call the process function
                success = process_lemma_for_task(task_key, lemma.id, self.config, client)

                if success:
                    successful += 1
                    logger.info(f"Successfully generated forms for '{item_info['english']}'")
                else:
                    failed += 1
                    logger.error(f"Failed to generate forms for '{item_info['english']}'")

                # Throttle to avoid overloading the API
                if i < len(items_to_process):
                    time.sleep(throttle)

        finally:
            session.close()

        logger.info(f"\n{'='*60}")
        logger.info(f"Fix complete:")
        logger.info(f"  Total needing fix: {total_needs_fix}")
        logger.info(f"  Processed: {len(items_to_process)}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"{'='*60}")

        return {
            "total_needing_fix": total_needs_fix,
            "processed": len(items_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
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
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "checks": {
                "missing_base_forms": self.check_missing_lithuanian_base_forms(),
                "noun_declensions": self.check_noun_declension_coverage(),
                "verb_conjugations": self.check_verb_conjugation_coverage(),
            },
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        logger.info("=" * 80)
        logger.info("VILKAS AGENT REPORT - Lithuanian Word Forms Check")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Missing base forms
        base_check = results["checks"]["missing_base_forms"]
        logger.info(f"MISSING LITHUANIAN BASE FORMS:")
        logger.info(
            f"  Total lemmas with Lithuanian translation: {base_check['total_with_translation']}"
        )
        logger.info(f"  Missing derivative forms: {base_check['missing_count']}")
        logger.info(f"  Coverage: {base_check['coverage_percentage']:.1f}%")
        logger.info("")

        # Noun declensions
        noun_check = results["checks"]["noun_declensions"]
        logger.info(f"LITHUANIAN NOUN DECLENSIONS:")
        logger.info(f"  Total nouns: {noun_check['total_nouns']}")
        logger.info(f"  With declensions: {noun_check['with_declensions']}")
        logger.info(f"  Needing declensions: {noun_check['needs_declensions']}")
        logger.info(f"  Coverage: {noun_check['declension_coverage_percentage']:.1f}%")
        logger.info("")

        # Verb conjugations
        verb_check = results["checks"]["verb_conjugations"]
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
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results
