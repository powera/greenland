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
from clients.barsukas_cache import BarsukasCacheClient
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.models.schema import Lemma, DerivativeForm
from wordfreq.storage.translation_helpers import get_translation
from wordfreq.translation.client import LinguisticClient

# Configure logging
logger = logging.getLogger(__name__)


class VilkasAgent:
    """Agent for checking word forms across multiple languages in the database."""

    def __init__(
        self,
        config: DataSourceConfig = None,
        debug: bool = False,
        default_model: str = "gpt-5-mini",
    ):
        """
        Initialize the Vilkas agent.

        Args:
            config: DataSourceConfig with storage backend, cache, and LLM settings
            debug: Enable debug logging
            default_model: Default LLM model to use if config is None or config.model is None
        """
        # Set up data source configuration
        if config is not None:
            self.config = config
            # If config exists but has no model, set the default
            if self.config.model is None:
                self.config.model = default_model
        else:
            # Use default configuration with model
            self.config = DataSourceConfig(
                backend_type=BackendType.SQLITE,
                sqlite_path=constants.WORDFREQ_DB_PATH,
                model=default_model,
            )

        # Extract commonly-used config values
        self.debug = debug
        self.model = self.config.model

        # Keep db_path for backward compatibility with LinguisticClient
        if self.config.backend_type == BackendType.SQLITE:
            self.db_path = self.config.sqlite_path
        else:
            self.db_path = None

        # Lazy initialization
        self.cache_client = None

        if debug:
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
                debug=self.debug
            )
        return self.cache_client

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
            lemmas_with_lt = (
                session.query(Lemma)
                .filter(
                    Lemma.lithuanian_translation.isnot(None), Lemma.lithuanian_translation != ""
                )
                .all()
            )

            logger.info(f"Found {len(lemmas_with_lt)} lemmas with Lithuanian translations")

            # Check which ones are missing Lithuanian derivative forms
            missing_forms = []

            for lemma in lemmas_with_lt:
                # Check for Lithuanian derivative forms
                lt_forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "lt"
                    )
                    .all()
                )

                if not lt_forms:
                    missing_forms.append(
                        {
                            "guid": lemma.guid,
                            "english": lemma.lemma_text,
                            "lithuanian_translation": get_translation(session, lemma, "lt"),
                            "pos_type": lemma.pos_type,
                            "pos_subtype": lemma.pos_subtype,
                            "difficulty_level": lemma.difficulty_level,
                        }
                    )

            logger.info(f"Found {len(missing_forms)} lemmas missing Lithuanian derivative forms")

            return {
                "total_with_translation": len(lemmas_with_lt),
                "missing_forms": missing_forms,
                "missing_count": len(missing_forms),
                "coverage_percentage": (
                    ((len(lemmas_with_lt) - len(missing_forms)) / len(lemmas_with_lt) * 100)
                    if lemmas_with_lt
                    else 0
                ),
            }

        except Exception as e:
            logger.error(f"Error checking missing Lithuanian base forms: {e}")
            return {
                "error": str(e),
                "total_with_translation": 0,
                "missing_forms": [],
                "missing_count": 0,
                "coverage_percentage": 0,
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
            noun_lemmas = (
                session.query(Lemma)
                .filter(
                    Lemma.pos_type == "noun",
                    Lemma.lithuanian_translation.isnot(None),
                    Lemma.lithuanian_translation != "",
                )
                .all()
            )

            logger.info(f"Found {len(noun_lemmas)} noun lemmas with Lithuanian translations")

            # Check declension coverage
            needs_declensions = []
            has_declensions = []

            for lemma in noun_lemmas:
                # Count Lithuanian derivative forms for this noun
                lt_forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "lt"
                    )
                    .all()
                )

                # If we only have 1 form (the base form), it needs declensions
                if len(lt_forms) <= 1:
                    needs_declensions.append(
                        {
                            "guid": lemma.guid,
                            "english": lemma.lemma_text,
                            "lithuanian": get_translation(session, lemma, "lt"),
                            "pos_subtype": lemma.pos_subtype,
                            "difficulty_level": lemma.difficulty_level,
                            "current_form_count": len(lt_forms),
                        }
                    )
                else:
                    has_declensions.append({"guid": lemma.guid, "form_count": len(lt_forms)})

            logger.info(f"Nouns with declensions: {len(has_declensions)}")
            logger.info(f"Nouns needing declensions: {len(needs_declensions)}")

            return {
                "total_nouns": len(noun_lemmas),
                "with_declensions": len(has_declensions),
                "needs_declensions": len(needs_declensions),
                "nouns_needing_declensions": needs_declensions,
                "declension_coverage_percentage": (
                    (len(has_declensions) / len(noun_lemmas) * 100) if noun_lemmas else 0
                ),
            }

        except Exception as e:
            logger.error(f"Error checking noun declension coverage: {e}")
            return {
                "error": str(e),
                "total_nouns": 0,
                "with_declensions": 0,
                "needs_declensions": 0,
                "nouns_needing_declensions": [],
                "declension_coverage_percentage": 0,
            }
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
        language_names = {"lt": "Lithuanian", "fr": "French"}
        language_name = language_names.get(language_code, language_code.upper())

        logger.info(f"Checking {language_name} verb conjugation coverage...")

        session = self.get_session()
        try:
            # Get the appropriate translation field name
            translation_field_map = {"lt": "lithuanian_translation", "fr": "french_translation"}
            translation_field = translation_field_map.get(language_code)

            if not translation_field:
                raise ValueError(f"Unsupported language code: {language_code}")

            # Find lemmas that are verbs with translations in the target language
            verb_lemmas = (
                session.query(Lemma)
                .filter(
                    Lemma.pos_type == "verb",
                    getattr(Lemma, translation_field).isnot(None),
                    getattr(Lemma, translation_field) != "",
                )
                .all()
            )

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
                    needs_conjugations.append(
                        {
                            "guid": lemma.guid,
                            "english": lemma.lemma_text,
                            "translation": getattr(lemma, translation_field),
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
        language_code: str = "lt",
        pos_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = "llm",
        guid: Optional[str] = None,
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
            language_code: Language code (e.g., 'lt', 'fr', 'de', 'es', 'pt', 'en')
            pos_type: Part of speech to fix (e.g., 'noun', 'verb', 'adjective'). If None, uses language-specific default.
            limit: Maximum number of lemmas to process
            model: LLM model to use for generation (if None, uses self.model from config)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki' (for Lithuanian nouns only)
            guid: Optional GUID to process only a specific lemma

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to instance model
        effective_model = model if model is not None else self.model
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
        from wordfreq.translation import (
            generate_lithuanian_noun_forms,
            generate_lithuanian_verb_forms,
            generate_lithuanian_adjective_forms,
            generate_lithuanian_adverb_forms,
            generate_french_noun_forms,
            generate_french_verb_forms,
            generate_german_noun_forms,
            generate_german_verb_forms,
            generate_spanish_noun_forms,
            generate_spanish_verb_forms,
            generate_portuguese_noun_forms,
            generate_portuguese_verb_forms,
            generate_english_noun_forms,
            generate_english_verb_forms,
            generate_english_adjective_forms,
            generate_english_adverb_forms,
        )

        handler_map = {
            "lt_noun": (generate_lithuanian_noun_forms.process_lemma, "Lithuanian", False),
            "lt_verb": (generate_lithuanian_verb_forms.process_lemma, "Lithuanian", True),
            "lt_adjective": (generate_lithuanian_adjective_forms.process_lemma, "Lithuanian", True),
            "lt_adverb": (generate_lithuanian_adverb_forms.process_lemma, "Lithuanian", True),
            "fr_noun": (generate_french_noun_forms.process_lemma, "French", True),
            "fr_verb": (generate_french_verb_forms.process_lemma, "French", True),
            "de_noun": (generate_german_noun_forms.process_lemma, "German", True),
            "de_verb": (generate_german_verb_forms.process_lemma, "German", True),
            "es_noun": (generate_spanish_noun_forms.process_lemma, "Spanish", True),
            "es_verb": (generate_spanish_verb_forms.process_lemma, "Spanish", True),
            "pt_noun": (generate_portuguese_noun_forms.process_lemma, "Portuguese", True),
            "pt_verb": (generate_portuguese_verb_forms.process_lemma, "Portuguese", True),
            "en_noun": (generate_english_noun_forms.process_lemma, "English", True),
            "en_verb": (generate_english_verb_forms.process_lemma, "English", True),
            "en_adjective": (generate_english_adjective_forms.process_lemma, "English", True),
            "en_adverb": (generate_english_adverb_forms.process_lemma, "English", True),
        }

        if handler_key not in handler_map:
            logger.error(f"No handler found for {language_code} {pos_type}")
            return {
                "error": f"Handler not implemented for {language_code} {pos_type}",
                "supported_combinations": list(handler_map.keys()),
            }

        # Get the process function and metadata
        process_func, language_name, use_generic = handler_map[handler_key]

        # Call the appropriate handler
        if handler_key == "lt_noun":
            return self._fix_lithuanian_noun_declensions(
                limit=limit, model=effective_model, throttle=throttle, dry_run=dry_run, source=source, guid=guid
            )
        elif handler_key == "fr_verb":
            return self._fix_french_verb_conjugations(
                limit=limit, model=effective_model, throttle=throttle, dry_run=dry_run, guid=guid
            )
        elif use_generic:
            return self._fix_generic_forms(
                language_code=language_code,
                language_name=language_name,
                pos_type=pos_type,
                process_func=process_func,
                limit=limit,
                model=effective_model,
                throttle=throttle,
                dry_run=dry_run,
                guid=guid,
            )
        else:
            logger.error(f"Unexpected handler configuration for {handler_key}")
            return {"error": f"Handler configuration error for {handler_key}"}

    def _fix_lithuanian_noun_declensions(
        self,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        source: str = "llm",
        guid: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Generate missing Lithuanian noun declensions.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_lithuanian_noun_forms.

        Args:
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses self.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            source: Source for forms - 'llm' or 'wiki'
            guid: Optional GUID to process only a specific lemma

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to instance model
        effective_model = model if model is not None else self.model
        from wordfreq.translation.generate_lithuanian_noun_forms import (
            process_lemma,
            get_lithuanian_noun_lemmas,
        )

        logger.info("Finding Lithuanian nouns needing declensions...")

        # If GUID is specified, process that specific lemma directly
        if guid:
            session = self.get_session()
            try:
                lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
                if not lemma:
                    logger.info(f"Lemma with GUID {guid} not found")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                if lemma.pos_type != "noun":
                    logger.info(f"Lemma with GUID {guid} is not a noun (it's {lemma.pos_type})")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                nouns_needing_declensions = [{
                    "guid": lemma.guid,
                    "english": lemma.lemma_text,
                    "lithuanian": get_translation(session, lemma, "lt") or "(from LemmaTranslation)",
                    "pos_subtype": lemma.pos_subtype,
                    "difficulty_level": lemma.difficulty_level,
                    "current_form_count": 0,
                }]
                total_needs_fix = 1
            finally:
                session.close()
        else:
            # Get noun declension coverage check results
            check_results = self.check_noun_declension_coverage()

            if "error" in check_results:
                return check_results

            nouns_needing_declensions = check_results["nouns_needing_declensions"]
            total_needs_fix = len(nouns_needing_declensions)

        if total_needs_fix == 0:
            logger.info("No Lithuanian nouns need declensions!")
            return {
                "total_needing_fix": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
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
                logger.info(
                    f"  - {noun['english']} -> {noun['lithuanian']} (level {noun['difficulty_level']})"
                )
            if len(nouns_to_process) > 10:
                logger.info(f"  ... and {len(nouns_to_process) - 10} more")
            return {
                "total_needing_fix": total_needs_fix,
                "would_process": len(nouns_to_process),
                "dry_run": True,
                "sample": nouns_to_process[:10],
            }

        # Initialize client for LLM-based generation
        client = LinguisticClient(model=effective_model, db_path=self.db_path, debug=self.debug)

        # Process each noun
        successful = 0
        failed = 0

        # Get lemma objects for processing
        session = self.get_session()
        try:
            for i, noun_info in enumerate(nouns_to_process, 1):
                logger.info(
                    f"\n[{i}/{len(nouns_to_process)}] Processing: {noun_info['english']} -> {noun_info['lithuanian']}"
                )

                # Get the full lemma object
                lemma = session.query(Lemma).filter(Lemma.guid == noun_info["guid"]).first()

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {noun_info['guid']}")
                    failed += 1
                    continue

                # Use the process_lemma function from generate_lithuanian_noun_forms
                success = process_lemma(
                    client=client, lemma_id=lemma.id, db_path=self.db_path, source=source
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
            "total_needing_fix": total_needs_fix,
            "processed": len(nouns_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
        }

    def _fix_french_verb_conjugations(
        self,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        guid: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Generate missing French verb conjugations.

        This method uses the existing infrastructure from
        wordfreq.translation.generate_french_verb_forms.

        Args:
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses self.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            guid: Optional GUID to process only a specific lemma

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to instance model
        effective_model = model if model is not None else self.model
        from wordfreq.translation.generate_french_verb_forms import (
            process_lemma,
            get_french_verb_lemmas,
        )

        logger.info("Finding French verbs needing conjugations...")

        # If GUID is specified, process that specific lemma directly
        if guid:
            session = self.get_session()
            try:
                lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
                if not lemma:
                    logger.info(f"Lemma with GUID {guid} not found")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                if lemma.pos_type != "verb":
                    logger.info(f"Lemma with GUID {guid} is not a verb (it's {lemma.pos_type})")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                verbs_needing_conjugations = [{
                    "guid": lemma.guid,
                    "english": lemma.lemma_text,
                    "translation": get_translation(session, lemma, "fr") or "(from LemmaTranslation)",
                    "pos_subtype": lemma.pos_subtype,
                    "difficulty_level": lemma.difficulty_level,
                    "current_form_count": 0,
                }]
                total_needs_fix = 1
            finally:
                session.close()
        else:
            # Get verb conjugation coverage check results
            check_results = self.check_verb_conjugation_coverage(language_code="fr")

            if "error" in check_results:
                return check_results

            verbs_needing_conjugations = check_results["verbs_needing_conjugations"]
            total_needs_fix = len(verbs_needing_conjugations)

        if total_needs_fix == 0:
            logger.info("No French verbs need conjugations!")
            return {
                "total_needing_fix": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
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
                logger.info(
                    f"  - {verb['english']} -> {verb['translation']} (level {verb['difficulty_level']})"
                )
            if len(verbs_to_process) > 10:
                logger.info(f"  ... and {len(verbs_to_process) - 10} more")
            return {
                "total_needing_fix": total_needs_fix,
                "would_process": len(verbs_to_process),
                "dry_run": True,
                "sample": verbs_to_process[:10],
            }

        # Initialize client for LLM-based generation
        client = LinguisticClient(model=effective_model, db_path=self.db_path, debug=self.debug)

        # Process each verb
        successful = 0
        failed = 0

        # Get lemma objects for processing
        session = self.get_session()
        try:
            for i, verb_info in enumerate(verbs_to_process, 1):
                logger.info(
                    f"\n[{i}/{len(verbs_to_process)}] Processing: {verb_info['english']} -> {verb_info['translation']}"
                )

                # Get the full lemma object
                lemma = session.query(Lemma).filter(Lemma.guid == verb_info["guid"]).first()

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {verb_info['guid']}")
                    failed += 1
                    continue

                # Use the process_lemma function from generate_french_verb_forms
                success = process_lemma(
                    client=client, lemma_id=lemma.id, db_path=self.db_path
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
            "total_needing_fix": total_needs_fix,
            "processed": len(verbs_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
        }

    def _fix_generic_forms(
        self,
        language_code: str,
        language_name: str,
        pos_type: str,
        process_func,
        limit: Optional[int] = None,
        model: Optional[str] = None,
        throttle: float = 1.0,
        dry_run: bool = False,
        guid: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Generic handler for generating missing word forms across languages.

        Args:
            language_code: Language code (e.g., 'fr', 'de')
            language_name: Human-readable language name
            pos_type: Part of speech type
            process_func: Function to call for processing each lemma
            limit: Maximum number of lemmas to process
            model: LLM model to use (if None, uses self.model)
            throttle: Seconds to wait between API calls
            dry_run: If True, show what would be fixed without making changes
            guid: Optional GUID to process only a specific lemma

        Returns:
            Dictionary with fix results
        """
        # Use provided model or fall back to instance model
        effective_model = model if model is not None else self.model
        logger.info(f"Finding {language_name} {pos_type}s needing forms...")

        # If GUID is specified, process that specific lemma directly
        if guid:
            session = self.get_session()
            try:
                lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
                if not lemma:
                    logger.info(f"Lemma with GUID {guid} not found")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                if lemma.pos_type != pos_type:
                    logger.info(f"Lemma with GUID {guid} is not a {pos_type} (it's {lemma.pos_type})")
                    return {
                        "total_needing_fix": 0,
                        "processed": 0,
                        "successful": 0,
                        "failed": 0,
                        "dry_run": dry_run,
                        "guid_filter": guid,
                    }

                items_needing_forms = [{
                    "guid": lemma.guid,
                    "english": lemma.lemma_text,
                    "translation": f"({language_code})",
                    "pos_subtype": lemma.pos_subtype,
                    "difficulty_level": lemma.difficulty_level,
                    "current_form_count": 0,
                }]
                total_needs_fix = 1
            finally:
                session.close()
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
        client = LinguisticClient(model=effective_model, db_path=self.db_path, debug=self.debug)

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
                lemma = session.query(Lemma).filter(Lemma.guid == item_info["guid"]).first()

                if not lemma:
                    logger.error(f"Could not find lemma with GUID {item_info['guid']}")
                    failed += 1
                    continue

                # Call the process function
                success = process_func(client=client, lemma_id=lemma.id, db_path=self.db_path)

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
