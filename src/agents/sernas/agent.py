"""
Šernas - Synonym and Alternative Form Generator Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/generate-synonyms/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

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

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import constants
import util.prompt_loader
from agents.common.lemma_selection import LemmaQueryBuilder, find_lemma_by_guid
from storage.backend import create_session as create_backend_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.derivative_form import add_derivative_form
from storage.crud.grammar_fact import add_grammar_fact, get_alternate_forms_facts
from storage.crud.word_token import add_word_token
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import get_supported_languages, get_translation
from wordfreq.tools.text_utils import is_numeral
from wordfreq.translation.client import LinguisticClient

# Configure logging
logger = logging.getLogger(__name__)

SYNONYM_FORM_MAP = {
    "synonyms": "synonym",
    "near_synonyms": "synonym_near",
    "regional_variants": "synonym_regional",
    "register_variants": "synonym_register",
    "spelling_variants": "synonym_spelling",
    "synecdoche_variants": "synonym_synecdoche",
    "related_learner_equivalents": "synonym_related",
}


def _normalize_generated_forms(forms: List[str], original_word: str) -> List[str]:
    """Normalize LLM-generated form lists by trimming and deduplicating."""
    normalized: List[str] = []
    seen: set[str] = set()
    original_normalized = original_word.strip().casefold()

    for raw_form in forms:
        clean_form = (raw_form or "").strip()
        if not clean_form or is_numeral(clean_form):
            continue
        if clean_form.casefold() == original_normalized:
            continue
        dedup_key = clean_form.casefold()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        normalized.append(clean_form)

    return normalized


class SernasAgent:
    """Agent for generating synonyms and alternative forms across multiple languages."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Šernas agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
        """
        self.config = config
        self.debug = config.debug

        # Lazy initialization for LinguisticClient
        self._linguistic_client: Optional[LinguisticClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_linguistic_client(self) -> LinguisticClient:
        """Get or create the linguistic client (lazy initialization).

        Returns:
            LinguisticClient instance
        """
        if self._linguistic_client is None:
            self._linguistic_client = LinguisticClient(config=self.config)
        return self._linguistic_client

    def check_missing_synonyms(
        self,
        lemmas: Optional[List[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check for lemmas missing synonyms or alternative forms.

        Args:
            lemmas: List of Lemma objects to check. If None, checks all curated lemmas.
            language_code: Language to check (e.g., 'en', 'lt'). If None, check all.
            form_type: Type to check (e.g., 'synonym', 'abbreviation', 'expanded_form', 'alternate_spelling').
                      If None, checks all types.

        Returns:
            Dictionary with check results
        """
        logger.info(f"Checking for lemmas missing synonyms/alternative forms...")

        session = self.get_session()
        try:
            # Get lemmas to check
            if lemmas is None:
                query = LemmaQueryBuilder(session).curated_only().order_by_id().build()
                lemmas = query.all()
            logger.info(f"Checking {len(lemmas)} lemmas")

            # Determine which language codes to check
            if language_code:
                lang_codes = [language_code]
            else:
                lang_codes = ["en"] + list(get_supported_languages().keys())

            # Determine which form types to check
            if form_type:
                form_types = [form_type]
            else:
                # Check all types (including legacy 'alternative_form')
                form_types = [
                    "synonym",
                    "abbreviation",
                    "expanded_form",
                    "alternate_spelling",
                    "alternative_form",
                ]

            missing_by_language: Dict[str, List[Dict[str, Any]]] = {}
            for lang in lang_codes:
                missing_by_language[lang] = []

            for lemma in lemmas:
                for lang in lang_codes:
                    # Get the translation for this language
                    if lang == "en":
                        translation: Optional[str] = lemma.lemma_text
                    else:
                        translation = get_translation(session, lemma, lang)

                    # Skip if no translation exists
                    if not translation or not translation.strip():
                        continue

                    # Check if alternate forms facts have been recorded for this lemma/language
                    facts = get_alternate_forms_facts(session, lemma.id, lang)

                    # If no facts recorded, we need to run ŠERNAS
                    if facts is None:
                        missing_by_language[lang].append(
                            {
                                "guid": lemma.guid,
                                "english": lemma.lemma_text,
                                "translation": translation,
                                "pos_type": lemma.pos_type,
                                "pos_subtype": lemma.pos_subtype,
                                "difficulty_level": lemma.difficulty_level,
                            }
                        )
                    # If form_type is specified, check if that specific fact is missing
                    elif form_type:
                        fact_key = (
                            f"has_{form_type}s"
                            if not form_type.endswith("s")
                            else f"has_{form_type}"
                        )
                        if fact_key not in facts:
                            missing_by_language[lang].append(
                                {
                                    "guid": lemma.guid,
                                    "english": lemma.lemma_text,
                                    "translation": translation,
                                    "pos_type": lemma.pos_type,
                                    "pos_subtype": lemma.pos_subtype,
                                    "difficulty_level": lemma.difficulty_level,
                                }
                            )

            # Calculate statistics
            total_missing = sum(len(items) for items in missing_by_language.values())

            logger.info(
                f"Found {total_missing} lemmas missing synonyms/alternatives across all languages"
            )

            return {
                "total_missing": total_missing,
                "missing_by_language": missing_by_language,
                "checked_languages": lang_codes,
                "checked_form_types": form_types,
            }

        except Exception as e:
            logger.error(f"Error checking missing synonyms: {e}")
            return {"error": str(e), "total_missing": 0, "missing_by_language": {}}
        finally:
            session.close()

    def generate_synonyms_for_lemma(
        self, lemma_id: int, language_code: str, model: str = "gpt-5-mini", dry_run: bool = False
    ) -> Dict[str, Any]:
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
                return {"error": f"Lemma ID {lemma_id} not found"}

            # Get the translation for the target language
            if language_code == "en":
                word = lemma.lemma_text
            else:
                word = get_translation(session, lemma, language_code)

            if not word or not word.strip():
                return {
                    "error": f"No translation found for language {language_code}",
                    "lemma_id": lemma_id,
                    "language_code": language_code,
                }

            logger.info(f"Generating synonyms for '{word}' ({language_code})")

            # Get LinguisticClient
            client = self.get_linguistic_client()

            # Generate synonyms using LLM
            result = self._query_synonyms(
                client=client,
                word=word,
                language_code=language_code,
                pos_type=lemma.pos_type,
                definition=lemma.definition_text,
                english_word=lemma.lemma_text,
            )

            if not result["success"]:
                return {
                    "error": result.get("error", "Failed to generate synonyms"),
                    "lemma_id": lemma_id,
                    "language_code": language_code,
                }

            synonym_groups: Dict[str, List[str]] = {}
            for group_name in SYNONYM_FORM_MAP:
                synonym_groups[group_name] = _normalize_generated_forms(
                    result.get(group_name, []), word
                )

            synonyms = []
            synonym_seen: set[str] = set()
            for group_name in SYNONYM_FORM_MAP:
                for synonym in synonym_groups[group_name]:
                    dedup_key = synonym.casefold()
                    if dedup_key not in synonym_seen:
                        synonym_seen.add(dedup_key)
                        synonyms.append(synonym)

            abbreviations = _normalize_generated_forms(result.get("abbreviations", []), word)
            expanded_forms = _normalize_generated_forms(result.get("expanded_forms", []), word)
            if result.get("alternate_spellings"):
                synonym_groups["spelling_variants"].extend(
                    _normalize_generated_forms(result.get("alternate_spellings", []), word)
                )
                synonym_groups["spelling_variants"] = _normalize_generated_forms(
                    synonym_groups["spelling_variants"], word
                )

            if dry_run:
                return {
                    "dry_run": True,
                    "lemma_id": lemma_id,
                    "language_code": language_code,
                    "word": word,
                    "synonyms": synonyms,
                    "abbreviations": abbreviations,
                    "expanded_forms": expanded_forms,
                    "spelling_variants": synonym_groups.get("spelling_variants", []),
                    "synecdoche_variants": synonym_groups.get("synecdoche_variants", []),
                    "total_count": len(synonyms) + len(abbreviations) + len(expanded_forms),
                }

            # Store the forms in the database
            stored_synonyms = 0
            stored_abbreviations = 0
            stored_expanded = 0
            stored_spellings = 0

            for group_name, group_synonyms in synonym_groups.items():
                grammatical_form = SYNONYM_FORM_MAP[group_name]
                for synonym in group_synonyms:
                    try:
                        word_token = add_word_token(session, synonym, language_code)
                        add_derivative_form(
                            session=session,
                            lemma=lemma,
                            derivative_form_text=synonym,
                            language_code=language_code,
                            grammatical_form=grammatical_form,
                            word_token=word_token,
                            verified=False,
                        )
                        stored_synonyms += 1
                        if group_name == "spelling_variants":
                            stored_spellings += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to store synonym '{synonym}' ({grammatical_form}): {e}"
                        )

            for abbr in abbreviations:
                try:
                    word_token = add_word_token(session, abbr, language_code)
                    add_derivative_form(
                        session=session,
                        lemma=lemma,
                        derivative_form_text=abbr,
                        language_code=language_code,
                        grammatical_form="abbreviation",
                        word_token=word_token,
                        verified=False,
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
                        grammatical_form="expanded_form",
                        word_token=word_token,
                        verified=False,
                    )
                    stored_expanded += 1
                except Exception as e:
                    logger.warning(f"Failed to store expanded form '{exp_form}': {e}")

            # Record grammar facts to track what ŠERNAS found (or didn't find)
            add_grammar_fact(
                session,
                lemma.id,
                language_code,
                "has_synonyms",
                "true" if stored_synonyms > 0 else "false",
                verified=True,
            )
            add_grammar_fact(
                session,
                lemma.id,
                language_code,
                "has_abbreviations",
                "true" if stored_abbreviations > 0 else "false",
                verified=True,
            )
            add_grammar_fact(
                session,
                lemma.id,
                language_code,
                "has_expanded_forms",
                "true" if stored_expanded > 0 else "false",
                verified=True,
            )
            add_grammar_fact(
                session,
                lemma.id,
                language_code,
                "has_alternate_spellings",
                "false",
                verified=True,
            )

            session.commit()

            logger.info(
                f"Stored {stored_synonyms} synonym variants, {stored_abbreviations} abbreviations, and {stored_expanded} expanded forms"
            )

            return {
                "success": True,
                "lemma_id": lemma_id,
                "language_code": language_code,
                "word": word,
                "synonyms": synonyms,
                "abbreviations": abbreviations,
                "expanded_forms": expanded_forms,
                "spelling_variants": synonym_groups.get("spelling_variants", []),
                "synecdoche_variants": synonym_groups.get("synecdoche_variants", []),
                "stored_synonyms": stored_synonyms,
                "stored_abbreviations": stored_abbreviations,
                "stored_expanded": stored_expanded,
                "stored_spellings": stored_spellings,
            }

        except Exception as e:
            session.rollback()
            logger.exception(f"Error generating synonyms for lemma {lemma_id}: {e}")
            return {"error": str(e), "lemma_id": lemma_id, "language_code": language_code}
        finally:
            session.close()

    def _query_synonyms(
        self,
        client: LinguisticClient,
        word: str,
        language_code: str,
        pos_type: str,
        definition: str,
        english_word: str,
    ) -> Dict[str, Any]:
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
        if language_code == "en":
            language_name = "English"
        else:
            language_name = language_names.get(language_code, language_code)

        # Load prompt templates from files
        context = util.prompt_loader.get_context("synonyms", "word")
        prompt_template = util.prompt_loader.get_prompt("synonyms", "word")

        # Add language-specific notes (Chinese is already covered in context.txt)
        language_note = ""
        if language_code == "ko":
            language_note = "- For Korean, provide words in Hangul (e.g., 거리, 길 for 'street')"

        # Build prompt with variables
        prompt_body = prompt_template.replace("{{language_name}}", language_name)
        prompt_body = prompt_body.replace("{{word}}", word)
        prompt_body = prompt_body.replace("{{pos_type}}", pos_type)
        prompt_body = prompt_body.replace("{{english_word}}", english_word)
        prompt_body = prompt_body.replace("{{definition}}", definition or "")
        prompt_body = prompt_body.replace("{{language_note}}", language_note)

        # Combine context and prompt
        prompt = f"{context}\n\n{prompt_body}"

        try:
            # Query the LLM using generate_chat with JSON schema
            json_schema = {
                "type": "object",
                "properties": {
                    "abbreviations": {"type": "array", "items": {"type": "string"}},
                    "expanded_forms": {"type": "array", "items": {"type": "string"}},
                    "synonyms": {"type": "array", "items": {"type": "string"}},
                    "near_synonyms": {"type": "array", "items": {"type": "string"}},
                    "regional_variants": {"type": "array", "items": {"type": "string"}},
                    "register_variants": {"type": "array", "items": {"type": "string"}},
                    "spelling_variants": {"type": "array", "items": {"type": "string"}},
                    "synecdoche_variants": {"type": "array", "items": {"type": "string"}},
                    "related_learner_equivalents": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "explanation": {"type": "string"},
                },
                "required": [
                    "abbreviations",
                    "expanded_forms",
                    "synonyms",
                    "near_synonyms",
                    "regional_variants",
                    "register_variants",
                    "spelling_variants",
                    "synecdoche_variants",
                    "related_learner_equivalents",
                ],
            }

            response = client.client.generate_chat(
                prompt=prompt, model=client.model, json_schema=json_schema
            )

            if not response.structured_data:
                return {"success": False, "error": "Empty response from LLM"}

            # Use structured data from response
            result = response.structured_data

            return {
                "success": True,
                "synonyms": result.get("synonyms", []),
                "near_synonyms": result.get("near_synonyms", []),
                "regional_variants": result.get("regional_variants", []),
                "register_variants": result.get("register_variants", []),
                "spelling_variants": result.get(
                    "spelling_variants", result.get("alternate_spellings", [])
                ),
                "synecdoche_variants": result.get("synecdoche_variants", []),
                "related_learner_equivalents": result.get("related_learner_equivalents", []),
                "abbreviations": result.get("abbreviations", []),
                "expanded_forms": result.get("expanded_forms", []),
                "explanation": result.get("explanation", ""),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response}")
            return {"success": False, "error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            return {"success": False, "error": str(e)}

    def fix_missing_synonyms(
        self,
        lemmas: Optional[List[Lemma]] = None,
        language_code: Optional[str] = None,
        form_type: Optional[str] = None,
        limit: Optional[int] = None,
        model: str = "gpt-5-mini",
        throttle: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate missing synonyms and alternative forms for lemmas.

        Args:
            lemmas: List of Lemma objects to process. If None, processes all curated lemmas.
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
            language_code = "en"
            logger.info("No language specified, defaulting to English")

        # Check what's missing
        check_results = self.check_missing_synonyms(
            lemmas=lemmas, language_code=language_code, form_type=form_type
        )

        if "error" in check_results:
            return check_results

        lemmas_missing = check_results["missing_by_language"].get(language_code, [])
        total_needs_fix = len(lemmas_missing)

        if total_needs_fix == 0:
            logger.info(f"No lemmas need synonyms/alternatives for {language_code}!")
            return {
                "total_needing_fix": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "dry_run": dry_run,
            }

        logger.info(
            f"Found {total_needs_fix} lemmas needing synonyms/alternatives for {language_code}"
        )

        # Apply limit if specified
        if limit:
            lemmas_to_process = lemmas_missing[:limit]
            logger.info(f"Processing limited to {limit} lemmas")
        else:
            lemmas_to_process = lemmas_missing

        if dry_run:
            logger.info(f"DRY RUN: Would process {len(lemmas_to_process)} lemmas:")
            for lemma_info in lemmas_to_process[:10]:  # Show first 10
                logger.info(
                    f"  - {lemma_info['english']} -> {lemma_info['translation']} (level {lemma_info['difficulty_level']})"
                )
            if len(lemmas_to_process) > 10:
                logger.info(f"  ... and {len(lemmas_to_process) - 10} more")
            return {
                "total_needing_fix": total_needs_fix,
                "would_process": len(lemmas_to_process),
                "dry_run": True,
                "sample": lemmas_to_process[:10],
            }

        # Process each lemma
        successful = 0
        failed = 0
        session = self.get_session()

        try:
            for i, lemma_info in enumerate(lemmas_to_process, 1):
                logger.info(
                    f"\n[{i}/{len(lemmas_to_process)}] Processing: {lemma_info['english']} -> {lemma_info['translation']}"
                )

                # Get lemma object
                lemma = find_lemma_by_guid(session, lemma_info["guid"], error_on_missing=False)
                if not lemma:
                    logger.error(f"Could not find lemma with GUID {lemma_info['guid']}")
                    failed += 1
                    continue

                # Generate synonyms
                result = self.generate_synonyms_for_lemma(
                    lemma_id=lemma.id, language_code=language_code, model=model, dry_run=False
                )

                if result.get("success"):
                    successful += 1
                    logger.info(
                        f"Successfully generated {result.get('stored_synonyms', 0)} synonyms and {result.get('stored_alternatives', 0)} alternatives"
                    )
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
            "total_needing_fix": total_needs_fix,
            "processed": len(lemmas_to_process),
            "successful": successful,
            "failed": failed,
            "dry_run": dry_run,
            "language_code": language_code,
        }
